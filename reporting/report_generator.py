"""Assemble a self-contained HTML report from StructIQ run outputs."""

from __future__ import annotations

import json
from pathlib import Path

from StructIQ.config import settings
from StructIQ.generators.json_writer import read_json_file
from StructIQ.llm.client import OpenAIClient
from StructIQ.reporting.svg_generator import generate_dependency_svg


class ReportGenerator:
    def _generate_narrative(
        self, system_summary: str, anti_patterns: list, decision: str, plan_mode: str
    ) -> str:
        if not settings.enable_llm:
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
            response = OpenAIClient().generate_json(prompt, json.dumps(payload))
            return str(response.get("narrative", "")).strip() if isinstance(response, dict) else ""
        except Exception:
            return ""

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
        svg = generate_dependency_svg(dep_graph, anti_pattern_files, entry_points_set)

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
        narrative = self._generate_narrative(
            system_summary, anti_patterns, decision, plan_mode
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
    .cards {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
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
      </div>
      {"<div class='surface' style='margin-top:12px;margin-bottom:4px;color:#e2e8f0;font-size:15px;line-height:1.6'>" + esc(narrative) + "</div>" if narrative else ""}
      <div class="surface" style="margin-top:12px;color:#cbd5e1">{esc(system_summary or "No system summary available.")}</div>
    </section>

    <section id="dependencies">
      <h2>Dependencies</h2>
      <div style="color:#94a3b8;font-size:13px;margin-bottom:8px">Nodes: {len(nodes)} | Edges: {len(edges)}</div>
      <div class="surface" style="overflow:auto">{svg}</div>
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
