"""Finding override storage — per-run suppress/intentional markers."""
from __future__ import annotations

import json
import threading
from pathlib import Path
class OverrideManager:
    """Read and write finding overrides for a given run.

    Overrides are stored in {run_dir}/overrides.json as a list:
    [
        {
            "type": "hub_file",
            "file": "models.py",
            "reason": "intentional",
            "note": "Django convention — high fan-in is expected",
            "created_at": "2026-04-09T10:00:00Z"
        },
        ...
    ]
    """

    def __init__(self, run_dir: str) -> None:
        self._path = Path(run_dir) / "overrides.json"
        self._lock = threading.Lock()

    def add(
        self,
        ap_type: str,
        file: str | None,
        reason: str,
        note: str = "",
    ) -> dict:
        """Add or update an override. Returns the stored override entry."""
        from datetime import datetime, timezone

        created_at = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        entry: dict = {
            "type": ap_type,
            "file": file or "",
            "reason": reason,
            "note": note,
            "created_at": created_at,
        }
        with self._lock:
            overrides = self._read_raw()
            # Replace existing override for same type+file
            overrides = [
                o
                for o in overrides
                if not (o.get("type") == ap_type and o.get("file") == (file or ""))
            ]
            overrides.append(entry)
            self._write_raw(overrides)
        return entry

    def list(self) -> list[dict]:
        """Return all overrides for this run."""
        with self._lock:
            return self._read_raw()

    def remove(self, ap_type: str, file: str | None) -> bool:
        """Remove an override. Returns True if one was removed."""
        with self._lock:
            before = self._read_raw()
            after = [
                o
                for o in before
                if not (o.get("type") == ap_type and o.get("file") == (file or ""))
            ]
            if len(after) == len(before):
                return False
            self._write_raw(after)
            return True

    def apply(self, anti_patterns: list[dict]) -> list[dict]:
        """Tag anti-patterns that match an override with suppression metadata.

        Does NOT remove findings — keeps them for audit trail.
        Adds: suppressed=True, suppression_reason, suppression_note.
        """
        overrides = self.list()
        if not overrides:
            return anti_patterns

        override_map: dict[tuple[str, str], dict] = {
            (str(o.get("type", "")), str(o.get("file", ""))): o for o in overrides
        }

        result = []
        for ap in anti_patterns:
            ap_type = ap.get("type", "")
            ap_file = str(ap.get("file") or "")
            key = (str(ap_type), ap_file)
            # Also try basename match (overrides stored as basename may match full path)
            from pathlib import Path as _P

            key_base = (str(ap_type), _P(ap_file).name if ap_file else "")

            override = override_map.get(key) or override_map.get(key_base)
            if override:
                ap = dict(ap)
                ap["suppressed"] = True
                ap["suppression_reason"] = override.get("reason", "")
                ap["suppression_note"] = override.get("note", "")
            result.append(ap)
        return result

    def _read_raw(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text(encoding="utf-8")) or []
        except (json.JSONDecodeError, OSError):
            return []

    def _write_raw(self, overrides: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(overrides, indent=2), encoding="utf-8")
