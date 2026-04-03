# tests/test_score_rationale.py
from unittest.mock import MagicMock
from StructIQ.llm.trust.score_rationale import generate_score_rationale


def _mock_client(rationale: str):
    client = MagicMock()
    client.generate_json.return_value = {"rationale": rationale}
    return client


def test_returns_rationale_string():
    client = _mock_client(
        "Score of 42 reflects 3 runtime-critical cycles in the payments module "
        "and 2 god files that own 34% of all inbound dependencies."
    )
    result = generate_score_rationale(
        score=42,
        grade="F",
        components={"cycle_penalty": 15, "god_file_penalty": 16, "coupling_penalty": 12, "weak_boundary_penalty": 15},
        cycle_count=3,
        god_file_count=2,
        llm_client=client,
    )
    assert len(result) > 20
    assert "42" in result or "cycle" in result.lower()


def test_returns_empty_string_on_failure():
    client = MagicMock()
    client.generate_json.side_effect = Exception("LLM error")
    result = generate_score_rationale(
        score=80, grade="A", components={}, cycle_count=0, god_file_count=0, llm_client=client,
    )
    assert result == ""
