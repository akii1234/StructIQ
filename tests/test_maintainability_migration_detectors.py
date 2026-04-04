"""Tests for maintainability and migration detectors."""
from __future__ import annotations

from StructIQ.architecture.detectors.hardcoded_config_detector import HardcodedConfigDetector
from StructIQ.architecture.detectors.mega_module_detector import MegaModuleDetector
from StructIQ.architecture.detectors.no_abstraction_detector import NoAbstractionLayerDetector
from StructIQ.architecture.detectors.test_gap_detector import TestGapDetector


def _graph(nodes: list[dict], edges: list[dict] | None = None) -> dict:
    return {"nodes": nodes, "edges": edges or []}


def test_test_gap_detector_finds_untested_files():
    g = _graph(
        [
            {"id": "/p/svc/payments.py", "module": "svc"},
            {"id": "/p/svc/helpers.py", "module": "svc"},
        ]
    )
    analysis = {
        "coupling_scores": [
            {"file": "/p/svc/payments.py", "afferent_coupling": 5},
        ],
    }
    r = TestGapDetector().detect(g, analysis, {})
    assert any(x["file"] == "/p/svc/payments.py" for x in r)


def test_test_gap_detector_skips_test_files_themselves():
    g = _graph([{"id": "/p/test_x.py", "module": "p"}])
    analysis = {"coupling_scores": []}
    r = TestGapDetector().detect(g, analysis, {})
    assert r == []


def test_test_gap_detector_caps_at_20_findings():
    nodes = [{"id": f"/p/m{i}.py", "module": "m"} for i in range(25)]
    g = _graph(nodes)
    analysis = {"coupling_scores": []}
    r = TestGapDetector().detect(g, analysis, {})
    assert len(r) <= 20


def test_mega_module_fires_when_module_exceeds_35pct():
    nodes = []
    for i in range(10):
        nodes.append({"id": f"/big/f{i}.py", "module": "big"})
    for i in range(10):
        nodes.append({"id": f"/other/x{i}.py", "module": "other"})
    g = _graph(nodes)
    r = MegaModuleDetector().detect(g, {}, {})
    assert any(x["type"] == "mega_module" for x in r)


def test_mega_module_skips_small_projects():
    g = _graph([{"id": "/a.py", "module": "m"} for _ in range(4)])
    r = MegaModuleDetector().detect(g, {}, {})
    assert r == []


def test_hardcoded_config_fires_on_url_in_deep_scanned_file(tmp_path):
    fp = str(tmp_path / "c.py")
    scan = {fp: {"hardcoded_signals": 2}}
    r = HardcodedConfigDetector().detect({}, {}, scan)
    assert len(r) == 1
    assert r[0]["type"] == "hardcoded_config"


def test_hardcoded_config_skips_low_priority_files(tmp_path):
    fp = str(tmp_path / "c.py")
    scan = {fp: {"line_count": 10}}
    r = HardcodedConfigDetector().detect({}, {}, scan)
    assert r == []


def test_no_abstraction_fires_when_framework_spread_across_modules():
    edges = []
    nodes = []
    for i in range(6):
        mod = f"m{i % 3}"
        src = f"/{mod}/f{i}.py"
        edges.append(
            {
                "source": src,
                "target": "/lib/x.py",
                "raw_import": "import fastapi",
            }
        )
        nodes.append({"id": src, "module": mod})
    g = _graph(nodes, edges)
    r = NoAbstractionLayerDetector().detect(g, {}, {})
    assert any(x["type"] == "no_abstraction_layer" for x in r)


def test_no_abstraction_skips_framework_imported_in_one_module():
    edges = [
        {"source": "/m/a.py", "target": "/x.py", "raw_import": "import django"},
    ]
    nodes = [{"id": "/m/a.py", "module": "m"}]
    g = _graph(nodes, edges)
    r = NoAbstractionLayerDetector().detect(g, {}, {})
    assert r == []
