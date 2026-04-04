"""Base class and result type for all StructIQ anti-pattern detectors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypedDict


class AntiPatternResult(TypedDict, total=False):
    type: str  # snake_case identifier e.g. "large_file"
    category: str  # "structural" | "complexity" | "maintainability" | "migration"
    severity: str  # "high" | "medium" | "low"
    description: str  # plain-English one-line description
    file: str  # primary file path (if single-file finding)
    files: list[str]  # multiple file paths (if multi-file finding e.g. cycle)
    module: str  # module name (if module-level finding)
    metrics: dict  # raw numbers that triggered this finding e.g. {"line_count": 842, "threshold": 500}
    effort: str  # "low" | "medium" | "high" — estimated fix effort


class BaseDetector(ABC):
    """All detectors inherit from this. One class = one anti-pattern type."""

    #: Unique snake_case identifier. Must match the `type` field in results.
    id: str
    #: Human-readable name e.g. "Large File"
    name: str
    #: Which domain this detector belongs to
    category: str  # "structural" | "complexity" | "maintainability" | "migration"

    @abstractmethod
    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        """Run detection. Must never raise — catch and return [] on error.

        Args:
            graph: dependency_graph.json payload (nodes + edges)
            analysis: dependency_analysis.json payload (coupling_scores, cycles, etc.)
            content_scan: per-file content metrics from ContentScanner
                          {file_path: {line_count, function_count, max_function_lines,
                                       has_hardcoded_values, nesting_depth, ...}}
        """
        ...
