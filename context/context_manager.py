"""Merge-safe project context persisted as JSON and human-readable Markdown.

No LLM usage — fully deterministic.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

from StructIQ.generators.json_writer import read_json_file, write_json_output


DEFAULT_CONTEXT: Dict[str, Any] = {
    "project_name": "StructIQ",
    "last_updated": "",
    "current_phase": "Phase 1",
    "capabilities": [
        "multi-language scanning",
        "cost-optimized summarization",
    ],
    "metrics": {
        "total_runs": 0,
        "avg_llm_calls": 0.0,
        "avg_cache_hits": 0.0,
    },
    "last_run_summary": {
        "run_id": "",
        "files_processed": 0,
        "llm_calls": 0,
        "skipped": 0,
    },
}


def _deep_merge_defaults(stored: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing keys from defaults without discarding stored values."""
    out = deepcopy(stored)
    for key, default_val in defaults.items():
        if key not in out:
            out[key] = deepcopy(default_val)
            continue
        if isinstance(default_val, dict) and isinstance(out[key], dict):
            out[key] = _deep_merge_defaults(out[key], default_val)
    return out


def _unique_capabilities(existing: List[str], defaults: List[str]) -> List[str]:
    """Preserve order; include defaults not already present."""
    seen: Set[str] = set()
    merged: List[str] = []
    for c in list(existing) + list(defaults):
        c = str(c).strip()
        if not c or c in seen:
            continue
        seen.add(c)
        merged.append(c)
    return merged


class ContextManager:
    """Load, merge, and persist cross-run project context."""

    def __init__(
        self,
        json_path: str = "data/context/project_context.json",
        md_path: str = "data/context/project_context.md",
    ) -> None:
        self.json_path = Path(json_path)
        self.md_path = Path(md_path)
        self._data: Dict[str, Any] = deepcopy(DEFAULT_CONTEXT)

    def load_existing_context(self) -> Dict[str, Any]:
        """Read JSON from disk or return defaults; always shape-normalized."""
        raw = read_json_file(str(self.json_path), {})
        if not raw:
            return deepcopy(DEFAULT_CONTEXT)
        return _deep_merge_defaults(raw, DEFAULT_CONTEXT)

    def save_context_json(self) -> None:
        """Write ``self._data`` to JSON (creates parent dirs)."""
        write_json_output(self._data, str(self.json_path))

    def update_context(self, run_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge a completed run into context, then save JSON and regenerate MD.

        ``run_data`` may include:
        - ``run_id`` (optional; generated if missing)
        - ``metrics`` (Phase 1 output metrics dict)
        - ``capabilities_added`` (optional list of strings)
        """
        previous = self.load_existing_context()
        prev_caps = list(previous.get("capabilities", []))
        default_caps = list(DEFAULT_CONTEXT["capabilities"])

        merged = deepcopy(previous)
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        )
        merged["project_name"] = DEFAULT_CONTEXT["project_name"]
        merged["last_updated"] = now
        merged["current_phase"] = run_data.get("current_phase") or merged.get(
            "current_phase", "Phase 1"
        )

        added = run_data.get("capabilities_added") or []
        if isinstance(added, str):
            added = [added]
        merged["capabilities"] = _unique_capabilities(
            list(prev_caps) + [str(x) for x in added if str(x).strip()],
            default_caps,
        )

        metrics_in = run_data.get("metrics") or {}
        llm_calls = int(metrics_in.get("llm_calls", 0) or 0)
        cache_hits = int(metrics_in.get("cache_hits", 0) or 0)

        prev_runs = int(merged.get("metrics", {}).get("total_runs", 0) or 0)
        new_runs = prev_runs + 1
        prev_avg_llm = float(merged.get("metrics", {}).get("avg_llm_calls", 0.0) or 0.0)
        prev_avg_cache = float(
            merged.get("metrics", {}).get("avg_cache_hits", 0.0) or 0.0
        )

        merged.setdefault("metrics", {})
        merged["metrics"]["total_runs"] = new_runs
        merged["metrics"]["avg_llm_calls"] = round(
            (prev_avg_llm * prev_runs + llm_calls) / new_runs, 4
        )
        merged["metrics"]["avg_cache_hits"] = round(
            (prev_avg_cache * prev_runs + cache_hits) / new_runs, 4
        )

        run_id = str(run_data.get("run_id") or "").strip() or _default_run_id()
        merged["last_run_summary"] = {
            "run_id": run_id,
            "files_processed": int(metrics_in.get("processed", 0) or 0),
            "llm_calls": llm_calls,
            "skipped": int(metrics_in.get("skipped", 0) or 0),
        }

        self._data = merged
        self.save_context_json()
        self.generate_context_md(previous_context=previous)
        return self._data

    def generate_context_md(self, previous_context: Dict[str, Any] | None = None) -> None:
        """Write Markdown view of ``self._data``; optional previous for diffs."""
        prev = previous_context or {}
        d = self._data
        caps = d.get("capabilities") or []
        m = d.get("metrics") or {}
        last = d.get("last_run_summary") or {}

        prev_caps = set(prev.get("capabilities") or [])
        new_caps = [c for c in caps if c not in prev_caps]

        pm = prev.get("metrics") or {}
        trends: List[str] = []
        if pm:
            old_llm = float(pm.get("avg_llm_calls", 0.0) or 0.0)
            new_llm = float(m.get("avg_llm_calls", 0.0) or 0.0)
            if new_llm > old_llm:
                trends.append(f"average LLM calls per run increasing ({old_llm} → {new_llm})")
            elif new_llm < old_llm:
                trends.append(f"average LLM calls per run decreasing ({old_llm} → {new_llm})")
            else:
                trends.append(f"average LLM calls per run stable ({new_llm})")

            old_ch = float(pm.get("avg_cache_hits", 0.0) or 0.0)
            new_ch = float(m.get("avg_cache_hits", 0.0) or 0.0)
            if new_ch > old_ch:
                trends.append(f"average cache hits per run increasing ({old_ch} → {new_ch})")
            elif new_ch < old_ch:
                trends.append(f"average cache hits per run decreasing ({old_ch} → {new_ch})")
            else:
                trends.append(f"average cache hits per run stable ({new_ch})")

        lines: List[str] = [
            f"# {d.get('project_name', 'Project')} Context",
            "",
            "## Current Phase",
            str(d.get("current_phase", "Phase 1")),
            "",
            f"*Last updated: {d.get('last_updated', '—')}*",
            "",
            "## Capabilities",
        ]
        for c in caps:
            lines.append(f"- {c}")
        if not caps:
            lines.append("- _(none listed)_")

        lines.extend(
            [
                "",
                "## Latest Run Summary",
                f"- **Run ID:** {last.get('run_id', '—')}",
                f"- **Files processed:** {last.get('files_processed', 0)}",
                f"- **LLM calls:** {last.get('llm_calls', 0)}",
                f"- **Skipped:** {last.get('skipped', 0)}",
                "",
                "## Cumulative Metrics",
                f"- **Total runs:** {m.get('total_runs', 0)}",
                f"- **Avg LLM calls / run:** {m.get('avg_llm_calls', 0.0)}",
                f"- **Avg cache hits / run:** {m.get('avg_cache_hits', 0.0)}",
                "",
                "## Changes Since Previous Context",
            ]
        )

        if new_caps:
            lines.append("### New capabilities")
            for c in new_caps:
                lines.append(f"- {c}")
        else:
            lines.append("- _No new capability strings added this run._")

        if trends:
            lines.append("")
            lines.append("### Metrics trend (vs previous averages)")
            for t in trends:
                lines.append(f"- {t}")
        else:
            lines.append("")
            lines.append("### Metrics trend (vs previous averages)")
            lines.append("- _First run or no prior averages to compare._")

        lines.extend(
            [
                "",
                "## System Characteristics",
                "- cost-optimized",
                "- batched LLM",
                "- caching enabled",
                "",
            ]
        )

        self.md_path.parent.mkdir(parents=True, exist_ok=True)
        self.md_path.write_text("\n".join(lines), encoding="utf-8")


def _default_run_id() -> str:
    return f"local-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
