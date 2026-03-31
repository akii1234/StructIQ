"""Reporting pipeline — generates HTML report from completed run outputs."""

from __future__ import annotations

import logging
from pathlib import Path

from StructIQ.reporting.report_generator import ReportGenerator
from StructIQ.utils.logger import get_logger


class ReportPipelineError(RuntimeError):
    """Raised when report generation cannot proceed."""


def run_report_pipeline(
    run_dir: str,
    run_id: str,
    logger: logging.Logger | None = None,
) -> str:
    if logger is None:
        logger = get_logger("reporting.pipeline")

    try:
        html = ReportGenerator().generate(run_dir, run_id)
        out_path = Path(run_dir) / "report.html"
        out_path.write_text(html, encoding="utf-8")
        logger.info("Report written: %s/report.html", run_dir)
        return str(out_path)
    except (OSError, ValueError) as exc:
        raise ReportPipelineError(str(exc)) from exc
