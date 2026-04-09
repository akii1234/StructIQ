"""Tests for finding deduplication pass in architecture pipeline."""
from __future__ import annotations

from StructIQ.architecture.pipeline import _deduplicate_findings


def _ap(type_, file="/proj/models.py", severity="medium"):
    return {"type": type_, "file": file, "severity": severity}


def test_high_coupling_removed_when_hub_file_covers_same_file():
    aps = [_ap("hub_file", severity="high"), _ap("high_coupling")]
    result = _deduplicate_findings(aps)
    types = [r["type"] for r in result]
    assert "hub_file" in types
    assert "high_coupling" not in types


def test_high_coupling_kept_when_no_hub_file_for_same_file():
    aps = [_ap("hub_file", file="/proj/hub.py", severity="high"), _ap("high_coupling", file="/proj/other.py")]
    result = _deduplicate_findings(aps)
    assert len(result) == 2


def test_god_file_also_suppresses_high_coupling():
    aps = [_ap("god_file", severity="high"), _ap("high_coupling")]
    result = _deduplicate_findings(aps)
    assert "god_file" in [r["type"] for r in result]
    assert "high_coupling" not in [r["type"] for r in result]


def test_unrelated_findings_untouched():
    aps = [_ap("cycle", file=None, severity="high"), _ap("large_file"), _ap("orphan_file", severity="low")]
    assert len(_deduplicate_findings(aps)) == 3


def test_empty_input():
    assert _deduplicate_findings([]) == []


def test_hub_file_kept_even_when_it_dominates():
    aps = [_ap("hub_file", severity="high")]
    result = _deduplicate_findings(aps)
    assert len(result) == 1 and result[0]["type"] == "hub_file"
