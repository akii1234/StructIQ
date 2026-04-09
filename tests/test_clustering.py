"""Tests for ClusteringEngine — service grouping."""
from __future__ import annotations

import math

from StructIQ.architecture.clustering import ClusteringEngine


def _graph(edges, extra_nodes=None):
    node_set = set()
    for s, t in edges:
        node_set.add(s)
        node_set.add(t)
    for n in extra_nodes or []:
        node_set.add(n)
    return {
        "nodes": [{"id": n} for n in sorted(node_set)],
        "edges": [{"source": s, "target": t} for s, t in edges],
    }


def test_files_in_same_directory_form_one_service():
    graph = _graph(
        [("/proj/candidate_ranking/views.py", "/proj/candidate_ranking/models.py")],
        extra_nodes=["/proj/candidate_ranking/admin.py", "/proj/candidate_ranking/tests.py"],
    )
    result = ClusteringEngine().cluster(graph, {})
    svc_for_cr = next((s for s, fs in result.items() if any("candidate_ranking" in f for f in fs)), None)
    assert svc_for_cr is not None
    cr_in_svc = [f for f in result[svc_for_cr] if "candidate_ranking" in f]
    all_cr = [n["id"] for n in graph["nodes"] if "candidate_ranking" in n["id"]]
    assert len(cr_in_svc) == len(all_cr)


def test_service_count_is_bounded():
    nodes = [f"/proj/app{i}/file{j}.py" for i in range(8) for j in range(5)]
    edges = [(f"/proj/app{i}/file0.py", f"/proj/app{i}/file1.py") for i in range(8)]
    graph = _graph(edges, extra_nodes=nodes)
    result = ClusteringEngine().cluster(graph, {})
    assert len(result) <= max(5, int(math.sqrt(len(nodes))) * 2)


def test_isolated_file_absorbed_not_isolated():
    graph = _graph(
        [
            ("/proj/myapp/views.py", "/proj/myapp/models.py"),
            ("/proj/myapp/services.py", "/proj/myapp/models.py"),
        ],
        extra_nodes=["/proj/myapp/admin.py"],
    )
    result = ClusteringEngine().cluster(graph, {})
    for svc, files in result.items():
        assert files != ["/proj/myapp/admin.py"], "admin.py became a lone service"


def test_highly_coupled_directories_merge():
    edges = [
        ("/proj/app1/views.py", "/proj/app2/models.py"),
        ("/proj/app1/services.py", "/proj/app2/models.py"),
        ("/proj/app1/serializers.py", "/proj/app2/models.py"),
    ]
    result = ClusteringEngine().cluster(_graph(edges), {})
    app1_svc = next((s for s, fs in result.items() if any("app1" in f for f in fs)), None)
    app2_svc = next((s for s, fs in result.items() if any("app2" in f for f in fs)), None)
    assert app1_svc == app2_svc


def test_unconnected_directories_stay_separate():
    # Each directory needs ≥3 files so pairs are not absorbed across dirs.
    graph = _graph(
        [
            ("/proj/frontend/api.js", "/proj/frontend/utils.js"),
            ("/proj/frontend/utils.js", "/proj/frontend/core.js"),
        ],
        extra_nodes=[
            "/proj/backend/models.py",
            "/proj/backend/views.py",
            "/proj/backend/services.py",
        ],
    )
    assert len(ClusteringEngine().cluster(graph, {})) >= 2


def test_returns_sorted_lists():
    graph = _graph([("/proj/app/views.py", "/proj/app/models.py")])
    for svc, files in ClusteringEngine().cluster(graph, {}).items():
        assert isinstance(files, list) and files == sorted(files)
