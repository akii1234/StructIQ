"""Deterministic graph analysis for Phase 2 dependency graphs.

Pure computation only: no disk I/O, no LLM, no side effects.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import datetime, timezone


def analyze_graph(graph: dict, run_id: str) -> dict:
    # Build internal structures from graph["edges"] and graph["nodes"].
    raw_edges = graph.get("edges") or []
    raw_nodes = graph.get("nodes") or []

    adj: dict[str, list[str]] = defaultdict(list)  # source -> [targets]
    rev_adj: dict[str, list[str]] = defaultdict(list)  # target -> [sources]
    node_meta: dict[str, dict] = {}  # id -> meta
    nodes: set[str] = set()

    for n in raw_nodes:
        if not isinstance(n, dict):
            continue
        node_id = n.get("id")
        if node_id is None:
            continue

        # Graph builder uses node ids as file paths (strings), but accept int ids too.
        node_key = str(node_id)
        nodes.add(node_key)
        node_meta[node_key] = {
            "language": n.get("language", ""),
            "module": n.get("module", ""),
            "in_degree": int(n.get("in_degree", 0) or 0),
            "out_degree": int(n.get("out_degree", 0) or 0),
        }

    # If edges contain string node ids, keep them; otherwise coerce via builder expectation.
    # We treat node IDs as opaque strings throughout analysis.
    for e in raw_edges:
        if not isinstance(e, dict):
            continue
        source = e.get("source")
        target = e.get("target")
        if source is None or target is None:
            continue
        source_key = str(source)
        target_key = str(target)
        nodes.add(source_key)
        nodes.add(target_key)
        adj[source_key].append(target_key)
        rev_adj[target_key].append(source_key)

    # Ensure deterministic neighbor traversal.
    for k in list(adj.keys()):
        adj[k] = sorted(set(adj[k]))
    for k in list(rev_adj.keys()):
        rev_adj[k] = sorted(set(rev_adj[k]))

    # Build edge line lookup: (source, target) -> line_number
    edge_line_lookup: dict[tuple[str, str], int | None] = {}
    for e in raw_edges:
        if isinstance(e, dict):
            src = str(e.get("source") or "")
            tgt = str(e.get("target") or "")
            if src and tgt:
                edge_line_lookup[(src, tgt)] = e.get("line_number")

    # Cycle detection — iterative 3-color DFS.
    colors: dict[str, int] = {n: 0 for n in nodes}  # 0=unvisited, 1=in-stack, 2=done
    back_edges: set[tuple[str, str]] = set()
    cycles: list[dict] = []
    seen_cycle_members: set[frozenset[str]] = set()

    for start in sorted(nodes):
        if colors.get(start, 0) != 0:
            continue

        stack: list[tuple[str, int]] = [(start, 0)]
        colors[start] = 1

        while stack:
            node, idx = stack[-1]
            neighbors = adj.get(node, [])

            if idx < len(neighbors):
                nei = neighbors[idx]
                stack[-1] = (node, idx + 1)

                if colors.get(nei, 0) == 0:
                    colors[nei] = 1
                    stack.append((nei, 0))
                elif colors.get(nei, 0) == 1:
                    # Back edge found.
                    back_edges.add((node, nei))

                    node_names = [frame[0] for frame in stack]
                    try:
                        start_idx = node_names.index(nei)
                    except ValueError:
                        start_idx = 0

                    cycle_members = node_names[start_idx:]
                    cycle_dedupe = frozenset(cycle_members)
                    if (
                        cycle_dedupe not in seen_cycle_members
                        and len(cycles) < 100
                    ):
                        seen_cycle_members.add(cycle_dedupe)
                        closing_line = edge_line_lookup.get((node, nei))
                        cycles.append({
                            "files": cycle_members + [nei],
                            "closing_edge": {
                                "source": node,
                                "target": nei,
                                "line_number": closing_line,
                            },
                        })
            else:
                stack.pop()
                colors[node] = 2

    has_cycles = len(cycles) > 0

    # Entry points: in_degree == 0 AND out_degree > 0, with name heuristics as a confidence boost.
    name_hints = {
        "main.py",
        "app.py",
        "index.js",
        "index.ts",
        "Main.java",
        "cmd/main.go",
    }

    entry_points: list[str] = []
    boosted_entry_points: list[str] = []

    # If node_meta doesn't include a node, treat degrees as derived from graph edges.
    in_degree_fallback: Counter = Counter()
    out_degree_fallback: Counter = Counter()
    for s, tos in adj.items():
        out_degree_fallback[s] += len(tos)
        for t in tos:
            in_degree_fallback[t] += 1

    for node in sorted(nodes):
        meta = node_meta.get(node, {})
        in_d = int(meta.get("in_degree", in_degree_fallback.get(node, 0)) or 0)
        out_d = int(meta.get("out_degree", out_degree_fallback.get(node, 0)) or 0)

        if in_d == 0 and out_d > 0:
            entry_points.append(node)

            # Confidence boost only (does not restrict).
            # Node ids are expected to be file paths; still keep it best-effort.
            if any(hint in str(node) for hint in name_hints):
                boosted_entry_points.append(node)

    # Coupling scores and instability for every node.
    coupling_scores_list: list[dict] = []
    for node in sorted(nodes):
        meta = node_meta.get(node, {})
        Ca = int(meta.get("in_degree", in_degree_fallback.get(node, 0)) or 0)
        Ce = int(meta.get("out_degree", out_degree_fallback.get(node, 0)) or 0)
        denom = Ca + Ce
        instability = 0.0 if denom == 0 else round(Ce / denom, 3)

        coupling_scores_list.append(
            {
                "file": node,
                "afferent_coupling": Ca,
                "efferent_coupling": Ce,
                "instability": instability,
            }
        )

    # Dependency depth — BFS from entry points, skipping back_edges.
    dependency_depth: dict[str, int] = {n: -1 for n in nodes}

    q: deque[str] = deque()
    for ep in sorted(entry_points):
        dependency_depth[ep] = 0
        q.append(ep)

    # Longest depth under constraints via relaxation.
    while q:
        node = q.popleft()
        base_depth = dependency_depth.get(node, -1)
        if base_depth < 0:
            continue

        for nei in adj.get(node, []):
            if (node, nei) in back_edges:
                continue
            cand_depth = base_depth + 1
            if dependency_depth.get(nei, -1) < cand_depth:
                dependency_depth[nei] = cand_depth
                q.append(nei)

    # MODULE COUPLING — group edges by (source_module, target_module).
    edge_module_counts: Counter = Counter()
    for e in raw_edges:
        if not isinstance(e, dict):
            continue
        source = e.get("source")
        target = e.get("target")
        if source is None or target is None:
            continue
        s_key = str(source)
        t_key = str(target)

        s_mod = str((node_meta.get(s_key) or {}).get("module", "") or "")
        t_mod = str((node_meta.get(t_key) or {}).get("module", "") or "")
        if s_mod and t_mod and s_mod != t_mod:
            edge_module_counts[(s_mod, t_mod)] += 1

    module_coupling = [
        {
            "source_module": sm,
            "target_module": tm,
            "edge_count": int(count),
        }
        for (sm, tm), count in edge_module_counts.most_common()
    ]

    # most_depended_on / most_dependencies
    most_depended_on = []
    most_dependencies = []
    in_degree_all: dict[str, int] = {
        n: int(
            node_meta.get(n, {}).get("in_degree", in_degree_fallback.get(n, 0)) or 0
        )
        for n in nodes
    }
    out_degree_all: dict[str, int] = {
        n: int(
            node_meta.get(n, {}).get("out_degree", out_degree_fallback.get(n, 0))
            or 0
        )
        for n in nodes
    }

    most_depended_on = [
        {"file": n, "in_degree": in_degree_all.get(n, 0)}
        for n in sorted(nodes, key=lambda x: (-in_degree_all.get(x, 0), x))[:20]
    ]
    most_dependencies = [
        {"file": n, "out_degree": out_degree_all.get(n, 0)}
        for n in sorted(nodes, key=lambda x: (-out_degree_all.get(x, 0), x))[:20]
    ]

    # summary dict
    files_with_no_dependencies = sorted(
        [n for n in nodes if out_degree_all.get(n, 0) == 0]
    )
    files_with_no_dependents = sorted(
        [n for n in nodes if in_degree_all.get(n, 0) == 0]
    )

    max_depth = max([d for d in dependency_depth.values() if d >= 0], default=-1)

    summary = {
        "total_files_analyzed": int(len(nodes)),
        "files_with_no_dependencies": len(files_with_no_dependencies),
        "files_with_no_dependents": len(files_with_no_dependents),
        "cycle_count": int(len(cycles)),
        "max_depth": int(max_depth),
    }

    generated_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "cycles": cycles,
        "has_cycles": has_cycles,
        "entry_points": sorted(entry_points),
        "boosted_entry_points": sorted(boosted_entry_points),
        "most_depended_on": most_depended_on,
        "most_dependencies": most_dependencies,
        "coupling_scores": coupling_scores_list,
        "dependency_depth": dependency_depth,
        "module_coupling": module_coupling,
        "summary": summary,
    }

