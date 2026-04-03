"""Terraform (.tf) HCL extractor for Phase 2 dependency analysis.

Uses line-by-line regex — no external HCL parser required.
Extracts two kinds of records:
  tf_module          — module "name" { source = "./path" }
  tf_lambda_handler  — resource "aws_lambda_function" "name" { filename = "..." }

All other resource types are ignored. Variable interpolations (${var.x}) in
source/filename values are skipped — only string literals are extracted.
"""

from __future__ import annotations

import re
from typing import Any


# Patterns for block headers
_MODULE_HEADER = re.compile(r'^\s*module\s+"([^"]+)"\s*\{')
_RESOURCE_HEADER = re.compile(r'^\s*resource\s+"([^"]+)"\s+"([^"]+)"\s*\{')

# Patterns for attribute values — only match plain string literals
_SOURCE_ATTR = re.compile(r'^\s*source\s*=\s*"([^"${}]+)"')
_FILENAME_ATTR = re.compile(r'^\s*filename\s*=\s*"([^"${}]+)"')
_ROLE_ATTR = re.compile(r'^\s*role\s*=\s*([^\n]+)')


def extract_terraform_records(file_path: str, lines: list[str]) -> list[dict[str, Any]]:
    """Parse .tf file lines and return import-compatible records."""
    out: list[dict[str, Any]] = []

    # State machine
    depth = 0                  # brace nesting depth
    block_type: str | None = None   # "module" or "resource"
    block_name: str | None = None   # resource/module logical name
    resource_type: str | None = None  # e.g. "aws_lambda_function"
    block_start_line: int = 0

    # Accumulate attributes while inside a block
    source_val: str | None = None
    filename_val: str | None = None
    role_val: str | None = None

    def _flush():
        nonlocal block_type, block_name, resource_type, source_val, filename_val, role_val
        if block_type == "module" and source_val:
            out.append({
                "source_file": file_path,
                "raw_import": f'module "{block_name}" {{ source = "{source_val}" }}',
                "import_target": source_val,
                "import_kind": "tf_module",
                "language": "terraform",
                "line_number": block_start_line,
                "role_arn": None,
            })
        elif block_type == "resource" and resource_type == "aws_lambda_function" and filename_val:
            out.append({
                "source_file": file_path,
                "raw_import": f'resource "aws_lambda_function" "{block_name}" {{ filename = "{filename_val}" }}',
                "import_target": filename_val,
                "import_kind": "tf_lambda_handler",
                "language": "terraform",
                "line_number": block_start_line,
                "role_arn": role_val.strip() if role_val else None,
            })
        block_type = None
        block_name = None
        resource_type = None
        source_val = None
        filename_val = None
        role_val = None

    for line_idx, line in enumerate(lines, 1):
        # Count braces to track nesting
        opens = line.count("{")
        closes = line.count("}")

        if depth == 0:
            # Look for block headers
            m = _MODULE_HEADER.match(line)
            if m:
                block_type = "module"
                block_name = m.group(1)
                block_start_line = line_idx
                depth += opens - closes
                continue

            m = _RESOURCE_HEADER.match(line)
            if m:
                block_type = "resource"
                resource_type = m.group(1)
                block_name = m.group(2)
                block_start_line = line_idx
                depth += opens - closes
                continue

            depth += opens - closes
            if depth < 0:
                depth = 0
            continue

        # Inside a block — extract attributes
        depth += opens - closes

        if block_type == "module" and source_val is None:
            m = _SOURCE_ATTR.match(line)
            if m:
                source_val = m.group(1)

        elif block_type == "resource" and resource_type == "aws_lambda_function":
            if filename_val is None:
                m = _FILENAME_ATTR.match(line)
                if m:
                    filename_val = m.group(1)
            if role_val is None:
                m = _ROLE_ATTR.match(line)
                if m:
                    role_val = m.group(1).strip()

        if depth <= 0:
            depth = 0
            _flush()

    return out
