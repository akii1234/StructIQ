"""Phase 4 modernization pipeline.

Deterministic planning: Planner → ChangeGenerator → ImpactAnalyzer → PlanGenerator.
Optional single LLM call in PlanGenerator for executive summary only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from StructIQ.generators.json_writer import read_json_file, write_json_output
from StructIQ.reporting.health_score import compute_health_score as _compute_hs
from StructIQ.modernization.change_generator import ChangeGenerator
from StructIQ.modernization.impact_analyzer import ImpactAnalyzer
from StructIQ.modernization.plan_generator import PlanGenerator
from StructIQ.modernization.planner import ModernizationPlanner
from StructIQ.llm.client import LLMClient
from StructIQ.utils.logger import get_logger


class ModernizationPipelineError(RuntimeError):
    """Raised when Phase 4 pipeline cannot proceed."""


def run_modernization_pipeline(
    insights_path: str,
    graph_path: str,
    run_dir: str,
    run_id: str,
    enable_llm: bool = True,
    llm_client: "LLMClient | None" = None,
    logger: logging.Logger | None = None,
) -> dict:
    if logger is None:
        logger = get_logger("modernization.pipeline")

    try:
        insights = read_json_file(insights_path, {})
        graph = read_json_file(graph_path, {})

        if not insights:
            raise ModernizationPipelineError(
                f"Phase 3 insights missing at {insights_path}"
            )
        if not graph:
            raise ModernizationPipelineError(
                f"Dependency graph missing at {graph_path}"
            )
        total_nodes = len((graph.get("nodes") or []))

        logger.info("Phase 4: generating modernization tasks for run %s", run_id)
        tasks_result = ModernizationPlanner().plan(insights)

        generated_at = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        tasks = tasks_result.get("tasks") or []
        if not isinstance(tasks, list):
            raise ModernizationPipelineError("Planner returned invalid tasks payload")

        for task in tasks:
            if not isinstance(task, dict):
                raise ModernizationPipelineError("Planner returned malformed task entry")
            required = {
                "type",
                "target",
                "priority",
                "reason",
                "confidence",
                "why",
                "impact_if_ignored",
                "alternative",
            }
            if not required.issubset(set(task.keys())):
                raise ModernizationPipelineError(
                    "Planner task missing required explainability/confidence fields"
                )

        low_value_tasks = bool(tasks) and all(
            str(t.get("priority", "")).lower() == "low"
            and float(t.get("confidence", 0) or 0) <= 0.5
            for t in tasks
            if isinstance(t, dict)
        )
        if not tasks or low_value_tasks:
            reason = (
                "No architectural anti-patterns detected in Phase 3 output."
                if not tasks
                else "Only low-value modernization tasks detected; no significant action required."
            )
            modernization_plan = {
                "run_id": run_id,
                "generated_at": generated_at,
                "decision": "no_action_required",
                "reason": reason,
                "plan_mode": "direct",
                "sequencing_notes": "",
                "tasks": [],
                "dominated_tasks": tasks_result.get("dominated_tasks", []),
                "changes": [],
                "impact": [],
                "execution_plan": [],
                "plan_summary": "No significant modernization required",
            }
            try:
                _dep = read_json_file(str(Path(run_dir) / "dependency_analysis.json")) or {}
                _arch = read_json_file(insights_path) or {}
                _p1 = read_json_file(str(Path(run_dir) / "output.json")) or {}
                modernization_plan["health_score"] = _compute_hs(_dep, _arch, _p1)
            except Exception as _hs_exc:
                logger.warning("Health score computation failed (non-fatal): %s", _hs_exc)
            if enable_llm and llm_client is not None and isinstance(modernization_plan.get("health_score"), dict):
                try:
                    from StructIQ.llm.trust.score_rationale import generate_score_rationale
                    _hs = modernization_plan["health_score"]
                    _rationale = generate_score_rationale(
                        score=_hs.get("score", 0),
                        grade=_hs.get("grade", ""),
                        components=_hs.get("components", {}),
                        cycle_count=len((_dep or {}).get("cycles") or []),
                        god_file_count=sum(
                            1 for _p in ((_arch or {}).get("anti_patterns") or [])
                            if isinstance(_p, dict) and _p.get("type") == "god_file"
                        ),
                        llm_client=llm_client,
                    )
                    if _rationale:
                        modernization_plan["health_score"]["rationale"] = _rationale
                except Exception as _rat_exc:
                    logger.warning("Health score rationale failed (non-fatal): %s", _rat_exc)
            plan_path = str(Path(run_dir) / "modernization_plan.json")
            write_json_output(modernization_plan, plan_path)
            logger.info(
                "Phase 4: plan written — %d tasks, %d changes, %d steps",
                len(modernization_plan["tasks"]),
                len(modernization_plan["changes"]),
                len(modernization_plan["execution_plan"]),
            )
            return modernization_plan

        logger.info("Phase 4: generating structural changes")
        changes_result = ChangeGenerator().generate(tasks_result)

        logger.info("Phase 4: analyzing change impact")
        impact_result = ImpactAnalyzer().analyze(changes_result, graph)

        logger.info("Phase 4: generating execution plan")
        plan_result = PlanGenerator(llm_client=llm_client).generate(
            tasks_result,
            changes_result,
            impact_result,
            enable_llm=enable_llm,
            context={"total_nodes": total_nodes},
        )

        modernization_plan = {
            "run_id": run_id,
            "generated_at": generated_at,
            "decision": "action_required",
            "plan_mode": plan_result.get("plan_mode", "direct"),
            "sequencing_notes": plan_result.get("sequencing_notes", ""),
            "tasks": tasks_result.get("tasks", []),
            "dominated_tasks": tasks_result.get("dominated_tasks", []),
            "changes": changes_result.get("changes", []),
            "impact": impact_result.get("impact", []),
            "execution_plan": plan_result.get("execution_plan", []),
            "plan_summary": plan_result.get("plan_summary", ""),
        }

        try:
            _dep = read_json_file(str(Path(run_dir) / "dependency_analysis.json")) or {}
            _arch = read_json_file(insights_path) or {}
            _p1 = read_json_file(str(Path(run_dir) / "output.json")) or {}
            modernization_plan["health_score"] = _compute_hs(_dep, _arch, _p1)
        except Exception as _hs_exc:
            logger.warning("Health score computation failed (non-fatal): %s", _hs_exc)
        if enable_llm and llm_client is not None and isinstance(modernization_plan.get("health_score"), dict):
            try:
                from StructIQ.llm.trust.score_rationale import generate_score_rationale
                _hs = modernization_plan["health_score"]
                _rationale = generate_score_rationale(
                    score=_hs.get("score", 0),
                    grade=_hs.get("grade", ""),
                    components=_hs.get("components", {}),
                    cycle_count=len((_dep or {}).get("cycles") or []),
                    god_file_count=sum(
                        1 for _p in ((_arch or {}).get("anti_patterns") or [])
                        if isinstance(_p, dict) and _p.get("type") == "god_file"
                    ),
                    llm_client=llm_client,
                )
                if _rationale:
                    modernization_plan["health_score"]["rationale"] = _rationale
            except Exception as _rat_exc:
                logger.warning("Health score rationale failed (non-fatal): %s", _rat_exc)
        plan_path = str(Path(run_dir) / "modernization_plan.json")
        write_json_output(modernization_plan, plan_path)
        logger.info(
            "Phase 4: plan written — %d tasks, %d changes, %d steps",
            len(modernization_plan["tasks"]),
            len(modernization_plan["changes"]),
            len(modernization_plan["execution_plan"]),
        )

        return modernization_plan

    except ModernizationPipelineError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ModernizationPipelineError(str(exc)) from exc
