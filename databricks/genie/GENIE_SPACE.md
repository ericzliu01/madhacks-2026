# Genie space: UX telemetry analyst

**What "training" means here.** A Genie space is *curated*, not trained: you choose tables, write instructions, add tested
example SQL, and run benchmarks. (From Databricks docs found by search: example SQL is the most strongly recommended lever,
up to 100 instructions per space, benchmarks measure accuracy but do not feed Genie's context, and you need a SQL warehouse
plus SELECT on the tables. Verify exact UI steps in the docs: this was written without workspace access.)

## 1. Create the space
- Tables: `gold_trial_metrics`, `gold_task_summary`, `gold_element_friction`, `gold_version_comparison`
  (add `gold_prompt_labels` once prompt data exists). Run `05_comments.sql` first: Genie reads those descriptions.

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
  from them.
- Samples are small. Report counts (n_trials) next to every rate and avoid claims of statistical significance.
- Exclude nothing silently. If a filter drops rows, say how many.
```

## 3. Example SQL queries (add as tested examples; replace the schema name)
1. *Which tasks are hardest?*
   `SELECT task_id, task_category, app_version, success_rate, abandon_rate, n_trials FROM gold_task_summary ORDER BY success_rate ASC`
2. *Did the proposed change (v2) help?*
   `SELECT task_id, task_category, success_rate_v1, success_rate_v2, success_delta, n_trials_v1, n_trials_v2 FROM gold_version_comparison ORDER BY success_delta DESC`
3. *Which UI elements cause rage clicks?*
   `SELECT uxid, app_version, n_rage_clicks, n_dead_clicks, rage_per_click FROM gold_element_friction ORDER BY n_rage_clicks DESC`
4. *Where do users report satisfaction but answer wrongly (over-trust)?*
   `SELECT task_id, task_category, app_version, overtrust_rate, n_trials FROM gold_task_summary WHERE overtrust_rate IS NOT NULL ORDER BY overtrust_rate DESC`
5. *Which tasks involve long hesitation before the first action?*
   `SELECT task_id, app_version, avg_first_action_ms, avg_idle_ms FROM gold_task_summary ORDER BY avg_idle_ms DESC`
6. *Compare friction by Amar task category.*
   `SELECT task_category, app_version, AVG(success_rate) AS success_rate, SUM(n_trials) AS n_trials FROM gold_task_summary GROUP BY task_category, app_version`

## 4. Benchmarks (2-4 phrasings each; the docs suggest at least 5 questions)
| Intent | Phrasings | Expected from |
|---|---|---|
| Hardest task | "Which task has the lowest success rate?" / "Where do users fail most?" | example 1 |
| Version impact | "Did v2 improve success?" / "How much better is the new design per task?" | example 2 |
| Rage-click source | "What do users rage-click?" / "Which element gets the most rage clicks in v1?" | example 3 |
| Over-trust | "Where are users satisfied but wrong?" / "Which task has the highest over-trust?" | example 4 |
| Hesitation | "Where do people hesitate most?" / "Which task has the highest idle time?" | example 5 |

Run the benchmarks after each change to instructions or tables. Treat a failing benchmark as a prompt to add an example
query or sharpen an instruction.

## 5. Where Claude fits (not Genie)
Genie answers analytic questions over the gold tables. The *design proposal* step is separate: Claude reads the gold
tables (or Genie API answers) plus the literature notes, proposes a concrete UI diff with the evidence for each change,
and a human designer signs off. Genie may also be called from the Databricks App through the Genie conversation API
(see the docs); that is a later step.
