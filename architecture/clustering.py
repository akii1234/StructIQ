from __future__ import annotations

from pathlib import Path
from typing import Any


def _extract_hub_candidates(analysis: dict | None, top_n: int = 5) -> set[str]:
    """Extract file paths that are likely hub files from coupling metrics.

    Uses Ca (afferent coupling) — files with the highest Ca are hub candidates.
    Returns the top_n files by Ca value (Ca >= 3).

    Path format assumption: coupling_metrics keys must use the same path
    representation (absolute vs. relative) as the graph node IDs used to build
    the adjacency dict in ClusteringEngine.cluster(). Both originate from
    dependency_analysis.json and dependency_graph.json written by Phase 2, so
    they are consistent in practice. If a mismatch occurs, hub merging silently
    produces no matches — it does not crash.
    """
    analysis = analysis or {}
    coupling = analysis.get("coupling_metrics") or {}
    if coupling:
        by_ca = sorted(
            (
                (fp, int((metrics or {}).get("ca", 0) or 0))
                for fp, metrics in coupling.items()
                if isinstance(metrics, dict)
            ),
            key=lambda x: x[1],
            reverse=True,
        )
        return {str(fp) for fp, ca in by_ca[:top_n] if ca >= 3}

    scores = analysis.get("coupling_scores") or []
    by_ca_list: list[tuple[str, int]] = []
    for row in scores:
        if not isinstance(row, dict):
            continue
        fp = str(row.get("file", "") or "")
        if not fp:
            continue
        ca = int(row.get("afferent_coupling", 0) or 0)
        by_ca_list.append((fp, ca))
    by_ca_list.sort(key=lambda x: x[1], reverse=True)
    return {fp for fp, ca in by_ca_list[:top_n] if ca >= 3}


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
        1b. Hub-signal pre-merge (high afferent coupling in analysis).
        2. Affinity merge — groups with >=3 cross-group edges merge.
        3. Absorb singletons — groups <3 files merge into most-coupled neighbor.
        4. Assign deterministic service keys.
        """
        del services_hint  # reserved for future hints

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

        # Step 1b: hub signal — merge groups that all share imports from a high-Ca hub.
        # The hub file's own group is intentionally excluded from this merge: the hub
        # (e.g. shared/models.py) belongs to its own directory group and stays there.
        # Only the groups that *import* the hub are merged together — they are coupled
        # via their shared dependency, so they likely form one logical service.
        hub_candidates = _extract_hub_candidates(analysis or {})
        if hub_candidates:
            for hub_fp in sorted(hub_candidates):
                importing_groups: list[str] = []
                for gk, gfiles in sorted(groups.items()):
                    for f in gfiles:
                        if hub_fp in adjacency.get(f, set()):
                            importing_groups.append(gk)
                            break
                if len(importing_groups) >= 2:
                    base = importing_groups[0]
                    for other in importing_groups[1:]:
                        if other in groups and base in groups and other != base:
                            groups[base] |= groups.pop(other)

        # Step 2: affinity merge
        changed = True
        while changed:
            changed = False
            keys = sorted(groups.keys(), key=lambda k: (-len(groups[k]), k))
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
                best_size = -1
                for other_key, other_files in sorted(groups.items()):
                    if other_key == small_key:
                        continue
                    count = _cross_edges(small_files, other_files)
                    same_dir_bonus = (
                        2 if other_key.split("_")[0] == small_key.split("_")[0] else 0
                    )
                    score = count + same_dir_bonus
                    other_size = len(groups[other_key])
                    if (score, other_size, other_key) > (
                        best_count,
                        best_size,
                        best_key or "",
                    ):
                        best_count = score
                        best_size = other_size
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
