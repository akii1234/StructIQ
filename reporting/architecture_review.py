"""Generate a deterministic architecture review from phase outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def generate_review(
    dep_analysis: dict,
    arch_insights: dict,
    mod_plan: dict,
    discovery: dict,
    llm_client: Any = None,
) -> dict:
    cycles = dep_analysis.get("cycles") or []
    coupling_scores = dep_analysis.get("coupling_scores") or []
    entry_points = dep_analysis.get("entry_points") or []
    anti_patterns = arch_insights.get("anti_patterns") or []
    tasks = (mod_plan.get("tasks") or [])
    execution_plan = mod_plan.get("execution_plan") or []
    summary_block = dep_analysis.get("summary") or {}

    files_list = discovery.get("files") or []
    file_count = (discovery.get("summary") or {}).get("total_files", 0) or len(files_list)
    modules = set()
    for f in files_list:
        if isinstance(f, dict):
            mod = f.get("module")
            if mod:
                modules.add(str(mod))
    module_count = len(modules)

    anti_pattern_locations: set[str] = set()
    for ap in anti_patterns:
        if isinstance(ap, dict):
            for loc in (ap.get("locations") or []):
                anti_pattern_locations.add(str(loc))
            if ap.get("file"):
                anti_pattern_locations.add(str(ap["file"]))

    def _instability(entry: dict) -> float:
        if not isinstance(entry, dict):
            return 0.0
        aff = int(entry.get("afferent_coupling", 0) or 0)
        eff = int(entry.get("efferent_coupling", 0) or 0)
        total = aff + eff
        return float(entry.get("instability", eff / total if total else 0.0))

    scores_sorted = sorted(coupling_scores, key=_instability, reverse=True)

    severity_counts: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for ap in anti_patterns:
        if isinstance(ap, dict):
            sev = str(ap.get("severity", "medium")).lower()
            if sev in severity_counts:
                severity_counts[sev] += 1

    cycle_count = len(cycles)
    anti_pattern_count = len(anti_patterns)

    issues: Dict[str, List[dict]] = {"critical": [], "high": [], "medium": [], "low": []}

    for cycle in cycles:
        if isinstance(cycle, list) and cycle:
            names = [str(c) for c in cycle]
            issues["critical"].append({
                "issue": f"Circular dependency: {' → '.join(names)}",
                "location": names[0],
                "impact": "Breaks static analysis, deployment ordering, and refactoring safety",
            })
            severity_counts["critical"] += 1

    for entry in scores_sorted:
        if not isinstance(entry, dict):
            continue
        score = _instability(entry)
        fname = str(entry.get("file", ""))
        if score > 0.7 and fname in anti_pattern_locations:
            issues["critical"].append({
                "issue": "Highly coupled god file",
                "location": Path(fname).name,
                "impact": "Single change ripples across the codebase",
            })
            severity_counts["critical"] += 1

    for ap in anti_patterns:
        if not isinstance(ap, dict):
            continue
        sev = str(ap.get("severity", "medium")).lower()
        locations = ap.get("locations") or []
        loc_str = ", ".join(str(l) for l in locations[:3]) if locations else str(ap.get("file", "unknown"))
        entry = {
            "issue": str(ap.get("type", "unknown")).replace("_", " ").title(),
            "location": loc_str,
            "impact": str(ap.get("description", "")),
        }
        if sev == "high":
            issues["high"].append(entry)
        elif sev == "medium":
            issues["medium"].append(entry)
        elif sev == "low":
            issues["low"].append(entry)

    critical_files = {i["location"] for i in issues["critical"]}
    medium_coupling_count = 0
    for entry in scores_sorted:
        if not isinstance(entry, dict):
            continue
        score = _instability(entry)
        fname = str(entry.get("file", ""))
        short = Path(fname).name
        if score > 0.5 and short not in critical_files and medium_coupling_count < 3:
            issues["medium"].append({
                "issue": "High coupling score",
                "location": short,
                "impact": f"Coupling score {score:.2f} — changes here affect many dependents",
            })
            medium_coupling_count += 1

    for task in tasks:
        if not isinstance(task, dict):
            continue
        p_score = float(task.get("priority_score", task.get("priority", 1)) or 1)
        if p_score < 0.3:
            affected = task.get("affected_files") or []
            issues["low"].append({
                "issue": str(task.get("task_type", task.get("type", "unknown"))).replace("_", " ").title(),
                "location": ", ".join(str(f) for f in affected[:2]) if affected else "unknown",
                "impact": "Low priority — address after higher severity items",
            })

    # --- strengths ---
    strengths: List[dict] = []
    nodes_count = summary_block.get("total_files_analyzed", file_count)

    if cycle_count == 0:
        strengths.append({
            "strength": "No circular dependencies",
            "evidence": f"{nodes_count} files with clean acyclic graph",
            "confidence": "High",
        })

    all_scores = [_instability(e) for e in coupling_scores if isinstance(e, dict)]
    if all_scores:
        avg = sum(all_scores) / len(all_scores)
        if avg < 0.3:
            strengths.append({
                "strength": "Low average coupling",
                "evidence": f"Mean coupling score {avg:.2f}",
                "confidence": "High",
            })
        elif avg < 0.5:
            strengths.append({
                "strength": "Moderate average coupling",
                "evidence": f"Mean coupling score {avg:.2f}",
                "confidence": "Medium",
            })

    if anti_pattern_count == 0:
        strengths.append({
            "strength": "No anti-patterns detected",
            "evidence": "Clean architecture across all analyzed files",
            "confidence": "High",
        })

    if entry_points:
        strengths.append({
            "strength": "Clear entry points identified",
            "evidence": f"{len(entry_points)} entry point(s) found",
            "confidence": "High",
        })

    if module_count > 1:
        strengths.append({
            "strength": "Modular structure",
            "evidence": f"{module_count} distinct modules",
            "confidence": "Medium",
        })

    # --- coupling map ---
    coupling_map: List[dict] = []
    entry_set = set(str(e) for e in entry_points)
    for entry in scores_sorted[:8]:
        if not isinstance(entry, dict):
            continue
        fname = str(entry.get("file", ""))
        score = _instability(entry)
        if fname in entry_set:
            note = "Entry point"
        elif score > 0.7:
            note = "High centrality"
        elif score > 0.4:
            note = "Moderate coupling"
        else:
            note = "Normal"
        coupling_map.append({
            "file": Path(fname).name,
            "score": round(score, 3),
            "note": note,
        })

    # --- fix order ---
    fix_order: List[dict] = []
    if isinstance(execution_plan, list):
        for i, step in enumerate(execution_plan):
            if isinstance(step, dict):
                fix_order.append({
                    "step": i + 1,
                    "action": str(step.get("action", step.get("step", ""))),
                    "files": step.get("files") or [],
                    "risk": str(step.get("risk", "medium")),
                })

    # --- executive summary ---
    sev_parts = []
    for sev_name in ("critical", "high", "medium", "low"):
        cnt = severity_counts[sev_name]
        if cnt > 0:
            sev_parts.append(f"{cnt} {sev_name}")
    severity_breakdown = ", ".join(sev_parts) if sev_parts else "no severity tiers flagged"

    if issues["critical"]:
        top_issue = issues["critical"][0]["issue"]
    elif issues["high"]:
        top_issue = issues["high"][0]["issue"]
    else:
        top_issue = "no critical issues"

    executive_summary = (
        f"{file_count} files scanned across {module_count} modules. "
        f"{cycle_count} dependency cycle(s) found. "
        f"{anti_pattern_count} anti-pattern(s) detected across {severity_breakdown}. "
        f"Primary concern: {top_issue}."
    )

    if llm_client is not None:
        try:
            prompt = (
                "You are a software architecture reviewer. "
                "Given the following template summary of a codebase analysis, "
                "rewrite it as a polished 2-3 sentence executive summary. "
                "Keep all numbers accurate. Be concise and professional. "
                "Return JSON with a single key 'executive_summary'."
            )
            response = llm_client.generate_json(prompt, executive_summary)
            if isinstance(response, dict):
                llm_summary = str(response.get("executive_summary", "")).strip()
                if llm_summary:
                    executive_summary = llm_summary
        except Exception:
            pass

    return {
        "executive_summary": executive_summary,
        "strengths": strengths,
        "issues": issues,
        "coupling_map": coupling_map,
        "fix_order": fix_order,
    }
