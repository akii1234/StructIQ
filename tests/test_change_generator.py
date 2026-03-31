from StructIQ.modernization.change_generator import (
    ChangeGenerator,
    _infer_split_target,
    _select_cycle_edge_to_break,
)


def test_infer_split_target() -> None:
    assert _infer_split_target("src/core/utils.py") == "src/core/utils_core.py"


def test_infer_split_target_no_extension() -> None:
    assert _infer_split_target("src/core/utils") == "src/core/utils_core.py"


def test_select_cycle_edge_prefers_low_centrality() -> None:
    src, tgt = _select_cycle_edge_to_break(
        ["a.py", "b.py", "c.py", "a.py"],
        centrality_by_file={"a.py": 0.1, "b.py": 0.9, "c.py": 0.3},
    )

    assert src == "a.py"
    assert tgt == "b.py"


def test_select_cycle_edge_avoids_entry_points() -> None:
    src, tgt = _select_cycle_edge_to_break(
        ["a.py", "b.py", "a.py"],
        entry_points={"a.py"},
    )

    assert src == "b.py"
    assert tgt == "a.py"


def test_select_cycle_edge_single_file() -> None:
    assert _select_cycle_edge_to_break(["file.py"]) == ("file.py", "file.py")


def test_select_cycle_edge_empty() -> None:
    assert _select_cycle_edge_to_break([]) == ("", "")


def test_change_generator_break_cycle() -> None:
    tasks_result = {
        "tasks": [
            {
                "type": "break_cycle",
                "target": ["a.py", "b.py", "c.py", "a.py"],
                "reason": "cycle",
                "why": "Break a circular dependency.",
                "impact_if_ignored": "The cycle remains.",
                "alternative": "Refactor shared logic.",
            }
        ]
    }

    result = ChangeGenerator().generate(tasks_result)

    assert len(result["changes"]) == 1
    assert result["changes"][0]["action"] == "break_dependency"


def test_change_generator_split_file() -> None:
    tasks_result = {
        "tasks": [
            {
                "type": "split_file",
                "target": ["src/god.py"],
                "reason": "god_file",
                "why": "Too many responsibilities.",
                "impact_if_ignored": "Harder to maintain.",
                "alternative": "Refactor later.",
            }
        ]
    }

    result = ChangeGenerator().generate(tasks_result)
    change = result["changes"][0]

    assert change["action"] == "split_file"
    assert change["from"] == "src/god.py"
    assert change["to"].endswith("_core.py")


def test_change_generator_reduce_coupling() -> None:
    tasks_result = {
        "tasks": [
            {
                "type": "reduce_coupling",
                "target": ["src/fat.py"],
                "reason": "high_coupling",
                "why": "Reduce shared dependencies.",
                "impact_if_ignored": "Coupling stays high.",
                "alternative": "Delay refactor.",
            }
        ]
    }

    result = ChangeGenerator().generate(tasks_result)
    change = result["changes"][0]

    assert change["action"] == "extract_utility"
    assert change["from"] == "src/fat.py"
    assert change["to"].endswith("utils.py")


def test_change_generator_extract_module() -> None:
    tasks_result = {
        "tasks": [
            {
                "type": "extract_module",
                "target": ["payments"],
                "reason": "weak_boundary",
                "why": "Strengthen boundaries.",
                "impact_if_ignored": "Module remains unclear.",
                "alternative": "Keep current structure.",
            }
        ]
    }

    result = ChangeGenerator().generate(tasks_result)
    change = result["changes"][0]

    assert change["action"] == "extract_module"
    assert change["to"] == "payments_extracted"


def test_change_generator_empty_tasks() -> None:
    assert ChangeGenerator().generate({"tasks": []}) == {"changes": []}


def test_change_generator_invalid_input() -> None:
    assert ChangeGenerator().generate(["not", "a", "dict"]) == {"changes": []}
