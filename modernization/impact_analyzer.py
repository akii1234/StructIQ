"""Assess risk and scope of each proposed structural change."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Set


def _build_adjacency(graph: dict) -> Dict[str, List[str]]:
    """Build bidirectional adjacency for impact traversal."""
    adj: Dict[str, List[str]] = {}
    for edge in (graph.get("edges") or []):
        if not isinstance(edge, dict):
            continue
        src = edge.get("source")
        tgt = edge.get("target")
        if not src or not tgt:
            continue
        src, tgt = str(src), str(tgt)
        adj.setdefault(src, [])
        adj.setdefault(tgt, [])
        if tgt not in adj[src]:
            adj[src].append(tgt)
        if src not in adj[tgt]:
            adj[tgt].append(src)
    return adj


def _build_in_degree(graph: dict) -> Dict[str, int]:
    """Build in-degree map as centrality proxy."""
    in_deg: Dict[str, int] = {}
    for node in (graph.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        if node_id is None:
            continue
        in_deg[str(node_id)] = int(node.get("in_degree", 0) or 0)
    return in_deg


def _build_centrality(graph: dict, in_deg: Dict[str, int]) -> Dict[str, float]:
    """Build normalized centrality map (prefer explicit node centrality if present)."""
    centrality: Dict[str, float] = {}
    max_in_degree = max(in_deg.values(), default=0)
    for node in (graph.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        if node_id is None:
            continue
        node_key = str(node_id)
        raw = node.get("centrality")
        if raw is not None:
            try:
                c = float(raw)
            except (TypeError, ValueError):
                c = 0.0
        else:
            c = (in_deg.get(node_key, 0) / max_in_degree) if max_in_degree > 0 else 0.0
        centrality[node_key] = max(0.0, min(1.0, c))
    return centrality


def _build_entry_points(graph: dict) -> Set[str]:
    entry_points: Set[str] = set()
    for ep in (graph.get("entry_points") or []):
        if ep:
            entry_points.add(str(ep))
    for node in (graph.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        if node_id is None:
            continue
        node_key = str(node_id)
        if node.get("is_entry_point") is True or node.get("entry_point") is True:
            entry_points.add(node_key)
            continue
        name = Path(node_key).name.lower()
        if name in {"main.py", "app.py", "index.js", "index.ts"}:
            entry_points.add(node_key)
    return entry_points


def _bfs_affected(
    start_files: List[str],
    adj: Dict[str, List[str]],
    max_hops: int = 3,
) -> Set[str]:
    """BFS up to max_hops from start files to find affected nodes."""
    visited: Set[str] = set()
    q: deque[tuple[str, int]] = deque()
    for f in start_files:
        if f not in visited:
            visited.add(f)
            q.append((f, 0))
    while q:
        node, depth = q.popleft()
        if depth >= max_hops:
            continue
        for nei in adj.get(node, []):
            if nei not in visited:
                visited.add(nei)
                q.append((nei, depth + 1))
    return visited


def _assess_risk(
    affected_files: Set[str],
    centrality: Dict[str, float],
    entry_points: Set[str],
) -> str:
    """Derive weighted risk from size, centrality, and entry-point impact."""
    count = len(affected_files)
    if count > 20:
        return "high"

    avg_centrality = (
        sum(centrality.get(f, 0.0) for f in affected_files) / count if count > 0 else 0.0
    )
    max_centrality = max((centrality.get(f, 0.0) for f in affected_files), default=0.0)
    entry_point_flag = 1.0 if any(f in entry_points for f in affected_files) else 0.0
    count_component = min(count / 20.0, 1.0)

    risk_score = (count_component * 0.4) + (avg_centrality * 0.4) + (entry_point_flag * 0.2)

    if risk_score >= 0.67:
        risk = "high"
    elif risk_score >= 0.34:
        risk = "medium"
    else:
        risk = "low"

    # Rule-based escalations.
    if max_centrality > 0.7:
        if risk == "low":
            risk = "medium"
        elif risk == "medium":
            risk = "high"
    if entry_point_flag > 0:
        if risk == "low":
            risk = "medium"
        elif risk == "medium":
            risk = "high"

    if risk == "high":
        return "high"
    if risk == "medium":
        return "medium"
    return "low"


class ImpactAnalyzer:
    """Evaluate the blast radius of each proposed change."""

    def analyze(self, changes_result: dict, graph: dict) -> dict:
        if not isinstance(changes_result, dict) or not isinstance(graph, dict):
            return {"impact": []}

        changes = changes_result.get("changes") or []
        adj = _build_adjacency(graph)
        in_deg = _build_in_degree(graph)
        centrality = _build_centrality(graph, in_deg)
        entry_points = _build_entry_points(graph)

        impact: List[Dict[str, Any]] = []

        for change in changes:
            if not isinstance(change, dict):
                continue
            from_target = change.get("from", "")
            to_target = change.get("to", "")
            action = change.get("action", "")

            start_files = [f for f in [from_target, to_target] if f and f in adj]
            if not start_files:
                start_files = [from_target] if from_target else []

            affected = _bfs_affected(start_files, adj)
            risk = _assess_risk(affected, centrality, entry_points)

            impact.append(
                {
                    "action": action,
                    "from": from_target,
                    "to": to_target,
                    "affected_files": sorted(affected),
                    "affected_count": len(affected),
                    "risk": risk,
                }
            )

        return {"impact": impact}
