"""Deterministic Structural Health Score. No LLM. No I/O. Pure function."""

from __future__ import annotations


def compute_health_score(
    dependency_analysis: dict,
    architecture_insights: dict,
    phase1_output: dict,
) -> dict:
    total_files = max(len(phase1_output.get("files") or []), 1)

    cycles = dependency_analysis.get("cycles") or []
    cycle_penalty = min(30, len(cycles) * 5)

    coupling_scores = dependency_analysis.get("coupling_scores") or []
    high_instability = sum(
        1 for c in coupling_scores
        if isinstance(c, dict) and float(c.get("instability") or 0) > 0.7
    )
    coupling_penalty = min(25, round((high_instability / total_files) * 100 * 0.5))

    anti_patterns = architecture_insights.get("anti_patterns") or []
    god_files = sum(1 for p in anti_patterns if isinstance(p, dict) and p.get("type") == "god_file")
    god_file_penalty = min(25, god_files * 8)

    weak_boundaries = sum(1 for p in anti_patterns if isinstance(p, dict) and p.get("type") == "weak_boundary")
    weak_boundary_penalty = min(20, weak_boundaries * 5)

    score = max(0, min(100, round(100 - cycle_penalty - coupling_penalty - god_file_penalty - weak_boundary_penalty)))

    return {
        "score": score,
        "grade": _score_to_grade(score),
        "components": {
            "cycle_penalty": cycle_penalty,
            "coupling_penalty": coupling_penalty,
            "god_file_penalty": god_file_penalty,
            "weak_boundary_penalty": weak_boundary_penalty,
        },
    }


def _score_to_grade(score: int) -> str:
    if score >= 80: return "A"
    if score >= 65: return "B"
    if score >= 50: return "C"
    if score >= 35: return "D"
    return "F"
