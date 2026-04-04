"""Tests for structural anti-pattern detectors."""
from __future__ import annotations

from StructIQ.architecture.analyzer import ArchitectureAnalyzer
from StructIQ.architecture.detectors.concentration_detector import ConcentrationRiskDetector
from StructIQ.architecture.detectors.hub_detector import HubFileDetector
from StructIQ.architecture.detectors.orphan_detector import OrphanFileDetector
from StructIQ.architecture.detectors.unstable_dep_detector import UnstableDependencyDetector


def _graph(nodes: list[dict], edges: list[dict]) -> dict:
    return {"nodes": nodes, "edges": edges}


def test_orphan_detector_finds_disconnected_file():
    graph = _graph(
        nodes=[{"id": "/p/orphan.py"}],
        edges=[],
    )
    analysis = {
        "entry_points": [],
        "coupling_scores": [
            {"file": "/p/orphan.py", "afferent_coupling": 0, "efferent_coupling": 0},
        ],
    }
    r = OrphanFileDetector().detect(graph, analysis, {})
    assert len(r) == 1
    assert r[0]["type"] == "orphan_file"
    assert r[0]["file"] == "/p/orphan.py"


def test_orphan_detector_skips_init_files():
    graph = _graph(nodes=[{"id": "/p/pkg/__init__.py"}], edges=[])
    analysis = {
        "entry_points": [],
        "coupling_scores": [
            {
                "file": "/p/pkg/__init__.py",
                "afferent_coupling": 0,
                "efferent_coupling": 0,
            },
        ],
    }
    r = OrphanFileDetector().detect(graph, analysis, {})
    assert r == []


def test_orphan_detector_skips_entry_points():
    graph = _graph(nodes=[{"id": "/p/main.py"}], edges=[])
    analysis = {
        "entry_points": ["/p/main.py"],
        "coupling_scores": [
            {"file": "/p/main.py", "afferent_coupling": 0, "efferent_coupling": 0},
        ],
    }
    r = OrphanFileDetector().detect(graph, analysis, {})
    assert r == []


def test_hub_detector_fires_on_high_ca_low_ce():
    analysis = {
        "coupling_scores": [
            {
                "file": "/p/hub.py",
                "afferent_coupling": 9,
                "efferent_coupling": 1,
            },
        ],
        "dependency_depth": {"/p/hub.py": 1},
    }
    r = HubFileDetector().detect({}, analysis, {})
    assert len(r) == 1
    assert r[0]["type"] == "hub_file"
    assert r[0]["file"] == "/p/hub.py"


def test_hub_detector_does_not_double_flag_god_files():
    """No hub_file finding may target a file already flagged as god_file."""
    analysis = {
        "coupling_scores": [
            {"file": "/p/god.py", "afferent_coupling": 30, "efferent_coupling": 30},
            {"file": "/p/a.py", "afferent_coupling": 2, "efferent_coupling": 2},
            {"file": "/p/b.py", "afferent_coupling": 2, "efferent_coupling": 2},
            {"file": "/p/c.py", "afferent_coupling": 2, "efferent_coupling": 2},
            {"file": "/p/hub.py", "afferent_coupling": 9, "efferent_coupling": 0},
        ],
        "dependency_depth": {
            "/p/god.py": 5,
            "/p/a.py": 1,
            "/p/b.py": 1,
            "/p/c.py": 1,
            "/p/hub.py": 1,
        },
        "module_coupling": [],
    }
    god_files = {
        ap["file"]
        for ap in ArchitectureAnalyzer().detect_god_files(analysis)
        if "file" in ap
    }
    assert "/p/god.py" in god_files
    hubs = HubFileDetector().detect({}, analysis, {})
    for h in hubs:
        assert h["file"] not in god_files
    assert any(h["file"] == "/p/hub.py" for h in hubs)


def test_concentration_risk_fires_when_edges_concentrated():
    nodes = [{"id": f"/p/f{i}.py"} for i in range(10)]
    edges = [{"source": "/p/f0.py", "target": f"/p/f{i}.py"} for i in range(1, 10)]
    graph = _graph(nodes=nodes, edges=edges)
    scores = [{"file": "/p/f0.py", "afferent_coupling": 100, "efferent_coupling": 0}]
    scores.extend(
        [
            {"file": f"/p/f{i}.py", "afferent_coupling": 1, "efferent_coupling": 1}
            for i in range(1, 10)
        ]
    )
    analysis = {"coupling_scores": scores}
    r = ConcentrationRiskDetector().detect(graph, analysis, {})
    assert len(r) == 1
    assert r[0]["type"] == "concentration_risk"
    assert r[0]["module"] == "system"


def test_concentration_risk_skips_small_graphs():
    nodes = [{"id": f"/p/f{i}.py"} for i in range(4)]
    graph = _graph(nodes=nodes, edges=[])
    analysis = {"coupling_scores": []}
    r = ConcentrationRiskDetector().detect(graph, analysis, {})
    assert r == []


def test_unstable_dep_detector_fires_on_stable_depending_on_unstable():
    graph = _graph(
        nodes=[{"id": "/p/stable.py"}, {"id": "/p/wild.py"}],
        edges=[{"source": "/p/stable.py", "target": "/p/wild.py"}],
    )
    analysis = {
        "coupling_scores": [
            {"file": "/p/stable.py", "instability": 0.2},
            {"file": "/p/wild.py", "instability": 0.9},
        ],
    }
    r = UnstableDependencyDetector().detect(graph, analysis, {})
    assert len(r) == 1
    assert r[0]["type"] == "unstable_dependency"
    assert r[0]["metrics"]["dependency"] == "/p/wild.py"


def test_unstable_dep_detector_skips_unstable_depending_on_unstable():
    graph = _graph(
        nodes=[{"id": "/p/a.py"}, {"id": "/p/b.py"}],
        edges=[{"source": "/p/a.py", "target": "/p/b.py"}],
    )
    analysis = {
        "coupling_scores": [
            {"file": "/p/a.py", "instability": 0.9},
            {"file": "/p/b.py", "instability": 0.9},
        ],
    }
    r = UnstableDependencyDetector().detect(graph, analysis, {})
    assert r == []
