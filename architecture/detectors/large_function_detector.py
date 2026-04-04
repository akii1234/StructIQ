"""Large function detector (deep scan only)."""
from __future__ import annotations

from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector


class LargeFunctionDetector(BaseDetector):
    id = "large_function"
    name = "Large function"
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
                if "max_function_lines" not in metrics:
                    continue
                try:
                    fc = int(metrics.get("function_count", 0) or 0)
                except (TypeError, ValueError):
                    fc = 0
                if fc == 0:
                    continue
                try:
                    mx = int(metrics.get("max_function_lines", 0) or 0)
                    avg = int(metrics.get("avg_function_lines", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if mx <= 50:
                    continue
                sev = "high" if mx > 100 else "medium"
                out.append(
                    {
                        "type": "large_function",
                        "category": "complexity",
                        "severity": sev,
                        "file": fp,
                        "description": (
                            f"Largest function in this file is {mx} lines — "
                            "functions over 50 lines are hard to test and migrate"
                        ),
                        "metrics": {
                            "max_function_lines": mx,
                            "avg_function_lines": avg,
                            "threshold": 50,
                        },
                        "effort": "medium",
                    }
                )
            return sorted(out, key=lambda x: x.get("file", ""))
        except Exception:
            return []
