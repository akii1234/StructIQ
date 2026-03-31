"""JSON output generator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def write_json_output(payload: Dict[str, Any], output_path: str) -> None:
    """Write discovery output to disk as formatted JSON."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_json_file(path: str, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Read JSON file and return default on failure."""
    payload_default = default or {}
    source = Path(path)
    if not source.exists():
        return payload_default
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return payload_default


def write_progress_snapshot(snapshot: Dict[str, Any], output_path: str = "data/runs/progress_snapshot.json") -> None:
    """Persist progress snapshot as JSON."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
