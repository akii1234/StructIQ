from StructIQ.api.models import (
    HealthResponse,
    AnalyzeResponse,
    ExplainResponse,
    RunSummary,
)


def test_health_response_shape():
    r = HealthResponse(status="ok")
    assert r.status == "ok"


def test_analyze_response_shape():
    r = AnalyzeResponse(run_id="abc-123", status="started")
    assert r.run_id == "abc-123"
    assert r.status == "started"


def test_explain_response_shape():
    r = ExplainResponse(run_id="abc", question="why?", answer="because.")
    assert r.answer == "because."


def test_run_summary_shape():
    r = RunSummary(run_id="abc", status="completed", created_at="2026-04-02T00:00:00Z")
    assert r.run_id == "abc"
