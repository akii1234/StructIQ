"""Convert architecture anti-patterns into actionable modernization tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

_TASK_TYPE_MAP = {
    "cycle": "break_cycle",
    "god_file": "split_file",
    "high_coupling": "reduce_coupling",
    "weak_boundary": "extract_module",
}

_SEVERITY_WEIGHT = {
    "high": 1.0,
    "medium": 0.7,
    "low": 0.4,
}

_PATTERN_WEIGHT = {
    "cycle": 1.0,
    "god_file": 0.9,
    "high_coupling": 0.7,
    "weak_boundary": 0.6,
}

_IMPACT_WEIGHT = {
    "cycle": 1.0,
    "god_file": 0.85,
    "high_coupling": 0.7,
    "weak_boundary": 0.65,
}

_EXPLAINABILITY_MAP = {
    "break_cycle": {
        "why": "Circular dependency detected between modules",
        "impact_if_ignored": "Increases coupling and makes system harder to maintain",
        "alternative": "Introduce abstraction layer or refactor shared logic",
    },
    "reduce_coupling": {
        "why": "Module has excessive external dependencies",
        "impact_if_ignored": "Reduced modularity and increased change impact",
        "alternative": "Refactor into smaller cohesive units",
    },
    "extract_module": {
        "why": "Module has high external interaction compared to internal cohesion",
        "impact_if_ignored": "Unclear module responsibilities",
        "alternative": "Reorganize responsibilities into clearer boundaries",
    },
    "split_file": {
        "why": "File contains too many responsibilities",
        "impact_if_ignored": "Difficult to maintain and test",
        "alternative": "Split into smaller focused components",
    },
}

STRATEGY_MAP = {
    "cycle": [
        {
            "name": "break_dependency",
            "impact": "low",
            "complexity": "low",
            "scope": "module",
        },
        {
            "name": "introduce_abstraction",
            "impact": "medium",
            "complexity": "medium",
            "scope": "module",
        },
        {
            "name": "invert_dependency_direction",
            "impact": "high",
            "complexity": "high",
            "scope": "system",
        },
    ],
    "god_file": [
        {
            "name": "split_file",
            "impact": "low",
            "complexity": "low",
            "scope": "module",
        },
        {
            "name": "extract_high_coupling_logic",
            "impact": "medium",
            "complexity": "medium",
            "scope": "module",
        },
        {
            "name": "feature_layer_reorganization",
            "impact": "high",
            "complexity": "high",
            "scope": "system",
        },
    ],
    "high_coupling": [
        {
            "name": "reduce_coupling",
            "impact": "low",
            "complexity": "low",
            "scope": "module",
        },
        {
            "name": "extract_interface",
            "impact": "medium",
            "complexity": "medium",
            "scope": "module",
        },
        {
            "name": "reorganize_into_layers",
            "impact": "high",
            "complexity": "high",
            "scope": "system",
        },
    ],
    "weak_boundary": [
        {
            "name": "extract_module",
            "impact": "low",
            "complexity": "low",
            "scope": "module",
        },
        {
            "name": "define_stable_public_interface",
            "impact": "medium",
            "complexity": "low",
            "scope": "module",
        },
        {
            "name": "enforce_boundary_contract",
            "impact": "high",
            "complexity": "medium",
            "scope": "system",
        },
    ],
}

_IMPACT_SCORE_MAP = {"low": 1, "medium": 2, "high": 3}
_COMPLEXITY_SCORE_MAP = {"low": 1, "medium": 2, "high": 3}
_SCOPE_SCORE_MAP = {"local": 1, "module": 2, "system": 3}


def evaluate_strategies(task: dict, strategies: list[dict], context: dict) -> dict:
    if not isinstance(strategies, list) or not strategies:
        return {
            "selected": "existing_solution",
            "score": 0,
            "alternatives": [],
            "selected_reason": "No predefined strategies; using existing single-solution mapping",
        }

    centrality = context.get("centrality", 0.0)
    try:
        centrality = float(centrality)
    except (TypeError, ValueError):
        centrality = 0.0
    centrality_penalty = 1 if centrality > 0.7 else 0

    scored: list[tuple[int, str, dict]] = []
    for strat in strategies:
        if not isinstance(strat, dict):
            continue
        name = str(strat.get("name", "")).strip()
        impact = str(strat.get("impact", "low")).lower()
        complexity = str(strat.get("complexity", "low")).lower()
        scope = str(strat.get("scope", "module")).lower()

        impact_score = _IMPACT_SCORE_MAP.get(impact, 1)
        complexity_score = _COMPLEXITY_SCORE_MAP.get(complexity, 1)
        scope_score = _SCOPE_SCORE_MAP.get(scope, 2)
        score = impact_score + complexity_score + scope_score + centrality_penalty

        scored.append((score, name, strat))

    if not scored:
        return {
            "selected": "existing_solution",
            "score": 0,
            "alternatives": [],
            "selected_reason": "No predefined strategies evaluated; using existing single-solution mapping",
        }

    scored_sorted = sorted(scored, key=lambda x: (x[0], x[1]))
    selected_score, selected_name, selected_strat = scored_sorted[0]

    def _reason_for_rejection(s: dict, best: dict) -> str:
        s_impact = _IMPACT_SCORE_MAP.get(str(s.get("impact", "low")).lower(), 1)
        s_complexity = _COMPLEXITY_SCORE_MAP.get(
            str(s.get("complexity", "low")).lower(), 1
        )
        s_scope = _SCOPE_SCORE_MAP.get(str(s.get("scope", "module")).lower(), 2)

        b_impact = _IMPACT_SCORE_MAP.get(str(best.get("impact", "low")).lower(), 1)
        b_complexity = _COMPLEXITY_SCORE_MAP.get(
            str(best.get("complexity", "low")).lower(), 1
        )
        b_scope = _SCOPE_SCORE_MAP.get(str(best.get("scope", "module")).lower(), 2)

        if s_complexity > b_complexity:
            return "higher complexity"
        if s_impact > b_impact:
            return "higher impact"
        if s_scope > b_scope:
            return "broader scope"
        return "higher overall score"

    alternatives: list[dict] = []
    for score, name, strat in scored_sorted[1:]:
        alternatives.append(
            {
                "strategy": name,
                "score": score,
                "reason": _reason_for_rejection(strat, selected_strat),
            }
        )

    return {
        "selected": selected_name,
        "score": selected_score,
        "alternatives": alternatives,
        "selected_reason": "Lowest score based on impact, complexity, scope, and centrality penalty",
    }


class ModernizationPlanner:
    """Derive modernization tasks from Phase 3 anti-patterns."""

    def plan(self, insights: dict) -> dict:
        if not isinstance(insights, dict):
            return {"tasks": [], "dominated_tasks": []}

        anti_patterns = insights.get("anti_patterns") or []
        tasks: List[Dict[str, Any]] = []
        entry_points = insights.get("entry_points") or []
        entry_points_set = (
            {str(ep) for ep in entry_points if ep} if isinstance(entry_points, list) else set()
        )

        for ap in anti_patterns:
            if not isinstance(ap, dict):
                continue
            ap_type = ap.get("type", "")
            task_type = _TASK_TYPE_MAP.get(ap_type)
            if not task_type:
                continue

            # Resolve target — cycles use files list, others use file or module.
            if ap_type == "cycle":
                target = [str(f) for f in (ap.get("files") or []) if f]
            elif ap_type == "weak_boundary":
                module = ap.get("module", "")
                target = [str(module)] if module else []
            else:
                file_path = ap.get("file", "")
                target = [str(file_path)] if file_path else []

            if not target:
                continue

            severity = str(ap.get("severity", "")).lower()
            severity_weight = _SEVERITY_WEIGHT.get(severity, 0.4)
            if ap_type in {"god_file", "high_coupling"}:
                try:
                    afferent = float(ap.get("afferent_coupling", 0) or 0)
                except (TypeError, ValueError):
                    afferent = 0.0
                try:
                    efferent = float(ap.get("efferent_coupling", 0) or 0)
                except (TypeError, ValueError):
                    efferent = 0.0
                total_coupling = afferent + efferent
                centrality = min(total_coupling / 20.0, 1.0)
            elif ap_type == "cycle":
                files = ap.get("files") or []
                cycle_len = len(files) if isinstance(files, list) else 0
                centrality = min(cycle_len / 5.0, 1.0)
            elif ap_type == "weak_boundary":
                try:
                    boundary_score = float(ap.get("score", 0) or 0)
                except (TypeError, ValueError):
                    boundary_score = 0.0
                centrality = min(boundary_score / 3.0, 1.0)
            else:
                centrality = 0.0
            centrality = max(0.0, min(1.0, centrality))
            pattern_weight = _PATTERN_WEIGHT.get(ap_type, 0.4)
            confidence = round(
                (severity_weight * 0.4) + (centrality * 0.4) + (pattern_weight * 0.2),
                2,
            )
            impact_estimate = _IMPACT_WEIGHT.get(ap_type, 0.5)
            priority_score = round(
                (severity_weight * 0.5) + (centrality * 0.3) + (impact_estimate * 0.2),
                2,
            )
            if priority_score > 0.75:
                priority = "high"
            elif priority_score > 0.5:
                priority = "medium"
            else:
                priority = "low"
            base_template = _EXPLAINABILITY_MAP.get(
                task_type, {"why": "", "impact_if_ignored": "", "alternative": ""}
            )
            if task_type == "reduce_coupling" and target:
                file_name = Path(target[0]).name
                template = {
                    "why": (
                        f"`{file_name}` has {int(afferent)} incoming and "
                        f"{int(efferent)} outgoing dependencies"
                    ),
                    "impact_if_ignored": (
                        f"Modifications to `{file_name}` affect {int(afferent)} "
                        f"dependent file(s), amplifying regression risk"
                    ),
                    "alternative": base_template["alternative"],
                }
            else:
                template = base_template

            # Prefer LLM-enriched text over templates when present.
            if ap.get("enriched_why"):
                template = dict(template)
                template["why"] = str(ap["enriched_why"])
            if ap.get("enriched_impact"):
                template = dict(template)
                template["impact_if_ignored"] = str(ap["enriched_impact"])

            strategies = STRATEGY_MAP.get(ap_type) or []
            eval_ctx = {
                "centrality": centrality,
                "affected_files": target,
                "entry_points": entry_points_set,
            }
            eval_result = evaluate_strategies(
                task={
                    "type": task_type,
                    "target": target,
                    "priority": priority,
                    "reason": ap_type,
                },
                strategies=strategies,
                context=eval_ctx,
            )
            selected_strategy = str(eval_result.get("selected", "")).strip()
            strategy_score = eval_result.get("score", 0)
            strategy_reason = str(eval_result.get("selected_reason", "")).strip()
            strategy_alternatives = (
                eval_result.get("alternatives") if isinstance(eval_result.get("alternatives"), list) else []
            )

            tasks.append(
                {
                    "type": task_type,
                    "target": target,
                    "priority": priority,
                    "priority_score": priority_score,
                    "reason": ap_type,
                    "severity": ap.get("severity", ""),
                    "confidence": confidence,
                    "confidence_factors": {
                        "severity_weight": round(severity_weight, 2),
                        "centrality": round(centrality, 2),
                        "pattern_weight": round(pattern_weight, 2),
                    },
                    "why": template["why"],
                    "impact_if_ignored": template["impact_if_ignored"],
                    "alternative": template["alternative"],
                    "selected_strategy": selected_strategy,
                    "strategy_score": strategy_score,
                    "strategy_reason": strategy_reason,
                    "alternatives": strategy_alternatives,
                    "line_number": (ap.get("closing_edge") or {}).get("line_number"),
                    "afferent_coupling": ap.get("afferent_coupling"),
                    "efferent_coupling": ap.get("efferent_coupling"),
                }
            )

        # Deterministic ordering: higher priority_score, then higher confidence.
        tasks_sorted = sorted(
            tasks,
            key=lambda t: (
                -float(t.get("priority_score", 0.0)),
                -float(t.get("confidence", 0.0)),
                t["type"],
                t["target"][0] if t["target"] else "",
            ),
        )
        dominating_files: Dict[str, str] = {}
        for task in tasks_sorted:
            if not isinstance(task, dict):
                continue
            t_type = task.get("type", "")
            target = task.get("target") or []
            if t_type in {"break_cycle", "split_file"} and isinstance(target, list):
                for file_path in target:
                    file_key = str(file_path)
                    if file_key and file_key not in dominating_files:
                        dominating_files[file_key] = f"{t_type}:{file_key}"

        dominating_modules: Dict[str, str] = {}
        for task in tasks_sorted:
            if not isinstance(task, dict):
                continue
            t_type = task.get("type", "")
            target = task.get("target") or []
            if t_type == "extract_module" and isinstance(target, list) and target:
                module_name = str(target[0])
                if module_name and module_name not in dominating_modules:
                    dominating_modules[module_name] = f"{t_type}:{module_name}"

        tasks_sorted_filtered: List[Dict[str, Any]] = []
        dominated_tasks: List[Dict[str, Any]] = []
        for task in tasks_sorted:
            if not isinstance(task, dict):
                continue
            t_type = task.get("type", "")
            target = task.get("target") or []
            target0 = str(target[0]) if isinstance(target, list) and target else ""
            if t_type != "reduce_coupling" or not target0:
                tasks_sorted_filtered.append(task)
                continue

            dominated_by = dominating_files.get(target0, "")
            if not dominated_by:
                parts = set(Path(target0).parts)
                for module_name, marker in dominating_modules.items():
                    if module_name in parts:
                        dominated_by = marker
                        break

            if dominated_by:
                dominated = dict(task)
                dominated["dominated_by"] = dominated_by
                dominated_tasks.append(dominated)
            else:
                tasks_sorted_filtered.append(task)

        return {"tasks": tasks_sorted_filtered, "dominated_tasks": dominated_tasks}
