"""Tests for FindingEnricher — LLM-powered anti-pattern description enrichment."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from StructIQ.llm.trust.finding_enricher import enrich_findings


def _ap(ap_type="high_coupling", severity="high", file="session_manager.py", **kw):
    base = {"type": ap_type, "severity": severity, "file": file, "description": "generic desc"}
    base.update(kw)
    return base


def test_no_llm_returns_original():
    aps = [_ap()]
    result = enrich_findings(aps, {}, None)
    assert result is aps


def test_empty_input_returns_empty():
    mock = MagicMock()
    assert enrich_findings([], {}, mock) == []
    mock.generate_json.assert_not_called()


def test_skips_low_severity():
    aps = [_ap(severity="low")]
    mock = MagicMock()
    result = enrich_findings(aps, {}, mock)
    assert result == aps
    mock.generate_json.assert_not_called()


def test_skips_test_gap_and_orphan_regardless_of_severity():
    aps = [
        _ap(ap_type="test_gap", severity="high", file="x.py"),
        _ap(ap_type="orphan_file", severity="medium", file="y.py"),
    ]
    mock = MagicMock()
    result = enrich_findings(aps, {}, mock)
    assert result == aps
    mock.generate_json.assert_not_called()


def test_enriches_medium_high_coupling():
    """high_coupling is always emitted at medium severity — enricher must process it."""
    aps = [_ap(ap_type="high_coupling", severity="medium", afferent_coupling=7, efferent_coupling=0)]
    mock = MagicMock()
    mock.generate_json.return_value = {
        "enriched": [{
            "id": 0,
            "description": "session_manager.py is specifically over-coordinated.",
            "why": "w",
            "impact_if_ignored": "i",
        }]
    }
    result = enrich_findings(aps, {}, mock)
    mock.generate_json.assert_called_once()
    assert "session_manager" in result[0]["description"]


def test_updates_high_severity_fields():
    aps = [_ap(severity="high", afferent_coupling=7, efferent_coupling=0)]
    mock = MagicMock()
    mock.generate_json.return_value = {
        "enriched": [{
            "id": 0,
            "description": "session_manager.py is a high-fan-in coordinator imported by the auth, views, and api layers.",
            "why": "Seven modules depend on session_manager.py, making any interface change a cascading refactor.",
            "impact_if_ignored": "Rotating the session storage backend requires synchronized changes across 7 dependent files.",
        }]
    }
    result = enrich_findings(aps, {}, mock)
    assert "session_manager" in result[0]["description"]
    assert result[0]["enriched_why"].startswith("Seven modules")
    assert "7 dependent" in result[0]["enriched_impact"]


def test_builds_neighbor_context_from_graph():
    aps = [_ap(severity="high", file="session_manager.py")]
    graph = {
        "edges": [
            {"source": "auth/middleware.py", "target": "session_manager.py"},
            {"source": "views/dashboard.py", "target": "session_manager.py"},
            {"source": "api/endpoints.py",   "target": "session_manager.py"},
        ]
    }
    mock = MagicMock()
    mock.generate_json.return_value = {"enriched": [{"id": 0, "description": "x", "why": "y", "impact_if_ignored": "z"}]}
    enrich_findings(aps, graph, mock)

    payload = json.loads(mock.generate_json.call_args[0][1])
    finding = payload["findings"][0]
    assert "middleware.py" in finding["imported_by"]
    assert "dashboard.py" in finding["imported_by"]


def test_non_fatal_on_llm_error():
    aps = [_ap(severity="high")]
    mock = MagicMock()
    mock.generate_json.side_effect = RuntimeError("LLM down")
    result = enrich_findings(aps, {}, mock)
    assert result == aps
    assert "enriched_why" not in result[0]


def test_non_fatal_on_invalid_response():
    aps = [_ap(severity="high")]
    mock = MagicMock()
    mock.generate_json.return_value = {"unexpected_key": "oops"}
    result = enrich_findings(aps, {}, mock)
    assert result == aps


def test_preserves_low_severity_alongside_high():
    low = _ap(ap_type="high_coupling", severity="low", file="utils.py")
    high = _ap(ap_type="high_coupling", severity="high", file="god_file.py")
    mock = MagicMock()
    mock.generate_json.return_value = {
        "enriched": [{
            "id": 0,
            "description": "god_file.py enriched with specific detail.",
            "why": "w",
            "impact_if_ignored": "i",
        }]
    }
    result = enrich_findings([low, high], {}, mock)
    assert result[0].get("enriched_why") is None   # low severity untouched
    assert result[1]["enriched_why"] == "w"         # high severity enriched


def test_does_not_mutate_original_dicts():
    original = _ap(severity="high")
    original_desc = original["description"]
    mock = MagicMock()
    mock.generate_json.return_value = {
        "enriched": [{"id": 0, "description": "new desc", "why": "w", "impact_if_ignored": "i"}]
    }
    enrich_findings([original], {}, mock)
    assert original["description"] == original_desc


def test_caps_at_max_findings():
    """Enricher never sends more than 8 findings to LLM regardless of input size."""
    aps = [_ap(severity="high", file=f"f{i}.py") for i in range(20)]
    mock = MagicMock()
    mock.generate_json.return_value = {"enriched": []}
    enrich_findings(aps, {}, mock)
    payload = json.loads(mock.generate_json.call_args[0][1])
    assert len(payload["findings"]) == 8


def test_mega_module_payload_uses_module_name_not_unknown():
    """Module-scoped findings must not send file='unknown' to the LLM."""
    aps = [
        {
            "type": "mega_module",
            "severity": "high",
            "module": "backend",
            "description": "orig",
            "metrics": {"module": "backend", "file_count": 17, "total_files": 28},
        }
    ]
    mock = MagicMock()
    mock.generate_json.return_value = {
        "enriched": [{"id": 0, "description": "x", "why": "y", "impact_if_ignored": "z"}]
    }
    enrich_findings(aps, {}, mock)
    payload = json.loads(mock.generate_json.call_args[0][1])
    assert payload["findings"][0]["file"] == "backend"
    assert "unknown" not in str(payload["findings"][0]["file"]).lower()


def test_enrich_findings_cycle_ap_uses_files_list():
    """Cycle anti-patterns use the files list, not a single file field."""
    aps = [{
        "type": "cycle",
        "severity": "high",
        "files": ["auth/session.py", "core/middleware.py"],
        "description": "Circular dependency between modules.",
    }]
    mock = MagicMock()
    mock.generate_json.return_value = {
        "enriched": [{"id": 0, "description": "session.py and middleware.py form a cycle that locks the auth and core layers together.", "why": "w", "impact_if_ignored": "i"}]
    }
    result = enrich_findings(aps, {}, mock)
    payload = json.loads(mock.generate_json.call_args[0][1])
    assert "session.py" in payload["findings"][0]["file"]
    assert "middleware.py" in payload["findings"][0]["file"]
    assert "session.py" in result[0]["description"]


def test_enrichment_rejected_when_filename_missing_from_description():
    aps = [_ap(ap_type="god_file", severity="high", file="session_manager.py")]
    mock = MagicMock()
    mock.generate_json.return_value = {
        "enriched": [{
            "id": 0,
            "description": "This file is an orphan with no connections.",
            "why": "It has zero dependencies.",
            "impact_if_ignored": "Nothing happens.",
        }]
    }
    result = enrich_findings(aps, {}, mock)
    assert result[0]["description"] == "generic desc"
    assert "enriched_why" not in result[0]


def test_enrichment_accepted_when_filename_present():
    aps = [_ap(ap_type="god_file", severity="high", file="session_manager.py")]
    mock = MagicMock()
    mock.generate_json.return_value = {
        "enriched": [{
            "id": 0,
            "description": "session_manager.py centralises auth, session, and token refresh.",
            "why": "14 modules depend on session_manager.py directly.",
            "impact_if_ignored": "Any change to session_manager.py requires coordinated updates.",
        }]
    }
    result = enrich_findings(aps, {}, mock)
    assert "session_manager" in result[0]["description"]
    assert result[0].get("enriched_why") is not None


def test_enrichment_rejected_when_description_too_short():
    original_desc = (
        "File has unusually high incoming/outgoing dependencies with many modules."
    )
    aps = [
        {
            "type": "high_coupling",
            "severity": "medium",
            "file": "session_manager.py",
            "description": original_desc,
        }
    ]
    mock = MagicMock()
    mock.generate_json.return_value = {
        "enriched": [{"id": 0, "description": "Bad.", "why": "w", "impact_if_ignored": "i"}]
    }
    result = enrich_findings(aps, {}, mock)
    assert result[0]["description"] == original_desc


def test_short_filename_skips_name_check():
    aps = [_ap(ap_type="god_file", severity="high", file="api.py")]
    mock = MagicMock()
    mock.generate_json.return_value = {
        "enriched": [{
            "id": 0,
            "description": "This module centralises all external service calls.",
            "why": "7 consumers depend on it.",
            "impact_if_ignored": "Any change cascades broadly.",
        }]
    }
    result = enrich_findings(aps, {}, mock)
    assert result[0].get("enriched_why") is not None
