from fastapi.testclient import TestClient

from StructIQ.api.models import (
    HealthResponse,
    AnalyzeResponse,
    ExplainResponse,
    RunSummary,
)
from StructIQ.api.routes import app


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
    r = RunSummary(run_id="abc", status="completed")
    assert r.run_id == "abc"
    assert r.progress is None


def test_runs_endpoint_returns_list():
    client = TestClient(app)
    resp = client.get("/runs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_explain_rate_limiter_blocks_after_quota():
    from StructIQ.api.rate_limiter import RateLimiter

    rl = RateLimiter(max_requests=2, window_seconds=60)
    assert rl.is_allowed("user-a") is True
    assert rl.is_allowed("user-a") is True
    assert rl.is_allowed("user-a") is False
    assert rl.is_allowed("user-b") is True
