"""Dependency graph preprocessing for architecture analysis."""

from __future__ import annotations

from collections import Counter
from typing import Any


class GraphProcessor:
    """Build analysis-ready graph structures from dependency graph payloads."""

    def process(self, graph: dict) -> dict:
        """
        Transform raw graph JSON into deterministic adjacency structures.

        Returns schema:
        {
          "adjacency": {},
          "reverse_adjacency": {},
          "degree_metrics": {},
          "centrality": {}
        }
        """
        if not isinstance(graph, dict):
            return {
                "adjacency": {},
                "reverse_adjacency": {},
                "degree_metrics": {},
                "centrality": {},
            }

        nodes_raw = graph.get("nodes") or []
        edges_raw = graph.get("edges") or []

        node_ids: set[str] = set()
        if isinstance(nodes_raw, list):
            for node in nodes_raw:
                if not isinstance(node, dict):
                    continue
                node_id = node.get("id")
                if node_id is None:
                    continue
                node_ids.add(str(node_id))

        adjacency: dict[str, list[str]] = {nid: [] for nid in sorted(node_ids)}
        reverse_adjacency: dict[str, list[str]] = {nid: [] for nid in sorted(node_ids)}

        out_deg: Counter[str] = Counter()
        in_deg: Counter[str] = Counter()

        # Track seen edges to keep deterministic deduplicated adjacency lists.
        seen_edges: set[tuple[str, str]] = set()

        if isinstance(edges_raw, list):
            for edge in edges_raw:
                if not isinstance(edge, dict):
                    continue
                src = edge.get("source")
                tgt = edge.get("target")
                if src is None or tgt is None:
                    continue

                src_id = str(src)
                tgt_id = str(tgt)
                pair = (src_id, tgt_id)
                if pair in seen_edges:
                    continue
                seen_edges.add(pair)

                if src_id not in adjacency:
                    adjacency[src_id] = []
                if tgt_id not in adjacency:
                    adjacency[tgt_id] = []
                if src_id not in reverse_adjacency:
                    reverse_adjacency[src_id] = []
                if tgt_id not in reverse_adjacency:
                    reverse_adjacency[tgt_id] = []

                adjacency[src_id].append(tgt_id)
                reverse_adjacency[tgt_id].append(src_id)
                out_deg[src_id] += 1
                in_deg[tgt_id] += 1

        # Deterministic ordering in outputs.
        for nid in list(adjacency.keys()):
            adjacency[nid] = sorted(adjacency[nid])
        for nid in list(reverse_adjacency.keys()):
            reverse_adjacency[nid] = sorted(reverse_adjacency[nid])

        degree_metrics: dict[str, dict[str, int]] = {}
        all_nodes = sorted(set(adjacency.keys()) | set(reverse_adjacency.keys()))
        for nid in all_nodes:
            degree_metrics[nid] = {
                "in_degree": int(in_deg.get(nid, 0)),
                "out_degree": int(out_deg.get(nid, 0)),
            }

        max_degree = max(
            (
                metrics["in_degree"] + metrics["out_degree"]
                for metrics in degree_metrics.values()
            ),
            default=0,
        )
        centrality: dict[str, float] = {}
        for node, metrics in degree_metrics.items():
            total = metrics["in_degree"] + metrics["out_degree"]
            centrality[node] = total / max_degree if max_degree > 0 else 0

        return {
            "adjacency": dict(sorted(adjacency.items())),
            "reverse_adjacency": dict(sorted(reverse_adjacency.items())),
            "degree_metrics": degree_metrics,
            "centrality": centrality,
        }

