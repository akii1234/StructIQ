"""Tests for finding override manager."""
from __future__ import annotations

import tempfile

from StructIQ.services.override_manager import OverrideManager


def _mgr() -> OverrideManager:
    return OverrideManager(tempfile.mkdtemp())


def test_add_and_list():
    mgr = _mgr()
    mgr.add("hub_file", "models.py", "intentional", "Django convention")
    entries = mgr.list()
    assert len(entries) == 1
    assert entries[0]["type"] == "hub_file"
    assert entries[0]["reason"] == "intentional"


def test_add_replaces_existing_same_type_file():
    mgr = _mgr()
    mgr.add("hub_file", "models.py", "intentional")
    mgr.add("hub_file", "models.py", "false_positive", "updated")
    assert len(mgr.list()) == 1
    assert mgr.list()[0]["reason"] == "false_positive"


def test_remove_existing():
    mgr = _mgr()
    mgr.add("hub_file", "models.py", "intentional")
    removed = mgr.remove("hub_file", "models.py")
    assert removed is True
    assert mgr.list() == []


def test_remove_nonexistent_returns_false():
    mgr = _mgr()
    assert mgr.remove("cycle", "utils.py") is False


def test_apply_tags_matched_finding():
    mgr = _mgr()
    mgr.add("hub_file", "models.py", "intentional", "Django hub")
    aps = [{"type": "hub_file", "file": "models.py", "severity": "high"}]
    result = mgr.apply(aps)
    assert result[0]["suppressed"] is True
    assert result[0]["suppression_reason"] == "intentional"


def test_apply_does_not_remove_suppressed_finding():
    mgr = _mgr()
    mgr.add("hub_file", "models.py", "intentional")
    aps = [{"type": "hub_file", "file": "models.py", "severity": "high"}]
    result = mgr.apply(aps)
    assert len(result) == 1  # still present, just tagged


def test_apply_leaves_unmatched_findings_unchanged():
    mgr = _mgr()
    mgr.add("hub_file", "models.py", "intentional")
    aps = [{"type": "cycle", "file": "utils.py", "severity": "high"}]
    result = mgr.apply(aps)
    assert "suppressed" not in result[0]


def test_apply_matches_basename_when_full_path_given():
    mgr = _mgr()
    mgr.add("hub_file", "models.py", "intentional")  # stored as basename
    aps = [{"type": "hub_file", "file": "/proj/myapp/models.py", "severity": "high"}]
    result = mgr.apply(aps)
    assert result[0].get("suppressed") is True


def test_list_on_missing_run_dir_returns_empty():
    mgr = OverrideManager("/tmp/does-not-exist-run-dir-xyz")
    assert mgr.list() == []
