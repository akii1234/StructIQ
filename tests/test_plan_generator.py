from StructIQ.modernization.plan_generator import (
    PlanGenerator,
    _find_task_explainability,
    _render_steps,
)


def test_render_steps_break_dependency_direct() -> None:
    steps = _render_steps("break_dependency", "a.py", "b.py", use_staged=False)

    assert len(steps) == 5
    assert all(isinstance(step, str) and step.strip() for step in steps)


def test_render_steps_break_dependency_staged() -> None:
    direct = _render_steps("break_dependency", "a.py", "b.py", use_staged=False)
    staged = _render_steps("break_dependency", "a.py", "b.py", use_staged=True)

    assert len(staged) == 5
    assert staged != direct


def test_render_steps_unknown_action() -> None:
    steps = _render_steps("unknown_action", "a.py", "b.py", use_staged=False)

    assert len(steps) == 2
    assert all(isinstance(step, str) and step.strip() for step in steps)


def test_render_steps_substitutes_targets() -> None:
    steps = _render_steps("split_file", "src/big.py", "src/small.py", use_staged=False)

    assert any("src/big.py" in step for step in steps)
    assert any("src/small.py" in step for step in steps)


def test_find_explainability_match() -> None:
    tasks = [
        {
            "type": "break_cycle",
            "target": ["a.py"],
            "why": "Break the cycle.",
            "impact_if_ignored": "The cycle remains.",
            "alternative": "Refactor shared code.",
        }
    ]

    result = _find_task_explainability(tasks, "break_dependency", "a.py")

    assert result["why"]
    assert result["impact_if_ignored"]
    assert result["alternative"]


def test_find_explainability_no_match() -> None:
    result = _find_task_explainability([], "break_dependency", "a.py")

    assert set(result.keys()) == {"why", "impact_if_ignored", "alternative"}
    assert all("ERROR" in value for value in result.values())


def test_generate_no_llm_returns_plan() -> None:
    tasks_result = {
        "tasks": [
            {
                "type": "break_cycle",
                "target": ["a.py", "b.py"],
                "priority": "high",
                "reason": "cycle",
                "confidence": 0.8,
                "why": "cycle",
                "impact_if_ignored": "bad",
                "alternative": "refactor",
                "selected_strategy": "break_dependency",
            }
        ],
        "dominated_tasks": [],
    }
    changes_result = {
        "changes": [{"action": "break_dependency", "from": "a.py", "to": "b.py"}]
    }
    impact_result = {
        "impact": [
            {
                "action": "break_dependency",
                "from": "a.py",
                "to": "b.py",
                "affected_files": ["a.py"],
                "affected_count": 1,
                "risk": "low",
            }
        ]
    }

    result = PlanGenerator().generate(
        tasks_result, changes_result, impact_result, enable_llm=False
    )

    assert {"execution_plan", "plan_summary", "sequencing_notes", "plan_mode"}.issubset(
        result.keys()
    )


def test_generate_empty_inputs() -> None:
    result = PlanGenerator().generate({}, {}, {}, enable_llm=False)

    assert result["execution_plan"] == []


def test_generate_invalid_inputs() -> None:
    result = PlanGenerator().generate([], [], [], enable_llm=False)

    assert result == {
        "execution_plan": [],
        "plan_summary": "",
        "sequencing_notes": "",
        "plan_mode": "direct",
    }


def test_generate_orders_low_risk_first() -> None:
    tasks_result = {
        "tasks": [
            {
                "type": "break_cycle",
                "target": ["a.py", "b.py"],
                "priority": "high",
                "reason": "cycle",
                "confidence": 0.8,
                "why": "Break the cycle.",
                "impact_if_ignored": "bad",
                "alternative": "refactor",
                "selected_strategy": "break_dependency",
            },
            {
                "type": "split_file",
                "target": ["big.py"],
                "priority": "medium",
                "reason": "god_file",
                "confidence": 0.7,
                "why": "Split large file.",
                "impact_if_ignored": "hard to maintain",
                "alternative": "defer",
                "selected_strategy": "split_file",
            },
        ],
        "dominated_tasks": [],
    }
    changes_result = {
        "changes": [
            {"action": "break_dependency", "from": "a.py", "to": "b.py"},
            {"action": "split_file", "from": "big.py", "to": "small.py"},
        ]
    }
    impact_result = {
        "impact": [
            {
                "action": "break_dependency",
                "from": "a.py",
                "to": "b.py",
                "affected_files": ["a.py", "b.py"],
                "affected_count": 2,
                "risk": "high",
            },
            {
                "action": "split_file",
                "from": "big.py",
                "to": "small.py",
                "affected_files": ["big.py"],
                "affected_count": 1,
                "risk": "low",
            },
        ]
    }

    result = PlanGenerator().generate(
        tasks_result, changes_result, impact_result, enable_llm=False
    )
    headers = [line for line in result["execution_plan"] if line.startswith("[Change")]

    assert "split_file" in headers[0]
    assert "risk: low" in headers[0]
