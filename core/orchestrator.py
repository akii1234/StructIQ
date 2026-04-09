"""Orchestrates Phase 1 discovery pipeline."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Set

from StructIQ.agents.summarizer import Summarizer
from StructIQ.architecture.analyzer import ArchitectureAnalyzer
from StructIQ.architecture.clustering import ClusteringEngine
from StructIQ.architecture.graph_processor import GraphProcessor
from StructIQ.architecture.recommender import RecommendationEngine
from StructIQ.config import settings
from StructIQ.context.context_manager import ContextManager
from StructIQ.core.state_manager import DiscoveryState
from StructIQ.generators.json_writer import (
    read_json_file,
    write_json_output,
    write_progress_snapshot,
)
from StructIQ.scanner.file_classifier import FileClassifier
from StructIQ.scanner.file_scanner import FileScanner
from StructIQ.scanner.module_extractor import ModuleExtractor
from StructIQ.utils.content_utils import is_relevant_file
from StructIQ.utils.logger import get_logger, log_file_event
from StructIQ.utils.static_analyzer import analyze_text, get_file_importance


class DiscoveryOrchestrator:
    """Pipeline: scan -> classify -> modules -> summarize -> write."""

    def __init__(
        self,
        scanner: FileScanner,
        classifier: FileClassifier,
        module_extractor: ModuleExtractor,
        summarizer: Summarizer,
    ) -> None:
        self.scanner = scanner
        self.classifier = classifier
        self.module_extractor = module_extractor
        self.summarizer = summarizer
        self.state = DiscoveryState()
        self.logger = get_logger(self.__class__.__name__)

    def run(self, project_directory: str, output_path: str) -> Dict[str, Any]:
        """Execute the full discovery pipeline."""
        return self.execute(project_directory=project_directory, output_path=output_path)

    def _emit_progress(
        self,
        file_path: str,
        summary: Dict[str, Any],
        elapsed: float,
        total_files: int,
        progress_callback: Any,
        counters: Dict[str, int],
    ) -> None:
        """Update counters, logs, and optional callback for one file."""
        status = summary.get("_status", "success")
        reason = summary.get("_reason", "")
        if status == "success":
            counters["processed"] += 1
        elif status == "skipped":
            counters["skipped"] += 1
        else:
            counters["failed"] += 1
        log_file_event(
            logger=self.logger,
            file_path=file_path,
            status=status,
            reason=reason,
            time_taken=elapsed,
        )
        if progress_callback:
            progress_callback(
                {
                    "file": file_path,
                    "status": status,
                    "reason": reason,
                    "time_taken": f"{elapsed:.4f}s",
                    "total_files": total_files,
                }
            )

    def execute(
        self,
        project_directory: str,
        output_path: str,
        max_workers: int = 4,
        already_processed_files: set[str] | None = None,
        progress_callback: Any = None,
        snapshot_path: str = "data/runs/progress_snapshot.json",
        run_id: str | None = None,
    ) -> Dict[str, Any]:
        """Execute discovery pipeline with optional concurrency hooks."""
        if max_workers < 1:
            max_workers = 1
        self.logger.info("Scanning files from: %s", project_directory)
        self.state.files = self.scanner.scan_directory(project_directory)

        self.logger.info("Classifying %d files", len(self.state.files))
        self.state.classified_files = [
            self.classifier.classify(file_path) for file_path in self.state.files
        ]

        self.logger.info("Extracting modules")
        self.state.modules = self.module_extractor.extract(
            self.state.files, project_directory
        )

        self.logger.info("Summarizing files (cost-aware)")
        self.state.summaries = []
        processed_files = already_processed_files or set()

        cost_tracker: Dict[str, Any] = {
            "llm_calls": 0,
            "batch_calls": 0,
            "cache_hits": 0,
            "llm_skipped_low_priority": 0,
            "batch_file_count_sum": 0,
        }
        total_files = len(self.state.classified_files)
        summary_by_path: Dict[str, Dict[str, Any]] = {}
        counters = {"processed": 0, "skipped": 0, "failed": 0}
        progress_emitted: Set[str] = set()

        def emit_once(
            fp: str,
            summary: Dict[str, Any],
            elapsed: float,
        ) -> None:
            if fp in progress_emitted:
                return
            progress_emitted.add(fp)
            self._emit_progress(
                fp,
                summary,
                elapsed,
                total_files,
                progress_callback,
                counters,
            )

        for item in self.state.classified_files:
            fp = item["file"]
            if fp in processed_files:
                summary_by_path[fp] = {
                    "file": fp,
                    "summary": "Skipped in resume mode (already processed).",
                    "key_elements": [],
                    "dependencies": [],
                    "_status": "skipped",
                    "_reason": "resume_skip",
                }

        work_rows: List[Dict[str, Any]] = []
        for item in self.state.classified_files:
            fp = item["file"]
            if fp in processed_files:
                continue
            try:
                path = Path(fp)
                disk_size = path.stat().st_size
                text = path.read_text(encoding="utf-8", errors="ignore")
                if disk_size > settings.max_file_size:
                    text = text[: settings.max_file_size]
                relevant, skip_reason = is_relevant_file(fp, text)
                if not relevant:
                    summary_by_path[fp] = {
                        "file": fp,
                        "summary": f"Skipped file ({skip_reason}).",
                        "key_elements": [],
                        "dependencies": [],
                        "_status": "skipped",
                        "_reason": skip_reason,
                    }
                    continue
                static_meta = analyze_text(fp, text, disk_size=disk_size)
            except OSError as exc:
                summary_by_path[fp] = {
                    "file": fp,
                    "summary": f"Failed to read file: {exc}",
                    "key_elements": [],
                    "dependencies": [],
                    "_status": "failed",
                    "_reason": f"read_error: {exc}",
                }
                continue

            importance = get_file_importance(static_meta, fp, item["type"])
            work_rows.append(
                {
                    "item": item,
                    "content": text,
                    "static_meta": static_meta,
                    "importance": importance,
                }
            )

        high_batch: List[Dict[str, Any]] = []
        medium_rows: List[Dict[str, Any]] = []
        low_rows: List[Dict[str, Any]] = []

        for row in work_rows:
            tier = row["importance"]
            if tier == "high":
                high_batch.append(row)
            elif tier == "medium":
                medium_rows.append(row)
            else:
                low_rows.append(row)

        for row in low_rows:
            item = row["item"]
            start = time.perf_counter()
            summary = self.summarizer.summarize_low_priority(
                item["file"], item["type"], row["static_meta"], cost_tracker=cost_tracker
            )
            elapsed = time.perf_counter() - start
            summary_by_path[item["file"]] = summary
            emit_once(item["file"], summary, elapsed)

        if high_batch:
            start = time.perf_counter()
            batch_items = [
                {
                    "file_path": r["item"]["file"],
                    "file_type": r["item"]["type"],
                    "content": r["content"],
                    "static_meta": r["static_meta"],
                }
                for r in high_batch
            ]
            batch_out = self.summarizer.summarize_batch_high_priority(
                batch_items, cost_tracker=cost_tracker
            )
            elapsed = time.perf_counter() - start
            n = max(1, len(high_batch))
            share = elapsed / n
            for r in high_batch:
                fp = r["item"]["file"]
                summary = batch_out.get(
                    fp,
                    self.summarizer.high_static_fallback(fp, r["static_meta"]),
                )
                summary_by_path[fp] = summary
                emit_once(fp, summary, share)

        def process_medium(row: Dict[str, Any]) -> Dict[str, Any]:
            item = row["item"]
            start = time.perf_counter()
            summary = self.summarizer.summarize_medium_priority(
                item["file"],
                item["type"],
                row["content"],
                row["static_meta"],
                cost_tracker=cost_tracker,
            )
            elapsed = time.perf_counter() - start
            return {"path": item["file"], "summary": summary, "elapsed": elapsed}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_medium, r) for r in medium_rows]
            for future in as_completed(futures):
                result = future.result()
                fp = result["path"]
                summary_by_path[fp] = result["summary"]
                emit_once(fp, result["summary"], result["elapsed"])

        for fp, summary in summary_by_path.items():
            emit_once(fp, summary, 0.0)

        for item in self.state.classified_files:
            fp = item["file"]
            summary = summary_by_path.get(fp)
            if summary:
                self.state.summaries.append(
                    {
                        "file": summary.get("file", fp),
                        "summary": summary.get("summary", ""),
                        "key_elements": summary.get("key_elements", []),
                        "dependencies": summary.get("dependencies", []),
                    }
                )

        processed = counters["processed"]
        skipped = counters["skipped"]
        failed = counters["failed"]

        self.summarizer.persist_cache()
        bc = int(cost_tracker.get("batch_calls", 0) or 0)
        bfs = int(cost_tracker.get("batch_file_count_sum", 0) or 0)
        avg_batch = round(bfs / bc, 4) if bc else 0.0
        output = self.state.to_dict()
        skipped_low = int(cost_tracker.get("llm_skipped_low_priority", 0) or 0)
        cache_hits = int(cost_tracker.get("cache_hits", 0) or 0)
        output["metrics"] = {
            "total_files": total_files,
            "processed": processed,
            "skipped": skipped,
            "failed": failed,
            "llm_calls": int(cost_tracker.get("llm_calls", 0) or 0),
            "batch_calls": int(cost_tracker.get("batch_calls", 0) or 0),
            "cache_hits": cache_hits,
            "llm_skipped_low_priority": skipped_low,
            "skipped_low_priority": skipped_low,
            "avg_batch_size": avg_batch,
        }
        self.logger.info("Writing output to: %s", output_path)
        write_json_output(output, output_path)
        write_progress_snapshot(
            {
                "step": "Phase 1 Final Hardening",
                "status": "completed",
                **output["metrics"],
            },
            output_path=snapshot_path,
        )
        try:
            ContextManager().update_context(
                {
                    "run_id": run_id or "",
                    "metrics": output["metrics"],
                }
            )
        except (OSError, UnicodeError, TypeError, ValueError, KeyError) as exc:
            self.logger.warning(
                "Project context update skipped (%s): %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )

        # Optional Phase 3: architecture insights from Phase 2 artifacts.
        try:
            if run_id:
                run_dir = Path("data/runs") / run_id
                graph_path = run_dir / "dependency_graph.json"
                analysis_path = run_dir / "dependency_analysis.json"
                graph = read_json_file(str(graph_path), {})
                dep_analysis = read_json_file(str(analysis_path), {})
                if graph and dep_analysis:
                    processed = GraphProcessor().process(graph)
                    clusters = ClusteringEngine().cluster(processed, dep_analysis)
                    arch_analysis = ArchitectureAnalyzer().analyze(dep_analysis)
                    recommendations = RecommendationEngine().generate(
                        {
                            "clusters": clusters,
                            "anti_patterns": arch_analysis.get("anti_patterns", []),
                            "entry_points": dep_analysis.get("entry_points", []),
                        }
                    )
                    architecture_insights = {
                        "run_id": run_id,
                        "graph_processed": processed,
                        "clusters": clusters,
                        "architecture_analysis": arch_analysis,
                        "recommendations": recommendations,
                    }
                    write_json_output(
                        architecture_insights,
                        str(run_dir / "architecture_insights.json"),
                    )
        except (OSError, UnicodeError, TypeError, ValueError, KeyError) as exc:
            self.logger.warning(
                "Phase 3 architecture pipeline skipped (%s): %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
        return output
