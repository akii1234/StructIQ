"""Tiered content scanner — extracts per-file body metrics for detectors."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from StructIQ.utils.logger import get_logger

logger = get_logger(__name__)

# Lightweight scan patterns (language-agnostic)
_FUNC_PATTERNS = [
    re.compile(r"^\s*def\s+\w+"),  # Python
    re.compile(r"^\s*(public|private|protected|static).*\w+\s*\("),  # Java
    re.compile(
        r"^\s*(function\s+\w+|\w+\s*[:=]\s*(function|\([^)]*\)\s*=>))"
    ),  # JS/TS
    re.compile(r"^\s*func\s+\w+"),  # Go
]
_HARDCODED_PATTERNS = [
    re.compile(r'(?<![A-Za-z_])(https?://[^\s"\']+)'),  # hardcoded URLs
    re.compile(r"(?<![A-Za-z_])([0-9]{4,})(?![A-Za-z_])"),  # magic numbers > 999
    re.compile(
        r'''["'](password|secret|api_key|token|key)["']?\s*[:=]\s*["'][^"']{4,}''',
        re.IGNORECASE,
    ),  # credentials
]


def _is_func_line(line: str) -> bool:
    return any(p.match(line) for p in _FUNC_PATTERNS)


def _scan_lightweight(lines: list[str]) -> dict[str, Any]:
    """Fast scan — runs on every file."""
    return {
        "line_count": len(lines),
        "function_count": sum(1 for ln in lines if _is_func_line(ln)),
        "blank_lines": sum(1 for ln in lines if not ln.strip()),
    }


def _scan_deep(lines: list[str]) -> dict[str, Any]:
    """Detailed scan — runs on high-priority files only."""
    func_sizes: list[int] = []
    current_func_start: int | None = None
    max_nesting = 0

    for i, line in enumerate(lines):
        indent = len(line) - len(line.lstrip())
        nesting = indent // 4  # approximate nesting by indent / 4 spaces
        max_nesting = max(max_nesting, nesting)

        if _is_func_line(line):
            if current_func_start is not None:
                func_sizes.append(i - current_func_start)
            current_func_start = i

    if current_func_start is not None:
        func_sizes.append(len(lines) - current_func_start)

    content = "\n".join(lines)
    hardcoded_signals = sum(1 for p in _HARDCODED_PATTERNS if p.search(content))

    return {
        "max_function_lines": max(func_sizes) if func_sizes else 0,
        "avg_function_lines": (
            int(sum(func_sizes) / len(func_sizes)) if func_sizes else 0
        ),
        "function_sizes": func_sizes,
        "max_nesting_depth": max_nesting,
        "hardcoded_signals": hardcoded_signals,
    }


class ContentScanner:
    """Scan project files for body-level metrics. Thread-safe, stateless."""

    MAX_FILE_BYTES = 2_000_000  # skip files over 2MB

    def scan_project(
        self,
        classified_files: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Scan all classified files. Returns {file_path: metrics_dict}."""
        results: dict[str, dict[str, Any]] = {}
        for file_info in classified_files:
            path = file_info.get("file", "")
            priority = file_info.get("priority", "low")
            if not path:
                continue
            try:
                results[path] = self._scan_file(path, priority)
            except Exception as exc:
                logger.debug("ContentScanner: skipping %s — %s", path, exc)
        return results

    def _scan_file(self, path: str, priority: str) -> dict[str, Any]:
        p = Path(path)
        if not p.exists() or p.stat().st_size > self.MAX_FILE_BYTES:
            return {"line_count": 0, "function_count": 0, "blank_lines": 0}

        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        result = _scan_lightweight(lines)

        if priority == "high":
            result.update(_scan_deep(lines))

        return result
