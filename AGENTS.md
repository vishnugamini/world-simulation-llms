# World Simulation LLMs

Python owns simulation behavior, experiments, persistence, and numeric reports. React renders recorded state and never determines outcomes. Do not introduce model calls into inhabitants or the daily engine.

## Local development

- `uv sync --extra dev`
- `uv run python scripts/dev.py` starts API :8765 and UI :5173, installing npm dependencies if missing.
- `uv run pytest -q` exercises simulation, persistence, jobs, HTTP, and researcher failure paths.
- `npm --prefix web run build` checks TypeScript and produces the local static UI.
- `uv run python scripts/generate_types.py` regenerates `web/src/generated.ts` from the FastAPI contract after model changes.
- `npm --prefix web test` starts an isolated browser-test server on :8766 using `.data/browser-tests.sqlite3`. Build the UI first. Tests use Chrome.

## Research with Codex

1. State a testable simulation question, identify relevant assumptions, and fix a run budget before execution.
2. Write an ExperimentSpec JSON file under `work/`; use the same seeds across policies. Start small, then confirm on a fresh disjoint seed range. No more than 500 runs or 30 minutes for a research session unless the user explicitly requests a different budget.
3. Execute `uv run virtual-world experiment --config work/experiment.json`. This is the same engine as the UI; no model API is required. CLI jobs are synchronous and print an experiment ID.
4. Inspect with `uv run virtual-world inspect JOB_ID`, and create a factual report with `uv run virtual-world report JOB_ID --output outputs/report.md`.
5. Separate measured numerical results from hypotheses and interpretation. Reference experiment IDs. Do not silently change the engine, select only favorable seeds, or equate simulation results with evidence about real societies.
6. Resume interrupted experiment batches with `uv run virtual-world experiment --resume JOB_ID`. Retain completed runs. Do not create recurring schedules unless asked.

SQLite state lives in `.data/world.sqlite3` (ignored). Override with `VIRTUAL_WORLD_DB` or CLI `--db`. Do not delete local worlds to fix failures. Run only one server per database. Do not download models automatically. The local Ollama researcher can propose only validated experiment parameters, and cannot execute code or enlarge its own limits.
