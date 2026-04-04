"""Terraform resource block scanner for Phase 2.

Extracts security-relevant resource blocks and backend configuration from .tf files.
Uses the same brace-depth state machine as terraform_extractor.py — no external HCL parser.

Produces terraform_scan.json payload:
  resources                  — list of resource records for security detectors
  backend                    — backend config or None (local state)
  resource_type_counts_by_file — all resource types per file (for god_module)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Resource types to capture full block_text for (security analysis)
_SCAN_TYPES: frozenset[str] = frozenset({
    "aws_security_group",
    "aws_iam_policy",
    "aws_iam_role",
    "aws_iam_role_policy",
    "aws_s3_bucket",
    "aws_s3_bucket_public_access_block",
    "aws_db_instance",
    "aws_rds_cluster",
    "aws_instance",
    "aws_eks_cluster",
})

_RESOURCE_HEADER = re.compile(r'^\s*resource\s+"([^"]+)"\s+"([^"]+)"\s*\{')
_TERRAFORM_HEADER = re.compile(r'^\s*terraform\s*\{')
_BACKEND_HEADER = re.compile(r'^\s*backend\s+"([^"]+)"\s*\{')
_DYNAMODB_TABLE = re.compile(r'dynamodb_table\s*=\s*"([^"${}]+)"')


class TerraformResourceScanner:
    """Scan .tf files and extract security-relevant resource blocks."""

    def scan(self, file_paths: list[str]) -> dict[str, Any]:
        """Scan a list of absolute .tf file paths. Non-fatal — skips unreadable files."""
        partial: list[dict[str, Any]] = []
        for fp in file_paths:
            try:
                text = Path(fp).read_text(encoding="utf-8", errors="ignore")
                partial.append(self._scan_text(text, fp))
            except OSError:
                continue
        return self._merge(partial)

    def _scan_text(self, text: str, file_path: str) -> dict[str, Any]:
        """Parse text from a single .tf file. Returns partial scan result."""
        lines = text.splitlines()
        resources: list[dict[str, Any]] = []
        resource_type_counts: dict[str, int] = {}
        backend: dict[str, Any] | None = None

        depth = 0
        mode: str | None = None  # "resource" | "terraform"
        resource_type: str | None = None
        resource_name: str | None = None
        block_start: int = 0
        block_lines: list[str] = []
        capture: bool = False  # True when resource_type in _SCAN_TYPES

        # Terraform block sub-state
        in_terraform = False
        terraform_depth = 0
        backend_type: str | None = None
        has_lock = False
        backend_start: int = 0

        for line_idx, line in enumerate(lines, 1):
            opens = line.count("{")
            closes = line.count("}")

            if depth == 0 and not in_terraform:
                m = _RESOURCE_HEADER.match(line)
                if m:
                    rtype, rname = m.group(1), m.group(2)
                    resource_type_counts[rtype] = resource_type_counts.get(rtype, 0) + 1
                    if rtype in _SCAN_TYPES:
                        mode = "resource"
                        resource_type = rtype
                        resource_name = rname
                        block_start = line_idx
                        block_lines = []
                        capture = True
                    depth = opens - closes
                    continue

                if _TERRAFORM_HEADER.match(line):
                    in_terraform = True
                    terraform_depth = opens - closes
                    backend_start = line_idx
                    continue

                depth += opens - closes
                if depth < 0:
                    depth = 0
                continue

            if in_terraform:
                terraform_depth += opens - closes
                mb = _BACKEND_HEADER.match(line)
                if mb and backend_type is None:
                    backend_type = mb.group(1)
                    backend_start = line_idx
                if _DYNAMODB_TABLE.search(line):
                    has_lock = True
                if terraform_depth <= 0:
                    terraform_depth = 0
                    in_terraform = False
                    if backend_type:
                        backend = {
                            "type": backend_type,
                            "has_lock": has_lock,
                            "file": file_path,
                            "line": backend_start,
                        }
                continue

            # Inside a resource block
            depth += opens - closes
            if capture:
                block_lines.append(line)

            if depth <= 0:
                depth = 0
                if capture and resource_type and resource_name:
                    resources.append({
                        "resource_type": resource_type,
                        "resource_name": resource_name,
                        "file": file_path,
                        "line": block_start,
                        "block_text": "\n".join(block_lines),
                    })
                mode = None
                resource_type = None
                resource_name = None
                block_lines = []
                capture = False

        return {
            "resources": resources,
            "backend": backend,
            "resource_type_counts_by_file": (
                {file_path: resource_type_counts} if resource_type_counts else {}
            ),
        }

    def _merge(self, partials: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge results from multiple file scans."""
        resources: list[dict[str, Any]] = []
        backend: dict[str, Any] | None = None
        counts: dict[str, dict[str, int]] = {}

        for p in partials:
            resources.extend(p.get("resources") or [])
            if backend is None and p.get("backend"):
                backend = p["backend"]
            for fp, type_counts in (p.get("resource_type_counts_by_file") or {}).items():
                counts[fp] = type_counts

        return {
            "resources": resources,
            "backend": backend,
            "resource_type_counts_by_file": counts,
        }
