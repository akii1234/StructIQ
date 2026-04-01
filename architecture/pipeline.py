"""Phase 3 architecture intelligence pipeline.

No direct LLM usage here. LLM is optionally invoked via RecommendationEngine only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from StructIQ.architecture.analyzer import ArchitectureAnalyzer
from StructIQ.architecture.clustering import ClusteringEngine
from StructIQ.architecture.graph_processor import GraphProcessor
from StructIQ.architecture.recommender import RecommendationEngine
from StructIQ.generators.json_writer import read_json_file, write_json_output
from StructIQ.llm.client import LLMClient
from StructIQ.utils.logger import get_logger


class ArchitecturePipelineError(RuntimeError):
    """Raised when Phase 3 pipeline cannot proceed."""


def _normalize_recommendations(items: object) -> list[dict]:
    """Normalize recommendations to stable structured shape."""
    if not isinstance(items, list):
        return []

    normalized: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message", "")).strip()
        if not message:
            continue
        based_on_raw = item.get("based_on", [])
        affected_raw = item.get("affected_files", [])
        based_on = (
            [str(v).strip() for v in based_on_raw if str(v).strip()]
            if isinstance(based_on_raw, list)
            else []
        )
        affected_files = (
            [str(v).strip() for v in affected_raw if str(v).strip()]
            if isinstance(affected_raw, list)
            else []
        )
        normalized.append(
            {
                "message": message,
                "based_on": based_on,
                "affected_files": affected_files,
            }
        )
    return normalized


def _build_system_summary(
    services: dict,
    arch_result: dict,
    analysis: dict,
) -> str:
    """Build a deterministic one-line system summary — no LLM required."""
    total_files = (analysis.get("summary") or {}).get("total_files_analyzed", 0)
    service_count = len(services)
    anti_patterns = arch_result.get("anti_patterns") or []
    cycle_count = sum(1 for ap in anti_patterns if ap.get("type") == "cycle")
    issue_count = len(anti_patterns)

    summary = (
        f"Analyzed {total_files} files grouped into {service_count} logical services. "
        f"Found {issue_count} architectural issue(s)"
    )
    if cycle_count:
        summary += f" including {cycle_count} circular dependenc{'y' if cycle_count == 1 else 'ies'}"
    summary += "."
    return summary


def run_architecture_pipeline(
    graph_path: str,
    analysis_path: str,
    run_dir: str,
    run_id: str,
    enable_llm: bool = True,
    llm_client: "LLMClient | None" = None,
    logger: logging.Logger | None = None,
) -> dict:
    if logger is None:
        logger = get_logger("architecture.pipeline")

    try:
        graph = read_json_file(graph_path, {})
        analysis = read_json_file(analysis_path, {})

        if not graph or not analysis:
            raise ArchitecturePipelineError(
                f"Phase 2 outputs missing — graph: {graph_path}, analysis: {analysis_path}"
            )

        logger.info("Phase 3: processing graph for run %s", run_id)
        processed_graph = GraphProcessor().process(graph)

        logger.info("Phase 3: clustering files into services")
        services = ClusteringEngine().cluster(processed_graph)

        logger.info("Phase 3: detecting architectural anti-patterns")
        arch_result = ArchitectureAnalyzer().analyze(analysis)

        recommendations: list[dict] = []
        if enable_llm:
            logger.info("Phase 3: generating recommendations via LLM")
            try:
                rec_input = {
                    "clusters": services,
                    "anti_patterns": arch_result.get("anti_patterns", []),
                    "entry_points": analysis.get("entry_points", []),
                }
                rec_result = RecommendationEngine(llm_client=llm_client).generate(rec_input)
                recommendations = _normalize_recommendations(
                    rec_result.get("recommendations")
                )
            except Exception as exc:
                logger.warning(
                    "Phase 3: recommendation generation failed (non-fatal): %s", exc
                )
        else:
            logger.info("Phase 3: LLM disabled — skipping recommendations")

        generated_at = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        anti_patterns = arch_result.get("anti_patterns", [])
        if not isinstance(anti_patterns, list):
            anti_patterns = []
        if not isinstance(services, dict):
            services = {}

        insights = {
            "run_id": run_id,
            "generated_at": generated_at,
            "services": services,
            "anti_patterns": anti_patterns,
            "recommendations": recommendations,
            "system_summary": _build_system_summary(services, arch_result, analysis),
        }

        insights_path = str(Path(run_dir) / "architecture_insights.json")
        write_json_output(insights, insights_path)
        logger.info(
            "Phase 3: insights written — %d services, %d anti-patterns, %d recommendations",
            len(services),
            len(insights["anti_patterns"]),
            len(recommendations),
        )

        return insights

    except ArchitecturePipelineError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ArchitecturePipelineError(str(exc)) from exc
