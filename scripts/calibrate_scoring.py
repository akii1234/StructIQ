#!/usr/bin/env python3
"""Scoring calibration harness.

Usage:
    python scripts/calibrate_scoring.py /path/to/project1 /path/to/project2 ...
    python scripts/calibrate_scoring.py --projects-file projects.txt

projects.txt format (one per line):
    /path/to/project  [optional_label]
    # lines starting with # are comments

Outputs:
    calibration_report.json  — machine-readable results
    calibration_summary.txt  — human-readable analysis
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import uuid
from pathlib import Path

# Ensure StructIQ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _run_phases_2_3(project_path: str, run_dir: str) -> dict:
    """Run Phase 2 (dependency) and Phase 3 (architecture) on a local project.

    Returns architecture_insights dict or empty dict on failure.
    """
    from StructIQ.generators.json_writer import write_json_output

    project_path = str(Path(project_path).resolve())
    if not Path(project_path).is_dir():
        return {"error": f"Project path is not a directory: {project_path}"}

    from StructIQ.scanner.file_scanner import FileScanner

    scanner = FileScanner()
    raw_files = scanner.scan_directory(project_path)
    files = [str(f) for f in raw_files if Path(f).is_file()]
    phase1_output = {"files": files, "project_path": project_path}
    out_json = str(Path(run_dir) / "output.json")
    write_json_output(phase1_output, out_json)

    run_id = str(uuid.uuid4())

    from StructIQ.dependency.pipeline import (
        run_dependency_pipeline,
        DependencyPipelineError,
    )

    try:
        run_dependency_pipeline(
            output_path=out_json,
            run_dir=run_dir,
            run_id=run_id,
            project_root=project_path,
            logger=None,
        )
    except DependencyPipelineError as exc:
        return {"error": f"Phase 2 failed: {exc}"}
    except OSError as exc:
        return {"error": f"Phase 2 failed: {exc}"}

    from StructIQ.architecture.pipeline import (
        run_architecture_pipeline,
        ArchitecturePipelineError,
    )

    graph_path = str(Path(run_dir) / "dependency_graph.json")
    analysis_path = str(Path(run_dir) / "dependency_analysis.json")
    try:
        result = run_architecture_pipeline(
            graph_path=graph_path,
            analysis_path=analysis_path,
            run_dir=run_dir,
            run_id=run_id,
            enable_llm=False,
            llm_client=None,
        )
        return result
    except ArchitecturePipelineError as exc:
        return {"error": f"Phase 3 failed: {exc}"}
    except OSError as exc:
        return {"error": f"Phase 3 failed: {exc}"}


def _summarize_findings(anti_patterns: list[dict]) -> dict:
    """Count findings by type and severity."""
    from collections import Counter

    type_counts: Counter = Counter()
    severity_counts: dict[str, Counter] = {}
    for ap in anti_patterns:
        if not isinstance(ap, dict):
            continue
        t = ap.get("type", "unknown")
        s = ap.get("severity", "medium")
        type_counts[t] += 1
        severity_counts.setdefault(t, Counter())[str(s)] += 1
    return {
        "by_type": dict(type_counts.most_common()),
        "by_type_severity": {k: dict(v) for k, v in severity_counts.items()},
    }


def _penalty_contribution(anti_patterns: list[dict]) -> dict[str, int]:
    """Show how many penalty points each type contributes."""
    from StructIQ.architecture.domain_aggregator import FINDING_PENALTIES, SEVERITY_MULTIPLIERS

    contributions: dict[str, int] = {}
    for ap in anti_patterns:
        if not isinstance(ap, dict):
            continue
        t = ap.get("type", "unknown")
        s = ap.get("severity", "medium")
        base = FINDING_PENALTIES.get(t, 3)
        mult = SEVERITY_MULTIPLIERS.get(str(s), 1.0)
        contributions[t] = contributions.get(t, 0) + int(base * mult)
    return dict(sorted(contributions.items(), key=lambda x: x[1], reverse=True))


def run_calibration(project_paths: list[tuple[str, str]]) -> dict:
    """Run calibration on a list of (path, label) tuples."""
    results = []
    for project_path, label in project_paths:
        print(f"  Calibrating: {label or project_path} ...", flush=True)
        with tempfile.TemporaryDirectory() as tmp:
            insights = _run_phases_2_3(project_path, tmp)

        if "error" in insights:
            results.append(
                {
                    "project": label or project_path,
                    "path": project_path,
                    "error": insights["error"],
                }
            )
            continue

        anti_patterns = insights.get("anti_patterns") or []
        domain_scores = insights.get("domain_scores") or {}
        overall_score = insights.get("overall_score")
        overall_grade = insights.get("overall_grade")

        results.append(
            {
                "project": label or project_path,
                "path": project_path,
                "overall_score": overall_score,
                "overall_grade": overall_grade,
                "domain_scores": {
                    d: {
                        "score": v.get("score"),
                        "grade": v.get("grade"),
                        "finding_count": v.get("finding_count"),
                    }
                    for d, v in domain_scores.items()
                    if isinstance(v, dict)
                },
                "finding_summary": _summarize_findings(anti_patterns),
                "penalty_contributions": _penalty_contribution(anti_patterns),
                "total_findings": len(anti_patterns),
            }
        )

    return {"projects": results}


def _write_summary(calibration_data: dict, output_path: str) -> None:
    """Write a human-readable calibration summary."""
    lines = ["StructIQ Scoring Calibration Summary", "=" * 50, ""]
    for proj in calibration_data["projects"]:
        lines.append(f"Project: {proj['project']}")
        if "error" in proj:
            lines.append(f"  ERROR: {proj['error']}")
            lines.append("")
            continue
        lines.append(f"  Overall: {proj['overall_score']} / {proj['overall_grade']}")
        lines.append("  Domain scores:")
        for domain, scores in proj.get("domain_scores", {}).items():
            lines.append(
                f"    {domain:20s}: {scores.get('score')!s:>6} ({scores.get('grade')})  [{scores.get('finding_count')} findings]"
            )
        lines.append("  Top penalty contributors:")
        contrib = proj.get("penalty_contributions") or {}
        for t, pts in list(contrib.items())[:5]:
            lines.append(f"    {t:30s}: -{pts} pts")
        lines.append("")

    valid = [p for p in calibration_data["projects"] if "error" not in p]
    if len(valid) >= 2:
        lines.append("Cross-project analysis")
        lines.append("-" * 30)
        from collections import Counter

        agg: Counter = Counter()
        for p in valid:
            by_type = p.get("finding_summary", {}).get("by_type") or {}
            for t, count in by_type.items():
                agg[t] += count
        lines.append("Finding types across all projects (total fires):")
        for t, count in agg.most_common(15):
            lines.append(f"  {t:35s}: {count}")
        lines.append("")
        from StructIQ.architecture.domain_aggregator import FINDING_PENALTIES

        fired = set(agg.keys())
        never_fired = sorted(set(FINDING_PENALTIES.keys()) - fired)
        if never_fired:
            lines.append("Types that never fired across any project:")
            for t in never_fired:
                lines.append(f"  {t}")
            lines.append("")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="StructIQ scoring calibration harness")
    parser.add_argument("paths", nargs="*", help="Project paths to calibrate")
    parser.add_argument(
        "--projects-file", help="File with one project path (and optional label) per line"
    )
    parser.add_argument("--output-dir", default=".", help="Directory to write calibration outputs")
    args = parser.parse_args()

    project_paths: list[tuple[str, str]] = []

    if args.projects_file:
        for line in Path(args.projects_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            project_paths.append((parts[0], parts[1] if len(parts) > 1 else ""))

    for p in args.paths:
        project_paths.append((p, ""))

    if not project_paths:
        print("No projects specified. Use paths as arguments or --projects-file.")
        sys.exit(1)

    print(f"Calibrating {len(project_paths)} project(s)...")
    data = run_calibration(project_paths)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = str(out_dir / "calibration_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Calibration report: {json_path}")

    summary_path = str(out_dir / "calibration_summary.txt")
    _write_summary(data, summary_path)
    print(f"Calibration summary: {summary_path}")


if __name__ == "__main__":
    main()
