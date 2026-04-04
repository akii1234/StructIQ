"""Hardcoded config signals (deep scan)."""
from __future__ import annotations

from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector


class HardcodedConfigDetector(BaseDetector):
    id = "hardcoded_config"
    name = "Hardcoded config"
    category = "migration"

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
                if "hardcoded_signals" not in metrics:
                    continue
                try:
                    n = int(metrics.get("hardcoded_signals", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if n <= 0:
                    continue
                sev = "high" if n > 3 else "medium"
                out.append(
                    {
                        "type": "hardcoded_config",
                        "category": "migration",
                        "severity": sev,
                        "file": fp,
                        "description": (
                            "File contains hardcoded URLs, credentials, or magic numbers — "
                            "must be extracted to config before migration"
                        ),
                        "metrics": {"hardcoded_signals": n},
                        "effort": "low",
                    }
                )
            return sorted(out, key=lambda x: x.get("file", ""))
        except Exception:
            return []
