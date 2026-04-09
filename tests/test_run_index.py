"""Tests for SQLite-backed run index."""
from __future__ import annotations

import tempfile
from pathlib import Path

from StructIQ.services.run_index import RunIndex


def _make_index() -> RunIndex:
    tmp = tempfile.mkdtemp()
    return RunIndex(str(Path(tmp) / "runs.db"))


def test_upsert_and_get():
    idx = _make_index()
    idx.upsert("run-1", status="running", repo_path="/proj", created_at="2026-04-09T10:00:00Z")
    row = idx.get("run-1")
    assert row is not None
    assert row["status"] == "running"
    assert row["repo_path"] == "/proj"


def test_upsert_updates_existing():
    idx = _make_index()
    idx.upsert("run-1", status="running", created_at="2026-04-09T10:00:00Z")
    idx.upsert("run-1", status="completed", updated_at="2026-04-09T10:05:00Z")
    assert idx.get("run-1")["status"] == "completed"


def test_get_missing_returns_none():
    idx = _make_index()
    assert idx.get("nonexistent") is None


def test_list_all_returns_sorted_by_created_at():
    idx = _make_index()
    idx.upsert("run-a", status="completed", created_at="2026-04-09T10:00:00Z")
    idx.upsert("run-b", status="completed", created_at="2026-04-09T11:00:00Z")
    rows = idx.list_all()
    assert rows[0]["run_id"] == "run-b"


def test_delete_removes_row():
    idx = _make_index()
    idx.upsert("run-1", status="completed", created_at="2026-04-09T10:00:00Z")
    idx.delete("run-1")
    assert idx.get("run-1") is None


def test_list_all_empty_returns_empty_list():
    idx = _make_index()
    assert idx.list_all() == []
