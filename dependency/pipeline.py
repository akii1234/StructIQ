from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple

from app.dependency.analyzer import analyze_graph
from app.dependency.graph_builder import build_graph
from app.generators.json_writer import read_json_file, write_json_output
from app.utils.logger import get_logger


class DependencyPipelineError(RuntimeError):
    """Raised when Phase 2 pipeline cannot proceed."""


def run_dependency_pipeline(
    output_path: str,
    run_dir: str,
    run_id: str,
    project_root: str,
    logger: logging.Logger | None = None,
) -> Tuple[dict, dict]:
    if logger is None:
        logger = get_logger("dependency.pipeline")

    try:
        phase1_output = read_json_file(output_path, {})
        if not phase1_output or not phase1_output.get("files"):
            raise DependencyPipelineError(
                f"Phase 1 output not found or empty at {output_path}"
            )

        logger.info("Phase 2: building dependency graph for run %s", run_id)
        graph = build_graph(phase1_output, project_root, run_id)

        graph_path = str(Path(run_dir) / "dependency_graph.json")
        write_json_output(graph, graph_path)
        logger.info(
            "Phase 2: graph written — %d nodes, %d edges",
            graph["stats"]["total_nodes"],
            graph["stats"]["total_edges"],
        )

        analysis = analyze_graph(graph, run_id)

        analysis_path = str(Path(run_dir) / "dependency_analysis.json")
        write_json_output(analysis, analysis_path)
        logger.info(
            "Phase 2: analysis written — cycles=%s, entry_points=%d",
            analysis.get("has_cycles"),
            len(analysis.get("entry_points") or []),
        )

        # Update snapshot paths (best-effort).
        try:
            snapshot_path = Path(run_dir) / "snapshot.json"
            snapshot = read_json_file(str(snapshot_path), {})
            snapshot["dependency_graph_path"] = graph_path
            snapshot["dependency_analysis_path"] = analysis_path
            write_json_output(snapshot, str(snapshot_path))
        except OSError as exc:
            logger.warning(
                "Phase 2: failed to update snapshot with dependency paths: %s",
                exc,
                exc_info=True,
            )

        return graph, analysis
    except DependencyPipelineError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DependencyPipelineError(str(exc)) from exc

