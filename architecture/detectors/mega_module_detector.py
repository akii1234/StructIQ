"""Mega module — too many files in one module."""
from __future__ import annotations

from collections import Counter
from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector


class MegaModuleDetector(BaseDetector):
    id = "mega_module"
    name = "Mega module"
    category = "maintainability"

    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        try:
            mods: Counter[str] = Counter()
            for n in graph.get("nodes") or []:
                if not isinstance(n, dict):
                    continue
                fp = n.get("id")
                if not isinstance(fp, str):
                    continue
                m = str(n.get("module") or "root")
                mods[m] += 1
            total = sum(mods.values())
            if total < 5:
                return []
            out: list[AntiPatternResult] = []
            for mod, cnt in sorted(mods.items(), key=lambda x: (-x[1], x[0])):
                share = round(100.0 * cnt / total, 1)
                if share > 35:
                    sev = "high" if share > 50 else "medium"
                    out.append(
                        {
                            "type": "mega_module",
                            "category": "maintainability",
                            "severity": sev,
                            "module": mod,
                            "description": (
                                f"Module '{mod}' contains {share}% of all files — "
                                "lacks meaningful boundary decomposition"
                            ),
                            "metrics": {
                                "module": mod,
                                "file_count": cnt,
                                "total_files": total,
                                "share_pct": share,
                            },
                            "effort": "high",
                        }
                    )
            return out
        except Exception:
            return []
