"""CLI entrypoint for StructIQ discovery phase."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import uuid

import uvicorn
from StructIQ.api.routes import app as api_app
from StructIQ.agents.summarizer import Summarizer
from StructIQ.config import settings
from StructIQ.core.orchestrator import DiscoveryOrchestrator
from StructIQ.llm.client import OpenAIClient
from StructIQ.scanner.file_classifier import FileClassifier
from StructIQ.scanner.file_scanner import FileScanner
from StructIQ.scanner.module_extractor import ModuleExtractor
from StructIQ.services.cache_manager import CacheManager
from StructIQ.utils.logger import get_logger


def build_parser() -> argparse.ArgumentParser:
    """Build command-line argument parser."""
    parser = argparse.ArgumentParser(description="StructIQ - Phase 1")
    parser.add_argument(
        "project_directory",
        nargs="?",
        help="Path to the project directory to analyze.",
    )
    parser.add_argument(
        "--output",
        default="data/runs/output.json",
        help="Path to save discovery output JSON.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="OpenAI model to use for summarization.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start FastAPI service instead of CLI analysis.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for API server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for API server.",
    )
    parser.add_argument(
        "--report",
        metavar="RUN_DIR",
        help="Generate HTML report for an existing run directory.",
    )
    return parser


def _build_orchestrator(model: str) -> tuple[DiscoveryOrchestrator, CacheManager]:
    """Create orchestrator + cache manager shared by CLI execution."""
    llm_client = OpenAIClient(model=model) if settings.enable_llm else None
    cache_manager = CacheManager(enabled=settings.cache_enabled)
    orchestrator = DiscoveryOrchestrator(
        scanner=FileScanner(),
        classifier=FileClassifier(),
        module_extractor=ModuleExtractor(),
        summarizer=Summarizer(llm_client=llm_client, cache_manager=cache_manager),
    )
    return orchestrator, cache_manager


def run_api_server(host: str, port: int) -> None:
    """Run FastAPI server; async work is handled by RunManager threads."""
    uvicorn.run(api_app, host=host, port=port)


def run_cli_sync(project_directory: str, output_path: str, model: str) -> None:
    """Run discovery synchronously in-process (no background threads)."""
    logger = get_logger("main")
    orchestrator, cache_manager = _build_orchestrator(model)
    orchestrator.execute(
        project_directory=project_directory,
        output_path=output_path,
        max_workers=settings.max_workers,
    )
    cache_manager.persist()
    run_id = str(uuid.uuid4())
    try:
        from StructIQ.dependency.pipeline import (
            run_dependency_pipeline,
            DependencyPipelineError,
        )

        run_dependency_pipeline(
            output_path=output_path,
            run_dir=str(Path(output_path).parent),
            run_id=run_id,
            project_root=project_directory,
            logger=logger,
        )
    except DependencyPipelineError as exc:
        logger.warning(
            "Phase 2 dependency analysis failed (non-fatal): %s", exc
        )
    else:
        run_dir = str(Path(output_path).parent)
        logger.info(
            "Phase 2 complete — graph: %s/dependency_graph.json, analysis: %s/dependency_analysis.json",
            run_dir,
            run_dir,
        )

    try:
        from StructIQ.architecture.pipeline import (
            run_architecture_pipeline,
            ArchitecturePipelineError,
        )
        run_architecture_pipeline(
            graph_path=str(Path(output_path).parent / "dependency_graph.json"),
            analysis_path=str(Path(output_path).parent / "dependency_analysis.json"),
            run_dir=str(Path(output_path).parent),
            run_id=run_id,
            enable_llm=settings.enable_llm,
            logger=logger,
        )
    except ArchitecturePipelineError as exc:
        logger.warning("Phase 3 architecture analysis failed (non-fatal): %s", exc)
    else:
        run_dir = str(Path(output_path).parent)
        logger.info(
            "Phase 3 complete — insights: %s/architecture_insights.json", run_dir
        )

    try:
        from StructIQ.modernization.pipeline import (
            run_modernization_pipeline,
            ModernizationPipelineError,
        )
        run_modernization_pipeline(
            insights_path=str(Path(output_path).parent / "architecture_insights.json"),
            graph_path=str(Path(output_path).parent / "dependency_graph.json"),
            run_dir=str(Path(output_path).parent),
            run_id=run_id,
            enable_llm=settings.enable_llm,
            logger=logger,
        )
    except ModernizationPipelineError as exc:
        logger.warning("Phase 4 modernization planning failed (non-fatal): %s", exc)
    else:
        run_dir = str(Path(output_path).parent)
        logger.info(
            "Phase 4 complete — plan: %s/modernization_plan.json", run_dir
        )
    logger.info("Discovery pipeline completed.")


def _read_plan_decision(output_path: str) -> str | None:
    """Read modernization plan decision from completed run.
    Returns None if file is missing, unreadable, or contains invalid JSON.
    """
    plan_path = Path(output_path).parent / "modernization_plan.json"
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        return data.get("decision") if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def main() -> None:
    """CLI/API entrypoint: explicit sync CLI path or API server path."""
    args = build_parser().parse_args()
    if args.report:
        from StructIQ.reporting.pipeline import run_report_pipeline, ReportPipelineError

        try:
            path = run_report_pipeline(
                run_dir=args.report, run_id=Path(args.report).name
            )
            print(f"Report written: {path}")
        except ReportPipelineError as exc:
            print(f"Report generation failed: {exc}")
        return
    if args.serve:
        run_api_server(host=args.host, port=args.port)
        return
    if not args.project_directory:
        raise ValueError("project_directory is required when not running --serve")
    run_cli_sync(
        project_directory=args.project_directory,
        output_path=args.output,
        model=args.model,
    )
    decision = _read_plan_decision(args.output)
    if decision == "action_required":
        sys.exit(1)


if __name__ == "__main__":
    # CLI execution: synchronous discovery run unless --serve is provided.
    main()
