"""Tests for DomainAggregator."""
from __future__ import annotations

from StructIQ.architecture.domain_aggregator import DomainAggregator


def test_all_four_domains_present_in_output():
    r = DomainAggregator().aggregate([])
    assert set(r["domain_scores"].keys()) == {
        "structural",
        "complexity",
        "maintainability",
        "security",
        "migration",
    }


def test_zero_findings_produces_score_100():
    r = DomainAggregator().aggregate([])
    for d in r["domain_scores"].values():
        assert d["score"] == 100.0
    assert r["overall_score"] == 100.0


def test_cycle_finding_penalizes_structural_domain():
    aps = [
        {
            "type": "cycle",
            "severity": "high",
            "description": "c",
        }
    ]
    r = DomainAggregator().aggregate(aps)
    assert r["domain_scores"]["structural"]["score"] < 100.0


def test_high_severity_penalizes_more_than_medium():
    high = DomainAggregator().aggregate(
        [{"type": "hub_file", "severity": "high", "description": "x"}]
    )
    med = DomainAggregator().aggregate(
        [{"type": "hub_file", "severity": "medium", "description": "x"}]
    )
    assert high["domain_scores"]["structural"]["score"] < med["domain_scores"]["structural"]["score"]


def test_overall_score_is_weighted_composite():
    r = DomainAggregator().aggregate([])
    assert r["overall_score"] == 100.0


def test_grade_boundaries_correct():
    agg = DomainAggregator()
    assert agg.aggregate([{"type": "cycle", "severity": "low"}])["overall_grade"] in {
        "A",
        "B",
        "C",
        "D",
        "F",
    }


def test_top_findings_capped_at_3_per_domain():
    aps = [{"type": "orphan_file", "severity": "low", "description": str(i)} for i in range(5)]
    r = DomainAggregator().aggregate(aps)
    assert len(r["domain_scores"]["structural"]["top_findings"]) <= 3


def test_unknown_detector_type_does_not_crash():
    r = DomainAggregator().aggregate(
        [{"type": "totally_unknown_xyz", "severity": "high", "description": "x"}]
    )
    assert "overall_score" in r


def test_security_domain_exists():
    """DomainAggregator must produce a security domain score."""
    result = DomainAggregator().aggregate([])
    assert "security" in result["domain_scores"]


def test_open_sg_penalises_security_domain():
    ap = {"type": "open_security_group", "severity": "high"}
    result = DomainAggregator().aggregate([ap])
    sec_score = result["domain_scores"]["security"]["score"]
    assert sec_score < 100


def test_domain_weights_sum_to_one():
    from StructIQ.architecture.domain_aggregator import DOMAIN_WEIGHTS

    total = sum(DOMAIN_WEIGHTS.values())
    assert abs(total - 1.0) < 0.001


def test_lambda_findings_in_security_domain():
    """god_lambda, direct_lambda_invocation, shared_iam_role moved to security domain."""
    from StructIQ.architecture.domain_aggregator import DOMAIN_DETECTORS

    assert "god_lambda" in DOMAIN_DETECTORS["security"]
    assert "direct_lambda_invocation" in DOMAIN_DETECTORS["security"]
    assert "shared_iam_role" in DOMAIN_DETECTORS["security"]
    assert "god_lambda" not in DOMAIN_DETECTORS.get("migration", [])


def test_score_floor_is_five_not_zero():
    """When penalties exceed 100, domain score must floor at 5.0, not 0.0."""
    # 14 hub_file high: 14 × 5 × 1.5 = 105 penalty (calibrated hub_file weight)
    aps = [{"type": "hub_file", "severity": "high"} for _ in range(14)]
    result = DomainAggregator().aggregate(aps)
    score = result["domain_scores"]["structural"]["score"]
    assert score == 5.0, f"Expected floor of 5.0, got {score}"
    assert result["domain_scores"]["structural"]["grade"] == "F"


def test_single_hub_file_does_not_floor_score():
    aps = [{"type": "hub_file", "severity": "high"}]
    result = DomainAggregator().aggregate(aps)
    score = result["domain_scores"]["structural"]["score"]
    assert score >= 85, f"Single hub_file should leave score ≥ 85, got {score}"


def test_typical_startup_scores_mid_range():
    aps = (
        [{"type": "cycle", "severity": "high"}] * 3
        + [{"type": "large_file", "severity": "medium"}] * 3
        + [{"type": "high_coupling", "severity": "medium"}] * 2
        + [{"type": "test_gap", "severity": "medium"}]
    )
    result = DomainAggregator().aggregate(aps)
    assert 45 <= result["overall_score"] <= 80


def test_monolith_scores_d_not_floor():
    aps = (
        [{"type": "hub_file", "severity": "high"}] * 7
        + [{"type": "cycle", "severity": "high"}]
        + [{"type": "concentration_risk", "severity": "medium"}]
    )
    result = DomainAggregator().aggregate(aps)
    score = result["domain_scores"]["structural"]["score"]
    assert 15 <= score <= 50, f"Monolith structural score should be 15-50, got {score}"


def test_grade_thresholds():
    from StructIQ.architecture.domain_aggregator import _score_to_grade

    assert _score_to_grade(92) == "A"
    assert _score_to_grade(85) == "A"
    assert _score_to_grade(84) == "B"
    assert _score_to_grade(70) == "B"
    assert _score_to_grade(69) == "C"
    assert _score_to_grade(55) == "C"
    assert _score_to_grade(54) == "D"
    assert _score_to_grade(35) == "D"
    assert _score_to_grade(34) == "F"
