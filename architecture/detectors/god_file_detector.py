"""God file anti-pattern detector (registry adapter)."""
from __future__ import annotations

from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector


class GodFileDetector(BaseDetector):
    id = "god_file"
    name = "God file"
    category = "structural"

    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        try:
            from StructIQ.architecture.analyzer import ArchitectureAnalyzer

            return ArchitectureAnalyzer().detect_god_files(analysis)
        except Exception:
            return []
