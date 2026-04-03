import textwrap
import pytest
from StructIQ.dependency.extractor import extract_imports


TF_MODULE = textwrap.dedent("""\
    module "networking" {
      source = "./modules/networking"
    }

    module "lambda_api" {
      source = "./modules/api"
      environment = var.env
    }
""")

TF_LAMBDA = textwrap.dedent("""\
    resource "aws_lambda_function" "checkout" {
      filename         = "../../src/handlers/checkout.zip"
      function_name    = "checkout"
      role             = aws_iam_role.lambda_exec.arn
      handler          = "checkout.handler"
      runtime          = "python3.11"
    }

    resource "aws_lambda_function" "refund" {
      filename      = "../../src/handlers/refund.zip"
      function_name = "refund"
      role          = aws_iam_role.lambda_exec.arn
      handler       = "refund.handler"
      runtime       = "python3.11"
    }
""")

TF_MIXED = textwrap.dedent("""\
    module "vpc" {
      source = "./modules/vpc"
    }

    resource "aws_dynamodb_table" "users" {
      name = "users"
    }

    resource "aws_lambda_function" "processor" {
      filename  = "../../src/handlers/processor.zip"
      role      = aws_iam_role.shared.arn
      handler   = "processor.handler"
      runtime   = "python3.11"
    }
""")


def test_terraform_module_records_extracted():
    records = extract_imports("infra/main.tf", "terraform", text=TF_MODULE)
    module_records = [r for r in records if r["import_kind"] == "tf_module"]
    assert len(module_records) == 2


def test_terraform_module_import_targets():
    records = extract_imports("infra/main.tf", "terraform", text=TF_MODULE)
    targets = {r["import_target"] for r in records if r["import_kind"] == "tf_module"}
    assert "./modules/networking" in targets
    assert "./modules/api" in targets


def test_terraform_lambda_handler_records_extracted():
    records = extract_imports("infra/lambdas.tf", "terraform", text=TF_LAMBDA)
    lambda_records = [r for r in records if r["import_kind"] == "tf_lambda_handler"]
    assert len(lambda_records) == 2


def test_terraform_lambda_handler_import_targets():
    records = extract_imports("infra/lambdas.tf", "terraform", text=TF_LAMBDA)
    targets = {r["import_target"] for r in records if r["import_kind"] == "tf_lambda_handler"}
    assert "../../src/handlers/checkout.zip" in targets
    assert "../../src/handlers/refund.zip" in targets


def test_terraform_lambda_resource_name_in_raw_import():
    records = extract_imports("infra/lambdas.tf", "terraform", text=TF_LAMBDA)
    checkout = next(r for r in records
                    if r["import_kind"] == "tf_lambda_handler"
                    and "checkout" in r["import_target"])
    assert "checkout" in checkout["raw_import"]


def test_terraform_non_lambda_resources_not_emitted_as_lambda():
    records = extract_imports("infra/main.tf", "terraform", text=TF_MIXED)
    lambda_records = [r for r in records if r["import_kind"] == "tf_lambda_handler"]
    assert len(lambda_records) == 1
    assert "processor" in lambda_records[0]["import_target"]


def test_terraform_records_have_line_number():
    records = extract_imports("infra/main.tf", "terraform", text=TF_LAMBDA)
    for rec in records:
        assert "line_number" in rec
        assert isinstance(rec["line_number"], int)
        assert rec["line_number"] >= 1


def test_terraform_records_have_required_fields():
    records = extract_imports("infra/main.tf", "terraform", text=TF_MODULE)
    for rec in records:
        for field in ["source_file", "raw_import", "import_target", "import_kind", "language", "line_number"]:
            assert field in rec, f"Missing field: {field}"


def test_extract_imports_returns_empty_for_unknown_language():
    records = extract_imports("some.xyz", "xyz", text="garbage")
    assert records == []


def test_terraform_role_metadata_record():
    """Lambda records should carry role_arn as metadata for anti-pattern detection."""
    records = extract_imports("infra/lambdas.tf", "terraform", text=TF_LAMBDA)
    lambda_records = [r for r in records if r["import_kind"] == "tf_lambda_handler"]
    for rec in lambda_records:
        assert "role_arn" in rec
        assert "lambda_exec" in rec["role_arn"]
