# tests/test_antipattern_confirmer.py
from unittest.mock import MagicMock
from StructIQ.llm.trust.antipattern_confirmer import confirm_antipattern, AntiPatternVerdict


def _mock_client(response: dict):
    client = MagicMock()
    client.generate_json.return_value = response
    return client


def test_confirmed_god_file():
    client = _mock_client({
        "verdict": "confirmed",
        "explanation": "auth_service.py handles authentication, session management, and email delivery simultaneously.",
    })
    result = confirm_antipattern(
        pattern_type="god_file",
        file_path="auth_service.py",
        file_content="def login(): pass\ndef send_email(): pass\ndef create_session(): pass",
        llm_client=client,
    )
    assert result.verdict == "confirmed"
    assert len(result.explanation) > 0


def test_likely_intentional_verdict():
    client = _mock_client({
        "verdict": "likely_intentional",
        "explanation": "This appears to be a base class registry — its broad scope is by design.",
    })
    result = confirm_antipattern(
        pattern_type="god_file",
        file_path="base_registry.py",
        file_content="class Registry: pass",
        llm_client=client,
    )
    assert result.verdict == "likely_intentional"


def test_invalid_response_returns_unverified():
    client = _mock_client({"garbage": "value"})
    result = confirm_antipattern(
        pattern_type="high_coupling",
        file_path="utils.py",
        file_content="import everything",
        llm_client=client,
    )
    assert result.verdict == "unverified"


def test_verdict_dataclass_to_dict():
    v = AntiPatternVerdict(verdict="confirmed", explanation="test")
    d = v.to_dict()
    assert d["verdict"] == "confirmed"
    assert d["explanation"] == "test"
