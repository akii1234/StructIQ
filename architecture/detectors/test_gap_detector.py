"""Missing test file detector."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector


def _skip_source(fp: str) -> bool:
    p = Path(fp)
    bn = p.name.lower()
    if bn == "__init__.py":
        return True
    if "migrations" in p.parts:
        return True
    if bn.startswith("test_") or "_test" in p.stem.lower():
        return True
    if p.suffix.lower() not in {".py", ".js", ".ts", ".go", ".java"}:
        return True
    return False


def _has_matching_test(stem: str, all_files: list[str]) -> bool:
    for p in all_files:
        bn = Path(p).name
        if bn.startswith(f"test_{stem}") or bn.startswith(f"{stem}_test"):
            return True
    return False


class TestGapDetector(BaseDetector):
    id = "test_gap"
    name = "Test gap"
    category = "maintainability"

    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        try:
            all_files: list[str] = []
            for n in graph.get("nodes") or []:
                if isinstance(n, dict) and isinstance(n.get("id"), str):
                    all_files.append(n["id"])
            ca_by_file: dict[str, int] = {}
            for rec in analysis.get("coupling_scores") or []:
                if not isinstance(rec, dict):
                    continue
                fp = rec.get("file")
                if not isinstance(fp, str):
                    continue
                try:
                    ca_by_file[fp] = int(rec.get("afferent_coupling", 0) or 0)
                except (TypeError, ValueError):
                    continue

            candidates: list[tuple[int, str]] = []
            for fp in all_files:
                if _skip_source(fp):
                    continue
                stem = Path(fp).stem
                if _has_matching_test(stem, all_files):
                    continue
                ca = ca_by_file.get(fp, 0)
                candidates.append((-ca, fp))

            candidates.sort()
            out: list[AntiPatternResult] = []
            for _, fp in candidates[:20]:
                stem = Path(fp).stem
                out.append(
                    {
                        "type": "test_gap",
                        "category": "maintainability",
                        "severity": "medium",
                        "file": fp,
                        "description": (
                            "No test file found for this source file — "
                            "migration without tests is high-risk"
                        ),
                        "metrics": {
                            "source_file": fp,
                            "test_file_searched": f"test_{stem}*",
                        },
                        "effort": "high",
                    }
                )
            return out
        except Exception:
            return []
