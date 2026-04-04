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
        [{"type": "orphan_file", "severity": "high", "description": "x"}]
    )
    med = DomainAggregator().aggregate(
        [{"type": "orphan_file", "severity": "medium", "description": "x"}]
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
