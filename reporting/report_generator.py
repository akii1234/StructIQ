"""Assemble a self-contained HTML report from StructIQ run outputs."""

from __future__ import annotations

import json
from pathlib import Path

from StructIQ.generators.json_writer import read_json_file
from StructIQ.llm.client import LLMClient


_EXPLAIN_BLOCK = """
<section id="explain-section" style="margin:2rem 0; padding:1.5rem; background:#111118; border:1px solid #1e1e2e; border-radius:6px;">
  <h3 style="font-family:sans-serif; font-size:1rem; color:#7c6af7; margin-bottom:1rem;">Ask a Question About This Run</h3>
  <div style="display:flex; gap:0.75rem;">
    <input id="explain-input" type="text" maxlength="500"
      placeholder="e.g. Which files should I not touch before the release?"
      style="flex:1; padding:0.6rem 0.8rem; background:#09090f; border:1px solid #1e1e2e; border-radius:4px; color:#e2e8f0; font-size:0.85rem;"
    />
    <button onclick="askExplain()" style="padding:0.6rem 1.2rem; background:#7c6af7; color:white; border:none; border-radius:4px; cursor:pointer; font-size:0.85rem;">Ask</button>
  </div>
  <div id="explain-answer" style="margin-top:1rem; font-size:0.85rem; color:#e2e8f0; line-height:1.6; display:none;"></div>
  <script>
    async function askExplain() {{
      const q = document.getElementById('explain-input').value.trim();
      if (!q) return;
      const ans = document.getElementById('explain-answer');
      ans.style.display = 'block';
      ans.textContent = 'Thinking...';
      try {{
        const res = await fetch('/explain/{RUN_ID}', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{question: q}})
        }});
        const data = await res.json();
        ans.textContent = data.answer || data.detail || 'No response.';
      }} catch(e) {{
        ans.textContent = 'Request failed: ' + e.message;
      }}
    }}
  </script>
</section>
"""


def generate_report_html(
    run_id: str,
    phase1_output: dict,
    dep_graph: dict,
    dep_analysis: dict,
    arch_insights: dict,
    mod_plan: dict,
    llm_client: "LLMClient | None" = None,
) -> str:
    """Generate a self-contained HTML report string from structured run data."""
    generator = ReportGenerator(llm_client=llm_client)

    anti_patterns = arch_insights.get("anti_patterns") or []
    anti_pattern_files = {
        str(ap.get("file"))
        for ap in anti_patterns
        if isinstance(ap, dict) and ap.get("file")
    }
    entry_points_set = {
        str(ep) for ep in (dep_analysis.get("entry_points") or []) if ep
    }

    nodes = dep_graph.get("nodes") or []
    edges = dep_graph.get("edges") or []
    graph_html = generator._render_graph_panel(dep_graph, anti_pattern_files, entry_points_set)

    files = phase1_output.get("files") or []
    total_files = len(files)
    services = arch_insights.get("services") or {}
    services_count = len(services) if isinstance(services, dict) else 0
    anti_count = len(anti_patterns) if isinstance(anti_patterns, list) else 0
    decision = str(mod_plan.get("decision", "") or "")
    decision_label = (
        "No Action Required"
        if decision == "no_action_required"
        else "Action Required"
    )
    decision_color = "#22c55e" if decision == "no_action_required" else "#f59e0b"
    system_summary = str(arch_insights.get("system_summary", "") or "")

    most_depended = dep_analysis.get("most_depended_on") or []
    most_dependencies = dep_analysis.get("most_dependencies") or []

    plan_mode = str(mod_plan.get("plan_mode", "direct") or "direct")
    plan_summary = str(mod_plan.get("plan_summary", "") or "")
    execution_plan = mod_plan.get("execution_plan") or []
    tasks = mod_plan.get("tasks") or []
    dominated_tasks = mod_plan.get("dominated_tasks") or []
    reason = str(mod_plan.get("reason", "") or "")

    llm_enabled = False

    narrative = generator._generate_narrative(
        system_summary, anti_patterns, decision, plan_mode,
        llm_client=llm_client,
    )

    def esc(val: object) -> str:
        text = str(val)
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def rows_top5(items: list, key: str) -> str:
        rows = []
        for rec in items[:5]:
            if not isinstance(rec, dict):
                continue
            file_val = Path(str(rec.get("file", ""))).name
            metric = rec.get(key, 0)
            rows.append(
                f"<tr><td>{esc(file_val)}</td><td style='text-align:right'>{esc(metric)}</td></tr>"
            )
        return "".join(rows) or "<tr><td colspan='2' style='color:#94a3b8'>No data</td></tr>"

    def anti_pattern_cards() -> str:
        if not anti_patterns:
            return (
                "<div style='background:#14532d;border:1px solid #22c55e;padding:12px;"
                "border-radius:10px;color:#dcfce7'>No issues detected</div>"
            )
        cards = []
        for ap in anti_patterns:
            if not isinstance(ap, dict):
                continue
            ap_type = str(ap.get("type", "unknown"))
            severity = str(ap.get("severity", ""))
            sev_color = "#ef4444" if severity == "high" else "#f59e0b" if severity == "medium" else "#22c55e"
            subject = ap.get("file") or ap.get("module") or ", ".join(ap.get("files", [])[:3])
            desc = ap.get("description", "")
            extra = ""
            if ap_type == "high_coupling":
                extra = (
                    f"<div style='color:#94a3b8;font-size:12px'>"
                    f"Afferent: {esc(ap.get('afferent_coupling', 0))} | "
                    f"Efferent: {esc(ap.get('efferent_coupling', 0))}</div>"
                )
            cards.append(
                "<div style='background:#1e293b;border:1px solid #334155;border-radius:12px;padding:12px;margin-bottom:12px'>"
                f"<div><span style='background:{sev_color};color:#0f172a;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700'>{esc(ap_type)}</span> "
                f"<span style='color:#94a3b8;font-size:12px'>Severity: {esc(severity)}</span></div>"
                f"<div style='color:#f1f5f9;font-weight:600;margin-top:6px'>{esc(subject)}</div>"
                f"<div style='color:#cbd5e1;font-size:13px;margin-top:4px'>{esc(desc)}</div>"
                f"{extra}"
                "</div>"
            )
        return "".join(cards)

    def tasks_table() -> str:
        if not tasks:
            return "<div style='color:#94a3b8'>No tasks</div>"
        rows = []
        for t in tasks:
            if not isinstance(t, dict):
                continue
            target = ", ".join(str(x) for x in (t.get("target") or []))
            rows.append(
                "<tr>"
                f"<td>{esc(t.get('type', ''))}</td>"
                f"<td>{esc(target)}</td>"
                f"<td>{esc(t.get('priority', ''))}</td>"
                f"<td>{esc(t.get('confidence', ''))}</td>"
                f"<td>{esc(t.get('selected_strategy', ''))}</td>"
                "</tr>"
            )
        return (
            "<table style='width:100%;border-collapse:collapse'>"
            "<thead><tr>"
            "<th>Type</th><th>Target</th><th>Priority</th><th>Confidence</th><th>Selected Strategy</th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

    def render_execution_plan() -> str:
        if not execution_plan:
            return "<div style='color:#94a3b8'>No execution steps</div>"
        out = []
        for line in execution_plan:
            line_s = str(line)
            if line_s.startswith("[Change"):
                out.append(
                    f"<div style='font-weight:700;color:#f1f5f9;margin-top:10px'>{esc(line_s)}</div>"
                )
            else:
                out.append(
                    f"<pre style='margin:0;color:#cbd5e1;font-size:12px;white-space:pre-wrap'>{esc(line_s)}</pre>"
                )
        return "".join(out)

    llm_card = (
        "<div class='card'>"
        "<div style='color:#94a3b8;font-size:12px'>LLM</div>"
        "<div style='font-size:14px;font-weight:700;color:#475569'>Disabled</div>"
        "<div style='color:#64748b;font-size:11px;margin-top:4px'>Static analysis only</div>"
        "</div>"
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>StructIQ Report</title>
  <style>
    body {{ margin:0; background:#0f172a; color:#f1f5f9; font-family:Inter,Arial,sans-serif; }}
    a {{ color:#94a3b8; text-decoration:none; }}
    a:hover {{ color:#f1f5f9; }}
    .wrap {{ max-width:1200px; margin:0 auto; padding:24px; }}
    section {{ margin:48px 0; }}
    .cards {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; }}
    .card {{ background:#1e293b; border:1px solid #334155; border-radius:12px; padding:14px; }}
    table th, table td {{ border-bottom:1px solid #334155; padding:8px; text-align:left; font-size:13px; }}
    .surface {{ background:#1e293b; border:1px solid #334155; border-radius:12px; padding:12px; }}
  </style>
</head>
<body>
  <nav style="position:sticky;top:0;z-index:100;background:#1e293b;border-bottom:1px solid #334155;padding:12px 24px;display:flex;gap:24px;align-items:center">
    <span style="font-weight:700;color:#f1f5f9">StructIQ</span>
    <a href="#overview">Overview</a>
    <a href="#dependencies">Dependencies</a>
    <a href="#architecture">Architecture</a>
    <a href="#plan">Plan</a>
    <span style="margin-left:auto;color:#94a3b8;font-size:12px">Run: {esc(run_id[:8])}</span>
  </nav>

  <div class="wrap">
    <section id="overview">
      <h2>Overview</h2>
      <div class="cards">
        <div class="card"><div style="color:#94a3b8;font-size:12px">Total files analyzed</div><div style="font-size:26px;font-weight:700">{total_files}</div></div>
        <div class="card"><div style="color:#94a3b8;font-size:12px">Services detected</div><div style="font-size:26px;font-weight:700">{services_count}</div></div>
        <div class="card"><div style="color:#94a3b8;font-size:12px">Anti-patterns found</div><div style="font-size:26px;font-weight:700">{anti_count}</div></div>
        <div class="card"><div style="color:#94a3b8;font-size:12px">Decision</div><div style="font-size:18px;font-weight:700;color:{decision_color}">{esc(decision_label)}</div></div>
        {llm_card}
      </div>
      {"<div class='surface' style='margin-top:12px;margin-bottom:4px;color:#e2e8f0;font-size:15px;line-height:1.6'>" + esc(narrative) + "</div>" if narrative else ""}
      <div class="surface" style="margin-top:12px;color:#cbd5e1">{esc(system_summary or "No system summary available.")}</div>
    </section>

    <section id="dependencies">
      <h2>Dependencies</h2>
      <div style="color:#94a3b8;font-size:13px;margin-bottom:8px">Nodes: {len(nodes)} | Edges: {len(edges)}</div>
      {graph_html}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px">
        <div class="surface">
          <h3 style="margin-top:0">Most Depended On</h3>
          <table style="width:100%;border-collapse:collapse"><tbody>{rows_top5(most_depended, "in_degree")}</tbody></table>
        </div>
        <div class="surface">
          <h3 style="margin-top:0">Most Dependencies</h3>
          <table style="width:100%;border-collapse:collapse"><tbody>{rows_top5(most_dependencies, "out_degree")}</tbody></table>
        </div>
      </div>
    </section>

    <section id="architecture">
      <h2>Architecture</h2>
      {anti_pattern_cards()}
    </section>

    <section id="plan">
      <h2>Plan</h2>
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <span style="padding:4px 10px;border-radius:999px;background:{decision_color};color:#0f172a;font-weight:700">{esc(decision_label)}</span>
        <span style="padding:4px 10px;border-radius:999px;background:#3b82f6;color:#0f172a;font-weight:700">{esc(plan_mode)}</span>
      </div>
      {"<div class='surface' style='margin-bottom:12px;color:#f1f5f9'>" + esc(plan_summary) + "</div>" if plan_summary else ""}
      {("<div class='surface' style='margin-bottom:12px;color:#cbd5e1'>" + esc(reason) + "</div>") if decision == "no_action_required" and reason else ""}
      {("<div class='surface' style='margin-bottom:12px'><strong style='color:#f1f5f9'>Dominated tasks (removed as redundant):</strong>" + "".join(f"<div style='color:#94a3b8;font-size:13px;margin-top:4px'>{esc(t.get('type',''))} — {esc(', '.join(str(x) for x in (t.get('target') or [])))} <span style='color:#475569'>({esc(t.get('dominated_by',''))})</span></div>" for t in dominated_tasks if isinstance(t, dict)) + "</div>") if decision == "no_action_required" and dominated_tasks else ""}
      {"<div class='surface'>" + tasks_table() + "</div>" if decision != "no_action_required" else ""}
      {"<div class='surface' style='margin-top:12px'>" + render_execution_plan() + "</div>" if decision != "no_action_required" else ""}
    </section>
  </div>
</body>
</html>"""

    explain_block = _EXPLAIN_BLOCK.replace("{RUN_ID}", str(run_id))
    html = html.replace("</body>", explain_block + "\n</body>", 1)
    return html


class ReportGenerator:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client

    def _generate_narrative(
        self,
        system_summary: str,
        anti_patterns: list,
        decision: str,
        plan_mode: str,
        llm_client: LLMClient | None = None,
    ) -> str:
        if llm_client is None:
            return ""
        payload = {
            "system_summary": system_summary[:500],
            "anti_pattern_count": len(anti_patterns),
            "anti_pattern_types": list(
                {ap.get("type") for ap in anti_patterns if isinstance(ap, dict)}
            )[:8],
            "high_severity_count": sum(
                1
                for ap in anti_patterns
                if isinstance(ap, dict) and ap.get("severity") == "high"
            ),
            "decision": decision,
            "plan_mode": plan_mode,
        }
        prompt = (
            "You are a software architecture advisor writing for a technical audience. "
            "Return JSON with a single key 'narrative' containing a 3-5 sentence plain-English "
            "summary of this codebase's architectural health. Lead with the most critical finding. "
            "End with one sentence on what the modernization plan addresses. "
            "Do not use bullet points, markdown, or code. Write in flowing prose."
        )
        try:
            response = llm_client.generate_json(prompt, json.dumps(payload))
            return str(response.get("narrative", "")).strip() if isinstance(response, dict) else ""
        except Exception:
            return ""

    def _render_graph_panel(
        self,
        dep_graph: dict,
        anti_pattern_files: set,
        entry_points_set: set,
    ) -> str:
        import json as _json
        from pathlib import Path

        nodes_raw = dep_graph.get("nodes") or []
        edges_raw = dep_graph.get("edges") or []

        # ── Build file-to-module map ──────────────────────────────────────────
        file_to_module: dict[str, str] = {}
        for n in nodes_raw:
            nid = str(n.get("id", ""))
            mod = str(n.get("module") or Path(nid).parts[0] if nid else "root")
            file_to_module[nid] = mod

        # ── Level 1: module-level aggregation ────────────────────────────────
        module_meta: dict[str, dict] = {}
        for n in nodes_raw:
            nid = str(n.get("id", ""))
            mod = file_to_module[nid]
            if mod not in module_meta:
                module_meta[mod] = {
                    "id": mod, "label": mod,
                    "is_ap": False, "is_entry": False,
                    "in_degree": 0, "out_degree": 0, "file_count": 0,
                }
            module_meta[mod]["in_degree"] += int(n.get("in_degree", 0) or 0)
            module_meta[mod]["out_degree"] += int(n.get("out_degree", 0) or 0)
            module_meta[mod]["file_count"] += 1
            if nid in anti_pattern_files:
                module_meta[mod]["is_ap"] = True
            if nid in entry_points_set:
                module_meta[mod]["is_entry"] = True

        l1_nodes = [{"data": v} for v in module_meta.values()]
        seen_l1: set[tuple] = set()
        l1_edges = []
        for e in edges_raw:
            sm = file_to_module.get(str(e.get("source", "")), "")
            tm = file_to_module.get(str(e.get("target", "")), "")
            if sm and tm and sm != tm and (sm, tm) not in seen_l1:
                seen_l1.add((sm, tm))
                l1_edges.append({"data": {"source": sm, "target": tm}})

        # ── Level 2: per-module file-level views ──────────────────────────────
        module_views: dict[str, dict] = {}
        for mod in module_meta:
            mod_node_ids = {
                str(n.get("id", ""))
                for n in nodes_raw
                if file_to_module.get(str(n.get("id", ""))) == mod
                and (int(n.get("in_degree", 0) or 0) + int(n.get("out_degree", 0) or 0)) > 0
            }
            if not mod_node_ids:
                mod_node_ids = {
                    str(n.get("id", ""))
                    for n in nodes_raw
                    if file_to_module.get(str(n.get("id", ""))) == mod
                }

            file_nodes = []
            for n in nodes_raw:
                nid = str(n.get("id", ""))
                if nid not in mod_node_ids:
                    continue
                label = Path(nid).name
                file_nodes.append({"data": {
                    "id": nid,
                    "label": label,
                    "module": mod,
                    "is_ap": nid in anti_pattern_files,
                    "is_entry": nid in entry_points_set,
                    "in_degree": int(n.get("in_degree", 0) or 0),
                    "out_degree": int(n.get("out_degree", 0) or 0),
                }})

            cross_mods: set[str] = set()
            for e in edges_raw:
                s, t = str(e.get("source", "")), str(e.get("target", ""))
                if s in mod_node_ids and file_to_module.get(t) != mod:
                    cross_mods.add(file_to_module.get(t, ""))
                if t in mod_node_ids and file_to_module.get(s) != mod:
                    cross_mods.add(file_to_module.get(s, ""))
            cross_mods.discard("")

            stub_nodes = [
                {"data": {"id": f"__stub_{cm}", "label": f"[{cm}]",
                           "is_stub": True, "is_ap": False, "is_entry": False,
                           "in_degree": 0, "out_degree": 0}}
                for cm in cross_mods
            ]

            file_edges = []
            seen_l2: set[tuple] = set()
            for e in edges_raw:
                s, t = str(e.get("source", "")), str(e.get("target", ""))
                sm2 = file_to_module.get(s, "")
                tm2 = file_to_module.get(t, "")
                src_node = s if s in mod_node_ids else None
                tgt_node = t if t in mod_node_ids else (f"__stub_{tm2}" if tm2 in cross_mods else None)
                if not src_node:
                    src_node = s if t in mod_node_ids else None
                    if src_node:
                        tgt_node = t if t in mod_node_ids else None
                        src_node = f"__stub_{sm2}" if sm2 in cross_mods else None
                        if src_node:
                            tgt_node = t if t in mod_node_ids else None

                if s in mod_node_ids and t in mod_node_ids:
                    k = (s, t)
                    if k not in seen_l2:
                        seen_l2.add(k)
                        file_edges.append({"data": {"source": s, "target": t}})
                elif s in mod_node_ids and tm2 in cross_mods:
                    k = (s, f"__stub_{tm2}")
                    if k not in seen_l2:
                        seen_l2.add(k)
                        file_edges.append({"data": {"source": s, "target": f"__stub_{tm2}"}})
                elif t in mod_node_ids and sm2 in cross_mods:
                    k = (f"__stub_{sm2}", t)
                    if k not in seen_l2:
                        seen_l2.add(k)
                        file_edges.append({"data": {"source": f"__stub_{sm2}", "target": t}})

            module_views[mod] = {
                "nodes": file_nodes + stub_nodes,
                "edges": file_edges,
                "file_count": module_meta[mod]["file_count"],
            }

        graph_data = _json.dumps({
            "l1": {"nodes": l1_nodes, "edges": l1_edges},
            "l2": module_views,
        })

        html = (
            '<div class="surface" style="padding:0;overflow:hidden;border-radius:12px">'
            '<div style="padding:10px 16px;border-bottom:1px solid #334155;display:flex;gap:12px;align-items:center;flex-wrap:wrap">'
            '<span style="font-weight:600;color:#f1f5f9">Dependency Graph</span>'
            '<span style="font-size:12px;color:#94a3b8" id="sg-breadcrumb">Module view — double-click a node to drill in</span>'
            '<span style="font-size:12px;color:#22c55e">&#9632; Entry</span>'
            '<span style="font-size:12px;color:#ef4444">&#9632; Anti-pattern</span>'
            '<span style="font-size:12px;color:#64748b">&#9632; External module stub</span>'
            '<button id="sg-back" onclick="sgBack()" style="display:none;background:#3b82f6;border:none;color:#fff;'
            'padding:4px 12px;border-radius:6px;cursor:pointer;font-size:12px">&#8592; Back</button>'
            '<button onclick="sgExport()" style="margin-left:auto;background:#334155;border:none;color:#f1f5f9;'
            'padding:4px 12px;border-radius:6px;cursor:pointer;font-size:12px">Export</button>'
            '<button onclick="sgCy&&sgCy.fit()" style="background:#334155;border:none;color:#f1f5f9;'
            'padding:4px 12px;border-radius:6px;cursor:pointer;font-size:12px">Reset zoom</button>'
            '</div>'
            '<div style="position:relative">'
            '<div id="sg-cy" style="width:100%;height:580px;background:#0f172a"></div>'
            '<div id="sg-tt" style="position:fixed;display:none;background:#1e293b;border:1px solid #475569;'
            'border-radius:8px;padding:8px 12px;font-size:12px;color:#f1f5f9;pointer-events:none;'
            'max-width:280px;z-index:9999;line-height:1.6"></div>'
            '</div>'
            '</div>'
            '<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.29.2/cytoscape.min.js"></script>'
            '<script src="https://cdnjs.cloudflare.com/ajax/libs/dagre/0.8.5/dagre.min.js"></script>'
            '<script src="https://cdn.jsdelivr.net/npm/cytoscape-dagre@2.5.0/cytoscape-dagre.min.js"></script>'
            '<script>'
            '(function(){'
            'if(typeof cytoscapeDagre!=="undefined")cytoscape.use(cytoscapeDagre);'
            'var DATA=__GRAPH_DATA__;'
            'var sgCy=null; window.sgCy=null;'
            'var tt=document.getElementById("sg-tt");'
            'var crumb=document.getElementById("sg-breadcrumb");'
            'var backBtn=document.getElementById("sg-back");'
            'var currentLevel="l1";'
            'var STYLE=['
            '{selector:"node",style:{"shape":"rectangle","width":"label","height":30,"padding":"10px",'
            '"background-color":"#3b82f6","border-width":1,"border-color":"#1d4ed8",'
            '"label":"data(label)","color":"#ffffff","font-size":11,"font-family":"monospace",'
            '"text-valign":"center","text-halign":"center","text-max-width":"140px","text-wrap":"ellipsis"}},'
            '{selector:"node[?is_ap]",style:{"background-color":"#ef4444","border-color":"#991b1b"}},'
            '{selector:"node[?is_entry]",style:{"background-color":"#22c55e","border-color":"#15803d","color":"#0f172a"}},'
            '{selector:"node[?is_stub]",style:{"background-color":"#1e293b","border-color":"#475569","color":"#64748b","border-style":"dashed"}},'
            '{selector:"node:selected",style:{"border-width":2,"border-color":"#f59e0b"}},'
            '{selector:"edge",style:{"width":1.5,"line-color":"#334155","target-arrow-color":"#475569",'
            '"target-arrow-shape":"triangle","curve-style":"bezier","arrow-scale":0.8}},'
            '{selector:"edge:selected",style:{"line-color":"#f59e0b","target-arrow-color":"#f59e0b"}}'
            '];'
            'function makeLayout(n){'
            'var useDagre=typeof cytoscapeDagre!=="undefined";'
            'if(useDagre)return{name:"dagre",rankDir:"TB",rankSep:70,nodeSep:40,animate:false,fit:true,padding:32};'
            'return n<=20?{name:"circle",animate:false,fit:true,padding:40}:{name:"cose",animate:false,nodeRepulsion:9000,idealEdgeLength:100,edgeElasticity:0.4,gravity:0.3,numIter:1000,fit:true,padding:28};'
            '}'
            'function renderGraph(elements, level, label){'
            'currentLevel=level;'
            'crumb.textContent=label;'
            'backBtn.style.display=level==="l1"?"none":"inline-block";'
            'if(sgCy){sgCy.destroy();}'
            'sgCy=cytoscape({container:document.getElementById("sg-cy"),elements:elements,'
            'style:STYLE,layout:makeLayout(elements.filter(function(e){return!e.data.source;}).length),'
            'wheelSensitivity:0.3});'
            'window.sgCy=sgCy;'
            'sgCy.on("mouseover","node",function(e){'
            'var n=e.target.data();'
            'var lines=["<strong>"+(n.label||n.id)+"</strong>"];'
            'if(n.file_count)lines.push(n.file_count+" files");'
            'if(n.in_degree||n.out_degree)lines.push("in: "+(n.in_degree||0)+" &nbsp; out: "+(n.out_degree||0));'
            'if(n.is_entry)lines.push("<span style=\'color:#22c55e\'>Entry point</span>");'
            'if(n.is_ap)lines.push("<span style=\'color:#ef4444\'>Anti-pattern</span>");'
            'if(n.is_stub)lines.push("<span style=\'color:#64748b\'>External module</span>");'
            'else if(level==="l1")lines.push("<em style=\'color:#94a3b8\'>Double-click to drill in</em>");'
            'tt.innerHTML=lines.join("<br>");tt.style.display="block";});'
            'sgCy.on("mouseout","node",function(){tt.style.display="none";});'
            'sgCy.on("mousemove",function(e){tt.style.left=(e.originalEvent.clientX+14)+"px";tt.style.top=(e.originalEvent.clientY-10)+"px";});'
            'sgCy.on("dblclick","node",function(e){'
            'var n=e.target.data();'
            'if(n.is_stub)return;'
            'var modId=n.id;'
            'if(level==="l1"&&DATA.l2[modId]){'
            'var view=DATA.l2[modId];'
            'renderGraph(view.nodes.concat(view.edges),"l2:"+modId,'
            '"Module: "+modId+" ("+view.file_count+" files) — click Back to return");'
            '}'
            '});'
            '}'
            'window.sgBack=function(){'
            'renderGraph(DATA.l1.nodes.concat(DATA.l1.edges),"l1","Module view — double-click a node to drill in");'
            '};'
            'renderGraph(DATA.l1.nodes.concat(DATA.l1.edges),"l1","Module view — double-click a node to drill in");'
            'window.sgExport=function(){'
            'if(!sgCy)return;'
            'var title=crumb.textContent;'
            'var png=sgCy.png({output:"base64uri",scale:3,full:true,bg:"#0f172a"});'
            'var w=window.open("","_blank");'
            'w.document.write("<!DOCTYPE html><html><head><meta charset=\'utf-8\'><title>StructIQ — Dependency Graph</title>"'
            '+"<style>body{margin:0;background:#0f172a;color:#f1f5f9;font-family:system-ui,Arial,sans-serif;}"'
            '+"h1{font-size:16px;font-weight:600;padding:20px 28px 12px;border-bottom:1px solid #334155;margin:0;}"'
            '+"p{font-size:12px;color:#64748b;padding:8px 28px;margin:0;}"'
            '+"img{display:block;max-width:100%;padding:20px 28px;box-sizing:border-box;}"'
            '+"@media print{h1,p{-webkit-print-color-adjust:exact;print-color-adjust:exact;}img{page-break-inside:avoid;}}"'
            '+"</style></head><body>"'
            '+"<h1>StructIQ — Dependency Graph</h1>"'
            '+"<p>"+title+"</p>"'
            '+"<img src=\'"+png+"\' />"'
            '+"<script>window.onload=function(){window.print();}<\\/script>"'
            '+"</body></html>");'
            'w.document.close();'
            '};'
            '})();'
            '</script>'
        )
        return html.replace("__GRAPH_DATA__", graph_data)

    def generate(self, run_dir: str, run_id: str) -> str:
        run_path = Path(run_dir)
        output = read_json_file(str(run_path / "output.json"), {})
        dep_graph = read_json_file(str(run_path / "dependency_graph.json"), {})
        dep_analysis = read_json_file(str(run_path / "dependency_analysis.json"), {})
        arch = read_json_file(str(run_path / "architecture_insights.json"), {})
        plan = read_json_file(str(run_path / "modernization_plan.json"), {})

        anti_patterns = arch.get("anti_patterns") or []
        anti_pattern_files = {
            str(ap.get("file"))
            for ap in anti_patterns
            if isinstance(ap, dict) and ap.get("file")
        }
        entry_points_set = {
            str(ep) for ep in (dep_analysis.get("entry_points") or []) if ep
        }

        nodes = dep_graph.get("nodes") or []
        edges = dep_graph.get("edges") or []
        graph_html = self._render_graph_panel(dep_graph, anti_pattern_files, entry_points_set)

        metrics = output.get("metrics") or {}
        total_files = int(metrics.get("total_files", 0) or 0)
        if total_files <= 0:
            total_files = len(output.get("files") or [])
        services = arch.get("services") or {}
        services_count = len(services) if isinstance(services, dict) else 0
        anti_count = len(anti_patterns) if isinstance(anti_patterns, list) else 0
        decision = str(plan.get("decision", "") or "")
        decision_label = (
            "No Action Required"
            if decision == "no_action_required"
            else "Action Required"
        )
        decision_color = "#22c55e" if decision == "no_action_required" else "#f59e0b"
        system_summary = str(arch.get("system_summary", "") or "")

        most_depended = dep_analysis.get("most_depended_on") or []
        most_dependencies = dep_analysis.get("most_dependencies") or []

        plan_mode = str(plan.get("plan_mode", "direct") or "direct")
        plan_summary = str(plan.get("plan_summary", "") or "")
        execution_plan = plan.get("execution_plan") or []
        tasks = plan.get("tasks") or []
        dominated_tasks = plan.get("dominated_tasks") or []
        reason = str(plan.get("reason", "") or "")

        snapshot = read_json_file(str(run_path / "snapshot.json"), {})
        llm_stats = snapshot.get("llm_stats") or {}
        llm_enabled = llm_stats.get("enabled", False)

        report_llm_client = self._llm_client
        if report_llm_client is None and llm_stats.get("enabled"):
            try:
                report_llm_client = LLMClient(
                    provider=llm_stats.get("provider") or "openai",
                    model=llm_stats.get("model") or None,
                )
            except Exception:
                report_llm_client = None

        narrative = self._generate_narrative(
            system_summary, anti_patterns, decision, plan_mode,
            llm_client=report_llm_client,
        )

        def esc(val: object) -> str:
            text = str(val)
            return (
                text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

        def rows_top5(items: list, key: str) -> str:
            rows = []
            for rec in items[:5]:
                if not isinstance(rec, dict):
                    continue
                file_val = Path(str(rec.get("file", ""))).name
                metric = rec.get(key, 0)
                rows.append(
                    f"<tr><td>{esc(file_val)}</td><td style='text-align:right'>{esc(metric)}</td></tr>"
                )
            return "".join(rows) or "<tr><td colspan='2' style='color:#94a3b8'>No data</td></tr>"

        def anti_pattern_cards() -> str:
            if not anti_patterns:
                return (
                    "<div style='background:#14532d;border:1px solid #22c55e;padding:12px;"
                    "border-radius:10px;color:#dcfce7'>No issues detected</div>"
                )
            cards = []
            for ap in anti_patterns:
                if not isinstance(ap, dict):
                    continue
                ap_type = str(ap.get("type", "unknown"))
                severity = str(ap.get("severity", ""))
                sev_color = "#ef4444" if severity == "high" else "#f59e0b" if severity == "medium" else "#22c55e"
                subject = ap.get("file") or ap.get("module") or ", ".join(ap.get("files", [])[:3])
                desc = ap.get("description", "")
                extra = ""
                if ap_type == "high_coupling":
                    extra = (
                        f"<div style='color:#94a3b8;font-size:12px'>"
                        f"Afferent: {esc(ap.get('afferent_coupling', 0))} | "
                        f"Efferent: {esc(ap.get('efferent_coupling', 0))}</div>"
                    )
                cards.append(
                    "<div style='background:#1e293b;border:1px solid #334155;border-radius:12px;padding:12px;margin-bottom:12px'>"
                    f"<div><span style='background:{sev_color};color:#0f172a;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700'>{esc(ap_type)}</span> "
                    f"<span style='color:#94a3b8;font-size:12px'>Severity: {esc(severity)}</span></div>"
                    f"<div style='color:#f1f5f9;font-weight:600;margin-top:6px'>{esc(subject)}</div>"
                    f"<div style='color:#cbd5e1;font-size:13px;margin-top:4px'>{esc(desc)}</div>"
                    f"{extra}"
                    "</div>"
                )
            return "".join(cards)

        def tasks_table() -> str:
            if not tasks:
                return "<div style='color:#94a3b8'>No tasks</div>"
            rows = []
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                target = ", ".join(str(x) for x in (t.get("target") or []))
                rows.append(
                    "<tr>"
                    f"<td>{esc(t.get('type', ''))}</td>"
                    f"<td>{esc(target)}</td>"
                    f"<td>{esc(t.get('priority', ''))}</td>"
                    f"<td>{esc(t.get('confidence', ''))}</td>"
                    f"<td>{esc(t.get('selected_strategy', ''))}</td>"
                    "</tr>"
                )
            return (
                "<table style='width:100%;border-collapse:collapse'>"
                "<thead><tr>"
                "<th>Type</th><th>Target</th><th>Priority</th><th>Confidence</th><th>Selected Strategy</th>"
                "</tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table>"
            )

        def render_execution_plan() -> str:
            if not execution_plan:
                return "<div style='color:#94a3b8'>No execution steps</div>"
            out = []
            for line in execution_plan:
                line_s = str(line)
                if line_s.startswith("[Change"):
                    out.append(
                        f"<div style='font-weight:700;color:#f1f5f9;margin-top:10px'>{esc(line_s)}</div>"
                    )
                else:
                    out.append(
                        f"<pre style='margin:0;color:#cbd5e1;font-size:12px;white-space:pre-wrap'>{esc(line_s)}</pre>"
                    )
            return "".join(out)

        def llm_stats_card() -> str:
            if not llm_enabled:
                return (
                    "<div class='card'>"
                    "<div style='color:#94a3b8;font-size:12px'>LLM</div>"
                    "<div style='font-size:14px;font-weight:700;color:#475569'>Disabled</div>"
                    "<div style='color:#64748b;font-size:11px;margin-top:4px'>Static analysis only</div>"
                    "</div>"
                )
            provider = esc(llm_stats.get("provider") or "openai")
            model = esc(llm_stats.get("model") or "default")
            phases = []
            if llm_stats.get("phase1_enabled"):
                phases.append("Phase 1")
            if llm_stats.get("phase3_narrative"):
                phases.append("Phase 3")
            if llm_stats.get("phase4_summary"):
                phases.append("Phase 4")
            phases_str = " · ".join(phases) if phases else "none"
            return (
                "<div class='card'>"
                "<div style='color:#94a3b8;font-size:12px'>LLM</div>"
                "<div style='font-size:14px;font-weight:700;color:#a78bfa'>"
                + provider + "</div>"
                "<div style='color:#64748b;font-size:11px;margin-top:2px'>" + model + "</div>"
                "<div style='color:#94a3b8;font-size:11px;margin-top:4px'>Used in: " + phases_str + "</div>"
                "</div>"
            )

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>StructIQ Report</title>
  <style>
    body {{ margin:0; background:#0f172a; color:#f1f5f9; font-family:Inter,Arial,sans-serif; }}
    a {{ color:#94a3b8; text-decoration:none; }}
    a:hover {{ color:#f1f5f9; }}
    .wrap {{ max-width:1200px; margin:0 auto; padding:24px; }}
    section {{ margin:48px 0; }}
    .cards {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; }}
    .card {{ background:#1e293b; border:1px solid #334155; border-radius:12px; padding:14px; }}
    table th, table td {{ border-bottom:1px solid #334155; padding:8px; text-align:left; font-size:13px; }}
    .surface {{ background:#1e293b; border:1px solid #334155; border-radius:12px; padding:12px; }}
  </style>
</head>
<body>
  <nav style="position:sticky;top:0;z-index:100;background:#1e293b;border-bottom:1px solid #334155;padding:12px 24px;display:flex;gap:24px;align-items:center">
    <span style="font-weight:700;color:#f1f5f9">StructIQ</span>
    <a href="#overview">Overview</a>
    <a href="#dependencies">Dependencies</a>
    <a href="#architecture">Architecture</a>
    <a href="#plan">Plan</a>
    <span style="margin-left:auto;color:#94a3b8;font-size:12px">Run: {esc(run_id[:8])}</span>
  </nav>

  <div class="wrap">
    <section id="overview">
      <h2>Overview</h2>
      <div class="cards">
        <div class="card"><div style="color:#94a3b8;font-size:12px">Total files analyzed</div><div style="font-size:26px;font-weight:700">{total_files}</div></div>
        <div class="card"><div style="color:#94a3b8;font-size:12px">Services detected</div><div style="font-size:26px;font-weight:700">{services_count}</div></div>
        <div class="card"><div style="color:#94a3b8;font-size:12px">Anti-patterns found</div><div style="font-size:26px;font-weight:700">{anti_count}</div></div>
        <div class="card"><div style="color:#94a3b8;font-size:12px">Decision</div><div style="font-size:18px;font-weight:700;color:{decision_color}">{esc(decision_label)}</div></div>
        {llm_stats_card()}
      </div>
      {"<div class='surface' style='margin-top:12px;margin-bottom:4px;color:#e2e8f0;font-size:15px;line-height:1.6'>" + esc(narrative) + "</div>" if narrative else ""}
      <div class="surface" style="margin-top:12px;color:#cbd5e1">{esc(system_summary or "No system summary available.")}</div>
    </section>

    <section id="dependencies">
      <h2>Dependencies</h2>
      <div style="color:#94a3b8;font-size:13px;margin-bottom:8px">Nodes: {len(nodes)} | Edges: {len(edges)}</div>
      {graph_html}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px">
        <div class="surface">
          <h3 style="margin-top:0">Most Depended On</h3>
          <table style="width:100%;border-collapse:collapse"><tbody>{rows_top5(most_depended, "in_degree")}</tbody></table>
        </div>
        <div class="surface">
          <h3 style="margin-top:0">Most Dependencies</h3>
          <table style="width:100%;border-collapse:collapse"><tbody>{rows_top5(most_dependencies, "out_degree")}</tbody></table>
        </div>
      </div>
    </section>

    <section id="architecture">
      <h2>Architecture</h2>
      {anti_pattern_cards()}
    </section>

    <section id="plan">
      <h2>Plan</h2>
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <span style="padding:4px 10px;border-radius:999px;background:{decision_color};color:#0f172a;font-weight:700">{esc(decision_label)}</span>
        <span style="padding:4px 10px;border-radius:999px;background:#3b82f6;color:#0f172a;font-weight:700">{esc(plan_mode)}</span>
      </div>
      {"<div class='surface' style='margin-bottom:12px;color:#f1f5f9'>" + esc(plan_summary) + "</div>" if plan_summary else ""}
      {("<div class='surface' style='margin-bottom:12px;color:#cbd5e1'>" + esc(reason) + "</div>") if decision == "no_action_required" and reason else ""}
      {("<div class='surface' style='margin-bottom:12px'><strong style='color:#f1f5f9'>Dominated tasks (removed as redundant):</strong>" + "".join(f"<div style='color:#94a3b8;font-size:13px;margin-top:4px'>{esc(t.get('type',''))} — {esc(', '.join(str(x) for x in (t.get('target') or [])))} <span style='color:#475569'>({esc(t.get('dominated_by',''))})</span></div>" for t in dominated_tasks if isinstance(t, dict)) + "</div>") if decision == "no_action_required" and dominated_tasks else ""}
      {"<div class='surface'>" + tasks_table() + "</div>" if decision != "no_action_required" else ""}
      {"<div class='surface' style='margin-top:12px'>" + render_execution_plan() + "</div>" if decision != "no_action_required" else ""}
    </section>
  </div>
</body>
</html>"""
