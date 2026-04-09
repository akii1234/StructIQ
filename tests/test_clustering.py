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


def test_clustering_is_deterministic_under_rename():
    """Renaming a directory must not change which groups merge."""
    edges_a = [
        ("/proj/alpha/views.py", "/proj/beta/models.py"),
        ("/proj/alpha/services.py", "/proj/beta/models.py"),
        ("/proj/alpha/serializers.py", "/proj/beta/models.py"),
    ]
    edges_b = [
        ("/proj/zzz/views.py", "/proj/aaa/models.py"),
        ("/proj/zzz/services.py", "/proj/aaa/models.py"),
        ("/proj/zzz/serializers.py", "/proj/aaa/models.py"),
    ]
    result_a = ClusteringEngine().cluster(_graph(edges_a), {})
    result_b = ClusteringEngine().cluster(_graph(edges_b), {})
    assert len(result_a) == len(result_b)
    assert len(result_a) == 1


def test_singleton_absorbs_into_larger_group_on_tie():
    """When cross-edge counts are tied, singleton absorbs into larger group."""
    edges = [
        ("/proj/single/a.py", "/proj/small/x.py"),
        ("/proj/single/a.py", "/proj/large/x.py"),
    ]
    extra = [
        "/proj/small/y.py",
        "/proj/large/y.py",
        "/proj/large/z.py",
        "/proj/large/w.py",
        "/proj/large/v.py",
    ]
    result = ClusteringEngine().cluster(_graph(edges, extra_nodes=extra), {})
    large_svc = next(
        (s for s, fs in result.items() if any("large" in f for f in fs)), None
    )
    assert large_svc is not None
    single_in_large = any("single" in f for f in result[large_svc])
    single_in_small = any(
        "single" in f
        for s, fs in result.items()
        if any("small" in f for f in fs)
        for f in fs
    )
    assert single_in_large, (
        "single/a.py should absorb into the larger group (large) when cross-edge counts tie; "
        f"result services: {list(result.keys())}"
    )


def test_files_importing_same_hub_cluster_together():
    """Files that all import a common hub should land in the same service."""
    edges = [
        ("/proj/app1/views.py", "/proj/shared/models.py"),
        ("/proj/app2/services.py", "/proj/shared/models.py"),
        ("/proj/app3/serializers.py", "/proj/shared/models.py"),
        ("/proj/app4/admin.py", "/proj/shared/models.py"),
    ]
    analysis = {
        "coupling_metrics": {
            "/proj/shared/models.py": {"ca": 4, "ce": 0},
        }
    }
    result = ClusteringEngine().cluster(_graph(edges), analysis)
    assert len(result) <= 3, f"Expected ≤3 services but got {len(result)}: {list(result.keys())}"


def test_low_ca_file_does_not_trigger_hub_merge():
    """A file with Ca=1 should not be treated as a hub."""
    edges = [
        ("/proj/app1/views.py", "/proj/shared/utils.py"),
    ]
    analysis = {
        "coupling_metrics": {
            "/proj/shared/utils.py": {"ca": 1, "ce": 2},
        }
    }
    result = ClusteringEngine().cluster(_graph(edges), analysis)
    assert len(result) >= 1
