"""Too many functions in one file."""
from __future__ import annotations

from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector


class TooManyFunctionsDetector(BaseDetector):
    id = "too_many_functions"
    name = "Too many functions"
    category = "complexity"

    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        try:
            out: list[AntiPatternResult] = []
            for fp, metrics in content_scan.items():
                if not isinstance(fp, str) or not isinstance(metrics, dict):
                    continue
                try:
                    n = int(metrics.get("function_count", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if n <= 20:
                    continue
                sev = "high" if n > 40 else "medium"
                out.append(
                    {
                        "type": "too_many_functions",
                        "category": "complexity",
                        "severity": sev,
                        "file": fp,
                        "description": (
                            f"File defines {n} functions/methods — a file with this many "
                            "responsibilities is hard to navigate and migrate"
                        ),
                        "metrics": {"function_count": n, "threshold": 20},
                        "effort": "medium",
                    }
                )
            return sorted(out, key=lambda x: x.get("file", ""))
        except Exception:
            return []
