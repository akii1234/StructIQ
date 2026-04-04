"""Tests for Terraform IaC security and structural detectors."""
from __future__ import annotations

import textwrap

from StructIQ.architecture.terraform_analyzer import TerraformAnalyzer


def _analyzer() -> TerraformAnalyzer:
    return TerraformAnalyzer()


# ── Fixtures ────────────────────────────────────────────────────────────────

_SG_OPEN = {
    "resources": [{
        "resource_type": "aws_security_group",
        "resource_name": "web_sg",
        "file": "/infra/main.tf",
        "line": 5,
        "block_text": textwrap.dedent("""\
            ingress {
              from_port   = 22
              to_port     = 22
              protocol    = "tcp"
              cidr_blocks = ["0.0.0.0/0"]
            }"""),
    }],
    "backend": {"type": "s3", "has_lock": True, "file": "/infra/backend.tf", "line": 1},
    "resource_type_counts_by_file": {},
}

_SG_RESTRICTED = {
    "resources": [{
        "resource_type": "aws_security_group",
        "resource_name": "internal_sg",
        "file": "/infra/main.tf",
        "line": 1,
        "block_text": 'ingress { from_port = 443 cidr_blocks = ["10.0.0.0/8"] }',
    }],
    "backend": {"type": "s3", "has_lock": True, "file": "/infra/b.tf", "line": 1},
    "resource_type_counts_by_file": {},
}

_IAM_WILDCARD = {
    "resources": [{
        "resource_type": "aws_iam_policy",
        "resource_name": "admin",
        "file": "/infra/iam.tf",
        "line": 1,
        "block_text": 'policy = "{ \\"Action\\": \\"*\\", \\"Resource\\": \\"*\\" }"',
    }],
    "backend": None,
    "resource_type_counts_by_file": {},
}

_IAM_SCOPED = {
    "resources": [{
        "resource_type": "aws_iam_policy",
        "resource_name": "read_only",
        "file": "/infra/iam.tf",
        "line": 1,
        "block_text": 'policy = "{ \\"Action\\": [\\"s3:GetObject\\"], \\"Resource\\": \\"arn:aws:s3:::my-bucket/*\\" }"',
    }],
    "backend": None,
    "resource_type_counts_by_file": {},
}

_S3_PUBLIC = {
    "resources": [{
        "resource_type": "aws_s3_bucket",
        "resource_name": "uploads",
        "file": "/infra/s3.tf",
        "line": 1,
        "block_text": 'bucket = "my-uploads"\nacl    = "public-read"',
    }],
    "backend": None,
    "resource_type_counts_by_file": {},
}

_S3_PRIVATE = {
    "resources": [{
        "resource_type": "aws_s3_bucket",
        "resource_name": "private",
        "file": "/infra/s3.tf",
        "line": 1,
        "block_text": 'bucket = "my-private"\nacl    = "private"',
    }, {
        "resource_type": "aws_s3_bucket_public_access_block",
        "resource_name": "private",
        "file": "/infra/s3.tf",
        "line": 10,
        "block_text": 'block_public_acls = true',
    }],
    "backend": None,
    "resource_type_counts_by_file": {},
}

_RDS_UNENCRYPTED = {
    "resources": [{
        "resource_type": "aws_db_instance",
        "resource_name": "main_db",
        "file": "/infra/rds.tf",
        "line": 1,
        "block_text": "identifier = \"prod\"\nstorage_encrypted = false",
    }],
    "backend": None,
    "resource_type_counts_by_file": {},
}

_RDS_ENCRYPTED = {
    "resources": [{
        "resource_type": "aws_db_instance",
        "resource_name": "secure_db",
        "file": "/infra/rds.tf",
        "line": 1,
        "block_text": "identifier = \"prod\"\nstorage_encrypted = true",
    }],
    "backend": None,
    "resource_type_counts_by_file": {},
}

_NO_BACKEND = {
    "resources": [],
    "backend": None,
    "resource_type_counts_by_file": {},
}

_LOCAL_BACKEND = {
    "resources": [],
    "backend": {"type": "local", "has_lock": False, "file": "/infra/main.tf", "line": 1},
    "resource_type_counts_by_file": {},
}

_GOD_MODULE = {
    "resources": [],
    "backend": None,
    "resource_type_counts_by_file": {
        "/infra/main.tf": {
            "aws_security_group": 2,
            "aws_db_instance": 1,
            "aws_s3_bucket": 1,
            "aws_iam_policy": 1,
            "aws_lambda_function": 2,
            "aws_cloudwatch_log_group": 1,
            "aws_sns_topic": 1,
        }  # 7 distinct types → exceeds threshold of 6
    },
}

_SMALL_MODULE = {
    "resources": [],
    "backend": None,
    "resource_type_counts_by_file": {
        "/infra/lambda.tf": {
            "aws_lambda_function": 2,
            "aws_iam_role": 1,
        }  # 2 types → fine
    },
}


# ── Tests: open_security_group ───────────────────────────────────────────────

def test_open_sg_detected():
    results = _analyzer().detect_open_security_groups(_SG_OPEN)
    assert len(results) == 1
    r = results[0]
    assert r["type"] == "open_security_group"
    assert r["resource_name"] == "web_sg"
    assert r["severity"] == "high"
    assert "web_sg" in r["description"]
    assert "0.0.0.0/0" in r["description"]


def test_restricted_sg_not_flagged():
    assert _analyzer().detect_open_security_groups(_SG_RESTRICTED) == []


def test_open_sg_empty_scan():
    assert _analyzer().detect_open_security_groups({}) == []


# ── Tests: wildcard_iam ──────────────────────────────────────────────────────

def test_wildcard_iam_detected():
    results = _analyzer().detect_wildcard_iam(_IAM_WILDCARD)
    assert len(results) == 1
    r = results[0]
    assert r["type"] == "wildcard_iam"
    assert r["resource_name"] == "admin"
    assert r["severity"] == "high"
    assert "admin" in r["description"]


def test_scoped_iam_not_flagged():
    assert _analyzer().detect_wildcard_iam(_IAM_SCOPED) == []


# ── Tests: public_s3_bucket ──────────────────────────────────────────────────

def test_public_s3_detected():
    results = _analyzer().detect_public_s3_buckets(_S3_PUBLIC)
    assert len(results) == 1
    r = results[0]
    assert r["type"] == "public_s3_bucket"
    assert r["resource_name"] == "uploads"
    assert r["severity"] == "high"
    assert "uploads" in r["description"]


def test_private_s3_not_flagged():
    assert _analyzer().detect_public_s3_buckets(_S3_PRIVATE) == []


# ── Tests: unencrypted_storage ───────────────────────────────────────────────

def test_unencrypted_rds_detected():
    results = _analyzer().detect_unencrypted_storage(_RDS_UNENCRYPTED)
    assert len(results) == 1
    r = results[0]
    assert r["type"] == "unencrypted_storage"
    assert r["resource_name"] == "main_db"
    assert r["severity"] == "medium"
    assert "main_db" in r["description"]


def test_encrypted_rds_not_flagged():
    assert _analyzer().detect_unencrypted_storage(_RDS_ENCRYPTED) == []


# ── Tests: no_remote_state ───────────────────────────────────────────────────

def test_no_backend_flagged():
    results = _analyzer().detect_no_remote_state(_NO_BACKEND)
    assert len(results) == 1
    assert results[0]["type"] == "no_remote_state"
    assert results[0]["severity"] == "medium"


def test_local_backend_flagged():
    results = _analyzer().detect_no_remote_state(_LOCAL_BACKEND)
    assert len(results) == 1
    assert results[0]["type"] == "no_remote_state"


def test_s3_backend_not_flagged():
    results = _analyzer().detect_no_remote_state(_SG_OPEN)  # has s3 backend
    assert results == []


# ── Tests: god_module ────────────────────────────────────────────────────────

def test_god_module_detected():
    results = _analyzer().detect_god_modules(_GOD_MODULE)
    assert len(results) == 1
    r = results[0]
    assert r["type"] == "god_module"
    assert r["file"] == "/infra/main.tf"
    assert r["resource_type_count"] == 7
    assert r["severity"] == "medium"
    assert "main.tf" in r["description"]


def test_small_module_not_flagged():
    assert _analyzer().detect_god_modules(_SMALL_MODULE) == []


# ── Tests: analyze() integration ────────────────────────────────────────────

def test_analyze_with_tf_scan_returns_all_findings():
    tf_scan = {
        "resources": (
            _SG_OPEN["resources"] +
            _IAM_WILDCARD["resources"] +
            _S3_PUBLIC["resources"] +
            _RDS_UNENCRYPTED["resources"]
        ),
        "backend": None,
        "resource_type_counts_by_file": _GOD_MODULE["resource_type_counts_by_file"],
    }
    result = _analyzer().analyze({}, {}, tf_scan=tf_scan)
    types = {ap["type"] for ap in result["anti_patterns"]}
    assert "open_security_group" in types
    assert "wildcard_iam" in types
    assert "public_s3_bucket" in types
    assert "unencrypted_storage" in types
    assert "no_remote_state" in types
    assert "god_module" in types


def test_analyze_without_tf_scan_returns_empty_new_detectors():
    """No tf_scan → new detectors produce nothing, existing Lambda detectors still work."""
    result = _analyzer().analyze({}, {}, tf_scan=None)
    types = {ap["type"] for ap in result["anti_patterns"]}
    assert "open_security_group" not in types
    assert "wildcard_iam" not in types
