# tests/test_comparator.py
import pytest
from StructIQ.reporting.comparator import compare_runs, _delta_direction


def _make_run_data(
    cycles=0,
    god_files=0,
    weak_boundaries=0,
    high_coupling_files=0,
    total_files=10,
    health_score=100,
):
    return {
        "health": {"score": health_score, "grade": "A", "components": {}},
        "dep_analysis": {
            "cycles": [{"files": ["a.py", "b.py"]}] * cycles,
            "coupling_scores": [
                {"file": f"f{i}.py", "instability": 0.9 if i < high_coupling_files else 0.2}
                for i in range(total_files)
            ],
        },
        "arch_insights": {
            "anti_patterns": (
                [{"type": "god_file"}] * god_files +
                [{"type": "weak_boundary"}] * weak_boundaries
            )
        },
        "phase1": {"files": [f"f{i}.py" for i in range(total_files)]},
    }


def test_compare_identical_runs():
    run_a = _make_run_data(cycles=2, god_files=1, health_score=75)
    run_b = _make_run_data(cycles=2, god_files=1, health_score=75)
    result = compare_runs(run_a, run_b)
    assert result["health_score"]["delta"] == 0
    assert result["health_score"]["direction"] == "unchanged"
    assert result["cycles"]["delta"] == 0


def test_compare_improvement():
    run_a = _make_run_data(cycles=3, god_files=2, health_score=42)
    run_b = _make_run_data(cycles=1, god_files=1, health_score=67)
    result = compare_runs(run_a, run_b)
    assert result["health_score"]["delta"] == 25
    assert result["health_score"]["direction"] == "improved"
    assert result["cycles"]["delta"] == -2
    assert result["cycles"]["direction"] == "improved"
    assert result["god_files"]["delta"] == -1
    assert result["god_files"]["direction"] == "improved"


def test_compare_regression():
    run_a = _make_run_data(cycles=1, health_score=80)
    run_b = _make_run_data(cycles=4, health_score=55)
    result = compare_runs(run_a, run_b)
    assert result["health_score"]["direction"] == "regressed"
    assert result["cycles"]["direction"] == "regressed"


def test_delta_direction_for_counts():
    # For counts (cycles, god files), lower is better
    assert _delta_direction(-2, lower_is_better=True) == "improved"
    assert _delta_direction(2, lower_is_better=True) == "regressed"
    assert _delta_direction(0, lower_is_better=True) == "unchanged"


def test_delta_direction_for_score():
    # For health score, higher is better
    assert _delta_direction(10, lower_is_better=False) == "improved"
    assert _delta_direction(-5, lower_is_better=False) == "regressed"
    assert _delta_direction(0, lower_is_better=False) == "unchanged"


def test_compare_result_has_required_keys():
    run_a = _make_run_data()
    result = compare_runs(run_a, run_a)
    for key in ["health_score", "cycles", "god_files", "weak_boundaries", "high_coupling_files"]:
        assert key in result, f"Missing key: {key}"
        assert "run_a" in result[key]
        assert "run_b" in result[key]
        assert "delta" in result[key]
        assert "direction" in result[key]
