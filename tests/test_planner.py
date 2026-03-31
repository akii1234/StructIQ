from StructIQ.modernization.planner import ModernizationPlanner


def test_plan_empty_insights() -> None:
    assert ModernizationPlanner().plan({}) == {"tasks": [], "dominated_tasks": []}


def test_plan_no_anti_patterns() -> None:
    result = ModernizationPlanner().plan({"anti_patterns": []})

    assert result == {"tasks": [], "dominated_tasks": []}


def test_plan_single_cycle() -> None:
    insights = {
        "anti_patterns": [
            {"type": "cycle", "severity": "high", "files": ["a.py", "b.py"]}
        ]
    }

    result = ModernizationPlanner().plan(insights)

    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["type"] == "break_cycle"


def test_plan_single_god_file() -> None:
    insights = {
        "anti_patterns": [{"type": "god_file", "severity": "high", "file": "big.py"}]
    }

    result = ModernizationPlanner().plan(insights)

    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["type"] == "split_file"


def test_plan_task_has_required_fields() -> None:
    insights = {
        "anti_patterns": [
            {"type": "cycle", "severity": "high", "files": ["a.py", "b.py"]}
        ]
    }

    task = ModernizationPlanner().plan(insights)["tasks"][0]
    required = {
        "type",
        "target",
        "priority",
        "confidence",
        "why",
        "impact_if_ignored",
        "alternative",
        "selected_strategy",
    }

    assert required.issubset(task.keys())


def test_plan_dominance_removes_reduce_coupling() -> None:
    insights = {
        "anti_patterns": [
            {"type": "god_file", "severity": "high", "file": "big.py"},
            {"type": "high_coupling", "severity": "high", "file": "big.py"},
        ]
    }

    result = ModernizationPlanner().plan(insights)

    assert all(task["type"] != "reduce_coupling" for task in result["tasks"])
    assert any(task["type"] == "reduce_coupling" for task in result["dominated_tasks"])


def test_plan_high_severity_gets_high_priority() -> None:
    insights = {
        "anti_patterns": [
            {"type": "cycle", "severity": "high", "files": ["a.py", "b.py"]}
        ]
    }

    task = ModernizationPlanner().plan(insights)["tasks"][0]

    assert task["priority"] == "high"


def test_plan_confidence_is_float() -> None:
    insights = {
        "anti_patterns": [
            {"type": "cycle", "severity": "high", "files": ["a.py", "b.py"]}
        ]
    }

    task = ModernizationPlanner().plan(insights)["tasks"][0]

    assert isinstance(task["confidence"], float)
    assert 0.0 <= task["confidence"] <= 1.0
