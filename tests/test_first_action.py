# tests/test_first_action.py
from unittest.mock import MagicMock
from StructIQ.llm.trust.first_action import generate_first_action


def _mock_client(answer: str):
    client = MagicMock()
    client.generate_json.return_value = {"first_action": answer}
    return client


def test_returns_precise_action():
    client = _mock_client(
        "In payments/utils.py line 47, wrap the `from ledger.service import LedgerService` "
        "import in a TYPE_CHECKING guard to break the cycle without touching runtime logic."
    )
    result = generate_first_action(
        top_step={"action": "break_dependency", "from": "payments/utils.py", "to": "ledger/service.py"},
        step_description="Remove line 47 in payments/utils.py — closing edge of the cycle.",
        affected_file_summaries={"payments/utils.py": "Handles payment processing and ledger coordination."},
        llm_client=client,
    )
    assert "payments/utils.py" in result or "line 47" in result
    assert len(result) > 20


def test_returns_empty_string_on_failure():
    client = MagicMock()
    client.generate_json.side_effect = ValueError("LLM error")
    result = generate_first_action(
        top_step={"action": "break_dependency", "from": "a.py", "to": "b.py"},
        step_description="Remove import",
        affected_file_summaries={},
        llm_client=client,
    )
    assert result == ""


def test_returns_empty_string_on_missing_key():
    client = MagicMock()
    client.generate_json.return_value = {"wrong_key": "value"}
    result = generate_first_action(
        top_step={},
        step_description="",
        affected_file_summaries={},
        llm_client=client,
    )
    assert result == ""
