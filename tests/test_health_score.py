import pytest
from StructIQ.reporting.health_score import compute_health_score, _score_to_grade

_CLEAN_DEP = {"cycles": [], "coupling_scores": [{"file": "a.py", "instability": 0.4}]}
_CLEAN_ARCH = {"anti_patterns": []}
_10_FILES = {"files": [f"f{i}.py" for i in range(10)]}


def test_perfect_score():
    r = compute_health_score(_CLEAN_DEP, _CLEAN_ARCH, _10_FILES)
    assert r["score"] == 100
    assert r["grade"] == "A"


def test_cycle_penalty():
    dep = {"cycles": [["a.py", "b.py"], ["c.py", "d.py"]], "coupling_scores": []}
    r = compute_health_score(dep, _CLEAN_ARCH, _10_FILES)
    assert r["components"]["cycle_penalty"] == 10
    assert r["score"] == 90


def test_god_file_penalty():
    arch = {"anti_patterns": [{"type": "god_file", "file": "big.py"}]}
    r = compute_health_score(_CLEAN_DEP, arch, _10_FILES)
    assert r["components"]["god_file_penalty"] == 8
    assert r["score"] == 92


def test_score_floored_at_zero():
    dep = {"cycles": [["a.py", "b.py"]] * 20, "coupling_scores": [{"file": f"f{i}.py", "instability": 0.9} for i in range(10)]}
    arch = {"anti_patterns": [{"type": "god_file"}] * 5 + [{"type": "weak_boundary"}] * 5}
    r = compute_health_score(dep, arch, _10_FILES)
    assert r["score"] == 0


def test_grade_boundaries():
    assert _score_to_grade(100) == "A"
    assert _score_to_grade(80) == "A"
    assert _score_to_grade(79) == "B"
    assert _score_to_grade(65) == "B"
    assert _score_to_grade(64) == "C"
    assert _score_to_grade(50) == "C"
    assert _score_to_grade(49) == "D"
    assert _score_to_grade(35) == "D"
    assert _score_to_grade(34) == "F"
    assert _score_to_grade(0) == "F"


def test_required_output_keys():
    r = compute_health_score(_CLEAN_DEP, _CLEAN_ARCH, _10_FILES)
    assert "score" in r and "grade" in r and "components" in r
    for k in ["cycle_penalty", "coupling_penalty", "god_file_penalty", "weak_boundary_penalty"]:
        assert k in r["components"]
