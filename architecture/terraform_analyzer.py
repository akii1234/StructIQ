"""Infrastructure anti-pattern detection for Terraform + Lambda stacks.

Reads the Phase 2 dependency graph (which now includes tf_lambda_handler edges)
and the Phase 2 analysis (coupling scores). Pure computation — no I/O except
reading handler file content for direct-invocation detection.

Three detectors:
  god_lambda              — Lambda handler with Ce (efferent coupling) > GOD_LAMBDA_CE_THRESHOLD
  direct_lambda_invocation — Handler calls boto3.client('lambda') synchronously
  shared_iam_role         — Multiple Lambdas sharing one IAM role ARN
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

GOD_LAMBDA_CE_THRESHOLD = 10  # efferent_coupling > this → god_lambda

_BOTO3_LAMBDA_PAT = re.compile(r"""boto3\.client\s*\(\s*['"]lambda['"]\s*\)""")


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

    def analyze(self, graph: dict, analysis: dict) -> dict:
        """Run all three detectors and return merged anti_patterns list."""
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
        return {"anti_patterns": anti_patterns}
