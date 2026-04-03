# tests/test_cycle_classifier.py
import pytest
from unittest.mock import MagicMock
from StructIQ.llm.trust.cycle_classifier import classify_cycle, CycleClassification


def _mock_client(response: dict):
    client = MagicMock()
    client.generate_json.return_value = response
    return client


def test_classify_returns_runtime_critical():
    client = _mock_client({
        "classification": "runtime_critical",
        "confidence": "high",
        "reasoning": "Both modules instantiate each other at import time.",
        "suggested_fix": None,
    })
    result = classify_cycle(
        source_file="payments/processor.py",
        source_content="from ledger.service import LedgerService\nclass Processor: pass",
        target_file="ledger/service.py",
        target_content="from payments.processor import Processor\nclass LedgerService: pass",
        raw_import="from ledger.service import LedgerService",
        llm_client=client,
    )
    assert result.classification == "runtime_critical"
    assert result.suggested_fix is None


def test_classify_returns_type_hint_only_with_fix():
    client = _mock_client({
        "classification": "type_hint_only",
        "confidence": "high",
        "reasoning": "Import only used in type annotations.",
        "suggested_fix": "Wrap in TYPE_CHECKING guard: from __future__ import annotations; from typing import TYPE_CHECKING; if TYPE_CHECKING: from ledger.service import LedgerService",
    })
    result = classify_cycle(
        source_file="payments/processor.py",
        source_content="from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from ledger.service import LedgerService",
        target_file="ledger/service.py",
        target_content="from payments.processor import Processor",
        raw_import="from ledger.service import LedgerService",
        llm_client=client,
    )
    assert result.classification == "type_hint_only"
    assert result.suggested_fix is not None
    assert "TYPE_CHECKING" in result.suggested_fix


def test_classify_invalid_response_returns_unknown():
    client = _mock_client({"bad_key": "garbage"})
    result = classify_cycle(
        source_file="a.py",
        source_content="import b",
        target_file="b.py",
        target_content="import a",
        raw_import="import b",
        llm_client=client,
    )
    assert result.classification == "unknown"


def test_cycle_classification_dataclass_fields():
    c = CycleClassification(
        classification="runtime_critical",
        confidence="high",
        reasoning="test",
        suggested_fix=None,
    )
    assert c.classification == "runtime_critical"
    assert c.to_dict()["classification"] == "runtime_critical"
