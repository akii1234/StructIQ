"""Tests for score trend badge rendering."""
from __future__ import annotations

from StructIQ.reporting.report_generator import _trend_badge


def test_improvement_shows_green_arrow():
    html = _trend_badge(75.0, 65.0)
    assert "▲" in html
    assert "+10" in html
    assert "#22c55e" in html


def test_regression_shows_red_arrow():
    html = _trend_badge(60.0, 70.0)
    assert "▼" in html
    assert "-10" in html
    assert "#ef4444" in html


def test_no_change_shows_grey_same():
    html = _trend_badge(65.0, 65.0)
    assert "same" in html
    assert "#6b7280" in html


def test_none_score_returns_empty():
    assert _trend_badge(None, 65.0) == ""
    assert _trend_badge(65.0, None) == ""
    assert _trend_badge(None, None) == ""


def test_small_delta_rounds_to_one_decimal():
    html = _trend_badge(65.15, 65.0)
    assert "0.2" in html or "+0.1" in html or "+0.2" in html
