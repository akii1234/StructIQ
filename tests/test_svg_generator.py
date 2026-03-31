from StructIQ.reporting.svg_generator import generate_dependency_svg


def _small_graph() -> dict:
    return {
        "nodes": [
            {"id": "module_a/a.py", "in_degree": 1},
            {"id": "module_a/b.py", "in_degree": 2},
            {"id": "module_b/c.py", "in_degree": 1},
        ],
        "edges": [
            {"source": "module_a/a.py", "target": "module_a/b.py"},
            {"source": "module_a/b.py", "target": "module_b/c.py"},
        ],
    }


def test_empty_graph_returns_svg() -> None:
    output = generate_dependency_svg({}, set(), set())

    assert "<svg" in output


def test_no_nodes_returns_empty_svg() -> None:
    graph = {"nodes": [], "edges": []}

    output = generate_dependency_svg(graph, set(), set())

    assert "No dependency data available" in output


def test_small_graph_renders_nodes() -> None:
    output = generate_dependency_svg(_small_graph(), set(), set())

    assert output.count("<circle") >= 6


def test_small_graph_renders_edges() -> None:
    output = generate_dependency_svg(_small_graph(), set(), set())

    assert "<line" in output


def test_anti_pattern_node_colored_red() -> None:
    output = generate_dependency_svg(_small_graph(), {"module_a/a.py"}, set())

    assert output.count("#ef4444") >= 2


def test_entry_point_node_colored_green() -> None:
    output = generate_dependency_svg(_small_graph(), set(), {"module_a/a.py"})

    assert output.count("#22c55e") >= 2


def test_large_graph_uses_module_aggregation() -> None:
    nodes = [{"id": f"module_{i % 5}/file_{i}.py", "in_degree": 1} for i in range(200)]
    graph = {"nodes": nodes, "edges": []}

    output = generate_dependency_svg(graph, set(), set())

    assert output.startswith("<svg")
    assert "<circle" in output


def test_legend_always_present() -> None:
    output = generate_dependency_svg(_small_graph(), set(), set())

    assert "#ef4444" in output
    assert "#22c55e" in output
    assert "#60a5fa" in output
