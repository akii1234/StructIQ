"""Infrastructure anti-pattern detection for Terraform + Lambda stacks.

Reads the Phase 2 dependency graph (which now includes tf_lambda_handler edges)
and the Phase 2 analysis (coupling scores). Pure computation — no I/O except
reading handler file content for direct-invocation detection.

Lambda detectors:
  god_lambda              — Lambda handler with Ce (efferent coupling) > GOD_LAMBDA_CE_THRESHOLD
  direct_lambda_invocation — Handler calls boto3.client('lambda') synchronously
  shared_iam_role         — Multiple Lambdas sharing one IAM role ARN

IaC detectors (when terraform_scan.json is present):
  open_security_group, wildcard_iam, public_s3_bucket, unencrypted_storage,
  no_remote_state, god_module
"""

from __future__ import annotations

import re as _re
from collections import defaultdict
from pathlib import Path
from typing import Any

GOD_LAMBDA_CE_THRESHOLD = 10  # efferent_coupling > this → god_lambda

_BOTO3_LAMBDA_PAT = _re.compile(r"""boto3\.client\s*\(\s*['"]lambda['"]\s*\)""")

_OPEN_CIDR_PAT = _re.compile(r'cidr_blocks\s*=\s*\[[^\]]*"0\.0\.0\.0/0"')
# HCL jsonencode policy strings often escape quotes as \"
_WILDCARD_ACTION_PAT = _re.compile(
    r'(?:["\']?Action["\']?\s*[=:]\s*["\[]?\s*"?\*"?)|\\"Action\\"\s*:\s*\\"\*\\"'
)
_PUBLIC_ACL_PAT = _re.compile(r'acl\s*=\s*"public-')
_STORAGE_ENC_FALSE_PAT = _re.compile(r'storage_encrypted\s*=\s*false')
_SERVER_SIDE_ENC_PAT = _re.compile(r'server_side_encryption_configuration')
GOD_MODULE_TYPE_THRESHOLD = 6


class TerraformAnalyzer:
    """Detect infrastructure anti-patterns from the augmented dependency graph."""

    def _lambda_handler_edges(self, graph: dict) -> list[dict]:
        """Return all edges with edge_type == 'tf_lambda_handler'."""
        return [
            e for e in (graph.get("edges") or [])
            if isinstance(e, dict) and e.get("edge_type") == "tf_lambda_handler"
        ]

    def detect_god_lambdas(self, graph: dict, analysis: dict) -> list[dict]:
        """Flag Lambda handler files with efferent_coupling > GOD_LAMBDA_CE_THRESHOLD."""
        lambda_edges = self._lambda_handler_edges(graph)
        if not lambda_edges:
            return []

        handler_files: set[str] = {str(e["target"]) for e in lambda_edges}

        ce_by_file: dict[str, int] = {}
        for rec in (analysis.get("coupling_scores") or []):
            if not isinstance(rec, dict):
                continue
            fp = rec.get("file")
            if isinstance(fp, str) and fp in handler_files:
                try:
                    ce_by_file[fp] = int(rec.get("efferent_coupling", 0) or 0)
                except (TypeError, ValueError):
                    pass

        anti_patterns: list[dict] = []
        for handler_fp in sorted(handler_files):
            ce = ce_by_file.get(handler_fp, 0)
            if ce > GOD_LAMBDA_CE_THRESHOLD:
                anti_patterns.append({
                    "type": "god_lambda",
                    "handler_file": handler_fp,
                    "efferent_coupling": ce,
                    "severity": "high",
                    "description": (
                        f"Lambda handler imports {ce} modules — "
                        "consider splitting into smaller focused functions."
                    ),
                })
        return anti_patterns

    def detect_direct_lambda_invocations(self, graph: dict) -> list[dict]:
        """Flag Lambda handlers that synchronously invoke other Lambdas via boto3."""
        lambda_edges = self._lambda_handler_edges(graph)
        anti_patterns: list[dict] = []
        seen: set[str] = set()

        for edge in lambda_edges:
            handler_fp = str(edge.get("target", ""))
            if not handler_fp:
                continue
            if handler_fp in seen:
                continue
            seen.add(handler_fp)
            try:
                content = Path(handler_fp).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if _BOTO3_LAMBDA_PAT.search(content):
                anti_patterns.append({
                    "type": "direct_lambda_invocation",
                    "handler_file": handler_fp,
                    "tf_file": str(edge.get("source", "")),
                    "severity": "medium",
                    "description": (
                        "Lambda directly invokes another Lambda via boto3. "
                        "Consider SQS/SNS for decoupling."
                    ),
                })
        return anti_patterns

    def detect_shared_iam_roles(self, graph: dict) -> list[dict]:
        """Flag IAM roles shared across multiple Lambda functions."""
        lambda_edges = self._lambda_handler_edges(graph)

        handlers_by_role: dict[str, list[str]] = defaultdict(list)
        for edge in lambda_edges:
            role_arn = edge.get("role_arn")
            if not isinstance(role_arn, str) or not role_arn.strip():
                continue
            if "${" in role_arn or role_arn.startswith("var."):
                continue
            handlers_by_role[role_arn.strip()].append(str(edge["target"]))

        anti_patterns: list[dict] = []
        for role_arn, handler_files in sorted(handlers_by_role.items()):
            if len(handler_files) > 1:
                anti_patterns.append({
                    "type": "shared_iam_role",
                    "role_arn": role_arn,
                    "lambda_files": sorted(set(handler_files)),
                    "severity": "medium",
                    "description": (
                        f"IAM role shared across {len(handler_files)} Lambda functions. "
                        "Each function should have a least-privilege dedicated role."
                    ),
                })
        return anti_patterns

    def detect_open_security_groups(self, tf_scan: dict) -> list[dict]:
        """Flag security groups with 0.0.0.0/0 ingress."""
        results = []
        for r in (tf_scan.get("resources") or []):
            if r.get("resource_type") != "aws_security_group":
                continue
            block_text = r.get("block_text", "")
            if _OPEN_CIDR_PAT.search(block_text):
                name = r.get("resource_name", "unknown")
                results.append({
                    "type": "open_security_group",
                    "resource_name": name,
                    "file": r.get("file", ""),
                    "line": r.get("line"),
                    "direction": "ingress",
                    "severity": "high",
                    "description": (
                        f"Security group '{name}' allows inbound traffic from 0.0.0.0/0 "
                        "— open to the entire internet."
                    ),
                })
        return results

    def detect_wildcard_iam(self, tf_scan: dict) -> list[dict]:
        """Flag IAM resources granting wildcard Action '*'."""
        _IAM_TYPES = {"aws_iam_policy", "aws_iam_role", "aws_iam_role_policy"}
        results = []
        for r in (tf_scan.get("resources") or []):
            if r.get("resource_type") not in _IAM_TYPES:
                continue
            block_text = r.get("block_text", "")
            if _WILDCARD_ACTION_PAT.search(block_text):
                name = r.get("resource_name", "unknown")
                rtype = r.get("resource_type", "")
                results.append({
                    "type": "wildcard_iam",
                    "resource_type": rtype,
                    "resource_name": name,
                    "file": r.get("file", ""),
                    "line": r.get("line"),
                    "severity": "high",
                    "description": (
                        f"IAM resource '{name}' grants wildcard Action '*' "
                        "— violates least-privilege principle."
                    ),
                })
        return results

    def detect_public_s3_buckets(self, tf_scan: dict) -> list[dict]:
        """Flag S3 buckets with public ACL or missing public access block."""
        resources = tf_scan.get("resources") or []
        buckets = [r for r in resources if r.get("resource_type") == "aws_s3_bucket"]
        access_blocks = {
            r.get("resource_name")
            for r in resources
            if r.get("resource_type") == "aws_s3_bucket_public_access_block"
        }
        results = []
        for r in buckets:
            name = r.get("resource_name", "unknown")
            block_text = r.get("block_text", "")
            if _PUBLIC_ACL_PAT.search(block_text):
                results.append({
                    "type": "public_s3_bucket",
                    "resource_name": name,
                    "file": r.get("file", ""),
                    "line": r.get("line"),
                    "reason": "public_acl",
                    "severity": "high",
                    "description": (
                        f"S3 bucket '{name}' has a public ACL "
                        "— bucket contents accessible to anyone on the internet."
                    ),
                })
            elif name not in access_blocks:
                results.append({
                    "type": "public_s3_bucket",
                    "resource_name": name,
                    "file": r.get("file", ""),
                    "line": r.get("line"),
                    "reason": "missing_access_block",
                    "severity": "high",
                    "description": (
                        f"S3 bucket '{name}' has no aws_s3_bucket_public_access_block "
                        "— public access may be possible."
                    ),
                })
        return results

    def detect_unencrypted_storage(self, tf_scan: dict) -> list[dict]:
        """Flag RDS/S3/cluster resources with encryption disabled or absent."""
        _ENC_TYPES = {"aws_db_instance", "aws_rds_cluster"}
        results = []
        for r in (tf_scan.get("resources") or []):
            rtype = r.get("resource_type", "")
            block_text = r.get("block_text", "")
            name = r.get("resource_name", "unknown")
            if rtype in _ENC_TYPES and _STORAGE_ENC_FALSE_PAT.search(block_text):
                results.append({
                    "type": "unencrypted_storage",
                    "resource_type": rtype,
                    "resource_name": name,
                    "file": r.get("file", ""),
                    "line": r.get("line"),
                    "severity": "medium",
                    "description": (
                        f"RDS resource '{name}' has storage_encrypted = false "
                        "— data at rest is unencrypted."
                    ),
                })
            elif rtype == "aws_s3_bucket" and not _SERVER_SIDE_ENC_PAT.search(block_text):
                results.append({
                    "type": "unencrypted_storage",
                    "resource_type": rtype,
                    "resource_name": name,
                    "file": r.get("file", ""),
                    "line": r.get("line"),
                    "severity": "medium",
                    "description": (
                        f"S3 bucket '{name}' has no server-side encryption configuration "
                        "— data at rest may be unencrypted."
                    ),
                })
        return results

    def detect_no_remote_state(self, tf_scan: dict) -> list[dict]:
        """Flag when no remote backend is configured (local state)."""
        if not tf_scan:
            return []
        backend = tf_scan.get("backend")
        if backend is None or str(backend.get("type", "")).lower() == "local":
            return [{
                "type": "no_remote_state",
                "file": (backend or {}).get("file"),
                "severity": "medium",
                "description": (
                    "No Terraform remote backend configured — state is stored locally, "
                    "preventing safe team collaboration and state locking."
                ),
            }]
        return []

    def detect_god_modules(self, tf_scan: dict) -> list[dict]:
        """Flag .tf files that define too many distinct resource types."""
        results = []
        for file_path, type_counts in (tf_scan.get("resource_type_counts_by_file") or {}).items():
            count = len(type_counts)
            if count >= GOD_MODULE_TYPE_THRESHOLD:
                results.append({
                    "type": "god_module",
                    "file": file_path,
                    "resource_type_count": count,
                    "resource_types": sorted(type_counts.keys()),
                    "severity": "medium",
                    "description": (
                        f"File '{Path(file_path).name}' defines {count} distinct resource types "
                        f"— high blast radius on any change."
                    ),
                })
        return results

    def analyze(
        self, graph: dict, analysis: dict, tf_scan: dict | None = None
    ) -> dict:
        """Run all detectors and return merged anti_patterns list."""
        anti_patterns: list[dict[str, Any]] = []
        try:
            anti_patterns.extend(self.detect_god_lambdas(graph, analysis))
        except Exception:
            pass
        try:
            anti_patterns.extend(self.detect_direct_lambda_invocations(graph))
        except Exception:
            pass
        try:
            anti_patterns.extend(self.detect_shared_iam_roles(graph))
        except Exception:
            pass
        if tf_scan:
            for method in [
                self.detect_open_security_groups,
                self.detect_wildcard_iam,
                self.detect_public_s3_buckets,
                self.detect_unencrypted_storage,
                self.detect_no_remote_state,
                self.detect_god_modules,
            ]:
                try:
                    anti_patterns.extend(method(tf_scan))
                except Exception:
                    pass
        return {"anti_patterns": anti_patterns}
