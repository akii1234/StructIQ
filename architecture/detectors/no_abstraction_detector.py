"""Direct framework imports spread across modules."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector

_FRAMEWORKS = [
    "fastapi",
    "flask",
    "django",
    "sqlalchemy",
    "boto3",
    "pymongo",
    "redis",
    "celery",
    "express",
    "react",
    "angular",
    "vue",
    "spring",
    "hibernate",
]


class NoAbstractionLayerDetector(BaseDetector):
    id = "no_abstraction_layer"
    name = "No abstraction layer"
    category = "migration"

    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        try:
            file_to_mod: dict[str, str] = {}
            for n in graph.get("nodes") or []:
                if isinstance(n, dict) and isinstance(n.get("id"), str):
                    file_to_mod[n["id"]] = str(n.get("module") or "root")

            fw_files: dict[str, set[str]] = defaultdict(set)
            fw_mods: dict[str, set[str]] = defaultdict(set)

            for e in graph.get("edges") or []:
                if not isinstance(e, dict):
                    continue
                src = e.get("source")
                raw = str(e.get("raw_import") or "").lower()
                if not isinstance(src, str):
                    continue
                for fw in _FRAMEWORKS:
                    if fw in raw:
                        fw_files[fw].add(src)
                        fw_mods[fw].add(file_to_mod.get(src, "root"))

            out: list[AntiPatternResult] = []
            for fw in sorted(fw_files.keys()):
                files = fw_files[fw]
                mods = fw_mods[fw]
                if len(files) > 5 and len(mods) >= 3:
                    out.append(
                        {
                            "type": "no_abstraction_layer",
                            "category": "migration",
                            "severity": "high",
                            "module": fw,
                            "description": (
                                f"'{fw}' is imported directly in {len(files)} files across "
                                f"{len(mods)} modules — no abstraction layer makes framework "
                                "migration very expensive"
                            ),
                            "metrics": {
                                "framework": fw,
                                "direct_import_count": len(files),
                                "module_count": len(mods),
                                "threshold_files": 5,
                            },
                            "effort": "high",
                        }
                    )
            return out
        except Exception:
            return []
