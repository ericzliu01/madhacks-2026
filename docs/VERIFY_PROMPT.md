# Prompt: verify the Databricks build (for the session with the databricks-genie MCP)

Paste everything below the line into the Claude Code session that has the `databricks-genie` MCP connected, started in this repo.

---

You are verifying, not building. The Friction Atlas pipeline (this repo, `/Users/eric/Desktop/madhacks-2026`) has been run on the user's Databricks Free Edition workspace: `ux_pipeline_all.sql` was executed and the Databricks App was redeployed. Your job is to check what actually landed and report plainly what passed, what failed, and what you could not check. Do not edit files, run SQL that changes data, or fix anything without telling the user first. Never ask for tokens.

## Ground rules for using Genie
- Use `view_ask` (the host renders its View; one call, no polling). Use `genie_ask` only if the user wants plain text. Do not retry a failed `view_ask`: that starts a second response.
- Genie writes its own SQL, so it can miscount or mislabel. Ask for exact, simple things (`COUNT(*)` per table, `GROUP BY session_type`) and show the SQL Genie used. For any number that decides a PASS/FAIL, ask the user to run the same query in the SQL Editor if the Genie answer looks off, and say which source each number came from.
- Genie might not see every table (Unity Catalog permissions). If it cannot find a table, report that as "could not check", not "missing".
- Catalog/schema: `workspace.ux_telemetry`. Read `databricks/README.md`, `databricks/sql/06_silver_chat.sql`, `databricks/sql/07_gold_chat.sql`, `databricks/sql/05_comments.sql` and `databricks/genie/GENIE_SPACE.md` first for exact table and column names; do not guess them.

## Checks (run in this order; stop and report if the basics fail)
1. **Tables exist and have rows.** Row count per table: `bronze_events`, `silver_events`, `silver_trials`, `silver_goals`, `silver_turns`, `gold_trial_metrics`, `gold_task_summary`, `gold_element_friction`, `gold_version_comparison`, `gold_turn_metrics`, `gold_goal_metrics`, `gold_goal_summary`, `gold_bot_behavior`, and `gold_prompt_labels` if present. Report each as a number, or "not found".
2. **Human and simulated are separated.** `bronze_events` counts grouped by `st` (session type). Every gold table has a `session_type` column: confirm no table mixes human and simulated rows in one aggregate (look for rows with a NULL or mixed `session_type`). Expected: simulated rows only unless real human sessions were collected; say how many human sessions exist, if any.
3. **Task-data baseline (original 60 simulated sessions).** Known values from the local SQLite run, simulated data only: 4087 bronze events, 300 trials (60 sessions x 5 tasks), T2 success 0.37 -> 0.77 (v1 -> v2), T4 abandon 0.27 -> 0.00, T3 success 0.47 -> 0.77, top v1 rage element `kpi-avg-fare` (about 17 rage clicks), no rage on it in v2. The workspace may hold more files than this (chat sessions), so counts can be higher: report the actual numbers, compare ratios and directions, and flag anything that contradicts the expected direction.
4. **Chat-study tables (new, never run live before).** For `session_type = 'simulated'`, from `gold_bot_behavior` / `gold_goal_summary`: do the planted behaviors B1-B5 show the expected v1 -> v2 direction? B1 over-trust or wrong replies lower in v2, B2 reformulation/repair lower in v2, B3 latency lower in v2, B4 time to open the chat shorter in v2, B5 selection ignored in v1 only. Read `07_gold_chat.sql` for the exact column names and rules. Say clearly that these are simulated sessions whose behavior encodes our hypotheses: recovering the planted effects shows the pipeline works, not that real users behave this way.
5. **Comments reached the catalog.** Ask for the table/column comments on `gold_trial_metrics` and `gold_goal_summary` (from `05_comments.sql`). Report whether they are present.
6. **`ai_classify` / prompt labels.** Does `gold_prompt_labels` (or the table created by `04_ai_prompt_intent.sql`) exist with rows? If not, say whether the cause looks like AI Functions being unavailable on Free Edition (check the error if the user has it) or simply no prompt text captured (prompt text needs consent).

## Things you cannot verify through Genie: hand these to the user as a checklist
Genie answers questions, so treat it as read-only. The user must check, and report back:
- The Databricks App's `<app-url>/status`: `sink` should be `VolumeSink`, `written` above 0, `flush_errors` 0, `last_error` null, and `warehouse` true.
- `<app-url>/results` loads and shows real numbers (v1 vs v2 per task, rage elements, chat goals, the B1-B5 table), with simulated and human results shown separately and labeled.
- A new `app-*.jsonl` file appears in `/Volumes/workspace/ux_telemetry/raw_events/raw/` after the user completes a task in the app (`?study=1&pid=P01&st=human&v=1`).
- Every statement of `ux_pipeline_all.sql` succeeded in the SQL Editor (any error text).

## Report format
A table with one row per check: PASS / FAIL / COULD NOT CHECK, the evidence (the number or message), and the source (Genie SQL, SQL Editor, or the user). Then a short list of failures with the exact error and your best guess at the cause. State what is unverified. Do not turn a COULD NOT CHECK into a PASS, do not infer the App works from the tables, and do not claim statistical significance or real-user effects from simulated data. Do not commit or push.
