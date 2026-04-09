"""Tests for framework detection and finding adjustments."""
from __future__ import annotations

from StructIQ.architecture.pipeline import _apply_framework_adjustments, _detect_framework


def test_detects_django_from_multiple_apps_py():
    files = [
        "/p/candidate_ranking/apps.py",
        "/p/resume_checker/apps.py",
        "/p/user_management/apps.py",
        "/p/manage.py",
    ]
    assert _detect_framework(files) == "django"


def test_detects_django_from_manage_and_settings():
    assert _detect_framework(["/p/manage.py", "/p/settings.py", "/p/views.py"]) == "django"


def test_returns_none_for_unknown_stack():
    assert _detect_framework(["/p/main.go", "/p/handler.go"]) is None


def test_returns_none_for_empty():
    assert _detect_framework([]) is None


def _ap(type_, file="/proj/app/models.py", severity="high"):
    return {"type": type_, "file": file, "severity": severity, "description": "desc"}


def test_django_models_hub_file_downgraded():
    result = _apply_framework_adjustments([_ap("hub_file")], "django")
    assert result[0]["severity"] == "medium"
    assert "Django" in result[0]["framework_note"]


def test_django_serializers_hub_file_downgraded():
    result = _apply_framework_adjustments([_ap("hub_file", file="/p/app/serializers.py")], "django")
    assert result[0]["severity"] == "medium"


def test_django_models_high_coupling_suppressed():
    result = _apply_framework_adjustments([_ap("high_coupling", severity="medium")], "django")
    assert len(result) == 0


def test_non_framework_file_unchanged():
    result = _apply_framework_adjustments([_ap("hub_file", file="/p/app/llm_service.py")], "django")
    assert result[0]["severity"] == "high"
    assert "framework_note" not in result[0]


def test_no_framework_unchanged():
    aps = [_ap("hub_file"), _ap("high_coupling", severity="medium")]
    assert _apply_framework_adjustments(aps, None) is aps
