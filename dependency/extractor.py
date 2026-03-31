"""Deterministic import extraction for Phase 2 dependency analysis."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from app.utils.static_analyzer import PYTHON_STDLIB


_COMMENT_LINE_PREFIXES = ("#", "//", "/*", "*")


def _is_comment_or_blank(line: str) -> bool:
    s = line.lstrip()
    if not s:
        return True
    return s.startswith(_COMMENT_LINE_PREFIXES)


def _python_import_kind(file_path: str, import_target: str) -> str:
    if import_target.startswith("."):
        return "relative"
    if import_target in PYTHON_STDLIB:
        return "stdlib"

    parts = [p for p in Path(file_path).parts if p]
    top_components = set(parts[:-1]) if len(parts) > 1 else set()
    top = import_target.split(".")[0]
    return "absolute_local" if top in top_components else "external"


def _js_ts_import_kind(import_target: str) -> str:
    if import_target.startswith("./") or import_target.startswith("../"):
        return "relative"
    if import_target.startswith("/"):
        return "absolute_local"
    if import_target.startswith("@") or "/" not in import_target:
        return "external"
    return "absolute_local"


def _java_import_kind(file_path: str, import_target: str) -> str:
    if import_target.startswith(("java.", "javax.", "sun.", "com.sun.")):
        return "stdlib"

    parts = [p for p in Path(file_path).parts if p]
    top_components = set(parts[:-1]) if len(parts) > 1 else set()
    top = import_target.split(".")[0]
    return "absolute_local" if top in top_components else "external"


def _go_import_kind(import_target: str) -> str:
    if "." not in import_target:
        return "stdlib"
    if "/" in import_target:
        return "absolute_local"
    return "external"


def extract_imports(
    file_path: str,
    language: str,
    text: str | None = None,
) -> list[dict]:
    if text is None:
        try:
            text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

    lang = (language or "").lower()
    lines = text.splitlines()
    out: List[Dict[str, Any]] = []

    if lang == "python":
        from_pat = re.compile(r"^from\s+(\S+)\s+import\b")
        import_pat = re.compile(r"^import\s+(\S+)", re.IGNORECASE)
        importlib_pat = re.compile(
            r"importlib\.import_module\s*\(\s*(?P<arg>[^)]+?)\s*\)"
        )

        for line in lines:
            if _is_comment_or_blank(line):
                continue
            raw_import = line.strip()

            # importlib.import_module(<dynamic expr>)
            if "importlib.import_module" in raw_import:
                m = importlib_pat.search(raw_import)
                if m:
                    arg = m.group("arg").strip()
                    if not (arg.startswith(("'", '"')) and arg.endswith(("'", '"'))):
                        out.append(
                            {
                                "source_file": file_path,
                                "raw_import": raw_import,
                                "import_target": arg,
                                "import_kind": "dynamic",
                                "language": language,
                            }
                        )
                        continue

            m = from_pat.match(raw_import)
            if m:
                import_target = m.group(1)
                out.append(
                    {
                        "source_file": file_path,
                        "raw_import": raw_import,
                        "import_target": import_target,
                        "import_kind": _python_import_kind(file_path, import_target),
                        "language": language,
                    }
                )
                continue

            m = import_pat.match(raw_import)
            if m:
                import_target = m.group(1).split(",")[0].strip()
                out.append(
                    {
                        "source_file": file_path,
                        "raw_import": raw_import,
                        "import_target": import_target,
                        "import_kind": _python_import_kind(file_path, import_target),
                        "language": language,
                    }
                )
                continue

        return out

    if lang in {"javascript", "typescript", "js", "ts", "tsx", "jsx"}:
        # Pattern 4: import('...') dynamic
        dynamic_import_pat = re.compile(r"import\s*\(\s*['\"](.+?)['\"]\s*\)")
        # Pattern 1: import ... from '...'
        import_from_pat = re.compile(r"import\s+.+?\s+from\s+['\"](.+?)['\"]")
        # Pattern 2: require('...')
        require_pat = re.compile(r"require\s*\(\s*['\"](.+?)['\"]\s*\)")
        # Pattern 3: export ... from '...'
        export_from_pat = re.compile(r"export\s+.*?\s+from\s+['\"](.+?)['\"]")

        for line in lines:
            if _is_comment_or_blank(line):
                continue
            raw_import = line.strip()

            m = dynamic_import_pat.search(raw_import)
            if m:
                import_target = m.group(1)
                out.append(
                    {
                        "source_file": file_path,
                        "raw_import": raw_import,
                        "import_target": import_target,
                        "import_kind": "dynamic",
                        "language": language,
                    }
                )
                continue

            m = import_from_pat.search(raw_import)
            if m:
                import_target = m.group(1)
                out.append(
                    {
                        "source_file": file_path,
                        "raw_import": raw_import,
                        "import_target": import_target,
                        "import_kind": _js_ts_import_kind(import_target),
                        "language": language,
                    }
                )
                continue

            m = require_pat.search(raw_import)
            if m:
                import_target = m.group(1)
                out.append(
                    {
                        "source_file": file_path,
                        "raw_import": raw_import,
                        "import_target": import_target,
                        "import_kind": _js_ts_import_kind(import_target),
                        "language": language,
                    }
                )
                continue

            m = export_from_pat.search(raw_import)
            if m:
                import_target = m.group(1)
                out.append(
                    {
                        "source_file": file_path,
                        "raw_import": raw_import,
                        "import_target": import_target,
                        "import_kind": _js_ts_import_kind(import_target),
                        "language": language,
                    }
                )
                continue

        return out

    if lang == "java":
        import_pat = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)(?:\.\*)?;\s*$")

        for line in lines:
            if _is_comment_or_blank(line):
                continue
            raw_import = line.strip()
            m = import_pat.match(raw_import)
            if not m:
                continue
            import_target = m.group(1)
            out.append(
                {
                    "source_file": file_path,
                    "raw_import": raw_import,
                    "import_target": import_target,
                    "import_kind": _java_import_kind(file_path, import_target),
                    "language": language,
                }
            )
        return out

    if lang == "go":
        in_import_block = False
        single_pat = re.compile(r'^\s*import\s+"(.+?)"\s*$')

        for line in lines:
            if _is_comment_or_blank(line):
                continue
            raw_import = line.strip()

            if not in_import_block:
                if raw_import.startswith("import"):
                    if raw_import.startswith("import ("):
                        in_import_block = True
                        continue
                    m = single_pat.match(raw_import)
                    if m:
                        import_target = m.group(1)
                        out.append(
                            {
                                "source_file": file_path,
                                "raw_import": raw_import,
                                "import_target": import_target,
                                "import_kind": _go_import_kind(import_target),
                                "language": language,
                            }
                        )
                continue

            # inside an import block
            if raw_import == ")":
                in_import_block = False
                continue
            m = re.search(r'"(.+?)"', raw_import)
            if not m:
                continue
            import_target = m.group(1)
            out.append(
                {
                    "source_file": file_path,
                    "raw_import": raw_import,
                    "import_target": import_target,
                    "import_kind": _go_import_kind(import_target),
                    "language": language,
                }
            )

        return out

    return out

