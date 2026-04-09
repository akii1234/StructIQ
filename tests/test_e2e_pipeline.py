"""End-to-end pipeline integration test using a small fixture project."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample_project"


@pytest.fixture(scope="module")
def run_output():
    """Run the full pipeline on the fixture project. Returns dict of output file contents."""
    if not FIXTURE_DIR.exists():
        pytest.skip("Fixture project not found")

    with tempfile.TemporaryDirectory() as tmp:
        run_path = Path(tmp) / "e2e_run"
        run_path.mkdir()

        py_files = sorted(str(p.resolve()) for p in FIXTURE_DIR.glob("*.py"))
        classified_files = [{"file": fp, "language": "python"} for fp in py_files]
        out_json = run_path / "output.json"
        out_json.write_text(
            json.dumps({"files": py_files, "classified_files": classified_files}),
            encoding="utf-8",
        )

        from StructIQ.architecture.pipeline import run_architecture_pipeline
        from StructIQ.dependency.pipeline import run_dependency_pipeline
        from StructIQ.modernization.pipeline import run_modernization_pipeline

        project_root = str(FIXTURE_DIR.resolve())
        run_id = "e2e-test"

        run_dependency_pipeline(
            output_path=str(out_json),
            run_dir=str(run_path),
            run_id=run_id,
            project_root=project_root,
        )

        run_architecture_pipeline(
            graph_path=str(run_path / "dependency_graph.json"),
            analysis_path=str(run_path / "dependency_analysis.json"),
            run_dir=str(run_path),
            run_id=run_id,
            enable_llm=False,
        )

        run_modernization_pipeline(
            insights_path=str(run_path / "architecture_insights.json"),
            graph_path=str(run_path / "dependency_graph.json"),
            run_dir=str(run_path),
            run_id=run_id,
            enable_llm=False,
        )

        outputs = {}
        for fname in (
            "dependency_graph.json",
            "architecture_insights.json",
            "modernization_plan.json",
            "snapshot.json",
        ):
            p = run_path / fname
            if p.exists():
                outputs[fname] = json.loads(p.read_text(encoding="utf-8"))

        yield outputs


def test_dependency_graph_produced(run_output):
    assert "dependency_graph.json" in run_output
    graph = run_output["dependency_graph.json"]
    assert len(graph.get("nodes", [])) > 0
    assert len(graph.get("edges", [])) > 0


def test_architecture_insights_produced(run_output):
    assert "architecture_insights.json" in run_output
    insights = run_output["architecture_insights.json"]
    assert len(insights.get("anti_patterns", [])) > 0


def test_cycle_detected(run_output):
    insights = run_output["architecture_insights.json"]
    types = {ap["type"] for ap in insights.get("anti_patterns", [])}
    assert "cycle" in types


def test_hub_file_detected(run_output):
    insights = run_output["architecture_insights.json"]
    hub_files = [ap for ap in insights.get("anti_patterns", []) if ap.get("type") == "hub_file"]
    assert len(hub_files) > 0


def test_domain_scores_present(run_output):
    insights = run_output["architecture_insights.json"]
    scores = insights.get("domain_scores", {})
    for domain in ("structural", "complexity", "maintainability", "security", "migration"):
        assert domain in scores
        assert "score" in scores[domain]
        assert "grade" in scores[domain]


def test_modernization_plan_produced(run_output):
    assert "modernization_plan.json" in run_output
    plan = run_output["modernization_plan.json"]
    assert plan.get("decision") in ("action_required", "no_action_required")


def test_break_cycle_task_present(run_output):
    plan = run_output["modernization_plan.json"]
    task_types = {t["type"] for t in plan.get("tasks", [])}
    assert "break_cycle" in task_types


def test_no_phase_errors(run_output):
    if "snapshot.json" in run_output:
        snap = run_output["snapshot.json"]
        for key in ("phase2_error", "phase3_error", "phase4_error"):
            assert key not in snap, f"Phase error: {snap.get(key)}"
