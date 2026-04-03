import textwrap
import pytest
from StructIQ.architecture.terraform_analyzer import TerraformAnalyzer


def _make_graph(edges: list[dict], nodes: list[dict] | None = None) -> dict:
    return {"edges": edges, "nodes": nodes or []}


def _make_analysis(coupling_scores: list[dict] | None = None) -> dict:
    return {"coupling_scores": coupling_scores or [], "cycles": []}


def _tf_edge(tf_file: str, handler_file: str, role_arn: str = "arn:aws:iam::123:role/exec") -> dict:
    return {
        "source": tf_file,
        "target": handler_file,
        "raw_import": f'resource "aws_lambda_function" "fn" {{ filename = "..." }}',
        "line_number": 1,
        "edge_type": "tf_lambda_handler",
        "role_arn": role_arn,
    }


# --- god_lambda ---

def test_god_lambda_detected_when_out_degree_high():
    graph = _make_graph(edges=[
        _tf_edge("infra/lambdas.tf", "/src/handlers/big.py"),
    ])
    analysis = _make_analysis(coupling_scores=[
        {"file": "/src/handlers/big.py", "afferent_coupling": 2, "efferent_coupling": 15, "instability": 0.88},
    ])
    results = TerraformAnalyzer().detect_god_lambdas(graph, analysis)
    assert len(results) == 1
    assert results[0]["type"] == "god_lambda"
    assert results[0]["handler_file"] == "/src/handlers/big.py"
    assert results[0]["efferent_coupling"] == 15


def test_god_lambda_not_detected_when_coupling_low():
    graph = _make_graph(edges=[
        _tf_edge("infra/lambdas.tf", "/src/handlers/small.py"),
    ])
    analysis = _make_analysis(coupling_scores=[
        {"file": "/src/handlers/small.py", "afferent_coupling": 1, "efferent_coupling": 3, "instability": 0.3},
    ])
    results = TerraformAnalyzer().detect_god_lambdas(graph, analysis)
    assert results == []


def test_god_lambda_not_detected_for_non_lambda_edges():
    """Regular code edges (edge_type=None) must not trigger god_lambda."""
    graph = _make_graph(edges=[
        {"source": "a.py", "target": "b.py", "raw_import": "import b", "line_number": 1, "edge_type": None},
    ])
    analysis = _make_analysis(coupling_scores=[
        {"file": "b.py", "afferent_coupling": 1, "efferent_coupling": 20, "instability": 0.95},
    ])
    results = TerraformAnalyzer().detect_god_lambdas(graph, analysis)
    assert results == []


# --- direct_lambda_invocation ---

def test_direct_invocation_detected(tmp_path):
    handler = tmp_path / "handler.py"
    handler.write_text(textwrap.dedent("""\
        import boto3
        def process(event, ctx):
            client = boto3.client('lambda')
            client.invoke(FunctionName='other-fn', Payload=b'{}')
    """))
    graph = _make_graph(edges=[
        _tf_edge("infra/lambdas.tf", str(handler)),
    ])
    results = TerraformAnalyzer().detect_direct_lambda_invocations(graph)
    assert len(results) == 1
    assert results[0]["type"] == "direct_lambda_invocation"
    assert str(handler) in results[0]["handler_file"]


def test_direct_invocation_not_detected_for_clean_handler(tmp_path):
    handler = tmp_path / "handler.py"
    handler.write_text("import json\ndef handler(event, ctx): return {'ok': True}")
    graph = _make_graph(edges=[
        _tf_edge("infra/lambdas.tf", str(handler)),
    ])
    results = TerraformAnalyzer().detect_direct_lambda_invocations(graph)
    assert results == []


def test_direct_invocation_skips_missing_file():
    """Missing handler file must not crash — returns empty list."""
    graph = _make_graph(edges=[
        _tf_edge("infra/lambdas.tf", "/nonexistent/handler.py"),
    ])
    results = TerraformAnalyzer().detect_direct_lambda_invocations(graph)
    assert results == []


# --- shared_iam_role ---

def test_shared_iam_role_detected():
    graph = _make_graph(edges=[
        _tf_edge("infra/lambdas.tf", "/src/checkout.py", role_arn="arn:aws:iam::123:role/shared"),
        _tf_edge("infra/lambdas.tf", "/src/refund.py", role_arn="arn:aws:iam::123:role/shared"),
        _tf_edge("infra/lambdas.tf", "/src/dispute.py", role_arn="arn:aws:iam::123:role/other"),
    ])
    results = TerraformAnalyzer().detect_shared_iam_roles(graph)
    assert len(results) == 1
    assert results[0]["type"] == "shared_iam_role"
    assert results[0]["role_arn"] == "arn:aws:iam::123:role/shared"
    assert len(results[0]["lambda_files"]) == 2


def test_shared_iam_role_not_detected_when_each_lambda_has_own_role():
    graph = _make_graph(edges=[
        _tf_edge("infra/lambdas.tf", "/src/checkout.py", role_arn="arn:aws:iam::123:role/checkout-role"),
        _tf_edge("infra/lambdas.tf", "/src/refund.py", role_arn="arn:aws:iam::123:role/refund-role"),
    ])
    results = TerraformAnalyzer().detect_shared_iam_roles(graph)
    assert results == []


def test_shared_iam_role_ignores_null_role_arn():
    graph = _make_graph(edges=[
        {"source": "infra/main.tf", "target": "/src/fn.py",
         "raw_import": "...", "line_number": 1, "edge_type": "tf_lambda_handler", "role_arn": None},
    ])
    results = TerraformAnalyzer().detect_shared_iam_roles(graph)
    assert results == []


# --- analyze() ---

def test_analyze_returns_anti_patterns_key():
    results = TerraformAnalyzer().analyze(_make_graph([]), _make_analysis())
    assert "anti_patterns" in results
    assert isinstance(results["anti_patterns"], list)
