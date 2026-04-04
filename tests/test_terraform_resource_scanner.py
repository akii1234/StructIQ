"""Tests for TerraformResourceScanner — resource block extraction from .tf files."""
from __future__ import annotations

import textwrap

from StructIQ.dependency.terraform_resource_scanner import TerraformResourceScanner

_SG = textwrap.dedent("""\
    resource "aws_security_group" "web_sg" {
      name = "web_sg"
      ingress {
        from_port   = 22
        to_port     = 22
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
      }
      egress {
        from_port   = 0
        to_port     = 0
        protocol    = "-1"
        cidr_blocks = ["0.0.0.0/0"]
      }
    }
""")

_IAM = textwrap.dedent("""\
    resource "aws_iam_policy" "admin" {
      name   = "AdminPolicy"
      policy = jsonencode({
        Statement = [{
          Action   = "*"
          Resource = "*"
          Effect   = "Allow"
        }]
      })
    }
""")

_S3 = textwrap.dedent("""\
    resource "aws_s3_bucket" "uploads" {
      bucket = "my-uploads"
      acl    = "public-read"
    }
""")

_RDS = textwrap.dedent("""\
    resource "aws_db_instance" "main" {
      identifier        = "prod-db"
      storage_encrypted = false
      instance_class    = "db.t3.medium"
    }
""")

_BACKEND_S3_NO_LOCK = textwrap.dedent("""\
    terraform {
      backend "s3" {
        bucket = "my-tfstate"
        key    = "prod/terraform.tfstate"
        region = "us-east-1"
      }
    }
""")

_BACKEND_S3_WITH_LOCK = textwrap.dedent("""\
    terraform {
      backend "s3" {
        bucket         = "my-tfstate"
        key            = "prod/terraform.tfstate"
        region         = "us-east-1"
        dynamodb_table = "terraform-locks"
      }
    }
""")

_UNKNOWN_RESOURCE = textwrap.dedent("""\
    resource "aws_dynamodb_table" "users" {
      name = "users"
    }
""")


def _scan(text: str, filename: str = "main.tf") -> dict:
    scanner = TerraformResourceScanner()
    return scanner._scan_text(text, f"/proj/{filename}")


def test_extracts_security_group_record():
    result = _scan(_SG)
    resources = result["resources"]
    assert len(resources) == 1
    r = resources[0]
    assert r["resource_type"] == "aws_security_group"
    assert r["resource_name"] == "web_sg"
    assert r["file"] == "/proj/main.tf"
    assert r["line"] == 1


def test_security_group_block_text_contains_cidr():
    result = _scan(_SG)
    block_text = result["resources"][0]["block_text"]
    assert "0.0.0.0/0" in block_text
    assert "from_port" in block_text


def test_extracts_iam_policy_record():
    result = _scan(_IAM)
    r = result["resources"][0]
    assert r["resource_type"] == "aws_iam_policy"
    assert r["resource_name"] == "admin"
    assert '"*"' in r["block_text"] or "'*'" in r["block_text"] or "\"*\"" in r["block_text"]


def test_extracts_s3_bucket_record():
    result = _scan(_S3)
    r = result["resources"][0]
    assert r["resource_type"] == "aws_s3_bucket"
    assert r["resource_name"] == "uploads"
    assert "public-read" in r["block_text"]


def test_extracts_rds_record():
    result = _scan(_RDS)
    r = result["resources"][0]
    assert r["resource_type"] == "aws_db_instance"
    assert "storage_encrypted" in r["block_text"]


def test_skips_non_security_relevant_types():
    """aws_dynamodb_table is not in _SCAN_TYPES — should not appear in resources."""
    result = _scan(_UNKNOWN_RESOURCE)
    assert result["resources"] == []


def test_resource_type_counts_all_types():
    """god_module needs counts of ALL resource types, not just security-relevant ones."""
    result = _scan(_UNKNOWN_RESOURCE)
    counts = result["resource_type_counts_by_file"].get("/proj/main.tf", {})
    assert counts.get("aws_dynamodb_table") == 1


def test_backend_s3_no_lock():
    result = _scan(_BACKEND_S3_NO_LOCK, "backend.tf")
    assert result["backend"] is not None
    assert result["backend"]["type"] == "s3"
    assert result["backend"]["has_lock"] is False


def test_backend_s3_with_lock():
    result = _scan(_BACKEND_S3_WITH_LOCK, "backend.tf")
    assert result["backend"]["has_lock"] is True


def test_no_backend_block():
    result = _scan(_SG)
    assert result["backend"] is None


def test_scan_merges_multiple_files():
    """scan() aggregates results from multiple file paths."""
    scanner = TerraformResourceScanner()
    # Write two temp files and scan them — use _scan_text directly for unit test
    r1 = scanner._scan_text(_SG, "/proj/sg.tf")
    r2 = scanner._scan_text(_IAM, "/proj/iam.tf")
    merged = scanner._merge([r1, r2])
    types = {r["resource_type"] for r in merged["resources"]}
    assert "aws_security_group" in types
    assert "aws_iam_policy" in types


def test_record_has_required_fields():
    result = _scan(_SG)
    r = result["resources"][0]
    for field in ("resource_type", "resource_name", "file", "line", "block_text"):
        assert field in r, f"Missing field: {field}"


def test_scan_returns_empty_on_no_tf_files():
    scanner = TerraformResourceScanner()
    result = scanner.scan([])
    assert result["resources"] == []
    assert result["backend"] is None
    assert result["resource_type_counts_by_file"] == {}
