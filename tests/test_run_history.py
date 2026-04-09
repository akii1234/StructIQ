"""Tests for run history endpoint logic."""
from __future__ import annotations


def _make_run_summary(
    run_id, repo_path, status="completed", created_at="2026-04-09T10:00:00Z"
):
    return {
        "run_id": run_id,
        "repo_path": repo_path,
        "status": status,
        "created_at": created_at,
    }


def test_get_runs_for_repo_filters_by_path(monkeypatch):
    from StructIQ.services.run_manager import RunManager

    mgr = RunManager.__new__(RunManager)
    monkeypatch.setattr(
        mgr,
        "list_runs",
        lambda: [
            _make_run_summary("run-1", "/proj/a"),
            _make_run_summary("run-2", "/proj/b"),
            _make_run_summary("run-3", "/proj/a"),
        ],
    )
    result = mgr.get_runs_for_repo("/proj/a")
    assert len(result) == 2
    assert all(r["repo_path"] == "/proj/a" for r in result)


def test_get_runs_for_repo_excludes_non_completed(monkeypatch):
    from StructIQ.services.run_manager import RunManager

    mgr = RunManager.__new__(RunManager)
    monkeypatch.setattr(
        mgr,
        "list_runs",
        lambda: [
            _make_run_summary("run-1", "/proj/a", status="running"),
            _make_run_summary("run-2", "/proj/a", status="completed"),
        ],
    )
    result = mgr.get_runs_for_repo("/proj/a")
    assert len(result) == 1
    assert result[0]["run_id"] == "run-2"


def test_get_runs_for_repo_sorted_ascending(monkeypatch):
    from StructIQ.services.run_manager import RunManager

    mgr = RunManager.__new__(RunManager)
    monkeypatch.setattr(
        mgr,
        "list_runs",
        lambda: [
            _make_run_summary("run-b", "/proj/a", created_at="2026-04-09T12:00:00Z"),
            _make_run_summary("run-a", "/proj/a", created_at="2026-04-09T10:00:00Z"),
        ],
    )
    result = mgr.get_runs_for_repo("/proj/a")
    assert result[0]["run_id"] == "run-a"
    assert result[1]["run_id"] == "run-b"


def test_get_runs_for_repo_empty_when_no_match(monkeypatch):
    from StructIQ.services.run_manager import RunManager

    mgr = RunManager.__new__(RunManager)
    monkeypatch.setattr(
        mgr,
        "list_runs",
        lambda: [
            _make_run_summary("run-1", "/proj/other"),
        ],
    )
    result = mgr.get_runs_for_repo("/proj/mine")
    assert result == []
