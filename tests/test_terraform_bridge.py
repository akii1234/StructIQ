import json
import textwrap
from pathlib import Path
import pytest
from StructIQ.dependency.graph_builder import build_graph


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_tf_module_edge_resolved(tmp_path):
    """module "vpc" { source = "./modules/vpc" } creates an edge to modules/vpc/main.tf."""
    _write(
        tmp_path / "infra" / "main.tf",
        textwrap.dedent(
            """\
        module "vpc" {
          source = "./modules/vpc"
        }
    """
        ),
    )
    _write(
        tmp_path / "infra" / "modules" / "vpc" / "main.tf",
        'resource "aws_vpc" "main" {}',
    )

    phase1 = {
        "files": [
            str(tmp_path / "infra" / "main.tf"),
            str(tmp_path / "infra" / "modules" / "vpc" / "main.tf"),
        ],
        "classified_files": [
            {"file": str(tmp_path / "infra" / "main.tf"), "language": "terraform"},
            {
                "file": str(tmp_path / "infra" / "modules" / "vpc" / "main.tf"),
                "language": "terraform",
            },
        ],
        "modules": {},
    }
    graph = build_graph(phase1, str(tmp_path), "test-run")
    edges = graph["edges"]
    matching = [
        e
        for e in edges
        if "infra/main.tf" in e["source"] and "vpc/main.tf" in e["target"]
    ]
    assert matching, f"Expected tf_module edge, got edges: {[e['source'] + ' -> ' + e['target'] for e in edges]}"


def test_tf_lambda_handler_edge_resolved(tmp_path):
    """filename = "../../src/handlers/checkout.zip" creates edge to src/handlers/checkout.py."""
    _write(
        tmp_path / "infra" / "lambdas.tf",
        textwrap.dedent(
            """\
        resource "aws_lambda_function" "checkout" {
          filename  = "../../src/handlers/checkout.zip"
          role      = aws_iam_role.exec.arn
          handler   = "checkout.handler"
          runtime   = "python3.11"
        }
    """
        ),
    )
    _write(
        tmp_path / "src" / "handlers" / "checkout.py",
        "def handler(event, ctx): pass",
    )

    phase1 = {
        "files": [
            str(tmp_path / "infra" / "lambdas.tf"),
            str(tmp_path / "src" / "handlers" / "checkout.py"),
        ],
        "classified_files": [
            {"file": str(tmp_path / "infra" / "lambdas.tf"), "language": "terraform"},
            {"file": str(tmp_path / "src" / "handlers" / "checkout.py"), "language": "python"},
        ],
        "modules": {},
    }
    graph = build_graph(phase1, str(tmp_path), "test-run")
    edges = graph["edges"]
    matching = [
        e
        for e in edges
        if "lambdas.tf" in e["source"] and "checkout.py" in e["target"]
    ]
    assert matching, f"Expected tf_lambda_handler edge, got edges: {edges}"


def test_tf_lambda_handler_edge_has_edge_type(tmp_path):
    """tf_lambda_handler edges carry edge_type field for anti-pattern detection."""
    _write(
        tmp_path / "infra" / "lambdas.tf",
        textwrap.dedent(
            """\
        resource "aws_lambda_function" "checkout" {
          filename  = "../../src/handlers/checkout.zip"
          role      = aws_iam_role.exec.arn
          handler   = "checkout.handler"
          runtime   = "python3.11"
        }
    """
        ),
    )
    _write(
        tmp_path / "src" / "handlers" / "checkout.py",
        "def handler(event, ctx): pass",
    )

    phase1 = {
        "files": [
            str(tmp_path / "infra" / "lambdas.tf"),
            str(tmp_path / "src" / "handlers" / "checkout.py"),
        ],
        "classified_files": [
            {"file": str(tmp_path / "infra" / "lambdas.tf"), "language": "terraform"},
            {"file": str(tmp_path / "src" / "handlers" / "checkout.py"), "language": "python"},
        ],
        "modules": {},
    }
    graph = build_graph(phase1, str(tmp_path), "test-run")
    edges = graph["edges"]
    lambda_edge = next(
        (
            e
            for e in edges
            if "lambdas.tf" in e["source"] and "checkout.py" in e["target"]
        ),
        None,
    )
    assert lambda_edge is not None
    assert lambda_edge.get("edge_type") == "tf_lambda_handler"
    assert lambda_edge.get("role_arn") == "aws_iam_role.exec.arn"


def test_unresolved_tf_lambda_does_not_crash(tmp_path):
    """If filename points to a file not in the project, it goes to unresolved — no crash."""
    _write(
        tmp_path / "infra" / "lambdas.tf",
        textwrap.dedent(
            """\
        resource "aws_lambda_function" "checkout" {
          filename  = "../../src/handlers/missing.zip"
          role      = aws_iam_role.exec.arn
          handler   = "missing.handler"
          runtime   = "python3.11"
        }
    """
        ),
    )

    phase1 = {
        "files": [str(tmp_path / "infra" / "lambdas.tf")],
        "classified_files": [{"file": str(tmp_path / "infra" / "lambdas.tf"), "language": "terraform"}],
        "modules": {},
    }
    # Should not raise
    graph = build_graph(phase1, str(tmp_path), "test-run")
    assert "edges" in graph
    assert "unresolved" in graph

