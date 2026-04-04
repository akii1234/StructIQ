"""Weak boundary anti-pattern detector (registry adapter)."""
from __future__ import annotations

from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector


class WeakBoundaryDetector(BaseDetector):
    id = "weak_boundary"
    name = "Weak module boundary"
    category = "maintainability"

    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        try:
            from StructIQ.architecture.analyzer import ArchitectureAnalyzer

            return ArchitectureAnalyzer().detect_weak_boundaries(analysis)
        except Exception:
            return []
