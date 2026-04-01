"""Build deterministic dependency graphs from Phase 1 output.

No LLM usage. No file writes. Resolution is best-effort and deterministic.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from StructIQ.dependency.extractor import extract_imports


def _to_abs_str(p: Path) -> str:
    """Best-effort absolute path string match (no strict filesystem dependency)."""
    try:
        return str(p.resolve())
    except OSError:
        return str(p.absolute())


def _module_dotted_name(
    file_path: str, project_root_path: Path
) -> tuple[str, str]:
    """Return (dotted_full, dotted_without_init) keys for dotted_to_path."""
    p = Path(file_path)
    try:
        rel = p.resolve().relative_to(project_root_path)
        rel_parts = rel.parts
    except (OSError, ValueError):
        abs_parts = p.parts
        rel_parts = abs_parts

    # Replace path separators with dots and strip a trailing ".py".
    dotted = ".".join(rel_parts)
    if dotted.endswith(".py"):
        dotted = dotted[: -len(".py")]

    dotted_without_init = dotted
    if dotted.endswith(".__init__"):
        dotted_without_init = dotted[: -len(".__init__")]

    return dotted, dotted_without_init


def _common_prefix_segments(parts_list: list[list[str]]) -> list[str]:
    if not parts_list:
        return []
    min_len = min(len(parts) for parts in parts_list)
    prefix: list[str] = []
    for i in range(min_len):
        token = parts_list[0][i]
        if all(parts[i] == token for parts in parts_list):
            prefix.append(token)
        else:
            break
    return prefix


def build_graph(
    phase1_output: dict,
    project_root: str,
    run_id: str,
) -> dict:
    # 1. Build file_index
    file_index: set[str] = set(phase1_output.get("files") or [])
    project_root_path = Path(project_root)
    try:
        project_root_path = project_root_path.resolve()
    except OSError:
        project_root_path = project_root_path.absolute()

    # 2. Build dotted_to_path (python files only)
    dotted_to_path: dict[str, str] = {}
    for fp in file_index:
        if Path(fp).suffix.lower() != ".py":
            continue
        dotted_full, dotted_wo_init = _module_dotted_name(fp, project_root_path)
        dotted_to_path[dotted_full] = fp
        dotted_to_path[dotted_wo_init] = fp
        # Also index all suffix sub-paths so imports relative to any ancestor work.
        # e.g. "backend.candidate_ranking.models" → also store "candidate_ranking.models" and "models"
        parts = dotted_wo_init.split(".")
        for i in range(1, len(parts)):
            suffix_key = ".".join(parts[i:])
            if suffix_key not in dotted_to_path:
                dotted_to_path[suffix_key] = fp

    # 3. Build language_map
    language_map: dict[str, str] = {}
    for row in phase1_output.get("classified_files") or []:
        if not isinstance(row, dict):
            continue
        file_path = row.get("file")
        language = row.get("language")
        if isinstance(file_path, str) and isinstance(language, str):
            language_map[file_path] = language

    # 4. Build module_map (invert phase1 modules)
    module_map: dict[str, str] = {}
    for module_name, module_files in (phase1_output.get("modules") or {}).items():
        if not isinstance(module_files, list):
            continue
        for fp in module_files:
            if isinstance(fp, str):
                module_map[fp] = module_name

    # Pre-collect go absolute_local imports to compute common prefix segments.
    cached_imports: dict[str, list[dict]] = {}
    go_abs_imports: list[str] = []
    if phase1_output.get("classified_files"):
        # Deterministic best-effort: collect from extract_imports results.
        for fp in sorted(file_index):
            if language_map.get(fp) != "go":
                continue
            records = extract_imports(fp, "go")
            cached_imports[fp] = records
            for rec in records:
                if isinstance(rec, dict) and rec.get("import_kind") == "absolute_local":
                    tgt = rec.get("import_target")
                    if isinstance(tgt, str):
                        go_abs_imports.append(tgt)
    go_abs_parts = [t.split("/") for t in go_abs_imports if t]
    go_common_prefix = _common_prefix_segments(go_abs_parts)

    # 5. Resolve imports
    resolved_pairs: set[tuple[str, str]] = set()
    pair_to_raw_import: dict[tuple[str, str], str] = {}
    unresolved: list[dict] = []

    for source_fp in sorted(file_index):
        language = language_map.get(source_fp, "")
        import_records = (
            cached_imports.get(source_fp)
            if language_map.get(source_fp) == "go"
            else None
        )
        if import_records is None:
            import_records = extract_imports(source_fp, language)
        for rec in import_records:
            if not isinstance(rec, dict):
                continue
            source_file = rec.get("source_file")
            raw_import = rec.get("raw_import")
            import_target = rec.get("import_target")
            import_kind = rec.get("import_kind")
            import_language = rec.get("language")

            if not (
                isinstance(source_file, str)
                and isinstance(raw_import, str)
                and isinstance(import_target, str)
                and isinstance(import_kind, str)
                and isinstance(import_language, str)
            ):
                continue

            target_fp: str | None = None
            attempted_resolution = False

            lang = import_language.lower()

            if lang == "python":
                if import_kind == "relative":
                    attempted_resolution = True
                    dots = 0
                    for ch in import_target:
                        if ch == ".":
                            dots += 1
                        else:
                            break
                    remainder = import_target[dots:]
                    if remainder:
                        base_dir = Path(source_fp).parent
                        for _ in range(dots - 1):
                            base_dir = base_dir.parent
                        candidate_base = base_dir.joinpath(*remainder.split("."))
                        cand_file = candidate_base.with_suffix(".py")
                        cand_init = candidate_base / "__init__.py"
                        cand_file_abs = _to_abs_str(cand_file)
                        cand_init_abs = _to_abs_str(cand_init)
                        if cand_file_abs in file_index:
                            target_fp = cand_file_abs
                        elif cand_init_abs in file_index:
                            target_fp = cand_init_abs
                elif import_kind == "absolute_local":
                    attempted_resolution = True
                    target_fp = dotted_to_path.get(import_target)
                    if target_fp is None:
                        target_fp = dotted_to_path.get(import_target + ".__init__")

                if target_fp is None and import_kind in {"stdlib", "external", "dynamic"}:
                    unresolved.append(
                        {
                            "source": source_file,
                            "raw_import": raw_import,
                            "import_target": import_target,
                            "import_kind": import_kind,
                            "reason": import_kind,
                        }
                    )
                    continue

            elif lang in {"javascript", "typescript"}:
                # Use normalized import_kind decisions from extractor.
                if import_kind == "relative":
                    attempted_resolution = True
                    base = Path(source_fp).parent / import_target
                    candidates: list[Path] = []
                    candidates.append(base)
                    for ext in [".js", ".ts", ".jsx", ".tsx"]:
                        candidates.append(Path(str(base) + ext))
                    candidates.append(base / "index.js")
                    candidates.append(base / "index.ts")
                    for c in candidates:
                        c_abs = _to_abs_str(c)
                        if c_abs in file_index:
                            target_fp = c_abs
                            break
                elif import_kind == "absolute_local":
                    attempted_resolution = True
                    base = project_root_path / import_target
                    candidates = []
                    candidates.append(base)
                    for ext in [".js", ".ts", ".jsx", ".tsx"]:
                        candidates.append(Path(str(base) + ext))
                    candidates.append(base / "index.js")
                    candidates.append(base / "index.ts")
                    for c in candidates:
                        c_abs = _to_abs_str(c)
                        if c_abs in file_index:
                            target_fp = c_abs
                            break
                else:
                    unresolved.append(
                        {
                            "source": source_file,
                            "raw_import": raw_import,
                            "import_target": import_target,
                            "import_kind": import_kind,
                            "reason": import_kind,
                        }
                    )
                    continue

            elif lang == "java":
                if import_kind == "absolute_local":
                    attempted_resolution = True
                    rel = import_target.replace(".", "/") + ".java"
                    rel_posix = rel.replace("\\", "/")
                    matches = []
                    for fp in file_index:
                        if Path(fp).as_posix().endswith(rel_posix):
                            matches.append(fp)
                    if matches:
                        matches.sort()
                        target_fp = matches[0]
                else:
                    unresolved.append(
                        {
                            "source": source_file,
                            "raw_import": raw_import,
                            "import_target": import_target,
                            "import_kind": import_kind,
                            "reason": import_kind,
                        }
                    )
                    continue

            elif lang == "go":
                if import_kind == "absolute_local":
                    attempted_resolution = True
                    parts = import_target.split("/") if import_target else []
                    remainder_parts = parts[len(go_common_prefix) :] if parts else []
                    base = project_root_path.joinpath(*remainder_parts)
                    cand_file = base.with_suffix(".go")
                    cand_abs = _to_abs_str(cand_file)
                    if cand_abs in file_index:
                        target_fp = cand_abs
                else:
                    unresolved.append(
                        {
                            "source": source_file,
                            "raw_import": raw_import,
                            "import_target": import_target,
                            "import_kind": import_kind,
                            "reason": import_kind,
                        }
                    )
                    continue

            # Unknown/unresolvable types
            if target_fp is not None:
                pair = (source_file, target_fp)
                resolved_pairs.add(pair)
                if pair not in pair_to_raw_import:
                    pair_to_raw_import[pair] = raw_import
            else:
                if attempted_resolution:
                    reason = "not_found"
                else:
                    reason = import_kind
                unresolved.append(
                    {
                        "source": source_file,
                        "raw_import": raw_import,
                        "import_target": import_target,
                        "import_kind": import_kind,
                        "reason": reason,
                    }
                )

    # 6. Collect resolved edges
    edges: list[dict] = []
    for source_fp, target_fp in sorted(resolved_pairs):
        raw_import = pair_to_raw_import.get((source_fp, target_fp), "")
        edges.append(
            {
                "source": source_fp,
                "target": target_fp,
                "raw_import": raw_import,
            }
        )

    # 7. Compute in_degree and out_degree
    node_files = sorted(file_index)
    out_counter: Counter = Counter()
    in_counter: Counter = Counter()
    for e in edges:
        out_counter[e["source"]] += 1
        in_counter[e["target"]] += 1

    # 8. Build nodes list (node id is the file path string)
    nodes: list[dict] = []
    for fp in node_files:
        nodes.append(
            {
                "id": fp,
                "language": language_map.get(fp, ""),
                "module": module_map.get(fp, ""),
                "in_degree": int(in_counter.get(fp, 0)),
                "out_degree": int(out_counter.get(fp, 0)),
            }
        )

    # 9. Return graph dict
    generated_at = (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        )
    )

    total_nodes = len(nodes)
    total_edges = len(edges)
    total_unresolved = len(unresolved)

    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "project_root": str(project_root_path),
        "nodes": nodes,
        "edges": edges,
        "unresolved": unresolved,
        "stats": {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "total_unresolved": total_unresolved,
        },
    }

