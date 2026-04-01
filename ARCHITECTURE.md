# StructIQ — Architecture Document

> This document is structured in three layers. A manager can stop after Layer 1. A tech lead will find everything they need in Layer 2. A developer contributing to or extending StructIQ should read all three.

---

## Layer 1 — The Problem, The Solution, The Value

### The Problem

Every engineering team eventually inherits a codebase they didn't write. It might be a legacy monolith, an acquired product, or a service that changed hands three times. The question is always the same: *where do I even start?*

The manual process looks like this:

- Weeks of reading code to understand what depends on what
- Whiteboards full of dependency diagrams that go stale the moment you draw them
- Debates about which files are "risky to touch" based on gut feel, not data
- Modernisation plans that are either too vague ("reduce coupling") or too specific to be actionable without full codebase context

Existing tools either sit at one extreme (static linters that flag style issues but say nothing about structure) or the other (AI-powered tools that require sending your entire codebase to an LLM at $10–$50 per run, with no guarantees of consistency).

The gap: **no tool gives you a structural audit with an actionable, prioritised plan, deterministically, at zero cost.**

---

### What StructIQ Does

StructIQ is a static analysis engine with an optional LLM advisory layer. Point it at any codebase and it produces:

1. **A complete dependency map** — who imports who, where the cycles are, which files are central
2. **Structural anti-pattern detection** — circular dependencies, god files, high coupling, weak module boundaries
3. **A prioritised modernisation plan** — risk-ordered steps with rationale, blast radius, and confidence scores
4. **An interactive HTML report** — self-contained, shareable, no server required

The entire pipeline is deterministic. The same codebase produces the same output every time. LLM is opt-in — it adds narrative quality to summaries and per-task rationale but is never the decision-maker. A tech lead can audit the logic behind every recommendation.

---

### Who It's For

| Persona | Pain point | What StructIQ gives them |
|---|---|---|
| **Tech lead inheriting a legacy codebase** | No map of the system, afraid to touch central files | Dependency graph, coupling scores, ranked change plan |
| **Engineering manager planning a migration** | Can't justify refactoring effort without data | Structured audit report, risk scores, decision: action required vs not |
| **Developer joining a new team** | Weeks of context-building before being productive | Visual architecture map, entry points, module structure in minutes |
| **Architect doing a pre-acquisition audit** | Need a structural health assessment quickly | HTML report, anti-pattern count, coupling heatmap |

---

### Why It's Better Than the Alternatives

| Approach | Cost | Consistency | Actionable plan | Works offline |
|---|---|---|---|---|
| Manual review | High (weeks of engineer time) | No | Maybe | Yes |
| LLM-only tools (send full codebase) | $10–50/run | No (non-deterministic) | Sometimes | No |
| Static linters (ESLint, Pylint) | $0 | Yes | No (style only) | Yes |
| **StructIQ (deterministic)** | **$0** | **Yes** | **Yes** | **Yes** |
| **StructIQ (LLM enriched)** | **~$0.001/run** | **Yes** | **Yes, with narrative** | **No** |

The key design insight: **static analysis makes the decisions; LLM writes the prose.** This means the plan is auditable, reproducible, and explainable — and the optional LLM cost is bounded and predictable.

---

### Cost Effectiveness

**Zero-LLM mode (default):**
- Compute: runs in under 5 seconds for a 200-file codebase on any laptop
- Infrastructure: a single Python process, no database, no external services
- Storage: ~50KB of JSON per run
- Cost: $0

**LLM-enriched mode:**
- Phase 1: ~100 tokens per high-priority file summary
- Phase 3: ~500 tokens for root cause narrative
- Phase 4: ~1,000 tokens for plan summary + per-task rationale (capped at 20 tasks)
- Report: ~300 tokens for narrative header
- **Total per run: ~2,000–3,000 tokens**
- At GPT-4.1-mini pricing ($0.40/1M input, $1.60/1M output): **~$0.001 per run**
- At claude-haiku-4-5 pricing: **~$0.0004 per run**
- At Groq (llama-3.1-8b-instant): **effectively free** (generous free tier)

A team running 100 analyses per month on GPT-4.1-mini spends less than $0.10/month on LLM costs.

---

## Layer 2 — System Architecture

### Design Principles

1. **Deterministic first** — Every structural decision (what's a cycle, what's high coupling, what's the fix order) is made by static analysis with explicit, auditable logic. LLM never determines structure.

2. **Non-fatal phase chain** — A failure in Phase 3 does not prevent Phase 4 from running. Each phase stores its error in the run snapshot and passes whatever it produced to the next phase. The run always reaches `completed` unless Phase 1 crashes.

3. **LLM as advisor, not engine** — LLM calls are wrapped in `try/except`, non-fatal, and purely additive. If every LLM call fails, the output is complete and correct — just without narrative prose.

4. **Per-run configuration** — LLM provider, model, and API key are specified per run (via API request body or UI), not as global server state. The server never stores API keys to disk.

5. **No code generation** — StructIQ describes *what* to change and *why*, never *how to write the code*. This keeps the output language-agnostic and avoids the liability of auto-applying changes.

---

### The Four-Phase Pipeline

```
Your Codebase (any path)
         │
         ▼
┌────────────────────────────────────────────────────┐
│  Phase 1 — Discovery                               │
│                                                    │
│  Walks directory tree, classifies every file by    │
│  language and role, extracts module structure,     │
│  computes complexity metrics, optionally calls     │
│  LLM for plain-English file summaries.             │
│                                                    │
│  Input:  filesystem path                           │
│  Output: output.json                               │
└────────────────────┬───────────────────────────────┘
                     │  (passes file list + summaries)
                     ▼
┌────────────────────────────────────────────────────┐
│  Phase 2 — Dependency Analysis                     │
│                                                    │
│  Parses imports across Python, JS/TS, Java, Go.    │
│  Builds directed dependency graph. Computes Ca,    │
│  Ce, instability, depth, cycles, entry points,     │
│  module coupling.                                  │
│                                                    │
│  Input:  output.json                               │
│  Output: dependency_graph.json                     │
│          dependency_analysis.json                  │
└────────────────────┬───────────────────────────────┘
                     │  (passes graph + metrics)
                     ▼
┌────────────────────────────────────────────────────┐
│  Phase 3 — Architecture Intelligence               │
│                                                    │
│  Detects anti-patterns (cycles, god files, high    │
│  coupling, weak boundaries). Groups files into     │
│  logical services. Optionally calls LLM for        │
│  recommendations and root cause narrative.         │
│                                                    │
│  Input:  dependency_analysis.json                  │
│  Output: architecture_insights.json                │
└────────────────────┬───────────────────────────────┘
                     │  (passes anti-patterns)
                     ▼
┌────────────────────────────────────────────────────┐
│  Phase 4 — Modernization Engine                    │
│                                                    │
│  Anti-patterns → Tasks → Changes → Impact →        │
│  Execution Plan. Risk-ordered steps with           │
│  confidence scores, blast radius, explainability.  │
│  Optionally calls LLM for per-task rationale.      │
│                                                    │
│  Input:  architecture_insights.json                │
│  Output: modernization_plan.json                   │
└────────────────────┬───────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────┐
│  Reporting Layer                                   │
│                                                    │
│  Reads all four JSON outputs. Renders self-        │
│  contained HTML report with interactive            │
│  Cytoscape.js dependency graph, anti-pattern       │
│  cards, and risk-ordered execution plan.           │
│                                                    │
│  Output: report.html (served at GET /report/{id})  │
└────────────────────────────────────────────────────┘
```

---

### Run Lifecycle

```
POST /analyze
     │
     ▼
run_manager.start_run()
     │  creates snapshot.json with status: running
     │  spawns background thread
     ▼
_execute_run()  ← background thread
     │
     ├─ phase1 → status: running        (Discovery)
     ├─ phase2 → status: phase2_running (Dependency)
     ├─ phase3 → status: phase3_running (Architecture)
     ├─ phase4 → status: phase4_running (Modernization)
     └─ done  → status: completed
                (or failed if Phase 1 crashes)

Phase errors are stored as phase2_error / phase3_error / phase4_error in snapshot.
Run always reaches `completed` unless Phase 1 crashes.
```

On server restart, `_reconcile_interrupted_runs()` marks any `running` snapshots as `failed` — no run is ever permanently stuck.

---

### Multi-LLM Architecture

All LLM calls go through a single unified client in `llm/client.py`:

```
AnalyzeRequest (per-run)
  { enable_llm, llm_provider, llm_model, openai_api_key }
         │
         ▼
  LLMClient(provider, api_key, model)
         │
         │  All four providers implement the same OpenAI-compatible
         │  API surface (chat completions + JSON mode).
         │
         ├── openai    → api.openai.com         (default: gpt-4.1-mini)
         ├── anthropic → api.anthropic.com      (default: claude-haiku-4-5)
         ├── groq      → api.groq.com/openai/v1 (default: llama-3.1-8b-instant)
         └── ollama    → localhost:11434/v1     (default: llama3.2)
         │
         ▼
  generate_json(prompt, content) → dict
```

The client is constructed once per run and passed down through the phase pipeline. If construction fails (bad key, missing provider), the error is caught and `llm_client` is set to `None` — all phases fall back to deterministic output gracefully.

---

### Security Model

| Mode | Authentication | Path restriction | Key storage |
|---|---|---|---|
| CLI | None | None (trusted operator) | Not applicable |
| API (`APP_MODE=api`) | `X-Api-Key` header required | `ALLOWED_BASE_DIR` env var — paths outside are rejected | Never stored to disk; per-request only |

Additional protections:
- All `run_id` parameters validated against UUID regex before filesystem access
- `/explain` question capped at 500 characters
- `pyvenv.cfg` marker detection skips virtualenv directories regardless of name
- `migrations`, `node_modules`, `dist`, `__pycache__`, `.git`, `venv`, `build`, `target` skipped by default (configurable via `IGNORED_DIRECTORIES`)

---

### Data Model

Each run stores its output as flat JSON files under `$DATA_DIR/{run_id}/`:

```
{run_id}/
├── snapshot.json             — live run state (status, progress, phase errors, llm_stats)
├── output.json               — Phase 1: file list, classifications, metrics, summaries
├── dependency_graph.json     — Phase 2: nodes[], edges[]
├── dependency_analysis.json  — Phase 2: cycles, coupling_scores, entry_points, module_coupling
├── architecture_insights.json — Phase 3: anti_patterns[], services{}, recommendations[]
├── modernization_plan.json   — Phase 4: tasks[], changes[], impact[], execution_plan[]
├── report.html               — Rendered HTML report (generated on demand)
└── logs.json                 — Per-file processing log
```

No database. No migrations. No ORM. JSON files are the database — readable, diffable, and portable.

---

## Layer 3 — Contributor Guide

### Key Files

```
StructIQ/
├── main.py                          CLI entrypoint — run_cli_sync(), --serve, --report flags
├── config.py                        Settings dataclass — all env vars with defaults
│
├── api/
│   └── routes.py                    12 FastAPI endpoints, AnalyzeRequest model, lifespan handler
│
├── services/
│   └── run_manager.py               Run lifecycle: start_run(), _execute_run(), get_status()
│                                    Reconciles interrupted runs on startup
│
├── scanner/
│   └── file_scanner.py              Directory walk, extension filtering, pyvenv.cfg detection
│
├── llm/
│   └── client.py                    Unified LLMClient — 4 providers, generate_json()
│                                    OpenAIClient = LLMClient  (backwards compat alias)
│
├── agents/
│   └── summarizer.py                Phase 1 LLM summarizer — priority routing, cache
│
├── dependency/
│   ├── graph_builder.py             Import parser for Python/JS/TS/Java/Go → edges
│   ├── graph_analyzer.py            Ca, Ce, instability, depth, cycle detection (iterative DFS)
│   └── pipeline.py                  Phase 2 orchestration
│
├── architecture/
│   ├── analyzer.py                  detect_cycles(), detect_high_coupling(), detect_god_files(),
│   │                                detect_weak_boundaries()
│   ├── recommender.py               Optional LLM recommendations + root_cause_narrative
│   ├── clustering.py                File → service grouping (WCC + merge on shared imports)
│   └── pipeline.py                  Phase 3 orchestration
│
├── modernization/
│   ├── planner.py                   Anti-patterns → Tasks with priority, confidence,
│   │                                explainability, strategy evaluation, dominance filtering
│   ├── change_generator.py          Tasks → structural change intents (from/to/action)
│   ├── impact_analyzer.py           BFS 3-hop blast radius, risk scoring per change
│   ├── plan_generator.py            Risk-ordered execution plan + optional LLM enrichment
│   └── pipeline.py                  Phase 4 orchestration + decision gate
│
├── reporting/
│   ├── report_generator.py          HTML report renderer — Cytoscape graph, anti-pattern
│   │                                cards, execution plan, optional LLM narrative
│   └── svg_generator.py            Legacy SVG generator (superseded by Cytoscape)
│
└── static/
    └── index.html                   Browser UI — run form, status polling, report viewer
```

---

### Phase Internals

#### Phase 1 — Discovery

`file_scanner.py` walks the directory, skipping `IGNORED_DIRECTORIES` by name and any directory containing a `pyvenv.cfg` file (virtualenv detection). For each file matching `SUPPORTED_EXTENSIONS`, it computes:
- Language classification
- Module (first path component)
- Line count, complexity estimate
- Priority tier: `high` (entry points, large files) / `medium` / `low`

`summarizer.py` then processes high-priority files through `LLMClient.generate_json()` if LLM is enabled. Results are cached by SHA256 of file content — identical files across runs never trigger a second LLM call.

#### Phase 2 — Dependency Analysis

`graph_builder.py` parses import statements per language:

| Language | What's parsed |
|---|---|
| Python | `import X`, `from X import Y`, relative imports (`from . import`, `from .. import`) |
| JS/TS | `import ... from '...'`, `require('...')` |
| Java | `import a.b.C` statements |
| Go | `import "pkg"` and grouped import blocks |

Each import is resolved to a known file path in the scanned codebase. Relative Python imports use the file's directory as the base. Dotted absolute paths are matched against all suffix sub-paths of known files (so `candidate_ranking.models` matches `backend/candidate_ranking/models.py`).

`graph_analyzer.py` computes metrics using iterative DFS (no recursion limit issues on deep graphs).

#### Phase 3 — Anti-Pattern Detection

**`detect_high_coupling`:** Sorts all files by `Ca + Ce` descending. Computes median total coupling across all files. Threshold = `max(median × 2, 4)`. Only flags files that meet the threshold — the first 10 are not automatically included. Package boilerplate (`__init__.py`, `apps.py`) is excluded regardless of coupling score.

**`detect_god_files`:** Requires both Ca ≥ 75th percentile AND Ce ≥ 75th percentile AND depth ≥ 2. All three conditions must hold.

**`detect_cycles`:** Reports strongly connected components from the dependency analyzer. Each cycle is one anti-pattern.

**`detect_weak_boundaries`:** Computes `external_edges / (internal_edges + 1)` per module. Flags modules where this ratio exceeds 1.5.

God file and high coupling results are deduplicated — if a file is already flagged as a god file, it is excluded from `high_coupling` results.

#### Phase 4 — Modernization Engine

The pipeline runs four components in sequence:

```
ModernizationPlanner
  Anti-patterns → Tasks
  Scoring: priority_score = (severity × 0.5) + (centrality × 0.3) + (impact_weight × 0.2)
  Confidence: (severity × 0.4) + (centrality × 0.4) + (pattern_weight × 0.2)
  Dominance filtering: if break_cycle or split_file already covers file X,
    any reduce_coupling on X is moved to dominated_tasks
       │
       ▼
ChangeGenerator
  Tasks → Change intents (action, from, to)
  reduce_coupling → extract_utility to {stem}_utils{suffix}  (preserves file extension)
  break_cycle → break_dependency on lowest-centrality, lowest-fanout cycle edge
       │
       ▼
ImpactAnalyzer
  BFS up to 3 hops from each changed file
  risk = affected_count × 0.4 + avg_centrality × 0.4 + entry_point_flag × 0.2
  Escalates to "high" if any affected node has centrality > 0.7
       │
       ▼
PlanGenerator
  Sorts changes: low risk → medium → high (within tier: fewer affected files first)
  Renders _STEP_TEMPLATES or _STAGED_STEP_TEMPLATES per action type
  use_staged = total_nodes > 300 OR max_affected > 30
  Optional LLM call (1 per run): plan_summary + sequencing_notes + per-task rationale
    Rationale merge: LLM output overwrites deterministic why/impact_if_ignored per file
    Capped at 20 tasks in the LLM payload to bound token usage
    Fallback: deterministic text retained if LLM call fails
```

**Decision gate** (in `pipeline.py`): outputs `no_action_required` if the task list is empty OR all tasks are low-priority with low confidence. Both paths include `sequencing_notes`.

---

### LLM Integration Points

There are exactly 5 locations where LLM is called. All are wrapped in `try/except`. All degrade gracefully to empty string or `None`.

| Location | File | Trigger | Payload size | Output key |
|---|---|---|---|---|
| File summarizer | `agents/summarizer.py` | Per high-priority file, if `llm_client is not None` | File content (capped at `MAX_CONTENT_LENGTH` chars) | `summaries[file_path]` |
| Architecture recommendations | `architecture/recommender.py` | 1× per run, if `llm_client is not None` | Top 10 anti-patterns + cluster summary | `recommendations`, `root_cause_narrative` |
| Plan summary + per-task rationale | `modernization/plan_generator.py` | 1× per run, if `enable_llm and llm_client is not None` | Tasks (capped at 20) + change counts | `plan_summary`, `sequencing_notes`, `task_rationale[]` |
| Report narrative | `reporting/report_generator.py` | 1× per report render, if `llm_client is not None` | system_summary + anti-pattern types + decision | `narrative` (report header) |
| Explain endpoint | `api/routes.py` | 1× per `/explain` request | plan context + user question (≤500 chars) | Response text |

---

### Extending StructIQ

#### Adding a new language

1. Add the file extension to `SUPPORTED_EXTENSIONS` default in `config.py`
2. In `dependency/graph_builder.py`, add a new `_parse_<lang>_imports(content, file_path)` function
3. Add a branch in `_extract_imports()` that calls your function based on file extension
4. Add tests in `tests/test_graph_builder.py`

#### Adding a new anti-pattern type

1. Add detection logic as a new method on `ArchitectureAnalyzer` in `architecture/analyzer.py`
2. Call it from `analyze()` and append results to `anti_patterns`
3. Add a `task_type` mapping in `_TASK_TYPE_MAP` in `modernization/planner.py`
4. Add explainability text in `_EXPLAINABILITY_MAP`
5. Add a strategy list in `STRATEGY_MAP`
6. Add a change action in `ChangeGenerator.generate()` in `modernization/change_generator.py`
7. Add step templates in `_STEP_TEMPLATES` and `_STAGED_STEP_TEMPLATES` in `modernization/plan_generator.py`

#### Running the test suite

```bash
cd /path/to/parent/of/StructIQ
python -m pytest StructIQ/tests/ -v
# 48 tests, ~0.03s, zero LLM calls
```

All tests are deterministic. No mocking of LLM — tests exercise only the static analysis pipeline.

---

### Output Schemas (quick reference)

```
snapshot.json
  { run_id, status, progress, llm_stats, phase2_error, phase3_error, phase4_error }

dependency_analysis.json
  { cycles[[]], coupling_scores[{file, afferent_coupling, efferent_coupling}],
    entry_points[], most_depended_on[], most_dependencies[],
    dependency_depth{}, module_coupling[] }

architecture_insights.json
  { anti_patterns[{type, file/files/module, severity, description, ...}],
    services{name: [files]}, recommendations[], root_cause_narrative, system_summary }

modernization_plan.json
  { decision, plan_mode, plan_summary, sequencing_notes,
    tasks[{type, target[], priority, priority_score, confidence, why,
           impact_if_ignored, alternative, selected_strategy}],
    dominated_tasks[], changes[], impact[], execution_plan[] }
```

---

*StructIQ is MIT licensed. Contributions welcome — follow the extension guides above and ensure all 48 tests pass before opening a PR.*
