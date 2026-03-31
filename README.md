# StructIQ (AI Modernization Engine)

StructIQ is a deterministic, multi-phase code analysis pipeline:

1. Discovery (Phase 1) — scan + summarize code (LLM used only for summaries, and can be disabled)
2. Dependency Analysis (Phase 2) — build dependency graph + compute architecture metrics
3. Architecture Intelligence (Phase 3) — cluster into services, detect anti-patterns, generate insights
4. Modernization Planning (Phase 4) — generate modernization tasks, structural change intents, and an execution plan
5. Decision Intelligence (Phase 4.5/Phase 5) — deterministic strategy selection and explainability for each task

## Requirements

```bash
pip install -r requirements.txt
```

## Environment Variables

- `APP_MODE` — `cli` (default) or `api`
- `ENABLE_LLM` — enable/disable LLM usage (default: `true`)
- `OPENAI_API_KEY` — required if `ENABLE_LLM=true`
- `API_KEY` — required when `APP_MODE=api`
- `ALLOWED_BASE_DIR` — required in API mode for request path validation
- `MAX_CONCURRENT_RUNS` — API concurrency limit (default: `5`)

## CLI Usage

Run from the parent directory of `StructIQ`:

```bash
cd /Users/akhiltripathi/dev
python -m StructIQ.main /path/to/project --output data/runs/output.json
```

By default, the discovery pipeline writes outputs under `data/runs/<run_id>/` (and uses `output.json` as an input/output anchor for CLI).

## API Usage

Run from the parent directory of `StructIQ`:

```bash
cd /Users/akhiltripathi/dev
export APP_MODE=api
export API_KEY=your_api_key
export ALLOWED_BASE_DIR=/path/you/allow
python -m StructIQ.main --serve --host 0.0.0.0 --port 8000
```

Health:
- `GET /health`

Run + results:
- `POST /analyze` (returns `{ "run_id": "...", "status": "started" }`)
- `GET /status/{run_id}`
- `GET /results/{run_id}`

Phase outputs:
- `GET /dependency/graph/{run_id}`
- `GET /dependency/analysis/{run_id}`
- `GET /architecture/insights/{run_id}`
- `GET /modernization/plan/{run_id}`

## Outputs (JSON)

Each run writes:
- `output.json` — Phase 1 discovery output
- `dependency_graph.json` — Phase 2 graph
- `dependency_analysis.json` — Phase 2 analysis metrics
- `architecture_insights.json` — Phase 3/3.5 insights (services, anti-patterns, recommendations)
- `modernization_plan.json` — Phase 4/4.5 modernization plan (tasks, changes, impact, execution plan)

