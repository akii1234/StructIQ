# tests/test_compare_endpoint.py
from fastapi.testclient import TestClient
import json
from pathlib import Path
import pytest

from StructIQ.api.routes import app
import StructIQ.services.run_manager as rm_module


def _write_run(base: Path, run_id: str, health_score: int, cycles: int, god_files: int):
    run_dir = base / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "snapshot.json").write_text(json.dumps({"status": "completed"}))
    (run_dir / "dependency_analysis.json").write_text(json.dumps({
        "cycles": [{"files": ["a.py", "b.py"]}] * cycles,
        "coupling_scores": [],
    }))
    (run_dir / "architecture_insights.json").write_text(json.dumps({
        "anti_patterns": [{"type": "god_file"}] * god_files,
    }))
    (run_dir / "output.json").write_text(json.dumps({"files": ["a.py", "b.py", "c.py"]}))
    (run_dir / "modernization_plan.json").write_text(json.dumps({
        "decision": "action_required",
        "health_score": {"score": health_score, "grade": "B", "components": {}},
    }))


def test_compare_endpoint_returns_delta(tmp_path, monkeypatch):
    monkeypatch.setattr(rm_module, "DATA_DIR", tmp_path)

    _write_run(tmp_path, "run-aaa", health_score=42, cycles=3, god_files=2)
    _write_run(tmp_path, "run-bbb", health_score=67, cycles=1, god_files=1)

    client = TestClient(app)
    resp = client.get("/compare/run-aaa/run-bbb")
    assert resp.status_code == 200
    data = resp.json()
    assert data["health_score"]["delta"] == 25
    assert data["health_score"]["direction"] == "improved"
    assert data["cycles"]["delta"] == -2
    assert data["cycles"]["direction"] == "improved"


def test_compare_endpoint_404_missing_run(tmp_path, monkeypatch):
    monkeypatch.setattr(rm_module, "DATA_DIR", tmp_path)

    _write_run(tmp_path, "run-exists", health_score=50, cycles=1, god_files=0)

    client = TestClient(app)
    resp = client.get("/compare/run-exists/run-missing")
    assert resp.status_code == 404
