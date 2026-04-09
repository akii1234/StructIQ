"""Smoke tests for redesigned HTML report sections (Prompt 8)."""
from __future__ import annotations

import json
from pathlib import Path

from StructIQ.reporting.report_generator import ReportGenerator


def test_report_includes_domain_dashboard_and_migration_section(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    run_id = "rpt-sec-test"

    (run_dir / "output.json").write_text(
        json.dumps({"files": ["/a.py"], "metrics": {"total_files": 1}}), encoding="utf-8"
    )
    (run_dir / "dependency_graph.json").write_text(
        json.dumps({"nodes": [], "edges": []}), encoding="utf-8"
    )
    (run_dir / "dependency_analysis.json").write_text(
        json.dumps({"entry_points": ["/main.py"], "most_depended_on": [], "most_dependencies": []}),
        encoding="utf-8",
    )
    arch = {
        "anti_patterns": [
            {
                "type": "hardcoded_config",
                "severity": "medium",
                "file": "/cfg.py",
                "description": "URL in source",
                "effort": "low",
            }
        ],
        "domain_scores": {
            "structural": {"score": 100, "grade": "A", "finding_count": 0},
            "complexity": {"score": 100, "grade": "A", "finding_count": 0},
            "maintainability": {"score": 100, "grade": "A", "finding_count": 0},
            "security": {"score": 100, "grade": "A", "finding_count": 0},
            "migration": {"score": 88, "grade": "B", "finding_count": 1},
        },
        "overall_score": 97,
        "overall_grade": "A",
        "services": {},
        "system_summary": "Test summary.",
    }
    (run_dir / "architecture_insights.json").write_text(
        json.dumps(arch), encoding="utf-8"
    )
    (run_dir / "modernization_plan.json").write_text(
        json.dumps(
            {
                "decision": "action_required",
                "plan_mode": "direct",
                "tasks": [
                    {
                        "type": "break_cycle",
                        "priority": "high",
                        "target": ["/a.py"],
                        "confidence": 0.9,
                        "selected_strategy": "s",
                    }
                ],
                "plan_summary": "",
                "execution_plan": [],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "snapshot.json").write_text(
        json.dumps({"llm_stats": {"enabled": False}}), encoding="utf-8"
    )
    (run_dir / "intelligence_report.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "digest": {},
                "narrative": {
                    "migration_assessment": "Fix config before migrating.",
                    "system_narrative": "",
                    "onboarding_guide": [],
                    "domain_narratives": {},
                },
            }
        ),
        encoding="utf-8",
    )

    html = ReportGenerator().generate(str(run_dir), run_id)
    assert "STRUCTURAL" in html
    assert "SECURITY" in html
    assert "MIGRATION" in html
    assert "Overall health" in html
    assert "Anti-pattern catalog" in html
    assert 'id="migration-readiness"' in html
    assert "Migration readiness" in html
    assert "Fix config before migrating." in html
    assert "hardcoded_config" in html
    assert "<th>Domain</th>" in html


def test_report_catalog_collapses_many_test_gaps(tmp_path):
    """Three or more test_gap findings render as one catalog summary row."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    run_id = "tg-collapse"

    (run_dir / "output.json").write_text(
        json.dumps({"files": ["/a.py"], "metrics": {"total_files": 1}}), encoding="utf-8"
    )
    (run_dir / "dependency_graph.json").write_text(
        json.dumps({"nodes": [], "edges": []}), encoding="utf-8"
    )
    (run_dir / "dependency_analysis.json").write_text(
        json.dumps({"entry_points": [], "most_depended_on": [], "most_dependencies": []}),
        encoding="utf-8",
    )
    gaps = [
        {
            "type": "test_gap",
            "severity": "medium",
            "file": f"/proj/m{i}.py",
            "description": "No test",
            "effort": "high",
        }
        for i in range(4)
    ]
    arch = {
        "anti_patterns": gaps
        + [{"type": "cycle", "severity": "high", "files": ["/a.py", "/b.py"]}],
        "domain_scores": {},
        "services": {},
        "system_summary": "",
    }
    (run_dir / "architecture_insights.json").write_text(
        json.dumps(arch), encoding="utf-8"
    )
    (run_dir / "modernization_plan.json").write_text(
        json.dumps(
            {
                "decision": "no_action_required",
                "plan_mode": "direct",
                "tasks": [],
                "dominated_tasks": [],
                "plan_summary": "",
                "execution_plan": [],
                "reason": "x",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "snapshot.json").write_text(
        json.dumps({"llm_stats": {"enabled": False}}), encoding="utf-8"
    )

    html = ReportGenerator().generate(str(run_dir), run_id)
    assert "4 source files have no matching test file" in html
    assert html.count("test_gap") == 1


def test_suppressed_finding_renders_as_collapsed_details():
    """Suppressed findings must render inside <details> element."""
    suppressed_ap = {
        "type": "hub_file",
        "file": "models.py",
        "severity": "medium",
        "description": "High fan-in file.",
        "suppressed": True,
        "suppression_reason": "intentional",
        "suppression_note": "Django convention",
    }
    rg = ReportGenerator()
    html = rg._render_finding_card(suppressed_ap)
    assert "<details" in html
    assert "Suppressed" in html


def test_na_domain_renders_without_numeric_score():
    """N/A domain card must not show a numeric score as 100/A."""
    rg = ReportGenerator()
    na_domain = {
        "score": None,
        "grade": "N/A",
        "finding_count": 0,
        "top_findings": [],
        "note": "Security domain not assessed — no relevant files detected.",
    }
    html = rg._render_domain_card("security", na_domain)
    assert "N/A" in html
    assert "100 /" not in html


def test_na_domain_shows_not_assessed_note():
    rg = ReportGenerator()
    na_domain = {
        "score": None,
        "grade": "N/A",
        "finding_count": 0,
        "top_findings": [],
        "note": "Security domain not assessed — no relevant files detected.",
    }
    html = rg._render_domain_card("security", na_domain)
    assert "not assessed" in html.lower() or "no" in html.lower()
