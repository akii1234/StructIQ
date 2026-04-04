"""Tests for complexity detectors."""
from __future__ import annotations

from StructIQ.architecture.detectors.large_file_detector import LargeFileDetector
from StructIQ.architecture.detectors.large_function_detector import LargeFunctionDetector
from StructIQ.architecture.detectors.too_many_functions_detector import (
    TooManyFunctionsDetector,
)


def test_large_file_detector_fires_over_threshold(tmp_path):
    fp = str(tmp_path / "big.py")
    scan = {fp: {"line_count": 600}}
    r = LargeFileDetector().detect({}, {}, scan)
    assert len(r) == 1
    assert r[0]["type"] == "large_file"
    assert r[0]["severity"] == "medium"


def test_large_file_detector_skips_test_files(tmp_path):
    fp = str(tmp_path / "test_foo.py")
    scan = {fp: {"line_count": 600}}
    r = LargeFileDetector().detect({}, {}, scan)
    assert r == []


def test_large_file_detector_escalates_severity_over_1000_lines(tmp_path):
    fp = str(tmp_path / "huge.py")
    scan = {fp: {"line_count": 1200}}
    r = LargeFileDetector().detect({}, {}, scan)
    assert r[0]["severity"] == "high"


def test_large_function_detector_fires_on_deep_scan_files(tmp_path):
    fp = str(tmp_path / "mod.py")
    scan = {fp: {"function_count": 2, "max_function_lines": 80, "avg_function_lines": 40}}
    r = LargeFunctionDetector().detect({}, {}, scan)
    assert len(r) == 1
    assert r[0]["type"] == "large_function"


def test_large_function_detector_skips_low_priority_files(tmp_path):
    fp = str(tmp_path / "shallow.py")
    scan = {fp: {"line_count": 100, "function_count": 1}}
    r = LargeFunctionDetector().detect({}, {}, scan)
    assert r == []


def test_too_many_functions_detector_fires_over_threshold(tmp_path):
    fp = str(tmp_path / "busy.py")
    scan = {fp: {"function_count": 25}}
    r = TooManyFunctionsDetector().detect({}, {}, scan)
    assert len(r) == 1
    assert r[0]["type"] == "too_many_functions"


def test_complexity_detectors_skip_files_missing_from_content_scan():
    """Graceful handling when content_scan has no entry for a file."""
    assert LargeFileDetector().detect({}, {}, {}) == []
    assert LargeFunctionDetector().detect({}, {}, {}) == []
    assert TooManyFunctionsDetector().detect({}, {}, {}) == []
