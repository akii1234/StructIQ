"""Generate ordered, safe, reversible execution steps for each change."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from StructIQ.config import settings
from StructIQ.llm.client import OpenAIClient

_LOGGER = logging.getLogger(__name__)


_STEP_TEMPLATES: Dict[str, List[str]] = {
    "break_dependency": [
        "Identify the import of `{to}` inside `{from}` that creates the cycle.",
        "Introduce an intermediary abstraction or interface to decouple `{from}` from `{to}`.",
        "Update `{from}` to depend on the abstraction rather than `{to}` directly.",
        "Run dependency analysis to confirm the cycle is resolved.",
        "Validate existing tests pass before merging.",
    ],
    "split_file": [
        "Create new file `{to}` alongside `{from}`.",
        "Identify responsibilities in `{from}` that belong in `{to}` (high-coupling logic).",
        "Move identified code to `{to}`, keeping public interfaces stable.",
        "Update all imports across the codebase from `{from}` to `{to}` where applicable.",
        "Validate no regressions by running full test suite.",
    ],
    "extract_utility": [
        "Create `{to}` as a shared utility module.",
        "Move shared dependencies from `{from}` into `{to}`.",
        "Update `{from}` to import from `{to}` instead of duplicating logic.",
        "Check for other files that duplicate the same logic and update them too.",
        "Validate imports resolve correctly across all affected files.",
    ],
    "extract_module": [
        "Create new module directory for `{to}`.",
        "Identify files from `{from}` that have high external coupling.",
        "Move high-external-coupling files into `{to}`, updating import paths.",
        "Update all references to moved files throughout the codebase.",
        "Validate module boundaries hold and no new cycles are introduced.",
    ],
}

_STAGED_STEP_TEMPLATES: Dict[str, List[str]] = {
    "break_dependency": [
        "Introduce an abstraction interface between `{from}` and `{to}` without removing the existing import.",
        "Migrate `{from}` to use the abstraction — keep old import as a fallback during transition.",
        "Validate the abstraction layer works correctly in isolation.",
        "Remove the direct import of `{to}` from `{from}` once migration is confirmed stable.",
        "Run dependency analysis to confirm the cycle is resolved.",
    ],
    "split_file": [
        "Create `{to}` as an empty module with the intended public interface documented.",
        "Move one responsibility at a time from `{from}` to `{to}`, validating after each move.",
        "Update callers of moved logic incrementally — do not update all imports at once.",
        "Run integration tests after each batch of moves before proceeding.",
        "Remove migrated code from `{from}` once all callers are updated.",
    ],
    "extract_utility": [
        "Create `{to}` and move one shared dependency at a time — do not move everything at once.",
        "Update `{from}` to use `{to}` for the first moved dependency and validate.",
        "Repeat for each additional shared dependency, validating after each step.",
        "Audit other files for duplicated logic and migrate them to `{to}` incrementally.",
        "Validate all imports resolve correctly after full migration.",
    ],
    "extract_module": [
        "Create the `{to}` module directory with an empty public interface.",
        "Move the highest-coupling file first and update its references — validate before proceeding.",
        "Move remaining files one at a time, validating module boundaries after each.",
        "Update all external references to moved files throughout the codebase.",
        "Run full dependency analysis to confirm no new cycles were introduced.",
    ],
}


def _render_steps(
    action: str,
    from_target: str,
    to_target: str,
    use_staged: bool = False,
) -> List[str]:
    template_source = _STAGED_STEP_TEMPLATES if use_staged else _STEP_TEMPLATES
    templates = template_source.get(
        action,
        [
            f"Review `{from_target}` and apply `{action}` change.",
            "Validate the change does not introduce regressions.",
        ],
    )
    return [
        t.format(from_=from_target, **{"from": from_target, "to": to_target})
        for t in templates
    ]


def _find_task_explainability(tasks: list, action: str, from_target: str) -> dict:
    """Find explainability fields for a change from matching task data."""
    if not isinstance(tasks, list):
        return {"why": "", "impact_if_ignored": "", "alternative": ""}

    action_to_task = {
        "break_dependency": "break_cycle",
        "split_file": "split_file",
        "extract_utility": "reduce_coupling",
        "extract_module": "extract_module",
    }
    expected_task_type = action_to_task.get(action, "")

    for task in tasks:
        if not isinstance(task, dict):
            continue
        if task.get("type", "") != expected_task_type:
            continue
        target = task.get("target") or []
        if isinstance(target, list) and from_target and from_target not in target:
            # Keep scanning until a better-matching task is found.
            continue
        return {
            "why": str(task.get("why", "")).strip(),
            "impact_if_ignored": str(task.get("impact_if_ignored", "")).strip(),
            "alternative": str(task.get("alternative", "")).strip(),
        }

    _LOGGER.warning(
        "Explainability missing for action=%s from=%s", action, from_target
    )
    return {
        "why": "ERROR: explainability missing",
        "impact_if_ignored": "ERROR: explainability missing",
        "alternative": "ERROR: explainability missing",
    }


class PlanGenerator:
    """Produce a sequential, risk-ordered execution plan."""

    def __init__(self, llm_client: OpenAIClient | None = None) -> None:
        self._llm_client = llm_client

    def _get_client(self) -> OpenAIClient:
        if self._llm_client is None:
            self._llm_client = OpenAIClient()
        return self._llm_client

    def generate(
        self,
        tasks_result: dict,
        changes_result: dict,
        impact_result: dict,
        enable_llm: bool = True,
        context: dict | None = None,
    ) -> dict:
        if not all(
            isinstance(x, dict) for x in [tasks_result, changes_result, impact_result]
        ):
            return {
                "execution_plan": [],
                "plan_summary": "",
                "sequencing_notes": "",
                "plan_mode": "direct",
            }

        context = context or {}
        tasks = tasks_result.get("tasks") or []
        changes = changes_result.get("changes") or []
        impact_list = impact_result.get("impact") or []
        total_nodes = int(context.get("total_nodes", 0) or 0)
        max_affected = max(
            (imp.get("affected_count", 0) for imp in impact_list if isinstance(imp, dict)),
            default=0,
        )
        use_staged = total_nodes > 300 or max_affected > 30

        # Build impact lookup keyed by (action, from).
        impact_by_key: Dict[tuple[str, str], dict] = {}
        for imp in impact_list:
            if isinstance(imp, dict):
                key = (imp.get("action", ""), imp.get("from", ""))
                impact_by_key[key] = imp

        # Pair each change with its impact entry.
        paired: List[Dict[str, Any]] = []
        for change in changes:
            if not isinstance(change, dict):
                continue
            action = change.get("action", "")
            from_target = change.get("from", "")
            to_target = change.get("to", "")
            imp = impact_by_key.get((action, from_target), {})
            risk = imp.get("risk", "medium")
            affected_count = imp.get("affected_count", 0)
            explain = _find_task_explainability(tasks, action, from_target)
            paired.append(
                {
                    "action": action,
                    "from": from_target,
                    "to": to_target,
                    "risk": risk,
                    "affected_count": affected_count,
                    "why": explain["why"],
                    "impact_if_ignored": explain["impact_if_ignored"],
                    "alternative": explain["alternative"],
                }
            )

        # Order: low risk first, then medium, then high. Within same risk, fewer affected files first.
        risk_order = {"low": 0, "medium": 1, "high": 2}
        paired_sorted = sorted(
            paired,
            key=lambda x: (
                risk_order.get(x["risk"], 1),
                x["affected_count"],
                x["from"],
            ),
        )

        execution_plan: List[str] = []
        for idx, item in enumerate(paired_sorted, start=1):
            steps = _render_steps(
                item["action"], item["from"], item["to"], use_staged=use_staged
            )
            execution_plan.append(
                f"[Change {idx} — {item['action']} | risk: {item['risk']}]"
            )
            if item.get("why"):
                execution_plan.append(f"  rationale: {item['why']}")
            if item.get("impact_if_ignored"):
                execution_plan.append(
                    f"  impact_if_ignored: {item['impact_if_ignored']}"
                )
            if item.get("alternative"):
                execution_plan.append(f"  alternative: {item['alternative']}")
            for step_num, step in enumerate(steps, start=1):
                execution_plan.append(f"  {idx}.{step_num}. {step}")

        # Optional LLM summary.
        plan_summary = ""
        sequencing_notes = ""
        if enable_llm and settings.enable_llm and execution_plan:
            try:
                task_count = len(tasks_result.get("tasks") or [])
                high_risk = sum(1 for p in paired if p["risk"] == "high")
                payload = {
                    "task_count": task_count,
                    "change_count": len(paired_sorted),
                    "high_risk_changes": high_risk,
                    "actions": [p["action"] for p in paired_sorted],
                }
                prompt = (
                    "You are a software modernization advisor. "
                    "Return JSON with keys 'summary' and 'sequencing_notes'. "
                    "'summary' must contain a 2-3 sentence "
                    "plain-English executive summary of this modernization plan. "
                    "'sequencing_notes' must be a 1-2 sentence explanation of which changes "
                    "should be done first and why (including what they unblock or risk of delay). "
                    "Be concise and actionable. Do not include code or markdown."
                )
                response = self._get_client().generate_json(
                    prompt, json.dumps(payload)
                )
                if isinstance(response, dict):
                    plan_summary = str(response.get("summary", "")).strip()
                    sequencing_notes = str(response.get("sequencing_notes", "")).strip()
            except Exception:
                pass

        return {
            "execution_plan": execution_plan,
            "plan_summary": plan_summary,
            "sequencing_notes": sequencing_notes,
            "plan_mode": "staged" if use_staged else "direct",
        }
