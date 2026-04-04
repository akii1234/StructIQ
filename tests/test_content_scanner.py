"""Tests for tiered ContentScanner."""
from __future__ import annotations

import textwrap

from StructIQ.scanner.content_scanner import ContentScanner


def test_lightweight_scan_counts_lines_and_functions(tmp_path):
    """Scan a Python file and verify line_count and function_count."""
    f = tmp_path / "mod.py"
    f.write_text(
        textwrap.dedent(
            """\
        def a():
            pass

        def b():
            return 1
        """
        )
    )
    scanner = ContentScanner()
    out = scanner.scan_project(
        [{"file": str(f), "language": "python", "priority": "low"}]
    )
    m = out[str(f)]
    assert m["line_count"] >= 5
    assert m["function_count"] == 2


def test_deep_scan_detects_large_function(tmp_path):
    """Deep scan on high-priority file must detect a 60-line function."""
    body_lines = "\n".join([f"    x = {i}" for i in range(60)])
    f = tmp_path / "big.py"
    f.write_text(f"def huge():\n{body_lines}\n")
    scanner = ContentScanner()
    out = scanner.scan_project(
        [{"file": str(f), "language": "python", "priority": "high"}]
    )
    m = out[str(f)]
    assert m.get("max_function_lines", 0) >= 60


def test_deep_scan_detects_hardcoded_url(tmp_path):
    """Deep scan must set hardcoded_signals > 0 when URL is hardcoded."""
    f = tmp_path / "cfg.py"
    f.write_text('API = "https://example.com/api/v1"\n')
    scanner = ContentScanner()
    out = scanner.scan_project(
        [{"file": str(f), "language": "python", "priority": "high"}]
    )
    m = out[str(f)]
    assert m.get("hardcoded_signals", 0) > 0


def test_scan_skips_missing_file():
    """ContentScanner must return empty metrics for non-existent file."""
    scanner = ContentScanner()
    out = scanner.scan_project(
        [{"file": "/nonexistent/path/does_not_exist.py", "language": "python"}]
    )
    m = out["/nonexistent/path/does_not_exist.py"]
    assert m["line_count"] == 0
    assert m["function_count"] == 0


def test_scan_project_returns_entry_per_file(tmp_path):
    """scan_project() must return one entry per classified file."""
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("x = 1\n")
    b.write_text("y = 2\n")
    scanner = ContentScanner()
    out = scanner.scan_project(
        [
            {"file": str(a), "language": "python"},
            {"file": str(b), "language": "python"},
        ]
    )
    assert len(out) == 2
    assert str(a) in out and str(b) in out
