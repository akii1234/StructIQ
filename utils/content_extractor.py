"""Structured content extraction for LLM prompts (no naive truncation)."""

from __future__ import annotations

import os
import re
from typing import List, Set

from app.config import settings


_PY_MAIN_GUARD = re.compile(
    r'if\s+__name__\s*==\s*(?:["\']__main__["\']|"""__main__"""|\'\'\'__main__\'\'\')\s*:'
)
_PY_MAIN_CALL = re.compile(r"\bmain\s*\(\s*\)")
_JS_LISTEN = re.compile(r"\.\s*listen\s*\(\s*|app\.listen\s*\(\s*|server\.listen\s*\(\s*")
_JS_SERVER_START = re.compile(r"\bserver\.start\s*\(\s*|\bapp\.start\s*\(\s*")
_MAIN_LIKE_DEF = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+main\s*\("
    r"|^\s*(?:export\s+)?async\s+function\s+main\s*\("
    r"|^\s*(?:async\s+)?def\s+main\s*\("
    r"|^\s*func\s+main\s*\("
    r"|^\s*(?:public\s+)?static\s+void\s+main\s*\("
)


def _collect_entry_points(lines: List[str]) -> List[str]:
    """Detect runnable / bootstrap patterns for LLM context."""
    seen: Set[str] = set()
    out: List[str] = []

    def add(line: str) -> None:
        s = line.rstrip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    for line in lines:
        s = line.rstrip()
        if not s or s.lstrip().startswith("#"):
            continue
        if _PY_MAIN_GUARD.search(s):
            add(s)
            continue
        if _PY_MAIN_CALL.search(s):
            add(s)
            continue
        if _JS_LISTEN.search(s) or _JS_SERVER_START.search(s):
            add(s)
            continue
        if _MAIN_LIKE_DEF.match(s):
            add(s)
            continue

    return out


def extract_relevant_content(file_content: str) -> str:
    """
    Build a structured excerpt: imports, class headers, function signatures,
    then optional header lines — never the raw full file.

    Length is capped by ``settings.max_content_length`` (``MAX_CONTENT_LENGTH`` env).
    """
    max_length = settings.max_content_length
    header_n = int(os.getenv("CONTENT_HEADER_LINES", "28"))

    lines = file_content.splitlines()
    import_lines: List[str] = []
    class_lines: List[str] = []
    signature_lines: List[str] = []

    import_re = re.compile(
        r"^\s*(?:import\s+|from\s+\S+\s+import|export\s+import|#include\s+)"
    )
    class_re = re.compile(
        r"^\s*(?:export\s+)?(?:abstract\s+)?(?:final\s+)?(?:public\s+|private\s+|protected\s+)?"
        r"(?:static\s+)?class\s+\w+"
        r"|^\s*(?:export\s+)?interface\s+\w+"
        r"|^\s*(?:export\s+)?type\s+\w+\s*=\s*"
        r"|^\s*type\s+\w+\s+struct\b"
    )
    func_sig_re = re.compile(
        r"^\s*(?:async\s+)?def\s+\w+\s*\("
        r"|^\s*(?:export\s+)?(?:async\s+)?function\s+\w+\s*\("
        r"|^\s*(?:export\s+)?\w+\s*\([^)]*\)\s*(?:\{|:)"
        r"|^\s*func\s+(?:\([^)]*\)\s*)?\w+\s*\("
        r"|^\s*(?:public|private|protected)?\s*(?:static\s+)?[\w<>,\[\]]+\s+\w+\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{?\s*$"
    )

    for i, line in enumerate(lines):
        s = line.rstrip()
        if import_re.match(s) or (
            s.startswith("from ") or s.startswith("import ") or s.startswith("using ")
        ):
            if s not in import_lines:
                import_lines.append(s)
            continue
        if class_re.search(s):
            if s not in class_lines:
                class_lines.append(s)
            continue
        if func_sig_re.search(s) and not s.strip().startswith(("if ", "for ", "while ", "switch ", "catch ")):
            if s not in signature_lines:
                signature_lines.append(s)

    header = lines[: max(0, header_n)]
    parts: List[str] = []

    if header:
        parts.append("## Header (first lines)\n" + "\n".join(header))

    entry_points = _collect_entry_points(lines)
    if entry_points:
        bullet = "\n".join(f"- {ep}" for ep in entry_points[:40])
        parts.append("Entry Points:\n" + bullet)

    if import_lines:
        parts.append("## Imports\n" + "\n".join(import_lines[:80]))

    if class_lines:
        parts.append("## Class / type declarations\n" + "\n".join(class_lines[:60]))

    if signature_lines:
        parts.append(
            "## Function / method signatures\n" + "\n".join(signature_lines[:120])
        )

    blob = "\n\n".join(parts) if parts else "\n".join(lines[:header_n])

    if len(blob) > max_length:
        return blob[:max_length] + "\n... [truncated]"
    return blob
