"""Run lifecycle manager for async analysis service."""

from __future__ import annotations

import re
import threading
import uuid
from pathlib import Path
from typing import Any, Dict

from StructIQ.agents.summarizer import Summarizer
from StructIQ.config import settings
from StructIQ.core.orchestrator import DiscoveryOrchestrator
from StructIQ.generators.json_writer import read_json_file, write_json_output
from StructIQ.llm.client import OpenAIClient
from StructIQ.scanner.file_classifier import FileClassifier
from StructIQ.scanner.file_scanner import FileScanner
from StructIQ.scanner.module_extractor import ModuleExtractor
from StructIQ.services.cache_manager import CacheManager
from StructIQ.utils.logger import get_logger

DATA_DIR = Path("data/runs")


class RunManager:
    """Manage asynchronous analysis runs and status tracking."""

    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__)
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._runs: Dict[str, Dict[str, Any]] = {}

    def start_run(self, repo_path: str, resume: bool = True) -> str:
        """Create and start an async run thread."""
        run_id = str(uuid.uuid4())
        run_dir = DATA_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        run_state = {
            "run_id": run_id,
            "repo_path": repo_path,
            "status": "running",
            "progress": {"total_files": 0, "processed": 0, "skipped": 0, "failed": 0},
            "run_dir": str(run_dir),
            "output_path": str(run_dir / "output.json"),
            "logs_path": str(run_dir / "logs.json"),
            "snapshot_path": str(run_dir / "snapshot.json"),
        }
        with self._lock:
            self._runs[run_id] = run_state
        self._write_snapshot(run_id)

        thread = threading.Thread(
            target=self._execute_run, args=(run_id, resume), daemon=False
        )
        thread.start()
        return run_id

    @staticmethod
    def _derive_phase2_status(run_status: str, phase2_error: str | None) -> str:
        if run_status == "running":
            return "pending"
        if run_status == "phase2_running":
            return "running"
        if run_status == "completed":
            return "failed" if phase2_error else "ok"
        return "not_run"

    @staticmethod
    def _derive_phase3_status(run_status: str, phase3_error: str | None) -> str:
        if run_status in {"running", "phase2_running"}:
            return "pending"
        if run_status == "phase3_running":
            return "running"
        if run_status == "completed":
            return "failed" if phase3_error else "ok"
        return "not_run"

    @staticmethod
    def _derive_phase4_status(run_status: str, phase4_error: str | None) -> str:
        if run_status in {"running", "phase2_running", "phase3_running"}:
            return "pending"
        if run_status == "phase4_running":
            return "running"
        if run_status == "completed":
            return "failed" if phase4_error else "ok"
        return "not_run"

    def get_status(self, run_id: str) -> Dict[str, Any]:
        """Return current status for run."""
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", run_id):
            return {}
        with self._lock:
            state = self._runs.get(run_id)
        if state:
            return {
                "run_id": run_id,
                "status": state["status"],
                "progress": state["progress"],
                "phase2_status": self._derive_phase2_status(
                    state["status"], state.get("phase2_error")
                ),
                "phase3_status": self._derive_phase3_status(
                    state["status"], state.get("phase3_error")
                ),
                "phase4_status": self._derive_phase4_status(
                    state["status"], state.get("phase4_error")
                ),
            }

        snapshot = read_json_file(str(DATA_DIR / run_id / "snapshot.json"), {})
        if snapshot:
            snap_status = snapshot.get("status", "unknown")
            return {
                "run_id": run_id,
                "status": snap_status,
                "progress": snapshot.get("progress", {}),
                "phase2_status": self._derive_phase2_status(
                    snap_status, snapshot.get("phase2_error")
                ),
                "phase3_status": self._derive_phase3_status(
                    snap_status, snapshot.get("phase3_error")
                ),
                "phase4_status": self._derive_phase4_status(
                    snap_status, snapshot.get("phase4_error")
                ),
            }
        return {"run_id": run_id, "status": "not_found", "progress": {}}

    def get_results(self, run_id: str) -> Dict[str, Any]:
        """Return output payload for run."""
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", run_id):
            return {}
        output_path = DATA_DIR / run_id / "output.json"
        return read_json_file(str(output_path), {})

    def get_dependency_graph(self, run_id: str) -> Dict[str, Any]:
        """Return dependency_graph.json payload for run."""
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", run_id):
            return {}
        graph_path = DATA_DIR / run_id / "dependency_graph.json"
        return read_json_file(str(graph_path), {})

    def get_dependency_analysis(self, run_id: str) -> Dict[str, Any]:
        """Return dependency_analysis.json payload for run."""
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", run_id):
            return {}
        analysis_path = DATA_DIR / run_id / "dependency_analysis.json"
        return read_json_file(str(analysis_path), {})

    def get_architecture_insights(self, run_id: str) -> Dict[str, Any]:
        """Return architecture_insights.json payload for run."""
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", run_id):
            return {}
        insights_path = DATA_DIR / run_id / "architecture_insights.json"
        return read_json_file(str(insights_path), {})

    def get_modernization_plan(self, run_id: str) -> Dict[str, Any]:
        """Return modernization_plan.json payload for run."""
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", run_id):
            return {}
        plan_path = DATA_DIR / run_id / "modernization_plan.json"
        return read_json_file(str(plan_path), {})

    def _execute_run(self, run_id: str, resume: bool) -> None:
        """Run orchestrator and update run state."""
        with self._lock:
            run_state = dict(self._runs[run_id])
        if self._shutdown_event.is_set():
            with self._lock:
                self._runs[run_id]["status"] = "failed"
            self._write_snapshot(run_id, reason="shutdown_before_start")
            return

        snapshot = read_json_file(run_state["snapshot_path"], {})
        processed_files = set(snapshot.get("processed_files", [])) if resume else set()

        cache_manager = CacheManager(enabled=settings.cache_enabled)
        llm_client = OpenAIClient()
        orchestrator = DiscoveryOrchestrator(
            scanner=FileScanner(),
            classifier=FileClassifier(),
            module_extractor=ModuleExtractor(),
            summarizer=Summarizer(llm_client=llm_client, cache_manager=cache_manager),
        )

        logs: list[Dict[str, Any]] = []

        def progress_callback(event: Dict[str, Any]) -> None:
            with self._lock:
                current = self._runs[run_id]
                progress = current["progress"]
                progress["total_files"] = max(progress["total_files"], event.get("total_files", 0))
                status = event.get("status")
                if status == "success":
                    progress["processed"] += 1
                elif status == "skipped":
                    progress["skipped"] += 1
                elif status == "failed":
                    progress["failed"] += 1
            logs.append(
                {
                    "file": event.get("file", ""),
                    "status": event.get("status", ""),
                    "reason": event.get("reason", ""),
                    "time_taken": event.get("time_taken", ""),
                }
            )
            self._write_snapshot(run_id, processed_file=event.get("file", ""))
            write_json_output(logs, run_state["logs_path"])

        try:
            orchestrator.execute(
                project_directory=run_state["repo_path"],
                output_path=run_state["output_path"],
                max_workers=settings.max_workers,
                already_processed_files=processed_files,
                progress_callback=progress_callback,
                snapshot_path=run_state["snapshot_path"],
                run_id=run_id,
            )

            with self._lock:
                self._runs[run_id]["status"] = "phase2_running"
            self._write_snapshot(run_id)

            phase2_error: str | None = None
            try:
                from StructIQ.dependency.pipeline import (
                    run_dependency_pipeline,
                    DependencyPipelineError,
                )

                run_dependency_pipeline(
                    output_path=run_state["output_path"],
                    run_dir=run_state["run_dir"],
                    run_id=run_id,
                    project_root=run_state["repo_path"],
                    logger=self.logger,
                )
            except DependencyPipelineError as exc:
                phase2_error = str(exc)
                self.logger.warning(
                    "Phase 2 dependency pipeline failed (non-fatal): %s", exc
                )
            with self._lock:
                self._runs[run_id]["phase2_error"] = phase2_error

            with self._lock:
                self._runs[run_id]["status"] = "phase3_running"
            self._write_snapshot(run_id)

            phase3_error: str | None = None
            try:
                from StructIQ.architecture.pipeline import (
                    run_architecture_pipeline,
                    ArchitecturePipelineError,
                )

                snapshot = read_json_file(run_state["snapshot_path"], {})
                graph_path = snapshot.get(
                    "dependency_graph_path",
                    str(DATA_DIR / run_id / "dependency_graph.json"),
                )
                analysis_path = snapshot.get(
                    "dependency_analysis_path",
                    str(DATA_DIR / run_id / "dependency_analysis.json"),
                )

                run_architecture_pipeline(
                    graph_path=graph_path,
                    analysis_path=analysis_path,
                    run_dir=run_state["run_dir"],
                    run_id=run_id,
                    enable_llm=settings.enable_llm,
                    logger=self.logger,
                )
            except ArchitecturePipelineError as exc:
                phase3_error = str(exc)
                self.logger.warning(
                    "Phase 3 architecture pipeline failed (non-fatal): %s", exc
                )

            with self._lock:
                self._runs[run_id]["phase3_error"] = phase3_error

            with self._lock:
                self._runs[run_id]["status"] = "phase4_running"
            self._write_snapshot(run_id)

            phase4_error: str | None = None
            try:
                from StructIQ.modernization.pipeline import (
                    run_modernization_pipeline,
                    ModernizationPipelineError,
                )

                snapshot = read_json_file(run_state["snapshot_path"], {})
                insights_path = str(DATA_DIR / run_id / "architecture_insights.json")
                graph_path = snapshot.get(
                    "dependency_graph_path",
                    str(DATA_DIR / run_id / "dependency_graph.json"),
                )

                run_modernization_pipeline(
                    insights_path=insights_path,
                    graph_path=graph_path,
                    run_dir=run_state["run_dir"],
                    run_id=run_id,
                    enable_llm=settings.enable_llm,
                    logger=self.logger,
                )
            except ModernizationPipelineError as exc:
                phase4_error = str(exc)
                self.logger.warning(
                    "Phase 4 modernization pipeline failed (non-fatal): %s", exc
                )

            with self._lock:
                self._runs[run_id]["phase4_error"] = phase4_error
            cache_manager.persist()
            with self._lock:
                self._runs[run_id]["status"] = "completed"
            self._write_snapshot(run_id)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Run failed: %s", run_id)
            with self._lock:
                self._runs[run_id]["status"] = "failed"
            self._write_snapshot(run_id, reason=str(exc))

    def shutdown(self) -> None:
        self._shutdown_event.set()

    def _write_snapshot(self, run_id: str, processed_file: str = "", reason: str = "") -> None:
        """Persist run snapshot for resume and observability."""
        with self._lock:
            run_state = self._runs.get(run_id, {})
        if not run_state:
            return

        snapshot_path = Path(run_state["snapshot_path"])
        existing = read_json_file(str(snapshot_path), {})
        processed_files = set(existing.get("processed_files", []))
        if processed_file:
            processed_files.add(processed_file)

        payload = {
            "run_id": run_id,
            "status": run_state["status"],
            "progress": run_state["progress"],
            "processed_files": sorted(processed_files),
            "reason": reason,
            "phase2_error": run_state.get("phase2_error"),
            "phase3_error": run_state.get("phase3_error"),
            "phase4_error": run_state.get("phase4_error"),
        }
        write_json_output({**existing, **payload}, str(snapshot_path))
