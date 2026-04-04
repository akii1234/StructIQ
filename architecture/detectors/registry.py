"""Detector registry — registers and runs all anti-pattern detectors."""
from __future__ import annotations

from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector
from StructIQ.utils.logger import get_logger

logger = get_logger(__name__)


class DetectorRegistry:
    """Holds all registered detectors and runs them safely."""

    def __init__(self) -> None:
        self._detectors: list[BaseDetector] = []

    def register(self, detector: BaseDetector) -> None:
        self._detectors.append(detector)

    def run_all(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        results: list[AntiPatternResult] = []
        for detector in self._detectors:
            try:
                findings = detector.detect(graph, analysis, content_scan)
                results.extend(findings)
            except Exception as exc:
                logger.warning(
                    "Detector %s failed (non-fatal): %s", detector.id, exc, exc_info=True
                )
        return results
