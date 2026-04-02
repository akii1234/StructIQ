import json
from pathlib import Path
import pytest
from StructIQ.main import _read_plan_decision


def test_read_plan_decision_action_required(tmp_path):
    (tmp_path / "modernization_plan.json").write_text(json.dumps({"decision": "action_required"}))
    assert _read_plan_decision(str(tmp_path / "output.json")) == "action_required"

def test_read_plan_decision_no_action(tmp_path):
    (tmp_path / "modernization_plan.json").write_text(json.dumps({"decision": "no_action_required"}))
    assert _read_plan_decision(str(tmp_path / "output.json")) == "no_action_required"

def test_read_plan_decision_missing_file(tmp_path):
    assert _read_plan_decision(str(tmp_path / "output.json")) is None

def test_read_plan_decision_invalid_json(tmp_path):
    (tmp_path / "modernization_plan.json").write_text("bad{{json")
    assert _read_plan_decision(str(tmp_path / "output.json")) is None
