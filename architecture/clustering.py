from __future__ import annotations

from collections import defaultdict, deque
from itertools import combinations
from pathlib import Path
from typing import Dict, List


class ClusteringEngine:
    """Simple, deterministic clustering of files into logical services."""

    def cluster(self, processed_graph: dict) -> dict:
        """
        Group files into logical services based on module/folder and dependencies.

        processed_graph is expected to come from GraphProcessor and contain:
        - adjacency: {node: [neighbors]}
        - reverse_adjacency: {node: [sources]}
        - degree_metrics: {node: {in_degree, out_degree}}
        """
        if not isinstance(processed_graph, dict):
            return {}

        adjacency = processed_graph.get("adjacency") or {}
        reverse_adjacency = processed_graph.get("reverse_adjacency") or {}
        degree_metrics = processed_graph.get("degree_metrics") or {}

        if not isinstance(adjacency, dict) or not isinstance(reverse_adjacency, dict):
            return {}

        # Collect all node ids from any of the structures
        nodes: set[str] = set()
        nodes.update(str(k) for k in adjacency.keys())
        nodes.update(str(k) for k in reverse_adjacency.keys())
        nodes.update(str(k) for k in degree_metrics.keys())

        if not nodes:
            return {}

        # Normalize adjacency maps: ensure every node has an entry
        adjacency = dict(adjacency)
        reverse_adjacency = dict(reverse_adjacency)
        for nid in list(nodes):
            adjacency.setdefault(nid, [])
            reverse_adjacency.setdefault(nid, [])

        # Build import map: import_target -> files that import it.
        import_map: Dict[str, List[str]] = defaultdict(list)
        for importer in sorted(adjacency.keys()):
            deps = adjacency.get(importer, [])
            if not isinstance(deps, list):
                continue
            for dep in sorted({str(d) for d in deps}):
                import_map[dep].append(importer)

        # 1) Group by "module/folder" (simple heuristic: parent directory name)
        module_groups: Dict[str, List[str]] = defaultdict(list)
        for nid in sorted(nodes):
            try:
                p = Path(nid)
                parts = p.parts
                if len(parts) > 1:
                    module = parts[-2] or "root"
                else:
                    module = "root"
            except (TypeError, ValueError):
                module = "unknown"
            module_groups[module].append(nid)

        # 2) Refine using dependency connections:
        #    within each module group, split into weakly connected components
        clusters: List[List[str]] = []

        for module_name in sorted(module_groups.keys()):
            group_nodes = set(module_groups[module_name])

            # Build undirected adjacency restricted to this group
            undirected: Dict[str, List[str]] = {n: [] for n in group_nodes}
            for n in group_nodes:
                for nei in adjacency.get(n, []):
                    if nei in group_nodes:
                        undirected[n].append(nei)
                        undirected.setdefault(nei, [])
                for src in reverse_adjacency.get(n, []):
                    if src in group_nodes:
                        undirected[n].append(src)
                        undirected.setdefault(src, [])

            # Find connected components via BFS
            seen: set[str] = set()
            module_components: List[List[str]] = []
            for start in sorted(group_nodes):
                if start in seen:
                    continue
                comp: List[str] = []
                q: deque[str] = deque([start])
                seen.add(start)
                while q:
                    node = q.popleft()
                    comp.append(node)
                    for nei in undirected.get(node, []):
                        if nei not in seen:
                            seen.add(nei)
                            q.append(nei)
                module_components.append(sorted(comp))

            # Extend clustering with shared-import affinity:
            # if two files share >= 2 imports, merge their clusters.
            shared_counts: Dict[tuple[str, str], int] = defaultdict(int)
            for dep in sorted(import_map.keys()):
                importers = [f for f in import_map.get(dep, []) if f in group_nodes]
                if len(importers) < 2:
                    continue
                unique_importers = sorted(set(importers))
                for a, b in combinations(unique_importers, 2):
                    shared_counts[(a, b)] += 1

            merged_components: List[set[str]] = [set(comp) for comp in module_components]
            for (a, b), count in sorted(shared_counts.items()):
                if count < 2:
                    continue
                idx_a = -1
                idx_b = -1
                for idx, comp_set in enumerate(merged_components):
                    if a in comp_set:
                        idx_a = idx
                    if b in comp_set:
                        idx_b = idx
                    if idx_a != -1 and idx_b != -1:
                        break
                if idx_a == -1 or idx_b == -1 or idx_a == idx_b:
                    continue
                merged_components[idx_a].update(merged_components[idx_b])
                merged_components[idx_b] = set()

            for comp_set in merged_components:
                if comp_set:
                    clusters.append(sorted(comp_set))

        # 3) Build service mapping deterministically
        services: Dict[str, List[str]] = {}
        clusters_sorted = sorted(clusters, key=lambda c: (c[0] if c else ""))

        # Build a folder-name -> occurrence counter for unique key generation.
        key_counter: Dict[str, int] = {}
        for comp in clusters_sorted:
            if not comp:
                continue
            try:
                folder = Path(comp[0]).parts[-2] if len(Path(comp[0]).parts) > 1 else "root"
            except (TypeError, ValueError):
                folder = "unknown"
            key_counter[folder] = key_counter.get(folder, 0) + 1
            count = key_counter[folder]
            key = folder if count == 1 else f"{folder}_{count}"
            services[key] = comp

        return services

