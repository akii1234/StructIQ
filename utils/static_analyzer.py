"""Language-agnostic static extraction (no LLM)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Set


PYTHON_STDLIB: Set[str] = {
    "abc",
    "argparse",
    "array",
    "ast",
    "asyncio",
    "base64",
    "bisect",
    "builtins",
    "collections",
    "contextlib",
    "copy",
    "csv",
    "dataclasses",
    "datetime",
    "enum",
    "functools",
    "gc",
    "hashlib",
    "html",
    "http",
    "importlib",
    "io",
    "itertools",
    "json",
    "logging",
    "math",
    "multiprocessing",
    "operator",
    "os",
    "pathlib",
    "pickle",
    "platform",
    "pprint",
    "random",
    "re",
    "resource",
    "shutil",
    "signal",
    "sqlite3",
    "string",
    "struct",
    "subprocess",
    "sys",
    "tempfile",
    "textwrap",
    "threading",
    "time",
    "traceback",
    "types",
    "typing",
    "unicodedata",
    "urllib",
    "uuid",
    "warnings",
    "weakref",
    "xml",
    "zipfile",
    "__future__",
}


def analyze_file(file_path: str) -> Dict[str, Any]:
    """Extract structural metadata from a source file."""
    path = Path(file_path)
    try:
        size = path.stat().st_size
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {
            "functions": [],
            "classes": [],
            "imports": [],
            "line_count": 0,
            "file_size": 0,
        }
    meta = analyze_text(file_path, text)
    meta["file_size"] = size
    return meta


def analyze_text(file_path: str, text: str, disk_size: int | None = None) -> Dict[str, Any]:
    """Extract metadata from already-read source text."""
    path = Path(file_path)
    lines = text.splitlines()
    line_count = len(lines)
    ext = path.suffix.lower()

    if ext == ".py":
        functions, classes, imports = _analyze_python(text)
    elif ext in {".js", ".jsx", ".ts", ".tsx"}:
        functions, classes, imports = _analyze_js_ts(text)
    elif ext == ".java":
        functions, classes, imports = _analyze_java(text)
    elif ext == ".go":
        functions, classes, imports = _analyze_go(text)
    else:
        functions, classes, imports = _analyze_generic(text)

    size = disk_size if disk_size is not None else len(text.encode("utf-8", errors="ignore"))
    return {
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "line_count": line_count,
        "file_size": size,
    }


def _analyze_python(text: str) -> tuple[List[str], List[str], List[str]]:
    functions: List[str] = []
    classes: List[str] = []
    imports: List[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("def ") or stripped.startswith("async def "):
            m = re.match(r"^(?:async\s+)?def\s+(\w+)\s*\(", stripped)
            if m:
                functions.append(m.group(1))
        elif stripped.startswith("class "):
            m = re.match(r"^class\s+(\w+)", stripped)
            if m:
                classes.append(m.group(1))
        elif stripped.startswith("import ") or stripped.startswith("from "):
            imports.append(stripped)

    return functions, classes, imports


def _analyze_js_ts(text: str) -> tuple[List[str], List[str], List[str]]:
    functions: List[str] = []
    classes: List[str] = []
    imports: List[str] = []

    func_pat = re.compile(
        r"(?:export\s+)?(?:async\s+)?function\s+(\w+)|"
        r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\("
    )
    class_pat = re.compile(r"(?:export\s+)?class\s+(\w+)")
    import_pat = re.compile(r"^(?:import\s+.+\s+from\s+['\"](.+)['\"]|require\s*\(\s*['\"](.+)['\"]\s*\))")

    for line in text.splitlines():
        stripped = line.strip()
        for m in func_pat.finditer(stripped):
            name = m.group(1) or m.group(2)
            if name:
                functions.append(name)
        cm = class_pat.search(stripped)
        if cm:
            classes.append(cm.group(1))
        im = import_pat.search(stripped)
        if im:
            imports.append(im.group(1) or im.group(2) or stripped)

    return functions, classes, imports


def _analyze_java(text: str) -> tuple[List[str], List[str], List[str]]:
    functions: List[str] = []
    classes: List[str] = []
    imports: List[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("import "):
            imports.append(stripped)
        if " class " in stripped or stripped.startswith("class "):
            m = re.search(r"\bclass\s+(\w+)", stripped)
            if m:
                classes.append(m.group(1))
        if re.search(
            r"\b(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?"
            r"(?:[\w<>,\[\]]+\s+)+(\w+)\s*\([^)]*\)\s*\{?",
            stripped,
        ):
            m2 = re.search(r"(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{?\s*$", stripped)
            if m2 and m2.group(1) not in {"if", "for", "while", "switch", "catch"}:
                functions.append(m2.group(1))

    return functions, classes, imports


def _analyze_go(text: str) -> tuple[List[str], List[str], List[str]]:
    functions: List[str] = []
    classes: List[str] = []
    imports: List[str] = []

    in_import = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("import "):
            imports.append(stripped)
            in_import = "(" in stripped and ")" not in stripped
            continue
        if in_import:
            imports.append(stripped)
            if ")" in stripped:
                in_import = False
            continue
        if stripped.startswith("func "):
            m = re.match(r"^func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(", stripped)
            if m:
                functions.append(m.group(1))
        if stripped.startswith("type ") and " struct" in stripped:
            m = re.match(r"^type\s+(\w+)\s+struct", stripped)
            if m:
                classes.append(m.group(1))

    return functions, classes, imports


def _analyze_generic(text: str) -> tuple[List[str], List[str], List[str]]:
    functions: List[str] = []
    classes: List[str] = []
    imports: List[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.lower().startswith("import ") or s.lower().startswith("from "):
            imports.append(s)
    return functions, classes, imports


def has_external_imports(metadata: Dict[str, Any], file_path: str) -> bool:
    """Heuristic: third-party or non-relative imports."""
    path = Path(file_path)
    ext = path.suffix.lower()
    imports: List[str] = metadata.get("imports", [])

    for raw in imports:
        line = raw.strip()
        if ext == ".py":
            if line.startswith("from "):
                m = re.match(r"^from\s+([\w.]+)\s+import", line)
                if not m:
                    continue
                root = m.group(1).split(".")[0]
                if root == "" or root == ".":
                    continue
                if root not in PYTHON_STDLIB:
                    return True
            elif line.startswith("import "):
                parts = line.replace("import ", "").split(",")[0].strip().split()
                if not parts:
                    continue
                mod = parts[0].split(".")[0]
                if mod and mod not in PYTHON_STDLIB:
                    return True
        elif ext in {".js", ".jsx", ".ts", ".tsx"}:
            if "/" in line or line.startswith("from ") or "from '" in line or 'from "' in line:
                if "from './/" in line or 'from ".//' in line or "./" in line or "../" in line:
                    continue
                if "@/" in line or line.startswith("import "):
                    return True
        else:
            if line.startswith("import ") and not line.startswith('import ".'):
                return True
    return False


def _bump_priority_for_import_count(tier: str, import_count: int) -> str:
    """Raise tier when many imports (simple heuristic)."""
    if import_count <= 5:
        return tier
    if tier == "low":
        return "medium"
    if tier == "medium":
        return "high"
    return tier


def get_file_importance(
    metadata: Dict[str, Any],
    file_path: str,
    file_type: str,
    low_size_bytes: int = 300,
) -> str:
    """Return priority tier for LLM routing."""
    parts_lower = Path(file_path).as_posix().lower()
    basename = Path(file_path).name.lower()

    is_config = file_type == "config" or Path(file_path).suffix.lower() in {
        ".json",
        ".yaml",
        ".yml",
    }
    file_size = int(metadata.get("file_size", 0))
    functions: List[str] = metadata.get("functions", [])
    line_count = int(metadata.get("line_count", 0))
    imports: List[str] = metadata.get("imports", [])
    import_count = len(imports)

    if is_config:
        return "low"
    if file_size < low_size_bytes or line_count < 2:
        return "low"

    if basename in ("main.py", "app.py"):
        return "high"

    if any(seg in parts_lower for seg in ("/util/", "/utils/", "/helper/", "helpers/", "/fixtures/")):
        if not any(k in parts_lower for k in ("service", "controller", "/api/")):
            tier = "low"
            return _bump_priority_for_import_count(tier, import_count)

    if any(k in parts_lower for k in ("service", "controller", "/api/", "/api")):
        return "high"
    if len(functions) > 5:
        return "high"
    if has_external_imports(metadata, file_path):
        return "high"

    tier = "medium"
    return _bump_priority_for_import_count(tier, import_count)


def build_partial_content(
    content: str,
    metadata: Dict[str, Any],
    max_length: int,
    head_lines: int = 48,
) -> str:
    """First N lines plus lines containing def/class/import signatures."""
    lines = content.splitlines()
    head = "\n".join(lines[:head_lines])
    keywords = ("def ", "class ", "function ", "func ", "import ", "from ", "interface ")
    extra: List[str] = []
    for i, line in enumerate(lines):
        if i < head_lines:
            continue
        s = line.strip()
        if s.startswith(keywords) or " function " in s or s.startswith("export "):
            extra.append(line)

    blob = head
    if extra:
        blob += "\n--- extracted signatures ---\n" + "\n".join(extra[:200])

    if len(blob) > max_length:
        return blob[:max_length] + "\n... [truncated]"
    return blob
