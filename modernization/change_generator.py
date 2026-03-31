"""Generate intent-level structural changes from modernization tasks.

No code generation. Output describes WHAT to change, not HOW to write code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def _infer_split_target(file_path: str) -> str:
    """Suggest a sibling file name for a god-file split."""
    p = Path(file_path)
    stem = p.stem
    suffix = p.suffix or ".py"
    return str(p.parent / f"{stem}_core{suffix}")


def _select_cycle_edge_to_break(
    target_files: list[str],
    centrality_by_file: dict[str, float] | None = None,
    entry_points: set[str] | None = None,
    fanout_by_file: dict[str, int] | None = None,
) -> tuple[str, str]:
    """
    Choose the safest edge to break in a cycle.

    Candidates are consecutive edges derived from the detected cycle file path.
    Scoring (lower is safer):
    - Prefer edges where the source is not an entry point.
    - Prefer edges from the lowest centrality source.
    - Prefer edges from the lowest fan-out source.
    """
    if not target_files:
        return "", ""
    if len(target_files) == 1:
        return target_files[0], target_files[0]

    centrality_by_file = centrality_by_file if isinstance(centrality_by_file, dict) else {}
    entry_points = entry_points if isinstance(entry_points, set) else set()
    fanout_by_file = fanout_by_file if isinstance(fanout_by_file, dict) else {}

    # Iterate cycle edges as consecutive pairs.
    candidate_edges: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for i in range(len(target_files) - 1):
        src = str(target_files[i])
        tgt = str(target_files[i + 1])
        edge = (src, tgt)
        if edge in seen:
            continue
        seen.add(edge)
        candidate_edges.append(edge)

    # Local fan-out proxy from the candidate edges if not provided.
    local_fanout: dict[str, int] = {}
    for src, _ in candidate_edges:
        local_fanout[src] = local_fanout.get(src, 0) + 1

    def _centrality(src: str) -> float:
        raw = centrality_by_file.get(src, 0.5)
        try:
            c = float(raw)
        except (TypeError, ValueError):
            c = 0.5
        return max(0.0, min(1.0, c))

    def _fanout(src: str) -> int:
        if src in fanout_by_file:
            try:
                return int(fanout_by_file.get(src, 0) or 0)
            except (TypeError, ValueError):
                return 0
        return int(local_fanout.get(src, 0))

    scored: list[tuple[tuple[int, float, int, str, str], tuple[str, str]]] = []
    for src, tgt in candidate_edges:
        entry_penalty = 1 if src in entry_points else 0
        centrality_score = _centrality(src)
        fanout_score = _fanout(src)
        score_key = (entry_penalty, centrality_score, fanout_score, src, tgt)
        scored.append((score_key, (src, tgt)))

    scored_sorted = sorted(scored, key=lambda x: x[0])
    _, (selected_source, selected_target) = scored_sorted[0]
    return selected_source, selected_target


class ChangeGenerator:
    """Translate modernization tasks into concrete structural change intents."""

    def generate(self, tasks_result: dict) -> dict:
        if not isinstance(tasks_result, dict):
            return {"changes": []}

        tasks = tasks_result.get("tasks") or []
        changes: List[Dict[str, Any]] = []

        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_type = task.get("type", "")
            target = task.get("target") or []
            reason = task.get("reason", "")
            why = str(task.get("why", "")).strip()
            impact_if_ignored = str(task.get("impact_if_ignored", "")).strip()
            alternative = str(task.get("alternative", "")).strip()

            if task_type == "break_cycle" and len(target) >= 2:
                centrality_by_file = task.get("centrality_by_file")
                entry_points = task.get("entry_points")
                fanout_by_file = task.get("fanout_by_file")

                entry_points_set = (
                    set(entry_points) if isinstance(entry_points, list) else entry_points
                )
                src, tgt = _select_cycle_edge_to_break(
                    target_files=target,
                    centrality_by_file=centrality_by_file,
                    entry_points=entry_points_set,
                    fanout_by_file=fanout_by_file,
                )
                changes.append(
                    {
                        "action": "break_dependency",
                        "from": src,
                        "to": tgt,
                        "why": why,
                        "impact_if_ignored": impact_if_ignored,
                        "alternative": alternative,
                    }
                )

            elif task_type == "split_file" and target:
                file_path = target[0]
                changes.append(
                    {
                        "action": "split_file",
                        "from": file_path,
                        "to": _infer_split_target(file_path),
                        "reason": f"Reduce centralised responsibilities: {reason}",
                        "task_type": task_type,
                        "why": why,
                        "impact_if_ignored": impact_if_ignored,
                        "alternative": alternative,
                    }
                )

            elif task_type == "reduce_coupling" and target:
                file_path = target[0]
                p = Path(file_path)
                utility_target = str(p.parent / "utils.py")
                changes.append(
                    {
                        "action": "extract_utility",
                        "from": file_path,
                        "to": utility_target,
                        "reason": f"Extract shared dependencies to reduce coupling: {reason}",
                        "task_type": task_type,
                        "why": why,
                        "impact_if_ignored": impact_if_ignored,
                        "alternative": alternative,
                    }
                )

            elif task_type == "extract_module" and target:
                module_name = target[0]
                changes.append(
                    {
                        "action": "extract_module",
                        "from": module_name,
                        "to": f"{module_name}_extracted",
                        "reason": f"Strengthen module boundary: {reason}",
                        "task_type": task_type,
                        "why": why,
                        "impact_if_ignored": impact_if_ignored,
                        "alternative": alternative,
                    }
                )

        return {"changes": changes}
