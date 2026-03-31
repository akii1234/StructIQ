"""Content and file utility helpers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, List

try:
    import yaml
except ImportError:  # pragma: no cover - optional until PyYAML installed
    yaml = None  # type: ignore[assignment]

import logging as _log
if yaml is None:
    _log.getLogger(__name__).warning(
        "PyYAML not installed — YAML configs will use line-based fallback. "
        "Fix: pip install pyyaml"
    )


def get_file_hash(content: str) -> str:
    """Return SHA256 hash for content."""
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


def is_binary_like(content: str) -> bool:
    """Heuristic check for binary-like decoded content."""
    if not content:
        return False
    null_ratio = content.count("\x00") / max(1, len(content))
    return null_ratio > 0.01


def is_relevant_file(file_path: str, content: str) -> tuple[bool, str]:
    """Return whether file should be summarized with reason."""
    min_bytes = int(os.getenv("MIN_FILE_BYTES", "200"))
    path = Path(file_path)
    suffix = path.suffix.lower()

    if is_binary_like(content):
        return False, "binary_like_content"

    size_in_bytes = len(content.encode("utf-8", errors="ignore"))
    config_ext = {".json", ".yaml", ".yml"}
    if size_in_bytes < min_bytes and suffix not in config_ext:
        return False, "too_small"

    return True, ""


def chunk_text(content: str) -> List[str]:
    """Split large content into fixed-size chunks."""
    chunk_size = int(os.getenv("LLM_CHUNK_SIZE", "3000"))
    if chunk_size <= 0:
        chunk_size = 3000
    return [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]


_MAX_LIGHTWEIGHT_KEYS = 25
_MAX_FALLBACK_SCAN_LINES = 200


def _top_level_keys_from_mapping(obj: Any) -> List[str]:
    """Return sorted top-level keys for a mapping; else empty."""
    if not isinstance(obj, dict):
        return []
    return sorted(str(k) for k in obj.keys())


def _fallback_line_based_config_keys(content: str) -> List[str]:
    """Naive line split on first ':' — used when structured parse fails."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    preview_keys: List[str] = []
    for line in lines[:_MAX_FALLBACK_SCAN_LINES]:
        if ":" not in line:
            continue
        key = line.split(":")[0].strip(" \"'")
        if key and key not in preview_keys:
            preview_keys.append(key)
        if len(preview_keys) >= _MAX_LIGHTWEIGHT_KEYS:
            break
    return preview_keys


def extract_lightweight_config_keys(file_path: str, content: str) -> List[str]:
    """
    Top-level keys from JSON/YAML config text for lightweight summaries.

    Uses ``json.loads`` / ``yaml.safe_load`` when possible; falls back to
    line-based heuristics on parse errors or unsupported root types.
    Only ``.json``, ``.yaml``, and ``.yml`` are parsed structurally; callers
    should restrict to those extensions.
    """
    suffix = Path(file_path).suffix.lower()

    if suffix == ".json":
        try:
            data = json.loads(content)
            keys = _top_level_keys_from_mapping(data)
            if keys:
                return keys[:_MAX_LIGHTWEIGHT_KEYS]
        except json.JSONDecodeError:
            pass
        return _fallback_line_based_config_keys(content)

    if suffix in {".yaml", ".yml"}:
        if yaml is not None:
            try:
                data = yaml.safe_load(content)
                keys = _top_level_keys_from_mapping(data)
                if keys:
                    return keys[:_MAX_LIGHTWEIGHT_KEYS]
            except yaml.YAMLError:
                pass
        return _fallback_line_based_config_keys(content)

    return _fallback_line_based_config_keys(content)
