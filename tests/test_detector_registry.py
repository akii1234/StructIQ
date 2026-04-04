"""Tests for detector registry and ArchitectureAnalyzer migration."""
from __future__ import annotations

from typing import Any

import pytest

from StructIQ.architecture.analyzer import ArchitectureAnalyzer
from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector
from StructIQ.architecture.detectors.registry import DetectorRegistry


def test_registry_runs_all_detectors():
    """Registry must call all registered detectors and aggregate results."""

    class _A(BaseDetector):
        id = "a"
        name = "A"
        category = "structural"

        def detect(
            self,
            graph: dict[str, Any],
            analysis: dict[str, Any],
            content_scan: dict[str, Any],
        ) -> list[AntiPatternResult]:
            return [{"type": "a_type", "severity": "low", "description": "from a"}]

    class _B(BaseDetector):
        id = "b"
        name = "B"
        category = "structural"

        def detect(
            self,
            graph: dict[str, Any],
            analysis: dict[str, Any],
            content_scan: dict[str, Any],
        ) -> list[AntiPatternResult]:
            return [{"type": "b_type", "severity": "medium", "description": "from b"}]

    reg = DetectorRegistry()
    reg.register(_A())
    reg.register(_B())
    out = reg.run_all({}, {}, {})
    assert len(out) == 2
    types = {x["type"] for x in out}
    assert types == {"a_type", "b_type"}


def test_registry_non_fatal_on_detector_exception():
    """A detector that raises must not crash the registry — others still run."""

    class _Raises(BaseDetector):
        id = "raises"
        name = "Raises"
        category = "structural"

        def detect(
            self,
            graph: dict[str, Any],
            analysis: dict[str, Any],
            content_scan: dict[str, Any],
        ) -> list[AntiPatternResult]:
            raise RuntimeError("detector boom")

    class _Ok(BaseDetector):
        id = "ok"
        name = "Ok"
        category = "structural"

        def detect(
            self,
            graph: dict[str, Any],
            analysis: dict[str, Any],
            content_scan: dict[str, Any],
        ) -> list[AntiPatternResult]:
            return [{"type": "survivor", "severity": "low", "description": "ok"}]

    reg = DetectorRegistry()
    reg.register(_Raises())
    reg.register(_Ok())
    out = reg.run_all({}, {}, {})
    assert len(out) == 1
    assert out[0]["type"] == "survivor"


def test_existing_detectors_produce_same_output():
    """After migration, existing detectors produce identical output to before."""
    analysis = {
        "cycles": [
            {"files": ["a.py", "b.py"], "closing_edge": {"source": "a.py", "target": "b.py"}},
        ],
        "coupling_scores": [
            {
                "file": "/proj/core.py",
                "afferent_coupling": 10,
                "efferent_coupling": 10,
                "instability": 0.5,
            },
            {
                "file": "/proj/helper.py",
                "afferent_coupling": 2,
                "efferent_coupling": 8,
                "instability": 0.8,
            },
        ],
        "dependency_depth": {"/proj/core.py": 3, "/proj/helper.py": 1},
        "module_coupling": [
            {"source_module": "core", "target_module": "other", "edge_count": 5},
        ],
        "summary": {"total_files_analyzed": 2},
    }

    def _legacy_expected() -> list[dict]:
        a = ArchitectureAnalyzer()
        anti_patterns: list[dict] = []
        anti_patterns.extend(a.detect_cycles(analysis))
        god_file_results = a.detect_god_files(analysis)
        god_file_paths: set[str] = {ap["file"] for ap in god_file_results if "file" in ap}
        anti_patterns.extend(
            [
                ap
                for ap in a.detect_high_coupling(analysis)
                if ap.get("file") not in god_file_paths
            ]
        )
        anti_patterns.extend(god_file_results)
        anti_patterns.extend(a.detect_weak_boundaries(analysis))

        def _sort_key(item: dict) -> tuple:
            return (
                item.get("type", ""),
                item.get("file") or item.get("module", ""),
                tuple(item.get("files", [])),
            )

        return sorted(anti_patterns, key=_sort_key)

    expected = _legacy_expected()
    got = ArchitectureAnalyzer().analyze(analysis)["anti_patterns"]
    assert got == expected
