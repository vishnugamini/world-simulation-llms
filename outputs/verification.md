# Verification record

World Simulation LLMs, engine 1.0.0.

- Python: 24 tests passed. Covers deterministic simulation, food conservation, proportional sharing, connected terrain, extinction, recovery, persistence, unchanged and nested branches, paired comparisons, cancellation during execution, resume without duplicates, deadline enforcement, local-model validation failures, and API pagination.
- Browser: 4 Playwright tests passed in Chrome, using an isolated SQLite database and a dedicated test server. Covers inspection, playback, pause, rewind, branch creation, synchronized comparison, experiment results, CSV/ZIP exports, replay, unavailable-model behavior, mobile overflow, and reopening saved worlds.
- TypeScript and production Vite build passed. Fonts are bundled locally.
- Ruff checks passed. Python test output contains two third-party deprecation warnings from the Starlette/httpx test-client integration.
- Default benchmark: 300 completed runs, each 365 days; 50 matched seeds across three policies and two conditions. Measured elapsed time: 37.248121040989645 seconds. About 449 MB of compressed SQLite history at benchmark completion. See benchmark-report.md and benchmark-summary.json.
- Live local-model integration: qwen3:8b completed one bounded research round, four worlds, and a labeled interpretation in 53.30288910865784 seconds. No model was downloaded and no paid API was used. See local-research-smoke.json. This proves the integration, not the scientific reliability of generated interpretations.

The preloaded dry-season pair shares its initial state and environmental inputs and branches on day 80. Both histories are saved through day 130. The private policy remains in The dry season; The same season, shared switches to a common pool. The first colony starts with surplus sharing and is saved through day 12.

No recurring schedule or public deployment has been created. Local operation requires the application process to remain running; optional model research also requires Ollama. Start the app with `uv run python scripts/dev.py`.
