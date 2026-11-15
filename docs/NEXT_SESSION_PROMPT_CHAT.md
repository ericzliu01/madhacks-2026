# Prompt: add a chat-assistant study layer (goals instead of scripted tasks)

Paste everything below the line into the Claude Code session that has the `databricks-genie` MCP connected, started in this repo.

---

You are extending a MadHacks 2026 hackathon project in this repo (`/Users/eric/Desktop/madhacks-2026`, branch `feat/sdk-demo-dashboard`). Judging is "Best Use of Databricks" (Databricks core, a real raw -> cleaned -> served spine, something live, creativity/impact), Sunday 2 PM. First read `databricks/README.md`, `databricks/app/README.md`, `databricks/genie/GENIE_SPACE.md`, `docs/NEXT_SESSION_PROMPT.md` (the earlier build brief, still valid), `packages/core/uxtelemetry.js`, `demo/dashboard/static/index.html`, `demo/gen_data.py`, and `databricks/sql/02_silver.sql`, `03_gold.sql`. If another session is already editing `databricks/app/`, check `git status` and coordinate through small commits; do not overwrite its work.

## Why this change
The current study makes participants read charts and answer scripted tasks in a side panel. Nobody uses a dashboard that way. Real analysts ask an LLM chatbot questions (Amar/Eagan/Stasko-type questions: retrieve value, filter, compute derived value, find extremum, determine range...) and then decide whether to trust the answer. We want to study that: goal-driven sessions with an assistant, where the interesting outcomes are over-trust, repair after misunderstanding, drop-off, and chart-to-chat interaction.

## What to build
1. **Chat panel in the demo dashboard** (bottom-left, as in real BI tools), keeping the existing v1 (flawed) / v2 (fixed) chart layer and the current task-panel mode as a fallback (`?study=1&mode=tasks`). New mode: `?study=1&mode=goals`. Participants get a goal, not a task. Goals have known ground truth computed from `demo/dashboard/static/data.json` (derive every answer programmatically in `demo/gen_data.py` and write `goals.json`; plant one hidden anomaly for an exploration goal; never hardcode numbers you have not computed). Each goal is tagged with the Amar categories it is expected to exercise.
2. **Stub assistant with planted, deterministic behaviors** (server-side route `POST /chat` in the app, and the stdlib dev server in `demo/dashboard/app.py` for local runs). A stub, not an LLM, because we need ground truth about when the bot is wrong. Each behavior exists in v1 (flawed) and is fixed in v2, mirroring the chart flaws:
   - B1 confident wrong answer on a derived-value question (v2: correct, or states uncertainty).
   - B2 misparses a filter (ignores the borough) so the user must rephrase (v2: parses it).
   - B3 slow reply with no progress indicator (v2: indicator, shorter latency).
   - B4 chat entry point collapsed/hard to find (v2: visible), the analog of the hidden filter.
   - B5 ignores the chart mark the user selected when they ask "why did this drop?" (v2: uses the selection).
   The stub parses a small, documented set of intents with keyword rules and returns `{text, answer_id, behavior, correct}`. Log `behavior` and `correct` in the event, labeled as testbed ground truth.
3. **Telemetry** (edit `packages/core/*` as the source of truth, then `scripts/sync-core.sh` and `scripts/build-app.sh`; keep `sync-core.sh --check` passing). The SDK already has `prompt_submit`, typing counts, salted hashes and `data-ux-prompt` markup. Add or confirm events: `chat_open`, `prompt_submit` (with `goal_id`, `turn_id`; prompt text only when `captureText` consent is on, otherwise hash + length), `assistant_response` (latency_ms, behavior, answer_id, correct), `answer_feedback` (copy / thumbs / accept), `goal_start`, `goal_outcome` (final answer, correct/incorrect/abandoned, satisfaction 1-5), and a `selection` marker when a chart mark is selected before a prompt. Keep the privacy defaults: no password fields, no query strings, no keystroke content.
4. **Databricks pipeline** (add new files `databricks/sql/06_silver_chat.sql`, `07_gold_chat.sql`, and extend `01_bronze_ddl.sql` + `01b_bronze_load.sql` with the new columns, regenerating the explicit read_files schema; do not break the existing tables). Existing silver assumes one trial per (session, task): add `silver_goals` and `silver_turns` (one row per prompt/response pair) rather than reshaping `silver_trials`. New gold tables: `gold_goal_summary` (success, abandon, turns to resolution, time to first prompt), `gold_turn_metrics` (reformulation, verification, latency), `gold_bot_behavior` (per planted behavior B1-B5: v1 vs v2). Metrics, defined in `05_comments.sql`-style table/column comments:
   - reformulation rate: a prompt followed by another prompt within 60 s that overlaps tokens with it (document the exact rule; keep it portable SQL).
   - verification rate: a chart interaction within 10 s after an assistant answer.
   - over-trust: a wrong assistant answer accepted (final answer equals the wrong answer, or accepted/copied) and satisfaction 4-5.
   - drop-off: goal abandoned, or no outcome, after k failed turns (report k).
   Run `04_ai_prompt_intent.sql` (Amar task x intent labels) on prompt text if `ai_classify` works on this workspace; otherwise say so and use the Genie MCP or a rule-based fallback, labeled as such.
5. **Local test harness.** Extend `databricks/tools/make_sessions.py` and `databricks/tests/run_sql_local.py` so simulated chat sessions flow through the portable SQL in SQLite and assert the planted behaviors are recovered (e.g. B1 over-trust higher in v1, B2 reformulation higher in v1, B3 more abandonment in v1). All must be labeled `simulated`.
6. **LLM-driven simulated users (optional, after the above works).** A Playwright script where an agent with a persona and a goal drives the dashboard chat. Label every such session `simulated`. Scripted bots may be used for the e2e tests.
7. **Genie space.** Update `databricks/genie/GENIE_SPACE.md` with the new tables, instructions, example SQL and benchmark questions (over-trust in chat, where users rephrase, which bot behavior hurts most). Use `view_ask` (the host renders its View; `genie_ask` only if a plain-text answer is needed) to test the questions once the tables exist on the workspace and the user has created the space; report wrong answers and fix the instruction text for the user to paste. The Databricks console blocks automated browsers, so the user performs UI steps.

## Order and checkpoints
Do 1-3 and the local test (5) first, commit, then tell the user how to redeploy the app and load the new data. Then 4 on Databricks with the user running the SQL (give exact files; the user pastes errors back), then 7, then 6 if time remains. Commit in small steps.

## Rules
- Simulated data must always be labeled simulated, in tables, UI and the demo. The simulation encodes our hypotheses, so it proves the pipeline recovers planted effects, not that they exist for real users. Plan a protocol for 3-5 real human sessions with goals and consent for prompt text. No claims of statistical significance, no claims of eye tracking.
- Verify Databricks-only SQL honestly: it cannot run locally, so say what was only tested locally. Keep these passing: `python3 databricks/tests/run_sql_local.py`, `./scripts/sync-core.sh --check`, `python3 databricks/app/test/test_app.py`, and the Playwright e2e tests (`demo/test/e2e_demo.mjs`).
- Never ask the user to paste tokens into chat; never create tokens, accounts or grants yourself; give the user exact SQL for grants. Do not push or publish unless the user says so.
- Literature claims (Setlur & Tory 2022, Srinivasan et al. 2021, Chopra et al., Gu et al. 2023 and others in `docs/literature/`) must come from papers the user has verified; do not invent citations or findings.
- Report outcomes plainly: what failed, what was skipped, what is untested.
