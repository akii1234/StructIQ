from __future__ import annotations

from pathlib import Path
from typing import Any


class ClusteringEngine:
    """Simple, deterministic clustering of files into logical services."""

    def cluster(
        self,
        graph: dict[str, Any],
        analysis: dict[str, Any] | None = None,
        services_hint: dict[str, list[str]] | None = None,
    ) -> dict[str, list[str]]:
        """Group files into logical services.

        Accepts either a raw dependency graph (nodes + edges) or GraphProcessor
        output (adjacency / reverse_adjacency).

        Algorithm:
        1. Group files by parent directory name.
        2. Affinity merge — groups with >=3 cross-group edges merge.
        3. Absorb singletons — groups <3 files merge into most-coupled neighbor.
        4. Assign deterministic service keys.
        """
        del analysis, services_hint  # reserved for future hints

        if not isinstance(graph, dict):
            return {}

        node_ids: list[str]
        adjacency: dict[str, set[str]]

        if isinstance(graph.get("adjacency"), dict) and "reverse_adjacency" in graph:
            raw_adj = graph.get("adjacency") or {}
            nodes: set[str] = set()
            adjacency = {}
            for src, tgts in raw_adj.items():
                s = str(src).strip()
                if not s:
                    continue
                nodes.add(s)
                if not isinstance(tgts, list):
                    continue
                for tgt in tgts:
                    t = str(tgt).strip()
                    if not t or s == t:
                        continue
                    nodes.add(t)
                    adjacency.setdefault(s, set()).add(t)
                    adjacency.setdefault(t, set()).add(s)
            for n in nodes:
                adjacency.setdefault(n, set())
            node_ids = sorted(nodes)
        else:
            node_ids = sorted(
                {
                    str(n["id"])
                    for n in (graph.get("nodes") or [])
                    if isinstance(n, dict) and isinstance(n.get("id"), str)
                }
            )
            if not node_ids:
                return {}
            adjacency = {n: set() for n in node_ids}
            for edge in graph.get("edges") or []:
                if not isinstance(edge, dict):
                    continue
                src = str(edge.get("source") or "").strip()
                tgt = str(edge.get("target") or "").strip()
                if src and tgt and src != tgt:
                    adjacency.setdefault(src, set()).add(tgt)
                    adjacency.setdefault(tgt, set()).add(src)

        if not node_ids:
            return {}

        # Step 1: group by parent directory name
        groups: dict[str, set[str]] = {}
        for fp in node_ids:
            key = Path(fp).parent.name or "root"
            groups.setdefault(key, set()).add(fp)

        def _cross_edges(files_a: set[str], files_b: set[str]) -> int:
            return sum(1 for f in files_a for g in adjacency.get(f, set()) if g in files_b)

        # Step 2: affinity merge — groups with >=3 cross-group edges merge
        changed = True
        while changed:
            changed = False
            keys = sorted(groups.keys())
            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    k1, k2 = keys[i], keys[j]
                    if k1 not in groups or k2 not in groups:
                        continue
                    if _cross_edges(groups[k1], groups[k2]) >= 3:
                        groups[k1] |= groups.pop(k2)
                        changed = True
                        break
                if changed:
                    break

        # Step 3: absorb singletons and pairs (<3 files)
        absorb_changed = True
        while absorb_changed:
            absorb_changed = False
            small_keys = sorted(
                [k for k, v in groups.items() if len(v) < 3],
                key=lambda k: len(groups[k]),
            )
            for small_key in small_keys:
                if small_key not in groups or len(groups[small_key]) >= 3:
                    continue
                small_files = groups[small_key]
                best_key: str | None = None
                best_count = -1
                for other_key, other_files in groups.items():
                    if other_key == small_key:
                        continue
                    count = _cross_edges(small_files, other_files)
                    same_dir_bonus = 2 if other_key.split("_")[0] == small_key.split("_")[0] else 0
                    if count + same_dir_bonus > best_count:
                        best_count = count + same_dir_bonus
                        best_key = other_key
                if best_key is not None:
                    groups[best_key] |= groups.pop(small_key)
                    absorb_changed = True

        # Step 4: deterministic service keys
        key_counts: dict[str, int] = {}
        services: dict[str, list[str]] = {}
        for group_key in sorted(groups.keys()):
            base = group_key
            n = key_counts.get(base, 0)
            key_counts[base] = n + 1
            svc_key = base if n == 0 else f"{base}_{n + 1}"
            services[svc_key] = sorted(groups[group_key])

        return services
