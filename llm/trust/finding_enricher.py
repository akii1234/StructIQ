"""Enrich high-severity anti-pattern findings with LLM-generated specific commentary."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from StructIQ.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_FINDINGS = 8  # cap to bound token usage (~230 tokens each)
_MAX_NEIGHBORS = 3

_SYSTEM_PROMPT = (
    "You are a software architecture advisor. "
    "For each finding, write specific architectural commentary — use the actual file or module name "
    "and its connections in every sentence. "
    'Return JSON: {"enriched": [{"id": N, "description": "...", '
    '"why": "...", "impact_if_ignored": "..."}]}. '
    "description: one sentence — what this file or module's pattern means architecturally (name it explicitly). "
    "why: one sentence — the specific architectural risk for this exact file or module. "
    "impact_if_ignored: one sentence — the concrete consequence if not fixed. "
    "For mega_module findings, 'imports' contains the file count and share percentage — use that. "
    "No markdown. No generic advice. No code blocks."
)


def _build_neighbor_map(
    graph: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Returns (importers, imports) maps built from graph edges."""
    importers: dict[str, list[str]] = {}
    imports_map: dict[str, list[str]] = {}
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        src = str(edge.get("source") or "").strip()
        tgt = str(edge.get("target") or "").strip()
        if src and tgt:
            importers.setdefault(tgt, []).append(src)
            imports_map.setdefault(src, []).append(tgt)
    return importers, imports_map


def _enrichment_is_plausible(ap: dict[str, Any], enriched_item: dict[str, Any]) -> bool:
    """Return True if enriched text is plausibly about the correct target.

    Rejects: (1) LLM wrote about the wrong file — target name absent.
             (2) Trivially short response — less than 70% of template length.
    """
    target = ap.get("file") or ap.get("module") or ""
    name = Path(target).stem if target else ""
    description = str(enriched_item.get("description") or "")
    why = str(enriched_item.get("why") or "")

    # Name check — skip for very short names (≤3 chars)
    if name and len(name) > 3:
        combined = (description + " " + why).lower()
        if name.lower() not in combined:
            return False

    # Length check — reject if shorter than 70% of original template
    template_len = len(str(ap.get("description") or ""))
    if template_len > 20 and len(description) < template_len * 0.7:
        return False

    return True


def enrich_findings(
    anti_patterns: list[dict[str, Any]],
    graph: dict[str, Any],
    llm_client: Any,
) -> list[dict[str, Any]]:
    """Return anti_patterns with enriched description/why/impact for high-severity findings.

    Non-fatal: on any LLM failure returns original anti_patterns unchanged.
    Only processes findings with severity == 'high'. Caps at _MAX_FINDINGS per call.
    """
    if not llm_client or not anti_patterns:
        return anti_patterns

    # Skip pattern types that are too many / too generic to benefit from LLM enrichment.
    _SKIP_TYPES = {"test_gap", "orphan_file"}
    # Enrich high severity always; also enrich medium for structural pattern types
    # (high_coupling is always emitted at medium by the detector but benefits most from enrichment).
    _ENRICH_MEDIUM_TYPES = {"high_coupling", "god_file", "weak_boundary", "mega_module"}

    high_severity = [
        (orig_idx, ap)
        for orig_idx, ap in enumerate(anti_patterns)
        if isinstance(ap, dict)
        and ap.get("type") not in _SKIP_TYPES
        and (
            str(ap.get("severity", "")).lower() == "high"
            or (
                str(ap.get("severity", "")).lower() == "medium"
                and ap.get("type") in _ENRICH_MEDIUM_TYPES
            )
        )
    ][:_MAX_FINDINGS]

    if not high_severity:
        return anti_patterns

    try:
        importers, imports_map = _build_neighbor_map(graph)

        findings_payload: list[dict[str, Any]] = []
        for finding_id, (_orig_idx, ap) in enumerate(high_severity):
            ap_type = ap.get("type", "")
            if ap_type == "cycle":
                files = ap.get("files") or []
                file_display = ", ".join(Path(str(f)).name for f in files[:3])
                afferent = 0
                efferent = 0
                imported_by: list[str] = []
                imports_list: list[str] = []
            elif ap_type in ("mega_module", "weak_boundary", "concentration_risk"):
                mod = str(ap.get("module") or "")
                if not mod:
                    metrics_dict = ap.get("metrics") if isinstance(ap.get("metrics"), dict) else {}
                    mod = str(metrics_dict.get("module") or "")
                if ap_type == "concentration_risk" and not mod:
                    mod = "system"
                file_display = mod or "unknown"
                afferent = int(ap.get("afferent_coupling", 0) or 0)
                efferent = int(ap.get("efferent_coupling", 0) or 0)
                imported_by = []
                imports_list = []
                # For mega_module, pass structural metrics so LLM has real context.
                if ap_type == "mega_module":
                    m = ap.get("metrics") if isinstance(ap.get("metrics"), dict) else {}
                    file_count = int(m.get("file_count", 0) or ap.get("file_count", 0) or 0)
                    share_pct = float(m.get("share_pct", 0) or ap.get("share_pct", 0) or 0)
                    if file_count:
                        imports_list = [f"{file_count} files ({share_pct:.0f}% of codebase)"]
            else:
                file_path = str(ap.get("file") or "")
                file_display = Path(file_path).name if file_path else "unknown"
                afferent = int(ap.get("afferent_coupling", 0) or 0)
                efferent = int(ap.get("efferent_coupling", 0) or 0)
                imported_by = [
                    Path(f).name
                    for f in importers.get(file_path, [])[:_MAX_NEIGHBORS]
                ]
                imports_list = [
                    Path(f).name
                    for f in imports_map.get(file_path, [])[:_MAX_NEIGHBORS]
                ]

            findings_payload.append(
                {
                    "id": finding_id,
                    "pattern": ap_type,
                    "file": file_display,
                    "afferent": afferent,
                    "efferent": efferent,
                    "imported_by": imported_by,
                    "imports": imports_list,
                }
            )

        response = llm_client.generate_json(
            _SYSTEM_PROMPT, json.dumps({"findings": findings_payload})
        )

        enriched_list = response.get("enriched")
        if not isinstance(enriched_list, list):
            return anti_patterns

        enriched_by_id: dict[int, dict[str, Any]] = {}
        for item in enriched_list:
            if isinstance(item, dict) and "id" in item:
                try:
                    enriched_by_id[int(item["id"])] = item
                except (TypeError, ValueError):
                    continue

        result = [dict(ap) for ap in anti_patterns]
        for finding_id, (orig_idx, _) in enumerate(high_severity):
            enriched = enriched_by_id.get(finding_id)
            if not enriched:
                continue
            if not _enrichment_is_plausible(high_severity[finding_id][1], enriched):
                logger.warning(
                    "FindingEnricher: rejected implausible enrichment for %s (%s)",
                    high_severity[finding_id][1].get("file")
                    or high_severity[finding_id][1].get("type"),
                    high_severity[finding_id][1].get("type"),
                )
                continue
            if enriched.get("description"):
                result[orig_idx]["description"] = str(enriched["description"]).strip()
            if enriched.get("why"):
                result[orig_idx]["enriched_why"] = str(enriched["why"]).strip()
            if enriched.get("impact_if_ignored"):
                result[orig_idx]["enriched_impact"] = str(
                    enriched["impact_if_ignored"]
                ).strip()

        return result

    except Exception as exc:
        logger.warning("FindingEnricher failed (non-fatal): %s", exc, exc_info=True)
        return anti_patterns
