"""Persistent cache manager for file summaries."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict

from filelock import FileLock, Timeout

from app.generators.json_writer import read_json_file
from app.utils.logger import get_logger


class CacheManager:
    """Thread-safe cache for summary outputs."""

    def __init__(self, cache_path: str = "data/cache/cache.json", enabled: bool = True) -> None:
        self.cache_path = cache_path
        self.enabled = enabled
        self.logger = get_logger(self.__class__.__name__)
        self._lock = threading.Lock()
        self._lock_path = str(Path(cache_path).with_suffix(Path(cache_path).suffix + ".lock"))
        self._file_lock = FileLock(self._lock_path, timeout=30)
        self._cache: Dict[str, Dict[str, Any]] = {}
        if enabled:
            with self._lock:
                try:
                    with self._file_lock:
                        self._cache = read_json_file(cache_path, {})
                except Timeout:
                    self.logger.warning(
                        "Cache load lock timeout; using empty cache. lock_path=%s",
                        self._lock_path,
                    )
                    self._cache = {}

    def get(self, file_path: str, content_hash: str) -> Dict[str, Any] | None:
        """Return cached summary if hash matches."""
        if not self.enabled:
            return None
        with self._lock:
            payload = self._cache.get(file_path)
            if not payload:
                return None
            if payload.get("hash") != content_hash:
                return None
            summary = payload.get("summary")
            return dict(summary) if isinstance(summary, dict) else None

    def set(self, file_path: str, content_hash: str, summary: Dict[str, Any]) -> None:
        """Store summary by file path and content hash."""
        if not self.enabled:
            return
        with self._lock:
            self._cache[file_path] = {"hash": content_hash, "summary": dict(summary)}

    def persist(self) -> None:
        """Write cache file to disk."""
        if not self.enabled:
            return
        with self._lock:
            snapshot = dict(self._cache)
        try:
            with self._file_lock:
                dest = Path(self.cache_path)
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(dest.suffix + ".tmp")
                tmp.write_text(
                    json.dumps(snapshot, indent=2),
                    encoding="utf-8",
                )
                tmp.replace(dest)
        except Timeout as exc:
            self.logger.error(
                "Cache persist lock timeout. lock_path=%s",
                self._lock_path,
                exc_info=True,
            )
            raise RuntimeError("cache_persist_lock_timeout") from exc
