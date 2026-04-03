"""Run-over-run comparison for StructIQ analysis outputs.

Pure function — no I/O, no LLM, no side effects.
Inputs: two dicts each containing health, dep_analysis, arch_insights, phase1.
Output: delta dict per metric.
"""

from __future__ import annotations


def _delta_direction(delta: int | float, lower_is_better: bool) -> str:
    if delta == 0:
        return "unchanged"
    if lower_is_better:
        return "improved" if delta < 0 else "regressed"
    return "improved" if delta > 0 else "regressed"


def _count_cycles(dep_analysis: dict) -> int:
    return len(dep_analysis.get("cycles") or [])


def _count_god_files(arch_insights: dict) -> int:
    return sum(
        1 for p in (arch_insights.get("anti_patterns") or [])
        if isinstance(p, dict) and p.get("type") == "god_file"
    )


def _count_weak_boundaries(arch_insights: dict) -> int:
    return sum(
        1 for p in (arch_insights.get("anti_patterns") or [])
        if isinstance(p, dict) and p.get("type") == "weak_boundary"
    )


def _count_high_coupling(dep_analysis: dict) -> int:
    return sum(
        1 for c in (dep_analysis.get("coupling_scores") or [])
        if isinstance(c, dict) and float(c.get("instability") or 0) > 0.7
    )


def _metric(val_a: int | float, val_b: int | float, lower_is_better: bool) -> dict:
    delta = val_b - val_a
    return {
        "run_a": val_a,
        "run_b": val_b,
        "delta": delta,
        "direction": _delta_direction(delta, lower_is_better=lower_is_better),
    }


def compare_runs(run_a_data: dict, run_b_data: dict) -> dict:
    """Compare two run data dicts. Each must have keys: health, dep_analysis, arch_insights, phase1."""
    score_a = int((run_a_data.get("health") or {}).get("score") or 0)
    score_b = int((run_b_data.get("health") or {}).get("score") or 0)

    dep_a = run_a_data.get("dep_analysis") or {}
    dep_b = run_b_data.get("dep_analysis") or {}
    arch_a = run_a_data.get("arch_insights") or {}
    arch_b = run_b_data.get("arch_insights") or {}

    return {
        "health_score": _metric(score_a, score_b, lower_is_better=False),
        "cycles": _metric(_count_cycles(dep_a), _count_cycles(dep_b), lower_is_better=True),
        "god_files": _metric(_count_god_files(arch_a), _count_god_files(arch_b), lower_is_better=True),
        "weak_boundaries": _metric(_count_weak_boundaries(arch_a), _count_weak_boundaries(arch_b), lower_is_better=True),
        "high_coupling_files": _metric(_count_high_coupling(dep_a), _count_high_coupling(dep_b), lower_is_better=True),
    }
