# Prompt for the next Claude Code session (with the Databricks Genie MCP connected)

Paste everything below the line into a new Claude Code session started in this repo.

---

You are finishing a MadHacks 2026 hackathon project in this repo (`/Users/eric/Desktop/madhacks-2026`, branch `feat/sdk-demo-dashboard`). Judging is "Best Use of Databricks": Databricks core, a real raw -> cleaned -> served data spine, something live (an App or Genie space), and creativity/impact. Judging is Sunday 2 PM. Read `databricks/README.md`, `databricks/app/README.md` and `databricks/genie/GENIE_SPACE.md` first.

## The project
A Human x AI / HCI loop: (1) a telemetry SDK records how people use a UI, (2) literature-based tasks (Amar/Eagan/Stasko chart-reading tasks with known answers) give success/abandon outcomes, (3) raw events land in Databricks (Volume -> bronze -> silver -> gold) with research-motivated metrics, (4) Genie diagnoses problems from the gold tables, (5) **Claude acts as the designer**: it proposes concrete UI changes citing the metric and element behind each one, (6) the proposed v2 is re-tested against v1 through the same pipeline. The mock company is "Taxi Ops"; its demo dashboard has planted flaws (F1 truncated axis, F2 low-contrast colors, F3 filter hidden in a "..." menu, F4 fake-clickable KPI `kpi-avg-fare`).

## What is already built and verified
- SDK (`packages/core`), Chrome extension (`dbx-telemetry-ext`), demo dashboard v1/v2 (`demo/`), with Playwright e2e tests.
- Databricks pipeline `databricks/sql/00..03,05`: ran on the user's Free Edition workspace (`workspace.ux_telemetry`, Volume `raw_events`, files in `/Volumes/workspace/ux_telemetry/raw_events/raw/`). Simulated data: bronze 4087 events, silver trials 300; v1->v2 matches the local test (T4 abandon 0.27 -> 0.00, T2 success 0.37 -> 0.77).
- Databricks App `databricks/app/` (collector + dashboard): deployed; the service principal needed READ VOLUME as well as WRITE VOLUME (use the client_id UUID in grants). `GET /status` shows sink, counts and last upload error.
- Genie MCP server `databricks-genie` is connected in this session's config (OAuth). Tools: `genie_ask`, `genie_poll_response` (poll until not in_progress), `genie_get_query_result`, `genie_cancel_response`.

## What is not done (your job, in this order)
1. **Verify the live data path.** Check the app's `/status` (written > 0, flush_errors 0) and that `app-*.jsonl` files exist in the Volume. Real human sessions have `st = 'human'`; the 4087 existing rows are `simulated`. `sql/01b_bronze_load.sql` (read_files with an explicit schema, skips files already loaded) is untested on Databricks; fix it if the user pastes an error.
2. **Genie space.** The space does not exist yet. The user creates it in the UI (the Databricks console blocks automated browsers: do not try to drive it). Use the MCP to ask the 5 benchmark questions in `GENIE_SPACE.md` and report which answers are wrong; adjust the instructions/example SQL text for the user to paste. Note the docs say the Genie One MCP may not use the curated space.
3. **Study mode default + results page in the app.** Make study mode the default (the sign-in redirect may drop `?study=1&...`). Add `/results` showing v1 vs v2 per task, top rage elements, and n per rate, labeled simulated vs human, reading the gold tables through a SQL warehouse (databricks-sdk, the app service principal needs SELECT/USE grants: tell the user exactly which). Keep stdlib + databricks-sdk; add tests in `databricks/app/test/`.
4. **Claude designer step.** Script `databricks/designer/propose.py` (or similar): reads gold evidence (via the MCP/Genie answers or SQL), the element list (`data-ux-id`s in `demo/dashboard/static/index.html`) and literature notes (`docs/literature/`), and writes a structured proposal file: each change cites metric, value, n, and `uxid`, plus the literature rationale. No human sign-off step: the check is the v1 -> v2 re-test. Show it with a proposals section in `/results`.
5. **Re-test.** Use the Playwright bot (`demo/test/e2e_demo.mjs`) to generate sessions for the proposed version, label them `simulated`, run them through the pipeline, and compare in `gold_version_comparison`.
6. **Demo prep.** A 4-minute script: capture in the app, show Volume/bronze/silver/gold, Genie questions, proposal, v1->v2 comparison. Remind the user to redeploy the app Sunday morning (Free Edition apps stop 24 hours after deploy).

## Rules
- Simulated data must always be labeled simulated, in tables, UI and the demo. The simulation encodes our hypotheses, so it proves the pipeline recovers planted effects, not that they exist for real users. Prefer a few real human sessions where possible. Do not claim statistical significance or eye tracking; samples are tiny and cursor position only loosely tracks attention.
- Never ask the user to paste tokens into chat, and never create tokens, accounts or grants yourself. Give the user exact SQL for grants and let them run it in the SQL Editor.
- Do not publish or push without the user saying so (the `origin` remote is fixed and `feat/sdk-demo-dashboard` is pushed). Commit in small steps with sensible messages.
- Databricks-only SQL (`read_files`, `ai_classify`, comments) cannot run locally. Say clearly what was only tested locally. `python3 databricks/tests/run_sql_local.py`, `./scripts/sync-core.sh --check` and `python3 databricks/app/test/test_app.py` must keep passing. Edit `packages/core/*` (source of truth), then run `scripts/sync-core.sh` and `scripts/build-app.sh`.
- Report outcomes plainly: say what failed, what was skipped, and what is untested.
