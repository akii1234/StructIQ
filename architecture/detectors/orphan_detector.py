"""Orphan file detector — no incoming or outgoing dependencies."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from StructIQ.architecture.detectors.base import AntiPatternResult, BaseDetector


def _skip_orphan_candidate(file_path: str) -> bool:
    bn = Path(file_path).name
    if bn in {"__init__.py", "conftest.py", "setup.py", "manage.py"}:
        return True
    if bn.startswith("test_"):
        return True
    stem = Path(file_path).stem
    if "_test" in stem:
        return True
    return False


class OrphanFileDetector(BaseDetector):
    id = "orphan_file"
    name = "Orphan file"
    category = "structural"

    def detect(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any],
        content_scan: dict[str, Any],
    ) -> list[AntiPatternResult]:
        try:
            entry_points: set[str] = {
                str(x) for x in (analysis.get("entry_points") or []) if x
            }
            ca_ce: dict[str, tuple[int, int]] = {}
            for rec in analysis.get("coupling_scores") or []:
                if not isinstance(rec, dict):
                    continue
                fp = rec.get("file")
                if not isinstance(fp, str):
                    continue
                try:
                    ca = int(rec.get("afferent_coupling", 0) or 0)
                    ce = int(rec.get("efferent_coupling", 0) or 0)
                except (TypeError, ValueError):
                    continue
                ca_ce[fp] = (ca, ce)

            node_ids: list[str] = []
            for n in graph.get("nodes") or []:
                if isinstance(n, dict) and isinstance(n.get("id"), str):
                    node_ids.append(n["id"])

            out: list[AntiPatternResult] = []
            for fp in sorted(set(node_ids) | set(ca_ce.keys())):
                if _skip_orphan_candidate(fp):
                    continue
                if fp in entry_points:
                    continue
                ca, ce = ca_ce.get(fp, (0, 0))
                if ca == 0 and ce == 0:
                    out.append(
                        {
                            "type": "orphan_file",
                            "category": "structural",
                            "severity": "low",
                            "file": fp,
                            "description": (
                                "File has no incoming or outgoing dependencies — "
                                "unreachable dead weight"
                            ),
                            "metrics": {
                                "afferent_coupling": 0,
                                "efferent_coupling": 0,
                            },
                            "effort": "low",
                        }
                    )
            return out
        except Exception:
            return []
