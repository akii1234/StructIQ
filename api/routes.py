"""FastAPI routes for analysis service."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, field_validator

from StructIQ.config import IS_API_MODE
from StructIQ.services.run_manager import RunManager
from StructIQ.api.models import HealthResponse, AnalyzeResponse, ExplainResponse, RunSummary, CompareResponse, CompareMetricResult


class AnalyzeRequest(BaseModel):
    """Input payload for analyze endpoint."""

    repo_path: str
    enable_llm: bool = False
    openai_api_key: str | None = None
    llm_provider: str = "openai"
    llm_model: str | None = None

    @field_validator("repo_path")
    @classmethod
    def validate_repo_path(cls, value: str) -> str:
        resolved = Path(value).resolve()

        if not resolved.exists():
            raise ValueError("Path does not exist")

        if not resolved.is_dir():
            raise ValueError("Path must be a directory")

        if IS_API_MODE:
            base = os.getenv("ALLOWED_BASE_DIR")
            if not base:
                raise RuntimeError("ALLOWED_BASE_DIR must be set in API mode")

            base_path = Path(base).resolve()

            if base_path not in resolved.parents and resolved != base_path:
                raise ValueError("Path outside allowed base directory")

        return str(resolved)


class ExplainRequest(BaseModel):
    question: str
    llm_api_key: str | None = None

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be empty")
        if len(value) > 500:
            raise ValueError("question must be 500 characters or fewer")
        return value


run_manager = RunManager()
if IS_API_MODE and not os.getenv("API_KEY"):
    raise RuntimeError(
        "API_KEY environment variable must be set when APP_MODE=api"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    run_manager.shutdown()


app = FastAPI(title="StructIQ Service", lifespan=lifespan)
active_runs = 0
MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "5"))
_active_runs_lock = threading.Lock()


def validate_api_key(x_api_key: str | None) -> None:
    if not IS_API_MODE:
        return

    expected = os.getenv("API_KEY")
    if not expected:
        return

    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/", response_class=FileResponse)
def index() -> str:
    """Serve the StructIQ browser UI."""
    return str(Path(__file__).parent.parent / "static" / "index.html")


@app.get("/runs", response_model=list[RunSummary])
def list_runs(x_api_key: str | None = Header(default=None)) -> list[RunSummary]:
    """List all runs with their current status."""
    validate_api_key(x_api_key)
    rows = run_manager.list_runs()
    return [RunSummary(**r) for r in rows]


def _release_slot_when_done(run_id: str) -> None:
    """Poll run status and release one API concurrency slot when finished."""
    global active_runs
    try:
        while True:
            status_payload = run_manager.get_status(run_id)
            state = status_payload.get("status")
            if state in {"completed", "failed", "not_found"}:
                break
            time.sleep(0.5)
    finally:
        with _active_runs_lock:
            active_runs = max(0, active_runs - 1)


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest, x_api_key: str | None = Header(default=None)) -> AnalyzeResponse:
    """Start async analysis run."""
    global active_runs
    validate_api_key(x_api_key)
    if IS_API_MODE:
        with _active_runs_lock:
            if active_runs >= MAX_CONCURRENT_RUNS:
                raise HTTPException(status_code=429, detail="Too many requests")
            active_runs += 1
    run_id = ""
    started = False
    try:
        run_id = run_manager.start_run(
            repo_path=request.repo_path,
            resume=True,
            enable_llm=request.enable_llm,
            openai_api_key=request.openai_api_key,
            llm_provider=request.llm_provider,
            llm_model=request.llm_model,
        )
        started = True
    finally:
        if IS_API_MODE and started and run_id:
            threading.Thread(
                target=_release_slot_when_done,
                args=(run_id,),
                daemon=True,
            ).start()
        elif IS_API_MODE:
            with _active_runs_lock:
                active_runs = max(0, active_runs - 1)
    return AnalyzeResponse(run_id=run_id, status="started")


@app.get("/status/{run_id}")
def status(run_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    """Fetch run status."""
    validate_api_key(x_api_key)
    payload = run_manager.get_status(run_id)
    if payload.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Run not found")
    return payload


@app.get("/results/{run_id}")
def results(run_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    """Fetch run output.json."""
    validate_api_key(x_api_key)
    payload = run_manager.get_results(run_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Results not found")
    return payload


@app.get("/dependency/graph/{run_id}")
def dependency_graph(run_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    """Fetch dependency graph for a completed run."""
    validate_api_key(x_api_key)
    payload = run_manager.get_dependency_graph(run_id)
    if not payload:
        status_payload = run_manager.get_status(run_id)
        run_status = status_payload.get("status")
        if run_status == "not_found" or not run_status:
            raise HTTPException(status_code=404, detail="Run not found")
        if run_status in {"running", "phase2_running"}:
            raise HTTPException(
                status_code=404,
                detail=f"Dependency graph not yet available — run status: {run_status}",
            )
        raise HTTPException(
            status_code=404,
            detail="Dependency graph not available — Phase 2 did not produce output for this run",
        )
    return payload


@app.get("/dependency/analysis/{run_id}")
def dependency_analysis(run_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    """Fetch dependency analysis for a completed run."""
    validate_api_key(x_api_key)
    payload = run_manager.get_dependency_analysis(run_id)
    if not payload:
        status_payload = run_manager.get_status(run_id)
        run_status = status_payload.get("status")
        if run_status == "not_found" or not run_status:
            raise HTTPException(status_code=404, detail="Run not found")
        if run_status in {"running", "phase2_running"}:
            raise HTTPException(
                status_code=404,
                detail=f"Dependency analysis not yet available — run status: {run_status}",
            )
        raise HTTPException(
            status_code=404,
            detail="Dependency analysis not available — Phase 2 did not produce output for this run",
        )
    return payload


@app.get("/architecture/insights/{run_id}")
def architecture_insights(run_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    """Fetch architecture insights for a completed run."""
    validate_api_key(x_api_key)
    payload = run_manager.get_architecture_insights(run_id)
    if not payload:
        status_payload = run_manager.get_status(run_id)
        run_status = status_payload.get("status")
        if run_status == "not_found" or not run_status:
            raise HTTPException(status_code=404, detail="Run not found")
        if run_status in {"running", "phase2_running", "phase3_running"}:
            raise HTTPException(
                status_code=404,
                detail=f"Architecture insights not yet available — run status: {run_status}",
            )
        raise HTTPException(
            status_code=404,
            detail="Architecture insights not available — Phase 3 did not produce output for this run",
        )
    return payload


@app.get("/modernization/plan/{run_id}")
def modernization_plan(run_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    """Fetch modernization plan for a completed run."""
    validate_api_key(x_api_key)
    payload = run_manager.get_modernization_plan(run_id)
    if not payload:
        status_payload = run_manager.get_status(run_id)
        run_status = status_payload.get("status")
        if run_status == "not_found" or not run_status:
            raise HTTPException(status_code=404, detail="Run not found")
        if run_status in {"running", "phase2_running", "phase3_running", "phase4_running"}:
            raise HTTPException(
                status_code=404,
                detail=f"Modernization plan not yet available — run status: {run_status}",
            )
        raise HTTPException(
            status_code=404,
            detail="Modernization plan not available — Phase 4 did not produce output for this run",
        )
    return payload


@app.get("/report/{run_id}", response_class=HTMLResponse)
def report(run_id: str, x_api_key: str | None = Header(default=None)) -> str:
    """Generate and return HTML report for a completed run."""
    validate_api_key(x_api_key)
    status_payload = run_manager.get_status(run_id)
    run_status = status_payload.get("status")
    if run_status == "not_found" or not run_status:
        raise HTTPException(status_code=404, detail="Run not found")
    if run_status not in {"completed"}:
        raise HTTPException(
            status_code=404,
            detail=f"Report not available — run status: {run_status}",
        )
    try:
        from StructIQ.reporting.pipeline import run_report_pipeline, ReportPipelineError

        run_dir = str(Path("data/runs") / run_id)
        html = run_report_pipeline(run_dir=run_dir, run_id=run_id)
        return Path(html).read_text(encoding="utf-8")
    except ReportPipelineError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/review/{run_id}")
def review(run_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    """Generate and return architecture review for a completed run."""
    validate_api_key(x_api_key)
    status_payload = run_manager.get_status(run_id)
    run_status = status_payload.get("status")
    if run_status == "not_found" or not run_status:
        raise HTTPException(status_code=404, detail="Run not found")
    if run_status != "completed":
        raise HTTPException(
            status_code=404,
            detail=f"Review not available — run status: {run_status}",
        )
    from StructIQ.generators.json_writer import read_json_file
    from StructIQ.reporting.architecture_review import generate_review

    run_dir = Path("data/runs") / run_id
    dep_analysis = read_json_file(str(run_dir / "dependency_analysis.json"), {})
    arch_insights = read_json_file(str(run_dir / "architecture_insights.json"), {})
    mod_plan = read_json_file(str(run_dir / "modernization_plan.json"), {})
    discovery = read_json_file(str(run_dir / "output.json"), {})

    if not dep_analysis or not arch_insights:
        raise HTTPException(
            status_code=404,
            detail="Review data not available — run may be incomplete",
        )

    return generate_review(dep_analysis, arch_insights, mod_plan, discovery)


@app.post("/explain/{run_id}", response_model=ExplainResponse)
def explain(run_id: str, request: ExplainRequest, x_api_key: str | None = Header(default=None)) -> ExplainResponse:
    """Answer a plain-English question about a completed run using the modernization plan."""
    validate_api_key(x_api_key)
    status_payload = run_manager.get_status(run_id)
    run_status = status_payload.get("status")
    if run_status == "not_found" or not run_status:
        raise HTTPException(status_code=404, detail="Run not found")
    if run_status != "completed":
        raise HTTPException(
            status_code=404,
            detail=f"Explanation not available — run status: {run_status}",
        )

    plan = run_manager.get_modernization_plan(run_id)
    insights = run_manager.get_architecture_insights(run_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Modernization plan not found for this run")

    from StructIQ.llm.client import LLMClient
    from StructIQ.services.run_manager import DATA_DIR
    import json

    _snap = run_manager.get_status(run_id)
    _llm_stats = _snap.get("llm_stats") or {}
    _provider = _llm_stats.get("provider") or "openai"
    _model = _llm_stats.get("model") or None
    try:
        _llm_client = LLMClient(
            provider=_provider,
            api_key=request.llm_api_key or None,
            model=_model,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"LLM not available — provide llm_api_key in request or set the provider's env var. ({exc})",
        )

    context_payload = {
        "system_summary": str((insights or {}).get("system_summary", ""))[:600],
        "decision": plan.get("decision", ""),
        "plan_mode": plan.get("plan_mode", ""),
        "plan_summary": str(plan.get("plan_summary", ""))[:400],
        "sequencing_notes": str(plan.get("sequencing_notes", ""))[:300],
        "task_count": len(plan.get("tasks") or []),
        "tasks": [
            {
                "type": t.get("type"),
                "target": (t.get("target") or [])[:3],
                "priority": t.get("priority"),
                "why": str(t.get("why", ""))[:200],
            }
            for t in (plan.get("tasks") or [])[:10]
            if isinstance(t, dict)
        ],
        "anti_pattern_count": len((insights or {}).get("anti_patterns") or []),
    }

    system_prompt = (
        "You are a software architecture advisor. "
        "You are given a modernization plan for a codebase analysis run. "
        "Answer the user's question in plain English, in 2-4 sentences. "
        "Be specific and actionable. Do not use markdown or bullet points. "
        "Return JSON with a single key 'answer'."
    )
    user_message = f"Context: {json.dumps(context_payload)}\n\nQuestion: {request.question}"

    try:
        response = _llm_client.generate_json(system_prompt, user_message)
        answer = str(response.get("answer", "")).strip() if isinstance(response, dict) else ""
        if not answer:
            raise HTTPException(status_code=500, detail="LLM returned an empty answer")
        return ExplainResponse(run_id=run_id, question=request.question, answer=answer)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM error: {exc}") from exc


@app.get("/compare/{run_id_a}/{run_id_b}", response_model=CompareResponse)
def compare(
    run_id_a: str,
    run_id_b: str,
    x_api_key: str | None = Header(default=None),
) -> CompareResponse:
    """Compare two completed runs — returns delta per metric."""
    validate_api_key(x_api_key)

    from StructIQ.reporting.comparator import compare_runs

    data_a = run_manager.get_run_data_for_compare(run_id_a)
    data_b = run_manager.get_run_data_for_compare(run_id_b)

    if not data_a:
        raise HTTPException(status_code=404, detail=f"Run {run_id_a} not found or incomplete")
    if not data_b:
        raise HTTPException(status_code=404, detail=f"Run {run_id_b} not found or incomplete")

    delta = compare_runs(data_a, data_b)

    return CompareResponse(
        run_id_a=run_id_a,
        run_id_b=run_id_b,
        health_score=CompareMetricResult(**delta["health_score"]),
        cycles=CompareMetricResult(**delta["cycles"]),
        god_files=CompareMetricResult(**delta["god_files"]),
        weak_boundaries=CompareMetricResult(**delta["weak_boundaries"]),
        high_coupling_files=CompareMetricResult(**delta["high_coupling_files"]),
    )
