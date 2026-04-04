"""Cycle anti-pattern detector (registry adapter)."""
from __future__ import annotations

from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector


class CycleDetector(BaseDetector):
    id = "cycle"
    name = "Circular dependency"
    category = "structural"

    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        try:
            from StructIQ.architecture.analyzer import ArchitectureAnalyzer

            return ArchitectureAnalyzer().detect_cycles(analysis)
        except Exception:
            return []
