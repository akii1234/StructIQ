"""Domain Aggregator — rolls anti-pattern findings into five domain health scores."""
from __future__ import annotations

from typing import Any

# Which detector IDs belong to which domain
DOMAIN_DETECTORS: dict[str, list[str]] = {
    "structural": [
        "cycle",
        "god_file",
        "orphan_file",
        "hub_file",
        "concentration_risk",
        "unstable_dependency",
    ],
    "complexity": [
        "large_file",
        "large_function",
        "too_many_functions",
        "high_coupling",
    ],
    "maintainability": [
        "test_gap",
        "weak_boundary",
        "mega_module",
    ],
    "security": [
        "open_security_group",
        "wildcard_iam",
        "public_s3_bucket",
        "unencrypted_storage",
        "no_remote_state",
        "god_module",
        "god_lambda",
        "direct_lambda_invocation",
        "shared_iam_role",
    ],
    "migration": [
        "hardcoded_config",
        "no_abstraction_layer",
    ],
}

# Domain weights for composite score
DOMAIN_WEIGHTS: dict[str, float] = {
    "structural": 0.25,
    "complexity": 0.20,
    "maintainability": 0.20,
    "security": 0.20,
    "migration": 0.15,
}

# Score penalty per finding of each type
FINDING_PENALTIES: dict[str, int] = {
    "cycle": 15,
    "god_file": 10,
    "hub_file": 8,
    "concentration_risk": 8,
    "orphan_file": 2,
    "unstable_dependency": 4,
    "large_file": 5,
    "large_function": 6,
    "too_many_functions": 4,
    "high_coupling": 5,
    "test_gap": 4,
    "weak_boundary": 3,
    "mega_module": 6,
    "hardcoded_config": 5,
    "no_abstraction_layer": 12,
    "god_lambda": 8,
    "direct_lambda_invocation": 4,
    "shared_iam_role": 5,
    "open_security_group": 20,
    "wildcard_iam": 20,
    "public_s3_bucket": 18,
    "unencrypted_storage": 10,
    "no_remote_state": 8,
    "god_module": 8,
}

# Severity penalty multiplier
SEVERITY_MULTIPLIERS: dict[str, float] = {
    "high": 1.5,
    "medium": 1.0,
    "low": 0.5,
}

GRADES = [(90, "A"), (75, "B"), (60, "C"), (45, "D"), (0, "F")]


def _score_to_grade(score: float) -> str:
    for threshold, grade in GRADES:
        if score >= threshold:
            return grade
    return "F"


class DomainAggregator:
    """Aggregate anti-pattern findings into domain scores and composite health."""

    def aggregate(self, anti_patterns: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Returns:
            {
                "domain_scores": {
                    "structural": {"score": 85, "grade": "B", "finding_count": 2,
                                   "top_findings": [...3 highest severity...]},
                    ...
                },
                "overall_score": 78,
                "overall_grade": "C",
            }
        """
        domain_findings: dict[str, list[dict]] = {d: [] for d in DOMAIN_DETECTORS}

        for ap in anti_patterns:
            if not isinstance(ap, dict):
                continue
            ap_type = ap.get("type", "")
            for domain, types in DOMAIN_DETECTORS.items():
                if ap_type in types:
                    domain_findings[domain].append(ap)
                    break

        domain_scores: dict[str, Any] = {}
        weighted_sum = 0.0

        for domain, findings in domain_findings.items():
            penalty = 0
            for f in findings:
                base = FINDING_PENALTIES.get(f.get("type", ""), 3)
                mult = SEVERITY_MULTIPLIERS.get(f.get("severity", "medium"), 1.0)
                penalty += int(base * mult)

            score = max(0.0, 100.0 - penalty)
            grade = _score_to_grade(score)
            top = sorted(
                findings,
                key=lambda x: SEVERITY_MULTIPLIERS.get(x.get("severity", "medium"), 1.0),
                reverse=True,
            )[:3]

            domain_scores[domain] = {
                "score": round(score, 1),
                "grade": grade,
                "finding_count": len(findings),
                "top_findings": top,
            }
            weighted_sum += score * DOMAIN_WEIGHTS[domain]

        overall = round(weighted_sum, 1)
        return {
            "domain_scores": domain_scores,
            "overall_score": overall,
            "overall_grade": _score_to_grade(overall),
        }
