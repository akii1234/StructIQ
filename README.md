# StructIQ — AI Modernization Engine

A deterministic, cost-aware codebase intelligence system that scans any software project, maps its architecture, detects structural problems, and produces a prioritized modernization plan — with no mandatory LLM dependency.

---

## What It Does

Point it at any codebase. It will:

1. **Discover and classify** every file — language, role, complexity, purpose
2. **Map dependencies** — who imports who, where the cycles are, which files are overloaded
3. **Detect architectural problems** — circular dependencies, god files, high coupling, weak module boundaries
4. **Generate a modernization plan** — prioritized, explainable, risk-ordered steps to fix what it found

All four stages are deterministic and run for $0. LLM is an optional advisor for summaries only — never the decision-maker.

---

## Quick Start

**Install:**
```bash
git clone <repo>
cd StructIQ
pip install -e .
```

**CLI (single run):**
```bash
structiq /path/to/your/project
```

Or without installation:
```bash
python -m StructIQ.main /path/to/your/project
```

**API server:**
```bash
structiq --serve --host 0.0.0.0 --port 8000
```

**Docker (API server):**
```bash
docker build -t structiq .
docker run -p 8000:8000 \
  -e API_KEY=your_api_key \
  -e ALLOWED_BASE_DIR=/repos \
  -v /your/repos:/repos \
  structiq
```

With LLM enabled:
```bash
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=your_openai_key \
  -e ENABLE_LLM=true \
  -e API_KEY=your_api_key \
  -e ALLOWED_BASE_DIR=/repos \
  -v /your/repos:/repos \
  structiq
```

**Analyze via API:**
```bash
# Start a run
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "/repos/your-project"}'

# Returns: {"run_id": "uuid", "status": "started"}
```

**Poll for completion:**
```bash
curl http://localhost:8000/status/{run_id}
```

**Fetch the modernization plan:**
```bash
curl http://localhost:8000/modernization/plan/{run_id}
```

**Ask a plain-English question about a completed run:**
```bash
curl -X POST http://localhost:8000/explain/{run_id} \
  -H "Content-Type: application/json" \
  -d '{"question": "Where should I start the refactoring?"}'
```

**Get the HTML report:**
```bash
curl http://localhost:8000/report/{run_id} > report.html
```

---

## Configuration

Set via environment variables:

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Required only if `ENABLE_LLM=true` |
| `ENABLE_LLM` | `false` | Enable optional LLM calls for summaries and narratives |
| `APP_MODE` | `cli` | Set to `api` to enable auth and path restrictions |
| `API_KEY` | — | Required when `APP_MODE=api` |
| `ALLOWED_BASE_DIR` | — | Required when `APP_MODE=api` — restricts analyzable paths |
| `DATA_DIR` | `data/runs` | Directory where run outputs are stored |
| `MAX_CONCURRENT_RUNS` | `5` | API mode concurrency cap |
| `MAX_WORKERS` | `4` | Parallel file processing threads |
| `CACHE_ENABLED` | `true` | SHA256-based LLM result cache |

---

## Architecture

The engine runs four sequential phases. Each phase is non-fatal — if Phase 3 fails, Phase 4 still attempts to run with whatever Phase 3 produced.

```
Your Codebase
      │
      ▼
┌─────────────┐
│   Phase 1   │  File discovery, classification, static analysis + optional LLM summaries
│  Discovery  │  Output: output.json
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Phase 2   │  Dependency graph construction and analysis
│ Dependency  │  Output: dependency_graph.json, dependency_analysis.json
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Phase 3   │  Architecture clustering, anti-pattern detection, optional LLM recommendations
│Architecture │  Output: architecture_insights.json
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Phase 4   │  Modernization planning, change generation, impact analysis, execution plan
│Modernization│  Output: modernization_plan.json
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Reporting  │  Self-contained HTML report with dependency graph, anti-patterns, and plan
│   Layer     │  Output: report.html
└─────────────┘
```

---

## Phase Details

### Phase 1 — Discovery

Scans the project directory, classifies every file by language and role, extracts module structure, and optionally generates LLM summaries for high-complexity files.

**Three-tier routing:**
- **Low priority** — static analysis only, no LLM
- **Medium priority** — static analysis, LLM optional
- **High priority** — full LLM summarization

**Output (`output.json`):**
```json
{
  "files": [...],
  "classified_files": [...],
  "modules": [...],
  "summaries": {...},
  "metrics": {...}
}
```

---

### Phase 2 — Dependency Analysis

Parses imports across Python, JavaScript/TypeScript, Java, and Go. Builds a directed dependency graph and computes structural metrics.

**What it computes:**
- Afferent coupling (Ca) — how many files depend on this file
- Efferent coupling (Ce) — how many files this file depends on
- Instability — `Ce / (Ca + Ce)` — 0 = stable, 1 = unstable
- Dependency depth — longest path from any root to this node
- Cycles — strongly connected components via iterative DFS
- Entry points — files with no incoming dependencies
- Module coupling — cross-module dependency edges

**Output files:**
- `dependency_graph.json` — nodes and edges
- `dependency_analysis.json` — computed metrics

---

### Phase 3 — Architecture Intelligence

Processes the dependency graph into architecture-level insights. Groups files into logical services and detects structural anti-patterns.

**Anti-patterns detected:**

| Type | Description | Severity |
|---|---|---|
| `cycle` | Circular dependency between files | High |
| `god_file` | File with high Ca, Ce, and depth — centralises too many responsibilities | High |
| `high_coupling` | File with unusually high total coupling (above 2× median, floor of 5) | Medium |
| `weak_boundary` | Module with significantly more external than internal dependencies | Medium |

**Service clustering:** Files grouped by parent directory, then split into weakly connected components within each group, then merged if they share ≥2 imports.

**Output (`architecture_insights.json`):**
```json
{
  "run_id": "...",
  "generated_at": "...",
  "services": { "service_name": ["file1.py", "file2.py"] },
  "anti_patterns": [...],
  "recommendations": [...],
  "root_cause_narrative": "The codebase shows signs of an organically grown monolith...",
  "system_summary": "Analyzed 142 files grouped into 8 logical services. Found 3 architectural issue(s)."
}
```

---

### Phase 4 — Modernization Engine

Translates architectural problems into an actionable, prioritized remediation plan.

**Pipeline:**
```
Anti-patterns
     │
     ▼
ModernizationPlanner      → tasks with priority, confidence, explainability
     │
     ▼
ChangeGenerator           → structural change intents (no code generation)
     │
     ▼
ImpactAnalyzer            → BFS blast radius + risk scoring per change
     │
     ▼
PlanGenerator             → risk-ordered execution steps + optional LLM sequencing
```

**Task types and what triggers them:**

| Anti-pattern | Task | Change action |
|---|---|---|
| `cycle` | `break_cycle` | `break_dependency` — removes closing edge of cycle |
| `god_file` | `split_file` | `split_file` — suggests `{stem}_core{suffix}` sibling |
| `high_coupling` | `reduce_coupling` | `extract_utility` — suggests `parent/utils.py` |
| `weak_boundary` | `extract_module` | `extract_module` — suggests `{module}_extracted` |

**Task dominance filtering:** If `break_cycle` or `split_file` already targets file X, any `reduce_coupling` task on file X is removed as dominated. Dominated tasks are preserved in `dominated_tasks` with a `dominated_by` explanation.

**Context-aware plan mode:**
- `direct` — standard step-by-step changes (default)
- `staged` — incremental migration steps, used when >300 nodes or >30 files affected by a single change

**Risk scoring per change:**
- `low` — few files affected, low centrality
- `medium` — moderate spread or centrality
- `high` — >20 files affected, or any affected node with centrality >0.7

**Decision gate:**
- `no_action_required` — no tasks generated, or all tasks are low-priority with low confidence
- `action_required` — normal path

**Output (`modernization_plan.json`):**
```json
{
  "run_id": "...",
  "generated_at": "...",
  "decision": "action_required",
  "plan_mode": "direct",
  "plan_summary": "...",
  "sequencing_notes": "Start with breaking the dependency cycle — it unblocks the god file split.",
  "tasks": [
    {
      "type": "break_cycle",
      "target": ["src/utils.py", "src/models.py"],
      "priority": "high",
      "priority_score": 0.87,
      "confidence": 0.82,
      "why": "Circular dependencies prevent modular deployment...",
      "impact_if_ignored": "Build times increase, test isolation fails...",
      "alternative": "If breaking the cycle is too disruptive, introduce a shared interface module.",
      "selected_strategy": "break_dependency",
      "strategy_score": 0.82,
      "strategy_reason": "Lowest complexity, targets the closing edge of the cycle directly."
    }
  ],
  "dominated_tasks": [...],
  "changes": [...],
  "impact": [...],
  "execution_plan": [
    "[Change 1 — break_dependency | risk: high]",
    "  rationale: Circular dependency detected between modules",
    "  1.1. Identify the import of `src/models.py` inside `src/utils.py` that creates the cycle.",
    "  ..."
  ]
}
```

---

## API Reference

All endpoints accept an optional `X-Api-Key` header (required when `APP_MODE=api`).

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health check |
| `GET` | `/runs` | List all runs with status |
| `POST` | `/analyze` | Start an async analysis run |
| `GET` | `/status/{run_id}` | Run status and per-phase status |
| `GET` | `/results/{run_id}` | Phase 1 discovery output |
| `GET` | `/dependency/graph/{run_id}` | Dependency graph |
| `GET` | `/dependency/analysis/{run_id}` | Dependency metrics |
| `GET` | `/architecture/insights/{run_id}` | Architecture anti-patterns and services |
| `GET` | `/modernization/plan/{run_id}` | Full modernization plan |
| `GET` | `/report/{run_id}` | Self-contained HTML report (completed runs only) |
| `POST` | `/explain/{run_id}` | Answer a plain-English question about a completed run |

**Status response:**
```json
{
  "run_id": "...",
  "status": "completed",
  "progress": { "total_files": 142, "processed": 138, "skipped": 4, "failed": 0 },
  "phase2_status": "ok",
  "phase3_status": "ok",
  "phase4_status": "ok"
}
```

Phase status values: `pending` | `running` | `ok` | `failed` | `not_run`

Run status values: `running` | `phase2_running` | `phase3_running` | `phase4_running` | `completed` | `failed`

---

## Example Report

A pre-generated example report is available at [`examples/report.html`](examples/report.html).

To regenerate it:
```bash
python scripts/generate_example.py
```

---

## LLM Usage

StructIQ runs fully without an LLM. When `ENABLE_LLM=true`:

| Phase | Component | What it does | When it fires |
|---|---|---|---|
| Phase 1 | Summarizer | Plain-English summaries for high-complexity files | Per high-priority file |
| Phase 3 | RecommendationEngine | Architecture recommendations + `root_cause_narrative` connecting all anti-patterns | 1 call per run |
| Phase 4 | PlanGenerator | Executive summary (`plan_summary`) + `sequencing_notes` on change ordering | 1 call per run |
| Reporting | ReportGenerator | Plain-English architectural story for the report header | 1 call per report |
| API | `/explain/{run_id}` | Answers plain-English questions using the modernization plan as context | 1 call per request |

All LLM calls use compressed payloads — raw file content is never sent. LLM failures are non-fatal; the pipeline continues without the optional output.

---

## Run Data

Each run stores its data under `$DATA_DIR/{run_id}/` (default: `data/runs/{run_id}/`):

```
{run_id}/
├── output.json                  # Phase 1 output
├── dependency_graph.json        # Phase 2 graph
├── dependency_analysis.json     # Phase 2 metrics
├── architecture_insights.json   # Phase 3 insights
├── modernization_plan.json      # Phase 4 plan
├── report.html                  # Generated HTML report
├── logs.json                    # Per-file processing log
└── snapshot.json                # Resume state and phase errors
```

Runs are resumable. If a run is interrupted, restarting with the same `repo_path` will skip already-processed files.

---

## Supported Languages

| Language | Import extraction |
|---|---|
| Python | `import`, `from ... import` |
| JavaScript / TypeScript | `import`, `require()` |
| Java | `import` statements |
| Go | `import` blocks (single and grouped) |

---

## What StructIQ Does NOT Do

- Does not modify any source code
- Does not auto-apply refactors
- Does not make decisions without explainable reasoning
- Does not require an LLM to produce a complete plan

---

## Known Limitations

- File-based storage only — no horizontal scaling
- Rate limiting is in-memory (single process)
- No run data retention or cleanup policy
- No response models on API endpoints

---

## Roadmap

**Phase 5 (complete)** — Decision Intelligence: confidence scoring with interpretable factors, multi-strategy evaluation per anti-pattern type, context-aware plan adaptation (direct vs staged), task dominance filtering.

**Phase 5 LLM enhancements (complete)** — `root_cause_narrative`, `sequencing_notes`, report narrative header, `POST /explain/{run_id}`.

**Phase 5.5 (planned)** — Feedback loop for confidence calibration based on execution outcomes.

**Phase 6 (future)** — Developer-in-the-loop assisted refactoring.
