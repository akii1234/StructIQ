# StructIQ — AI Modernization Engine

A deterministic, cost-aware codebase intelligence system that scans any software project, maps its architecture, detects structural and security problems, and produces a prioritized modernization plan — with no mandatory LLM dependency.

---

## What It Does

Point it at any codebase. It will:

1. **Discover and classify** every file — language, role, complexity, purpose
2. **Map dependencies** — who imports who, where the cycles are, which files are overloaded
3. **Detect architectural problems** — 24 anti-pattern types across 5 domains: structural, complexity, maintainability, security, and migration readiness
4. **Scan Terraform IaC** — flags security misconfigurations in `.tf` files: open security groups, wildcard IAM, public S3 buckets, unencrypted storage, missing remote state, and oversized modules
5. **Generate a modernization plan** — prioritized, explainable, risk-ordered steps to fix what it found
6. **Enrich findings with LLM** — when LLM is enabled, replaces generic template descriptions with file-specific commentary for each high-severity finding

All stages are deterministic and run for $0. LLM is an optional advisor — never the decision-maker.

Developer: django.devakhil21@gmail.com

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
  -e LLM_PROVIDER=openai \
  -e API_KEY=your_api_key \
  -e ALLOWED_BASE_DIR=/repos \
  -v /your/repos:/repos \
  structiq
```

**Browser UI:**

Open `http://localhost:8000` in your browser for the interactive UI — start runs, monitor progress, and view reports without the CLI.

**Analyze via API:**
```bash
# Start a run (LLM disabled)
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "/repos/your-project"}'

# Start a run with LLM enabled (OpenAI)
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "repo_path": "/repos/your-project",
    "enable_llm": true,
    "llm_provider": "openai",
    "llm_model": "gpt-4.1-mini",
    "openai_api_key": "sk-..."
  }'

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
| `ENABLE_LLM` | `false` | Enable optional LLM calls for summaries, narratives, and finding enrichment |
| `LLM_PROVIDER` | `openai` | LLM provider: `openai`, `anthropic`, `groq`, `ollama` |
| `OPENAI_API_KEY` | — | API key for OpenAI (or compatible provider) |
| `APP_MODE` | `cli` | Set to `api` to enable auth and path restrictions |
| `API_KEY` | — | Required when `APP_MODE=api` |
| `ALLOWED_BASE_DIR` | — | Required when `APP_MODE=api` — restricts analyzable paths |
| `DATA_DIR` | `data/runs` | Directory where run outputs are stored |
| `MAX_CONCURRENT_RUNS` | `5` | API mode concurrency cap |
| `MAX_WORKERS` | `4` | Parallel file processing threads |
| `CACHE_ENABLED` | `true` | SHA256-based LLM result cache |
| `IGNORED_DIRECTORIES` | `__pycache__,venv,.git,node_modules,dist,build,target,migrations` | Comma-separated list of directory names to skip during scanning |

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
│   Phase 2   │  Dependency graph construction, analysis, and Terraform IaC resource scan
│ Dependency  │  Output: dependency_graph.json, dependency_analysis.json, terraform_scan.json
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Phase 3   │  Architecture clustering, anti-pattern detection (24 types, 5 domains),
│Architecture │  optional LLM recommendations + per-finding enrichment
│             │  Output: architecture_insights.json, enriched_insights.json (when LLM enabled)
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

Parses imports across Python, JavaScript/TypeScript, Java, and Go. Builds a directed dependency graph and computes structural metrics. Also runs a Terraform resource scan when `.tf` files are present.

**What it computes:**
- Afferent coupling (Ca) — how many files depend on this file
- Efferent coupling (Ce) — how many files this file depends on
- Instability — `Ce / (Ca + Ce)` — 0 = stable, 1 = unstable
- Dependency depth — longest path from any root to this node
- Cycles — strongly connected components via iterative DFS
- Entry points — files with no incoming dependencies
- Module coupling — cross-module dependency edges

**Terraform IaC scan:**

When `.tf` files are found, a `TerraformResourceScanner` extracts all security-relevant resource blocks (using a brace-depth state machine — no external HCL parser) and writes `terraform_scan.json`. Non-fatal: no `.tf` files means `terraform_scan.json` is not written and all downstream IaC detectors silently skip.

Scanned resource types: `aws_security_group`, `aws_iam_policy`, `aws_iam_role`, `aws_iam_role_policy`, `aws_s3_bucket`, `aws_s3_bucket_public_access_block`, `aws_db_instance`, `aws_rds_cluster`, `aws_instance`, `aws_eks_cluster`.

**Output files:**
- `dependency_graph.json` — nodes and edges
- `dependency_analysis.json` — computed metrics
- `terraform_scan.json` — resource blocks, backend config, resource type counts per file (only when `.tf` files present)

---

### Phase 3 — Architecture Intelligence

Processes the dependency graph into architecture-level insights. Groups files into logical services and detects structural anti-patterns across 5 domains. Produces a domain health score for each.

**Domain scoring:**

| Domain | Weight | What it covers |
|---|---|---|
| `structural` | 25% | Cycles, coupling, hub files, concentration risk |
| `complexity` | 20% | File size, function density, coupling thresholds |
| `maintainability` | 20% | Test coverage gaps, boundary violations, oversized modules |
| `security` | 20% | IaC misconfigurations, IAM hygiene, Lambda architecture |
| `migration` | 15% | Hardcoded config, missing abstraction layers |

**Anti-patterns detected (24 types):**

*Structural*

| Type | Description | Severity |
|---|---|---|
| `cycle` | Circular dependency between files | High |
| `god_file` | File with high Ca, Ce, and depth — centralises too many responsibilities | High |
| `hub_file` | File that is a disproportionate dependency hub across modules | High |
| `concentration_risk` | Single file accounts for a large share of all inter-module dependencies | High |
| `high_coupling` | Total coupling above 2× the project median (package boilerplate excluded) | Medium |
| `unstable_dependency` | Stable file depends on an unstable file — fragile foundation | Medium |
| `orphan_file` | File with no incoming or outgoing dependencies | Low |

*Complexity*

| Type | Description | Severity |
|---|---|---|
| `large_file` | File significantly exceeds the project's median line count | Medium |
| `large_function` | Function body exceeds safe length threshold | Medium |
| `too_many_functions` | File defines more functions than a single module should own | Medium |

*Maintainability*

| Type | Description | Severity |
|---|---|---|
| `test_gap` | Production module with no corresponding test file | Medium |
| `weak_boundary` | Module with significantly more external than internal dependencies | Medium |
| `mega_module` | Module containing a disproportionate share of all project files | Medium |

*Security — IaC (requires Terraform files)*

| Type | Description | Severity |
|---|---|---|
| `open_security_group` | `aws_security_group` with `0.0.0.0/0` ingress — open to the internet | High |
| `wildcard_iam` | IAM resource granting wildcard `Action "*"` — violates least-privilege | High |
| `public_s3_bucket` | S3 bucket with public ACL or no `aws_s3_bucket_public_access_block` | High |
| `unencrypted_storage` | RDS with `storage_encrypted = false`, or S3 with no encryption config | Medium |
| `no_remote_state` | No remote Terraform backend — state is local, blocks team collaboration | Medium |
| `god_module` | Single `.tf` file defines ≥ 6 distinct resource types — high blast radius | Medium |

*Security — Lambda*

| Type | Description | Severity |
|---|---|---|
| `god_lambda` | Lambda function handling too many event source types | High |
| `direct_lambda_invocation` | Lambda invoked directly rather than through an event bus | Medium |
| `shared_iam_role` | Multiple Lambda functions sharing a single IAM execution role | Medium |

*Migration*

| Type | Description | Severity |
|---|---|---|
| `hardcoded_config` | Configuration values embedded directly in source code | Medium |
| `no_abstraction_layer` | Direct infrastructure calls with no service/repository abstraction | Medium |

**Service clustering:** Files grouped by parent directory, then split into weakly connected components within each group, then merged if they share ≥2 imports.

**Per-finding LLM enrichment (when LLM enabled):**

High-severity findings, plus selected medium-severity structural patterns (`high_coupling`, `god_file`, `weak_boundary`, `mega_module`), are sent in a single batched LLM call. The LLM replaces generic template descriptions with file-specific commentary — including what the file actually does and who depends on it. Enriched results are stored in `enriched_insights.json` and preferred over `architecture_insights.json` by the report generator.

**Output:**
- `architecture_insights.json` — services, anti_patterns, recommendations, domain_scores, system_summary
- `enriched_insights.json` — same structure with LLM-enriched descriptions (only when LLM enabled)

```json
{
  "run_id": "...",
  "generated_at": "...",
  "services": { "service_name": ["file1.py", "file2.py"] },
  "anti_patterns": [...],
  "recommendations": [...],
  "domain_scores": {
    "structural":      { "score": 82, "weight": 0.25 },
    "complexity":      { "score": 91, "weight": 0.20 },
    "maintainability": { "score": 74, "weight": 0.20 },
    "security":        { "score": 55, "weight": 0.20 },
    "migration":       { "score": 88, "weight": 0.15 }
  },
  "overall_score": 79,
  "root_cause_narrative": "The codebase shows signs of an organically grown monolith...",
  "system_summary": "Analyzed 142 files grouped into 8 logical services. Found 6 architectural issue(s)."
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
| `high_coupling` | `reduce_coupling` | `extract_utility` — suggests `{stem}_utils{suffix}` (preserves original file extension) |
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
| `GET` | `/` | Browser UI |
| `GET` | `/health` | Service health check |
| `GET` | `/runs` | List all runs with status |
| `POST` | `/analyze` | Start an async analysis run |
| `GET` | `/status/{run_id}` | Run status, per-phase status, and LLM usage stats |
| `GET` | `/results/{run_id}` | Phase 1 discovery output |
| `GET` | `/dependency/graph/{run_id}` | Dependency graph |
| `GET` | `/dependency/analysis/{run_id}` | Dependency metrics |
| `GET` | `/architecture/insights/{run_id}` | Architecture anti-patterns, domain scores, and services |
| `GET` | `/modernization/plan/{run_id}` | Full modernization plan |
| `GET` | `/report/{run_id}` | Self-contained HTML report (completed runs only) |
| `POST` | `/explain/{run_id}` | Answer a plain-English question about a completed run |

**`POST /analyze` request body:**
```json
{
  "repo_path": "/path/to/project",
  "enable_llm": false,
  "llm_provider": "openai",
  "llm_model": "gpt-4.1-mini",
  "openai_api_key": "sk-..."
}
```

`llm_provider` accepts: `openai`, `anthropic`, `groq`, `ollama`. Provider and model are per-run — no server restart needed to switch.

**Status response:**
```json
{
  "run_id": "...",
  "status": "completed",
  "progress": { "total_files": 142, "processed": 138, "skipped": 4, "failed": 0 },
  "phase2_status": "ok",
  "phase3_status": "ok",
  "phase4_status": "ok",
  "llm_stats": {
    "enabled": true,
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "phase1_enabled": true,
    "phase3_narrative": true,
    "phase4_summary": true
  }
}
```

Phase status values: `pending` | `running` | `ok` | `failed` | `not_run`

Run status values: `running` | `phase2_running` | `phase3_running` | `phase4_running` | `completed` | `failed`

---

## HTML Report

The report is a self-contained HTML file served at `GET /report/{run_id}`. It includes:

- **Overview** — file count, service count, anti-pattern count, decision badge, LLM provider/phases used
- **Dependency Graph** — interactive Cytoscape.js graph with dagre layout. Double-click any module node to drill into its file-level view. Green = entry point, red = anti-pattern, dashed = external module stub. Export button saves a PNG.
- **Architecture** — domain health scores, anti-pattern cards with severity, location, coupling metrics, and LLM-enriched descriptions (when LLM enabled)
- **Plan** — risk-ordered execution steps with per-change rationale, impact, and alternatives

A pre-generated example is at [`examples/report.html`](examples/report.html). To regenerate:
```bash
python scripts/generate_example.py
```

---

## LLM Usage

StructIQ runs fully without an LLM. LLM is opt-in per run — enabled via the UI toggle, the `/analyze` request body, or the `ENABLE_LLM` env var.

**Supported providers:**

| Provider | Default model | Notes |
|---|---|---|
| `openai` | `gpt-4.1-mini` | Requires `OPENAI_API_KEY` or key in request |
| `anthropic` | `claude-haiku-4-5-20251001` | Requires `ANTHROPIC_API_KEY` or key in request |
| `groq` | `llama-3.1-8b-instant` | Requires `GROQ_API_KEY` or key in request |
| `ollama` | `llama3.2` | Requires local Ollama server at `http://localhost:11434` |

**What LLM adds when enabled:**

| Phase | Component | What it does | Calls per run |
|---|---|---|---|
| Phase 1 | Summarizer | Plain-English summaries for high-complexity files | 1 per high-priority file |
| Phase 3 | RecommendationEngine | Architecture recommendations + `root_cause_narrative` | 1 |
| Phase 3 | FindingEnricher | Replaces generic template text with file-specific descriptions for high/key-medium findings | 1 (batched) |
| Phase 4 | PlanGenerator | `plan_summary` + `sequencing_notes` + per-task rationale enrichment | 1 |
| Reporting | ReportGenerator | Plain-English architectural story for the report header | 1 per report |
| API | `/explain/{run_id}` | Answers plain-English questions using the plan as context | 1 per request |

**FindingEnricher detail:** Batches all eligible findings into a single LLM call. Always enriches `severity == high` findings. Also enriches `high_coupling`, `god_file`, `weak_boundary`, and `mega_module` at medium severity (these are structural signals, not alarms). Skips `test_gap` and `orphan_file` (too numerous, too repetitive). Capped at 8 findings per run. Enriched descriptions overwrite generic templates; the planner prefers `enriched_why`/`enriched_impact` over its own templates when present.

All LLM calls use compressed payloads — raw file content is never sent. LLM failures are non-fatal; the pipeline continues with deterministic output if any call fails.

---

## Run Data

Each run stores its data under `$DATA_DIR/{run_id}/` (default: `data/runs/{run_id}/`):

```
{run_id}/
├── output.json                  # Phase 1 output
├── dependency_graph.json        # Phase 2 graph
├── dependency_analysis.json     # Phase 2 metrics
├── terraform_scan.json          # Phase 2 Terraform IaC scan (only when .tf files present)
├── architecture_insights.json   # Phase 3 insights
├── enriched_insights.json       # Phase 3 LLM-enriched findings (only when LLM enabled)
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
| Terraform | Module sources, Lambda function edges, full resource block scanning |

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
- Terraform parsing uses regex-based state machine — heavily malformed HCL may produce incomplete results

---

## Roadmap

**Complete:**
- Phase 1–4 core pipeline — deterministic discovery, dependency graph, architecture analysis, modernization planning
- Decision intelligence — confidence scoring, multi-strategy evaluation, task dominance filtering, context-aware plan modes
- LLM intelligence layer — root_cause_narrative, sequencing_notes, report narrative, /explain endpoint, multi-provider support, per-run LLM config
- Per-finding LLM enrichment — FindingEnricher replaces generic template text with file-specific LLM commentary
- Reporting — interactive Cytoscape.js dependency graph with module drill-down, domain health scores, LLM usage card
- Terraform IaC analysis — TerraformResourceScanner + 6 security detectors (open_security_group, wildcard_iam, public_s3_bucket, unencrypted_storage, no_remote_state, god_module) + security domain in health score

**Planned:**
- Architecture Review tab — deterministic structured review (severity table, coupling map, fix order) derived from existing phase outputs
- Run lifecycle — TTL-based cleanup, run deletion API
- SARIF output + GitHub Action for CI integration

**Future:**
- Developer-in-the-loop assisted refactoring (Phase 6)
- YAML/Kubernetes manifest analysis

---

## License

MIT — see [LICENSE](LICENSE) for details.
