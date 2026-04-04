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


def test_planner_uses_enriched_why_when_present():
    """If anti-pattern has enriched_why, planner must use it instead of template."""
    from StructIQ.modernization.planner import ModernizationPlanner
    insights = {
        "anti_patterns": [{
            "type": "high_coupling",
            "file": "session_manager.py",
            "severity": "high",
            "afferent_coupling": 7,
            "efferent_coupling": 0,
            "enriched_why": "Seven modules depend on session_manager.py, making any interface change a cascade.",
            "enriched_impact": "Rotating session storage requires synchronized changes across 7 files.",
        }]
    }
    result = ModernizationPlanner().plan(insights)
    tasks = result["tasks"]
    assert tasks, "Expected at least one task"
    task = tasks[0]
    assert task["why"] == "Seven modules depend on session_manager.py, making any interface change a cascade."
    assert task["impact_if_ignored"] == "Rotating session storage requires synchronized changes across 7 files."


def test_planner_falls_back_to_template_without_enriched_fields():
    """Without enriched fields, planner still generates template-based text."""
    from StructIQ.modernization.planner import ModernizationPlanner
    insights = {
        "anti_patterns": [{
            "type": "high_coupling",
            "file": "session_manager.py",
            "severity": "high",
            "afferent_coupling": 7,
            "efferent_coupling": 0,
        }]
    }
    result = ModernizationPlanner().plan(insights)
    tasks = result["tasks"]
    assert tasks
    assert "session_manager.py" in tasks[0]["why"]
    assert "7" in tasks[0]["impact_if_ignored"]
