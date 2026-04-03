# tests/test_line_precision.py
import textwrap
from StructIQ.dependency.extractor import extract_imports


def test_python_import_has_line_number():
    src = textwrap.dedent("""\
        import os
        from pathlib import Path
        from mymodule import something
    """)
    records = extract_imports("myfile.py", "python", text=src)
    for rec in records:
        assert "line_number" in rec, f"Missing line_number in record: {rec}"


def test_python_import_line_numbers_are_correct():
    src = textwrap.dedent("""\
        import os
        # comment line
        from pathlib import Path
        from mymodule import something
    """)
    records = extract_imports("myfile.py", "python", text=src)
    by_target = {r["import_target"]: r["line_number"] for r in records}
    assert by_target["os"] == 1
    assert by_target["pathlib"] == 3
    assert by_target["mymodule"] == 4


def test_javascript_import_has_line_number():
    src = textwrap.dedent("""\
        const x = require('./utils');
        import foo from './bar';
    """)
    records = extract_imports("app.js", "javascript", text=src)
    for rec in records:
        assert "line_number" in rec


def test_java_import_has_line_number():
    src = textwrap.dedent("""\
        package com.example;
        import com.example.models.User;
        import com.example.services.AuthService;
    """)
    records = extract_imports("App.java", "java", text=src)
    java_records = [r for r in records if r.get("import_kind") == "absolute_local"]
    for rec in java_records:
        assert "line_number" in rec


def test_go_import_has_line_number():
    src = textwrap.dedent("""\
        package main
        import (
            "fmt"
            "github.com/myorg/myproject/utils"
        )
    """)
    records = extract_imports("main.go", "go", text=src)
    for rec in records:
        assert "line_number" in rec


def test_graph_edge_has_line_number(tmp_path):
    from StructIQ.dependency.graph_builder import build_graph

    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("x = 1\n")
    b.write_text("import os\nfrom a import x\n")

    phase1 = {
        "files": [str(a), str(b)],
        "classified_files": [
            {"file": str(a), "language": "python"},
            {"file": str(b), "language": "python"},
        ],
        "modules": {},
    }
    graph = build_graph(phase1, str(tmp_path), "test-run")
    edges = graph.get("edges") or []
    matching = [e for e in edges if "b.py" in e["source"] and "a.py" in e["target"]]
    assert matching, "Expected edge from b.py to a.py"
    assert matching[0].get("line_number") == 2
