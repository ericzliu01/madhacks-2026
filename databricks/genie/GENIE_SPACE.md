# Genie space: UX telemetry analyst

**What "training" means here.** A Genie space is *curated*, not trained: you choose tables, write instructions, add tested
example SQL, and run benchmarks. (From Databricks docs found by search: example SQL is the most strongly recommended lever,
up to 100 instructions per space, benchmarks measure accuracy but do not feed Genie's context, and you need a SQL warehouse
plus SELECT on the tables. Verify exact UI steps in the docs: this was written without workspace access.)

## 1. Create the space
- Task study (mode=tasks): `gold_trial_metrics`, `gold_task_summary`, `gold_element_friction`, `gold_version_comparison`.
- Chat study (mode=goals): `gold_goal_summary`, `gold_bot_behavior`, `gold_goal_metrics`, `gold_turn_metrics`, and
  `gold_prompt_labels` / `gold_prompt_label_agreement` after running `ux_ai_labels.sql`.
- `ux_pipeline_all.sql` ends with the table and column comments (`05_comments.sql`): Genie reads those descriptions.

## 2. General instructions (paste into the space)
```
You analyze UX telemetry from usability trials of a dashboard. Each trial is one participant attempting one task.
- "Success" means outcome = 'correct'. "Abandoned" means the participant gave up. Never treat satisfaction alone as success.
- satisfaction is a 1-5 self-report (5 = very satisfied). overtrust_rate is the share of INCORRECT answers rated 4-5.
- app_version v1 is the current UI, v2 is a proposed change. Compare versions with gold_version_comparison.
- task_category follows Amar, Eagan and Stasko (2005) low-level analytic tasks.
- Rage clicks and dead clicks signal frustration or affordance problems. idle_ms and first_action_ms signal hesitation.
  These are proxies, not proof: say so when explaining causes.
- Rows with session_type = 'simulated' are bot-generated test data, not real people. State this whenever you report results
  from them. Every gold table has a session_type column: always group or filter by it, never average human and simulated
  rows together. If the question does not say which, show both, human first.
- Samples are small. Report counts (n_trials) next to every rate and avoid claims of statistical significance.
- Exclude nothing silently. If a filter drops rows, say how many.

Chat-assistant study (tables gold_goal_*, gold_turn_metrics, gold_bot_behavior):
- A goal is an open-ended need worked on with a dashboard assistant over several turns. A turn is one prompt and its reply.
- The assistant is a scripted stub with planted behaviors, flawed in v1 and fixed in v2: B1 confident wrong percent,
  B2 ignores the borough the first time, B3 slow reply with no progress indicator, B4 chat entry point hidden,
  B5 ignores the chart point the user selected. "correct" on a turn is testbed ground truth about the stub's reply.
- To compare behaviors, use gold_bot_behavior and compare v1 with v2 for the same behavior. B4 has only
  avg_ms_to_chat_open and never_opened_rate (per session); its turn columns are NULL by design.
- "Which behavior hurts most": compare the v1 minus v2 difference in goal_abandon_rate, wrong_answer_rate and
  overtrust_rate per behavior, and show n_turns or n_goals. Do not rank on a single rate without its n.
- Never invent a composite, weighted or "harm" score. Report each metric separately as v1 versus v2, and say that
  different metrics can rank the behaviors differently (e.g. one behavior drives abandonment, another over-trust).
- A planted behavior's effect is the v1 minus v2 difference, never the v1 value alone.
- reformulated = next prompt within 60 s with token overlap >= 0.6. repair_attempt = any follow-up within 60 s after a
  failed reply. verified = chart interaction within 10 s after a reply. overtrust (goals) = a wrong reply accepted or
  submitted, satisfaction 4-5, final answer wrong. overtrust_rate is over goals that showed a wrong reply (n_wrong_answer_shown).
- In the chat tables success is outcome = 'correct' in gold_goal_metrics, or success_rate in gold_goal_summary.
- pasted_goal = the participant pasted the goal text itself into the chat (paste + similarity >= 0.8). Pasting is allowed
  and equally possible in v1 and v2. When reporting time to first prompt, reformulation or prompt labels, also give the
  *_excl_pasted value (or filter pasted_goal = 0) and say how many goals or turns were pasted.
- Two studies share this space. Questions about the assistant, chat, bot, prompts, goals or behaviors B1-B5 use the
  chat tables (gold_goal_*, gold_turn_metrics, gold_bot_behavior, gold_prompt_*). Questions about tasks T1-T5,
  charts, rage or dead clicks, or UI elements use the task tables (gold_task_summary, gold_version_comparison,
  gold_element_friction, gold_trial_metrics). If a question could mean either, answer for both and label which is which.
```

## 3. Example SQL queries (add as tested examples)
Use fully qualified names (`workspace.ux_telemetry.<table>`): benchmark ground-truth SQL runs with `workspace.default`
as the default schema, so bare names fail with TABLE_OR_VIEW_NOT_FOUND. `GENIE_PASTE.md` has the qualified versions.
1. *Which tasks are hardest?*
   `SELECT session_type, task_id, task_category, app_version, success_rate, abandon_rate, n_trials FROM gold_task_summary ORDER BY session_type, success_rate ASC`
2. *Did the proposed change (v2) help?*
   `SELECT session_type, task_id, task_category, success_rate_v1, success_rate_v2, success_delta, n_trials_v1, n_trials_v2 FROM gold_version_comparison ORDER BY session_type, success_delta DESC`
3. *Which UI elements cause rage clicks?*
   `SELECT session_type, uxid, app_version, n_rage_clicks, n_dead_clicks, rage_per_click FROM gold_element_friction ORDER BY session_type, n_rage_clicks DESC`
4. *Where do users report satisfaction but answer wrongly (over-trust)?*
   `SELECT session_type, task_id, task_category, app_version, overtrust_rate, n_trials FROM gold_task_summary WHERE overtrust_rate IS NOT NULL ORDER BY session_type, overtrust_rate DESC`
5. *Which tasks involve long hesitation before the first action?*
   `SELECT session_type, task_id, app_version, avg_first_action_ms, avg_idle_ms, n_trials FROM gold_task_summary ORDER BY session_type, avg_idle_ms DESC`
6. *Compare friction by Amar task category.*
   `SELECT session_type, task_category, app_version, SUM(success_rate * n_trials) / SUM(n_trials) AS success_rate, SUM(n_trials) AS n_trials FROM gold_task_summary GROUP BY session_type, task_category, app_version`

Chat study:

7. *Which planted assistant behavior hurts most?*
   `SELECT a.session_type, a.behavior, a.goal_abandon_rate - b.goal_abandon_rate AS abandon_increase_v1, a.wrong_answer_rate - b.wrong_answer_rate AS wrong_increase_v1, a.overtrust_rate AS overtrust_v1, a.n_turns AS n_turns_v1, b.n_turns AS n_turns_v2 FROM gold_bot_behavior a JOIN gold_bot_behavior b ON a.session_type = b.session_type AND a.behavior = b.behavior AND a.app_version = 'v1' AND b.app_version = 'v2' WHERE a.behavior <> 'B4' ORDER BY a.session_type, abandon_increase_v1 DESC`
8. *Where do users over-trust the assistant?*
   `SELECT session_type, goal_id, app_version, overtrust_rate, n_wrong_answer_shown, n_goals FROM gold_goal_summary WHERE n_wrong_answer_shown > 0 ORDER BY session_type, overtrust_rate DESC`
9. *Where do users rephrase their questions?*
   `SELECT session_type, behavior, app_version, reformulation_rate, repair_rate, n_turns FROM gold_bot_behavior WHERE behavior <> 'B4' ORDER BY session_type, reformulation_rate DESC`
10. *Did the v2 assistant help per goal?*
   `SELECT session_type, goal_id, goal_cats, app_version, success_rate, abandon_rate, avg_turns, n_goals FROM gold_goal_summary ORDER BY session_type, goal_id, app_version`
11. *How hard is the assistant to find?*
   `SELECT session_type, app_version, avg_ms_to_chat_open, never_opened_rate, n_sessions FROM gold_bot_behavior WHERE behavior = 'B4' ORDER BY session_type, app_version`

## 4. Benchmarks (2-4 phrasings each; the docs suggest at least 5 questions)
Baseline before curation (2026-11-15, Genie through the MCP, not the curated space, simulated data only): asked "which
planted bot behavior hurts users most?", Genie checked human rows first (good), then made up a weighted harm score and
looked at v1 only, ranking B5 first. Example 7 ranks by v1 minus v2 instead: B3 leads on abandonment (+0.29), B1 on
over-trust (0.38). The "never invent a composite score" instruction targets this.

Curated space result (2026-11-15, the user's Genie space, simulated data plus 1 human session): **10/10 benchmarks Good**
(Agent mode, evaluation notes as in `GENIE_PASTE.md`, one ground-truth SQL fixed for an unqualified table name first).
These are our own 10 questions, close to our example SQL: the score shows Genie handles them as intended, not general
accuracy.

| Intent | Phrasings | Expected from |
|---|---|---|
| Hardest task | "Which task has the lowest success rate?" / "Where do users fail most?" | example 1 |
| Version impact | "Did v2 improve success?" / "How much better is the new design per task?" | example 2 |
| Rage-click source | "What do users rage-click?" / "Which element gets the most rage clicks in v1?" | example 3 |
| Over-trust | "Where are users satisfied but wrong?" / "Which task has the highest over-trust?" | example 4 |
| Hesitation | "Where do people hesitate most?" / "Which task has the highest idle time?" | example 5 |
| Worst bot behavior | "Which bot behavior hurts most?" / "Which planted assistant flaw causes the most abandonment?" | example 7 |
| Chat over-trust | "Where do users over-trust the assistant?" / "Which goal has the most accepted wrong answers?" | example 8 |
| Rephrasing | "Where do users rephrase their questions?" / "Which behavior makes people reformulate?" | example 9 |
| Goal impact | "Did the v2 assistant improve goal success?" / "Which goal improved most in v2?" | example 10 |
| Entry point | "How long does it take to find the assistant?" / "How many sessions never open the chat?" | example 11 |

Run the benchmarks after each change to instructions or tables. Treat a failing benchmark as a prompt to add an example
query or sharpen an instruction.

## 5. Where Claude fits (not Genie)
Genie answers analytic questions over the gold tables. The *design proposal* step is separate: Claude drafts the
design change. It reads the gold tables (or Genie API answers) plus the literature notes and proposes a concrete UI diff,
citing the metric and element (`uxid`) behind each change. **A UX developer signs off** (approve, edit or reject) before
anything is built. Only the approved change becomes v2, which is then re-tested against v1 in the same pipeline. Genie may
also be called from the Databricks App through the Genie conversation API (see the docs); that is a later step.
