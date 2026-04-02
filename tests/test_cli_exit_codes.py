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


from unittest.mock import patch


def test_main_exits_1_when_action_required(tmp_path):
    """main() must sys.exit(1) when plan decision is action_required."""
    import json as _json
    out = tmp_path / "output.json"
    out.write_text("{}")
    (tmp_path / "modernization_plan.json").write_text(
        _json.dumps({"decision": "action_required"})
    )
    with patch("StructIQ.main.run_cli_sync"), \
         patch("sys.argv", ["structiq", str(tmp_path / "some_dir"), "--output", str(out)]):
        with pytest.raises(SystemExit) as exc_info:
            from StructIQ.main import main
            main()
        assert exc_info.value.code == 1


def test_main_does_not_exit_when_no_action(tmp_path):
    """main() must not sys.exit when plan decision is no_action_required."""
    import json as _json
    out = tmp_path / "output.json"
    out.write_text("{}")
    (tmp_path / "modernization_plan.json").write_text(
        _json.dumps({"decision": "no_action_required"})
    )
    with patch("StructIQ.main.run_cli_sync"), \
         patch("sys.argv", ["structiq", str(tmp_path / "some_dir"), "--output", str(out)]):
        from StructIQ.main import main
        main()  # must not raise SystemExit
