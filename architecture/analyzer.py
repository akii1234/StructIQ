from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


class ArchitectureAnalyzer:
    """Detect simple architecture-level anti-patterns from Phase 2 analysis data."""

    def detect_cycles(self, analysis: dict) -> List[dict]:
        """Detect strongly connected cycles reported by the dependency analyzer."""
        if not isinstance(analysis, dict):
            return []
        cycles = analysis.get("cycles") or []
        anti_patterns: List[dict] = []
        for cycle in cycles:
            if isinstance(cycle, dict):
                files = [str(f) for f in (cycle.get("files") or [])]
            elif isinstance(cycle, list):
                files = [str(f) for f in cycle]
            else:
                continue
            if not files:
                continue
            anti_patterns.append(
                {
                    "type": "cycle",
                    "files": files,
                    "severity": "high",
                    "description": "Circular dependency between modules/files.",
                    "closing_edge": cycle.get("closing_edge") if isinstance(cycle, dict) else None,
                }
            )
        return anti_patterns

    def detect_high_coupling(self, analysis: dict) -> List[dict]:
        """Detect files with unusually high coupling based on Ca/Ce metrics."""
        if not isinstance(analysis, dict):
            return []
        scores = analysis.get("coupling_scores") or []
        if not isinstance(scores, list):
            return []

        records: List[Dict[str, Any]] = []
        for rec in scores:
            if not isinstance(rec, dict):
                continue
            file_path = rec.get("file")
            Ca = rec.get("afferent_coupling")
            Ce = rec.get("efferent_coupling")
            if not isinstance(file_path, str):
                continue
            try:
                Ca_i = int(Ca or 0)
                Ce_i = int(Ce or 0)
            except (TypeError, ValueError):
                continue
            total = Ca_i + Ce_i
            records.append(
                {
                    "file": file_path,
                    "Ca": Ca_i,
                    "Ce": Ce_i,
                    "total": total,
                }
            )

        if not records:
            return []

        # Simple, deterministic threshold: mark the top 10 by total coupling,
        # and any file whose total is at least 2x the median total.
        totals_sorted = sorted(r["total"] for r in records)
        mid = len(totals_sorted) // 2
        if totals_sorted:
            if len(totals_sorted) % 2 == 1:
                median_total = totals_sorted[mid]
            else:
                median_total = (totals_sorted[mid - 1] + totals_sorted[mid]) / 2.0
        else:
            median_total = 0

        threshold = max(median_total * 2, 5)
        # Sort descending by total, then file path.
        records_sorted = sorted(
            records, key=lambda r: (-r["total"], r["file"])
        )

        # Boilerplate files that are always zero-coupling in Django/Python packages
        _EXCLUDED_NAMES = {"__init__.py", "apps.py"}

        anti_patterns: List[dict] = []
        for idx, rec in enumerate(records_sorted):
            if idx >= 10:
                break
            if rec["total"] < threshold:
                break
            if Path(rec["file"]).name in _EXCLUDED_NAMES:
                continue
            anti_patterns.append(
                {
                    "type": "high_coupling",
                    "file": rec["file"],
                    "afferent_coupling": rec["Ca"],
                    "efferent_coupling": rec["Ce"],
                    "total_coupling": rec["total"],
                    "severity": "medium",
                    "description": "File has unusually high incoming/outgoing dependencies.",
                }
            )

        return anti_patterns

    def detect_god_files(self, analysis: dict) -> List[dict]:
        """Detect 'god files' with both high fan-in and fan-out and deep in the graph."""
        if not isinstance(analysis, dict):
            return []

        scores = analysis.get("coupling_scores") or []
        depth_map = analysis.get("dependency_depth") or {}
        if not isinstance(scores, list) or not isinstance(depth_map, dict):
            return []

        # Build quick lookup for degrees.
        in_out: Dict[str, Dict[str, int]] = {}
        for rec in scores:
            if not isinstance(rec, dict):
                continue
            file_path = rec.get("file")
            if not isinstance(file_path, str):
                continue
            try:
                Ca = int(rec.get("afferent_coupling", 0) or 0)
                Ce = int(rec.get("efferent_coupling", 0) or 0)
            except (TypeError, ValueError):
                continue
            in_out[file_path] = {"Ca": Ca, "Ce": Ce}

        if not in_out:
            return []

        # Determine thresholds: "god file" if both Ca and Ce are in the upper quantile
        # and the node is relatively deep (depth >= 2).
        Ca_values = sorted(v["Ca"] for v in in_out.values())
        Ce_values = sorted(v["Ce"] for v in in_out.values())
        idx_75 = max(int(len(Ca_values) * 0.75) - 1, 0)
        Ca_thresh = max(Ca_values[idx_75], 3)
        Ce_thresh = max(Ce_values[idx_75], 3)

        anti_patterns: List[dict] = []
        for file_path, vals in sorted(in_out.items()):
            Ca = vals["Ca"]
            Ce = vals["Ce"]
            depth_raw = depth_map.get(file_path, -1)
            try:
                depth = int(depth_raw)
            except (TypeError, ValueError):
                depth = -1

            if Ca >= Ca_thresh and Ce >= Ce_thresh and depth >= 2:
                anti_patterns.append(
                    {
                        "type": "god_file",
                        "file": file_path,
                        "afferent_coupling": Ca,
                        "efferent_coupling": Ce,
                        "depth": depth,
                        "severity": "high",
                        "description": "File appears to centralize too many responsibilities.",
                    }
                )

        return anti_patterns

    def detect_weak_boundaries(self, analysis: dict) -> List[dict]:
        """Detect modules with high external coupling relative to internal cohesion."""
        if not isinstance(analysis, dict):
            return []

        def _module_from_node(node_id: Any) -> str:
            try:
                parts = Path(str(node_id)).parts
                return parts[-2] if len(parts) > 1 else "root"
            except (TypeError, ValueError):
                return "unknown"

        # Sum total efferent coupling per module from coupling_scores.
        module_total_ce: Dict[str, int] = {}
        for rec in (analysis.get("coupling_scores") or []):
            if not isinstance(rec, dict):
                continue
            file_path = rec.get("file")
            if not isinstance(file_path, str):
                continue
            try:
                ce = int(rec.get("efferent_coupling", 0) or 0)
            except (TypeError, ValueError):
                continue
            module = _module_from_node(file_path)
            module_total_ce[module] = module_total_ce.get(module, 0) + ce

        # Sum outgoing cross-module edges per source module from module_coupling.
        module_external_out: Dict[str, int] = {}
        for rec in (analysis.get("module_coupling") or []):
            if not isinstance(rec, dict):
                continue
            source_module = rec.get("source_module")
            if not isinstance(source_module, str):
                continue
            try:
                edge_count = int(rec.get("edge_count", 0) or 0)
            except (TypeError, ValueError):
                continue
            if edge_count <= 0:
                continue
            module_external_out[source_module] = (
                module_external_out.get(source_module, 0) + edge_count
            )

        # Derive internal edges: total outgoing minus external outgoing.
        all_modules = sorted(
            set(module_total_ce.keys()) | set(module_external_out.keys())
        )
        anti_patterns: List[dict] = []
        for module_name in all_modules:
            external_edges = module_external_out.get(module_name, 0)
            total_ce = module_total_ce.get(module_name, 0)
            internal_edges = max(0, total_ce - external_edges)
            boundary_score = round(external_edges / (internal_edges + 1), 3)
            if boundary_score > 1.5:
                anti_patterns.append(
                    {
                        "type": "weak_boundary",
                        "module": module_name,
                        "severity": "medium",
                        "score": boundary_score,
                        "external_edges": external_edges,
                        "internal_edges": internal_edges,
                        "description": (
                            "Module has significantly more external dependencies "
                            "than internal cohesion."
                        ),
                    }
                )
        return anti_patterns

    def analyze(
        self,
        analysis: dict,
        graph: dict | None = None,
        content_scan: dict | None = None,
        extra_detectors: list | None = None,
    ) -> dict:
        """Aggregate all anti-pattern detections into a single result."""
        if not isinstance(analysis, dict):
            return {"anti_patterns": []}

        g = graph if isinstance(graph, dict) else {}
        cs = content_scan if isinstance(content_scan, dict) else {}

        from StructIQ.architecture.detectors.boundary_detector import WeakBoundaryDetector
        from StructIQ.architecture.detectors.coupling_detector import HighCouplingDetector
        from StructIQ.architecture.detectors.cycle_detector import CycleDetector
        from StructIQ.architecture.detectors.god_file_detector import GodFileDetector
        from StructIQ.architecture.detectors.registry import DetectorRegistry

        registry = DetectorRegistry()
        # Order matches legacy analyze(): cycles, high_coupling (excluding gods), god_file, weak_boundary
        registry.register(CycleDetector())
        registry.register(HighCouplingDetector())
        registry.register(GodFileDetector())
        registry.register(WeakBoundaryDetector())
        for det in extra_detectors or []:
            registry.register(det)

        anti_patterns: List[dict] = list(
            registry.run_all(g, analysis, cs)
        )

        # Deterministic ordering by type then file (if present).
        def _sort_key(item: dict) -> Any:
            return (
                item.get("type", ""),
                item.get("file") or item.get("module", ""),
                tuple(item.get("files", [])),
            )

        anti_patterns_sorted = sorted(anti_patterns, key=_sort_key)
        return {"anti_patterns": anti_patterns_sorted}

