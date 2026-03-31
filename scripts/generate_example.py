"""Generate a synthetic example StructIQ HTML report."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from StructIQ.reporting.report_generator import ReportGenerator

RUN_ID = "example-run-00000000"


def _build_fixtures() -> dict[str, dict]:
    nodes = [
        {
            "id": f"src/module_{i % 4}/file_{i}.py",
            "in_degree": (i % 5),
            "out_degree": (i % 3),
        }
        for i in range(24)
    ]
    edges = [
        {
            "source": f"src/module_{i % 4}/file_{i}.py",
            "target": f"src/module_{(i + 1) % 4}/file_{i + 1}.py",
        }
        for i in range(20)
    ] + [
        {"source": "src/module_0/file_0.py", "target": "src/module_1/file_5.py"},
        {"source": "src/module_1/file_5.py", "target": "src/module_0/file_0.py"},
    ]

    return {
        "output.json": {
            "files": [f"src/module_{i}/file_{i}.py" for i in range(24)],
            "metrics": {"total_files": 24, "processed": 22, "skipped": 2, "failed": 0},
        },
        "dependency_graph.json": {"nodes": nodes, "edges": edges},
        "dependency_analysis.json": {
            "entry_points": ["src/module_0/file_0.py"],
            "most_depended_on": [
                {"file": "src/module_0/file_0.py", "in_degree": 8},
                {"file": "src/module_1/file_5.py", "in_degree": 6},
                {"file": "src/module_2/file_10.py", "in_degree": 5},
                {"file": "src/module_3/file_15.py", "in_degree": 4},
                {"file": "src/module_0/file_4.py", "in_degree": 3},
            ],
            "most_dependencies": [
                {"file": "src/module_1/file_9.py", "out_degree": 7},
                {"file": "src/module_2/file_14.py", "out_degree": 5},
                {"file": "src/module_0/file_2.py", "out_degree": 4},
                {"file": "src/module_3/file_19.py", "out_degree": 3},
                {"file": "src/module_1/file_7.py", "out_degree": 2},
            ],
        },
        "architecture_insights.json": {
            "system_summary": "Analyzed 24 files grouped into 4 logical services. Found 3 architectural issues requiring attention.",
            "services": {
                "module_0": ["src/module_0/file_0.py", "src/module_0/file_4.py"],
                "module_1": ["src/module_1/file_5.py", "src/module_1/file_9.py"],
                "module_2": ["src/module_2/file_10.py", "src/module_2/file_14.py"],
                "module_3": ["src/module_3/file_15.py", "src/module_3/file_19.py"],
            },
            "anti_patterns": [
                {
                    "type": "cycle",
                    "severity": "high",
                    "files": ["src/module_0/file_0.py", "src/module_1/file_5.py"],
                    "description": "Circular dependency between module_0 and module_1 prevents independent deployment and complicates testing.",
                },
                {
                    "type": "god_file",
                    "severity": "high",
                    "file": "src/module_1/file_9.py",
                    "description": "File has unusually high afferent and efferent coupling — centralises too many responsibilities.",
                    "afferent_coupling": 8,
                    "efferent_coupling": 7,
                },
                {
                    "type": "high_coupling",
                    "severity": "medium",
                    "file": "src/module_2/file_10.py",
                    "description": "File coupling exceeds 2× the project median.",
                    "afferent_coupling": 5,
                    "efferent_coupling": 6,
                },
            ],
            "recommendations": [
                {
                    "message": "Break the circular dependency between module_0 and module_1 by introducing an abstraction layer.",
                    "based_on": ["cycle"],
                    "affected_files": ["src/module_0/file_0.py", "src/module_1/file_5.py"],
                }
            ],
        },
        "modernization_plan.json": {
            "run_id": RUN_ID,
            "generated_at": "2026-04-01T12:00:00Z",
            "decision": "action_required",
            "plan_mode": "direct",
            "plan_summary": "Three structural issues require attention. Begin with the dependency cycle as it blocks independent testing of both modules. The god file split can be parallelised once the cycle is resolved.",
            "sequencing_notes": "Start with breaking the dependency cycle — it unblocks the god file split. The coupling reduction in module_2 is independent and can proceed in parallel.",
            "tasks": [
                {
                    "type": "break_cycle",
                    "target": ["src/module_0/file_0.py", "src/module_1/file_5.py"],
                    "priority": "high",
                    "priority_score": 0.91,
                    "confidence": 0.88,
                    "reason": "Circular dependency detected",
                    "severity": "high",
                    "why": "Circular dependency prevents independent module deployment and complicates unit testing.",
                    "impact_if_ignored": "Coupling will worsen as the codebase grows, increasing build times and test complexity.",
                    "alternative": "If breaking the cycle is disruptive, introduce a shared interface module that both sides depend on.",
                    "selected_strategy": "break_dependency",
                    "strategy_score": 0.82,
                    "strategy_reason": "Lowest complexity, targets the closing edge of the cycle directly.",
                    "alternatives": ["introduce_abstraction"],
                },
                {
                    "type": "split_file",
                    "target": ["src/module_1/file_9.py"],
                    "priority": "high",
                    "priority_score": 0.84,
                    "confidence": 0.79,
                    "reason": "God file detected",
                    "severity": "high",
                    "why": "File concentrates too many responsibilities, making isolated changes risky.",
                    "impact_if_ignored": "Test coverage becomes harder to achieve; change radius grows over time.",
                    "alternative": "Introduce a facade to reduce external surface before splitting.",
                    "selected_strategy": "vertical_slice",
                    "strategy_score": 0.75,
                    "strategy_reason": "Vertical slice reduces risk by moving one responsibility at a time.",
                    "alternatives": ["horizontal_layer"],
                },
            ],
            "dominated_tasks": [
                {
                    "type": "reduce_coupling",
                    "target": ["src/module_1/file_9.py"],
                    "dominated_by": "split_file on src/module_1/file_9.py already addresses coupling",
                }
            ],
            "changes": [
                {"action": "break_dependency", "from": "src/module_0/file_0.py", "to": "src/module_1/file_5.py"},
                {"action": "split_file", "from": "src/module_1/file_9.py", "to": "src/module_1/file_9_core.py"},
            ],
            "execution_plan": [
                "[Change 1 — break_dependency | risk: medium]",
                "  rationale: Circular dependency prevents independent module deployment and complicates unit testing.",
                "  impact_if_ignored: Coupling will worsen as the codebase grows, increasing build times and test complexity.",
                "  alternative: If breaking the cycle is disruptive, introduce a shared interface module that both sides depend on.",
                "  1.1. Identify the import of `src/module_1/file_5.py` inside `src/module_0/file_0.py` that creates the cycle.",
                "  1.2. Introduce an intermediary abstraction or interface to decouple `src/module_0/file_0.py` from `src/module_1/file_5.py`.",
                "  1.3. Update `src/module_0/file_0.py` to depend on the abstraction rather than `src/module_1/file_5.py` directly.",
                "  1.4. Run dependency analysis to confirm the cycle is resolved.",
                "  1.5. Validate existing tests pass before merging.",
                "[Change 2 — split_file | risk: low]",
                "  rationale: File concentrates too many responsibilities, making isolated changes risky.",
                "  impact_if_ignored: Test coverage becomes harder to achieve; change radius grows over time.",
                "  2.1. Create new file `src/module_1/file_9_core.py` alongside `src/module_1/file_9.py`.",
                "  2.2. Identify responsibilities in `src/module_1/file_9.py` that belong in `src/module_1/file_9_core.py` (high-coupling logic).",
                "  2.3. Move identified code to `src/module_1/file_9_core.py`, keeping public interfaces stable.",
                "  2.4. Update all imports across the codebase from `src/module_1/file_9.py` to `src/module_1/file_9_core.py` where applicable.",
                "  2.5. Validate no regressions by running full test suite.",
            ],
        },
    }


def main() -> None:
    fixtures = _build_fixtures()
    with tempfile.TemporaryDirectory() as tmp:
        for filename, data in fixtures.items():
            Path(tmp, filename).write_text(json.dumps(data, indent=2), encoding="utf-8")
        html = ReportGenerator().generate(tmp, RUN_ID)

    project_root = Path(__file__).resolve().parents[1]
    out = project_root / "examples" / "report.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print("Example report written: examples/report.html")


if __name__ == "__main__":
    main()
