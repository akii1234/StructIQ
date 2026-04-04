"""Tests for Phase 4.5 intelligence digest and narrative generator."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from StructIQ.intelligence.digest_builder import DigestBuilder
from StructIQ.intelligence.narrative_generator import NarrativeGenerator


def test_digest_builder_bounds_token_count():
    """Digest must serialize to < 3000 characters."""
    phase1 = {
        "files": [f"/proj/f{i}.py" for i in range(500)],
        "classified_files": [
            {"file": f"/proj/f{i}.py", "language": "python"} for i in range(500)
        ],
    }
    graph = {"edges": [{}] * 80}
    insights = {
        "domain_scores": {"structural": {"score": 80, "grade": "B", "finding_count": 1}},
        "anti_patterns": [
            {
                "type": "cycle",
                "severity": "high",
                "description": "x" * 400,
                "files": ["/a.py", "/b.py"],
            }
        ],
        "services": {"api": [f"/svc/{i}.py" for i in range(20)]},
    }
    plan = {
        "decision": "action_required",
        "plan_mode": "direct",
        "tasks": [{"type": "break_cycle", "priority": "high", "target": ["/a.py"]}],
    }
    d = DigestBuilder().build(phase1, graph, {}, insights, plan)
    assert len(json.dumps(d)) < 3000


def test_digest_builder_includes_all_four_sections():
    """Digest must have system, domain_scores, top_anti_patterns, migration_blockers."""
    d = DigestBuilder().build(
        {"files": [], "classified_files": []},
        {"edges": []},
        {},
        {"anti_patterns": [], "domain_scores": {}},
        {"tasks": []},
    )
    assert "system" in d
    assert "domain_scores" in d
    assert "top_anti_patterns" in d
    assert "migration_blockers" in d


def test_narrative_generator_returns_empty_on_no_llm_client():
    """NarrativeGenerator with None client returns empty strings, does not raise."""
    out = NarrativeGenerator(None).generate({"a": 1})
    assert out["system_narrative"] == ""
    assert out["onboarding_guide"] == []
    assert out["domain_narratives"] == {}
    assert out["migration_assessment"] == ""


def test_narrative_generator_non_fatal_on_llm_exception():
    """NarrativeGenerator catching LLM exception returns empty-shaped dict, does not raise."""
    mock = MagicMock()
    mock.generate_json.side_effect = RuntimeError("LLM down")
    out = NarrativeGenerator(mock).generate({"k": "v"})
    assert out["system_narrative"] == ""
    assert out["onboarding_guide"] == []
    assert out["domain_narratives"] == {}
    assert out["migration_assessment"] == ""


def test_digest_top_anti_patterns_sorted_by_severity():
    """High severity findings appear before medium in digest."""
    insights = {
        "anti_patterns": [
            {"type": "a", "severity": "low", "description": "low"},
            {"type": "b", "severity": "high", "description": "high"},
            {"type": "c", "severity": "medium", "description": "med"},
        ]
    }
    d = DigestBuilder().build(
        {"files": [], "classified_files": []},
        {"edges": []},
        {},
        insights,
        {"tasks": []},
    )
    tops = d["top_anti_patterns"]
    assert [x["type"] for x in tops[:3]] == ["b", "c", "a"]
