"""Generate SVG dependency graph from StructIQ graph payload."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Set, Tuple


def _truncate_label(text: str, max_len: int = 16) -> str:
    return text if len(text) <= max_len else f"{text[: max_len - 1]}…"


def _module_name(file_id: str) -> str:
    parts = Path(str(file_id)).parts
    return parts[-2] if len(parts) > 1 else "root"


def _node_color(file_id: str, anti_pattern_files: Set[str], entry_points: Set[str]) -> str:
    if file_id in anti_pattern_files:
        return "#ef4444"
    if file_id in entry_points:
        return "#22c55e"
    return "#60a5fa"


def _svg_empty(width: int, height: int) -> str:
    cx = width / 2
    cy = height / 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" style="background:#0f172a">'
        f'<text x="{cx}" y="{cy}" text-anchor="middle" fill="#94a3b8" '
        f'font-size="18">No dependency data available</text>'
        "</svg>"
    )


def generate_dependency_svg(
    graph: dict,
    anti_pattern_files: Set[str],
    entry_points: Set[str],
    width: int = 900,
    height: int = 600,
) -> str:
    nodes_raw = graph.get("nodes") or []
    edges_raw = graph.get("edges") or []
    if not isinstance(nodes_raw, list) or not nodes_raw:
        return _svg_empty(width, height)

    nodes: List[dict] = [n for n in nodes_raw if isinstance(n, dict) and n.get("id") is not None]
    if not nodes:
        return _svg_empty(width, height)

    cx = width / 2
    cy = height / 2
    group_radius = min(width, height) * 0.35

    edges_svg: List[str] = []
    nodes_svg: List[str] = []
    labels_svg: List[str] = []

    if len(nodes) <= 150:
        module_groups: Dict[str, List[dict]] = {}
        for node in nodes:
            nid = str(node.get("id"))
            module_groups.setdefault(_module_name(nid), []).append(node)
        for module in module_groups:
            module_groups[module] = sorted(module_groups[module], key=lambda n: str(n.get("id")))

        groups = sorted(module_groups.items(), key=lambda x: x[0])
        group_pos: Dict[str, Tuple[float, float]] = {}
        if groups:
            for idx, (module, group_nodes) in enumerate(groups):
                ang = (2 * math.pi * idx) / len(groups)
                gcx = cx + (group_radius * math.cos(ang))
                gcy = cy + (group_radius * math.sin(ang))
                group_pos[module] = (gcx, gcy)

        node_pos: Dict[str, Tuple[float, float]] = {}
        for module, group_nodes in groups:
            gcx, gcy = group_pos[module]
            mini_r = max(25, len(group_nodes) * 8)
            for idx, node in enumerate(group_nodes):
                nid = str(node.get("id"))
                if len(group_nodes) == 1:
                    nx, ny = gcx, gcy
                else:
                    ang = (2 * math.pi * idx) / len(group_nodes)
                    nx = gcx + (mini_r * math.cos(ang))
                    ny = gcy + (mini_r * math.sin(ang))
                node_pos[nid] = (nx, ny)

        for edge in edges_raw:
            if not isinstance(edge, dict):
                continue
            src = edge.get("source")
            tgt = edge.get("target")
            if src is None or tgt is None:
                continue
            s = str(src)
            t = str(tgt)
            if s == t or s not in node_pos or t not in node_pos:
                continue
            x1, y1 = node_pos[s]
            x2, y2 = node_pos[t]
            edges_svg.append(
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                'stroke="#94a3b8" stroke-width="0.8" opacity="0.4" />'
            )

        for node in sorted(nodes, key=lambda n: str(n.get("id"))):
            nid = str(node.get("id"))
            x, y = node_pos.get(nid, (cx, cy))
            in_degree = int(node.get("in_degree", 0) or 0)
            r = max(6, min(6 + in_degree * 2, 18))
            color = _node_color(nid, anti_pattern_files, entry_points)
            label = _truncate_label(Path(nid).name)
            nodes_svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="{color}" />')
            labels_svg.append(
                f'<text x="{x:.2f}" y="{y + r + 12:.2f}" text-anchor="middle" '
                'fill="#cbd5e1" font-size="9px">'
                f"{label}</text>"
            )
    else:
        module_files: Dict[str, Set[str]] = {}
        for node in nodes:
            nid = str(node.get("id"))
            module_files.setdefault(_module_name(nid), set()).add(nid)
        modules = sorted(module_files.keys())
        mod_pos: Dict[str, Tuple[float, float]] = {}
        if modules:
            for idx, module in enumerate(modules):
                ang = (2 * math.pi * idx) / len(modules)
                mx = cx + (group_radius * math.cos(ang))
                my = cy + (group_radius * math.sin(ang))
                mod_pos[module] = (mx, my)

        edge_pairs: Set[Tuple[str, str]] = set()
        for edge in edges_raw:
            if not isinstance(edge, dict):
                continue
            src = edge.get("source")
            tgt = edge.get("target")
            if src is None or tgt is None:
                continue
            sm = _module_name(str(src))
            tm = _module_name(str(tgt))
            if sm == tm:
                continue
            edge_pairs.add((sm, tm))

        for sm, tm in sorted(edge_pairs):
            if sm not in mod_pos or tm not in mod_pos:
                continue
            x1, y1 = mod_pos[sm]
            x2, y2 = mod_pos[tm]
            edges_svg.append(
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                'stroke="#94a3b8" stroke-width="0.8" opacity="0.4" />'
            )

        for module in modules:
            x, y = mod_pos[module]
            files = module_files[module]
            r = max(10, min(len(files) * 3, 35))
            color = "#ef4444" if any(f in anti_pattern_files for f in files) else "#60a5fa"
            nodes_svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="{color}" />')
            labels_svg.append(
                f'<text x="{x:.2f}" y="{y + r + 12:.2f}" text-anchor="middle" '
                'fill="#cbd5e1" font-size="9px">'
                f"{_truncate_label(module)}</text>"
            )

    legend_y = height - 60
    legend = [
        f'<circle cx="16" cy="{legend_y}" r="6" fill="#ef4444" />',
        f'<text x="28" y="{legend_y + 3}" fill="#cbd5e1" font-size="11px">Anti-pattern</text>',
        f'<circle cx="16" cy="{legend_y + 20}" r="6" fill="#22c55e" />',
        f'<text x="28" y="{legend_y + 23}" fill="#cbd5e1" font-size="11px">Entry point</text>',
        f'<circle cx="16" cy="{legend_y + 40}" r="6" fill="#60a5fa" />',
        f'<text x="28" y="{legend_y + 43}" fill="#cbd5e1" font-size="11px">Regular</text>',
    ]

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" style="background:#0f172a">'
        + "".join(edges_svg)
        + "".join(nodes_svg)
        + "".join(labels_svg)
        + "".join(legend)
        + "</svg>"
    )
