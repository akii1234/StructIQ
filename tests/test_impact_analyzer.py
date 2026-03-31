from StructIQ.modernization.impact_analyzer import (
    ImpactAnalyzer,
    _assess_risk,
    _bfs_affected,
    _build_adjacency,
    _build_centrality,
    _build_in_degree,
)


def test_build_adjacency_bidirectional() -> None:
    graph = {"edges": [{"source": "A", "target": "B"}]}

    adj = _build_adjacency(graph)

    assert "B" in adj["A"]
    assert "A" in adj["B"]


def test_build_adjacency_no_self_loops() -> None:
    graph = {"edges": [{"source": "A", "target": "A"}]}

    adj = _build_adjacency(graph)

    assert "A" not in adj.get("A", [])


def test_bfs_affected_max_hops() -> None:
    adj = {
        "A": ["B"],
        "B": ["A", "C"],
        "C": ["B", "D"],
        "D": ["C"],
    }

    affected = _bfs_affected(["A"], adj, max_hops=2)

    assert affected == {"A", "B", "C"}
    assert "D" not in affected


def test_bfs_affected_single_node() -> None:
    assert _bfs_affected(["solo.py"], {}, max_hops=3) == {"solo.py"}


def test_assess_risk_high_by_count() -> None:
    affected = {f"file_{i}.py" for i in range(21)}

    assert _assess_risk(affected, {}, set()) == "high"


def test_assess_risk_low() -> None:
    affected = {"a.py", "b.py"}
    centrality = {"a.py": 0.1, "b.py": 0.1}

    assert _assess_risk(affected, centrality, set()) == "low"


def test_assess_risk_escalates_on_high_centrality() -> None:
    affected = {"a.py", "b.py", "c.py"}
    centrality = {"a.py": 0.8, "b.py": 0.1, "c.py": 0.1}

    assert _assess_risk(affected, centrality, set()) in {"medium", "high"}


def test_assess_risk_escalates_on_entry_point() -> None:
    affected = {"a.py", "b.py"}
    centrality = {"a.py": 0.1, "b.py": 0.1}

    assert _assess_risk(affected, centrality, {"a.py"}) in {"medium", "high"}


def test_impact_analyzer_basic() -> None:
    graph = {
        "nodes": [
            {"id": "a.py", "in_degree": 1},
            {"id": "b.py", "in_degree": 2, "centrality": 0.8},
            {"id": "c.py", "in_degree": 0},
            {"id": "d.py", "in_degree": 1, "is_entry_point": True},
        ],
        "edges": [
            {"source": "a.py", "target": "b.py"},
            {"source": "b.py", "target": "c.py"},
            {"source": "c.py", "target": "d.py"},
        ],
    }
    changes_result = {
        "changes": [{"action": "break_dependency", "from": "a.py", "to": "b.py"}]
    }

    in_degree = _build_in_degree(graph)
    centrality = _build_centrality(graph, in_degree)
    result = ImpactAnalyzer().analyze(changes_result, graph)

    assert in_degree["b.py"] == 2
    assert 0.0 <= centrality["b.py"] <= 1.0
    assert len(result["impact"]) == 1
    assert result["impact"][0]["action"] == "break_dependency"
    assert result["impact"][0]["affected_count"] >= 1
    assert result["impact"][0]["risk"] in {"low", "medium", "high"}


def test_impact_analyzer_invalid_input() -> None:
    assert ImpactAnalyzer().analyze(["bad"], {}) == {"impact": []}
    assert ImpactAnalyzer().analyze({}, ["bad"]) == {"impact": []}
