"""Tests for the scoring calibration harness."""
from __future__ import annotations

import tempfile
from pathlib import Path


def test_penalty_contribution_sums_correctly():
    """Penalty contributions must match manual calculation."""
    from scripts.calibrate_scoring import _penalty_contribution

    aps = [
        {"type": "hub_file", "severity": "high"},
        {"type": "hub_file", "severity": "high"},
        {"type": "cycle", "severity": "high"},
    ]
    contribs = _penalty_contribution(aps)
    assert contribs["cycle"] == 22
    assert contribs["hub_file"] == 14


def test_summarize_findings_counts_correctly():
    from scripts.calibrate_scoring import _summarize_findings

    aps = [
        {"type": "cycle", "severity": "high"},
        {"type": "cycle", "severity": "high"},
        {"type": "hub_file", "severity": "medium"},
    ]
    summary = _summarize_findings(aps)
    assert summary["by_type"]["cycle"] == 2
    assert summary["by_type"]["hub_file"] == 1


def test_calibration_output_structure():
    """run_calibration returns expected keys for each project."""
    from scripts.calibrate_scoring import run_calibration

    fixture = str(Path(__file__).parent / "fixtures" / "sample_project")
    data = run_calibration([(fixture, "sample")])
    assert len(data["projects"]) == 1
    proj = data["projects"][0]
    assert "error" not in proj, f"Calibration failed on fixture project: {proj.get('error')}"
    assert "overall_score" in proj
    assert "domain_scores" in proj
    assert "finding_summary" in proj
    assert "penalty_contributions" in proj


def test_write_summary_creates_readable_output():
    from scripts.calibrate_scoring import _write_summary

    data = {
        "projects": [
            {
                "project": "test-proj",
                "path": "/tmp/test",
                "overall_score": 65.0,
                "overall_grade": "C",
                "domain_scores": {
                    "structural": {"score": 70.0, "grade": "B", "finding_count": 2},
                },
                "finding_summary": {"by_type": {"hub_file": 2}, "by_type_severity": {}},
                "penalty_contributions": {"hub_file": 14},
                "total_findings": 2,
            }
        ]
    }
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        tmp_path = f.name
    _write_summary(data, tmp_path)
    content = Path(tmp_path).read_text(encoding="utf-8")
    assert "test-proj" in content
    assert "65.0" in content
    assert "hub_file" in content


def test_calibration_handles_nonexistent_path_gracefully():
    from scripts.calibrate_scoring import run_calibration

    data = run_calibration([("/does/not/exist/xyz", "missing")])
    assert len(data["projects"]) == 1
    assert "error" in data["projects"][0]
