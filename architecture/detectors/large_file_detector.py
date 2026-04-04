"""Large file detector (line count threshold)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector
from StructIQ.config import settings


def _skip_large_file(file_path: str) -> bool:
    p = Path(file_path)
    n = p.name.lower()
    stem = p.stem.lower()
    if n.endswith(".min.js"):
        return True
    if "migrations" in p.parts:
        return True
    if n.startswith("test_") or "_test" in stem:
        return True
    return False


class LargeFileDetector(BaseDetector):
    id = "large_file"
    name = "Large file"
    category = "complexity"

    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        try:
            threshold = settings.large_file_threshold
            out: list[AntiPatternResult] = []
            for fp, metrics in content_scan.items():
                if not isinstance(fp, str) or not isinstance(metrics, dict):
                    continue
                if _skip_large_file(fp):
                    continue
                try:
                    lc = int(metrics.get("line_count", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if lc <= threshold:
                    continue
                sev = "high" if lc > 1000 else "medium"
                out.append(
                    {
                        "type": "large_file",
                        "category": "complexity",
                        "severity": sev,
                        "file": fp,
                        "description": (
                            f"File has {lc} lines — exceeds the maintainability "
                            f"threshold of {threshold}"
                        ),
                        "metrics": {"line_count": lc, "threshold": threshold},
                        "effort": "medium",
                    }
                )
            return sorted(out, key=lambda x: x.get("file", ""))
        except Exception:
            return []
