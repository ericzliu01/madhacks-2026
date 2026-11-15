-- GOLD: research metrics. Each metric is a hypothesis about a construct, motivated by the HCI literature triage
-- (docs/literature/signal_paper_matrix.csv). The paper links are title-level and UNVERIFIED until the matrix is filled in.
--   rage / dead clicks      -> frustration or "looks clickable" affordance errors     (struggle/frustration detection papers)
--   hover dwell, hovers     -> attention / reading effort on chart marks              (cursor-as-attention: Huang et al. 2012)
--   idle_ms, first action   -> hesitation / confusion before acting                   (implicit behavioral measures: Rzeszotarski & Kittur 2011)
--   outcome + satisfaction  -> objective success vs self-report; "satisfied but wrong" = over-trust (Human-AI reliance work)
-- Portable subset (Databricks SQL and the local SQLite harness). Study-panel clicks are excluded from friction counts.

-- Per-trial friction metrics: behavior events that fall inside the trial's time window.
CREATE OR REPLACE TABLE ${catalog}.${schema}.gold_trial_metrics AS
SELECT t.session_id, t.session_type, t.app_id, t.app_version, t.participant_id, t.task_id, t.task_category,
       t.outcome, t.satisfaction, t.duration_ms,
       SUM(CASE WHEN e.event_type = 'click' THEN 1 ELSE 0 END) AS n_clicks,
       SUM(CASE WHEN e.event_type = 'rage_click' THEN 1 ELSE 0 END) AS n_rage_clicks,
       SUM(CASE WHEN e.event_type = 'click' AND e.ptr = TRUE AND e.interactive = FALSE THEN 1 ELSE 0 END) AS n_dead_clicks,
       SUM(CASE WHEN e.event_type = 'chart_hover' THEN 1 ELSE 0 END) AS n_chart_hovers,
       COALESCE(SUM(CASE WHEN e.event_type = 'chart_hover' THEN e.dur END), 0) AS chart_hover_ms,
       SUM(CASE WHEN e.event_type = 'chart_legend_click' THEN 1 ELSE 0 END) AS n_legend_clicks,
       COALESCE(SUM(CASE WHEN e.event_type = 'idle_end' THEN e.dur END), 0) AS idle_ms,
       SUM(CASE WHEN e.event_type = 'prompt_submit' THEN 1 ELSE 0 END) AS n_prompts,
       MIN(CASE WHEN e.event_type IN ('click', 'key', 'chart_hover', 'chart_click') THEN e.ts_ms END) - t.start_ms AS first_action_ms
FROM ${catalog}.${schema}.silver_trials t
LEFT JOIN ${catalog}.${schema}.silver_events e
  ON e.session_id = t.session_id
 AND e.ts_ms >= t.start_ms
 AND e.ts_ms <= COALESCE(t.end_ms, 9223372036854775807)
 AND COALESCE(e.region, '') <> 'aside:study-panel'
GROUP BY t.session_id, t.session_type, t.app_id, t.app_version, t.participant_id, t.task_id, t.task_category,
         t.outcome, t.satisfaction, t.duration_ms, t.start_ms;

-- Per session type x task x design version: outcomes and friction. overtrust_rate = share of WRONG answers rated satisfied (4-5).
-- session_type is a grouping key so simulated (bot) trials are never averaged together with human ones.
CREATE OR REPLACE TABLE ${catalog}.${schema}.gold_task_summary AS
SELECT session_type, app_version, task_id, task_category,
       COUNT(*) AS n_trials,
       AVG(CASE WHEN outcome = 'correct' THEN 1.0 ELSE 0.0 END) AS success_rate,
       AVG(CASE WHEN outcome = 'abandoned' THEN 1.0 ELSE 0.0 END) AS abandon_rate,
       AVG(satisfaction) AS avg_satisfaction,
       AVG(duration_ms) AS avg_duration_ms,
       AVG(n_rage_clicks) AS avg_rage_clicks,
       AVG(n_dead_clicks) AS avg_dead_clicks,
       AVG(n_chart_hovers) AS avg_chart_hovers,
       AVG(n_legend_clicks) AS avg_legend_clicks,
       AVG(idle_ms) AS avg_idle_ms,
       AVG(first_action_ms) AS avg_first_action_ms,
       SUM(CASE WHEN outcome = 'incorrect' AND satisfaction >= 4 THEN 1.0 ELSE 0.0 END)
         / NULLIF(SUM(CASE WHEN outcome = 'incorrect' THEN 1.0 ELSE 0.0 END), 0) AS overtrust_rate
FROM ${catalog}.${schema}.gold_trial_metrics
GROUP BY session_type, app_version, task_id, task_category;

-- Which UI elements attract rage / dead clicks (excludes the study panel). Ranks candidate affordance problems.
CREATE OR REPLACE TABLE ${catalog}.${schema}.gold_element_friction AS
SELECT session_type, app_version, uxid,
       SUM(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) AS n_clicks,
       SUM(CASE WHEN event_type = 'rage_click' THEN 1 ELSE 0 END) AS n_rage_clicks,
       SUM(CASE WHEN event_type = 'click' AND ptr = TRUE AND interactive = FALSE THEN 1 ELSE 0 END) AS n_dead_clicks,
       COUNT(DISTINCT session_id) AS n_sessions,
       SUM(CASE WHEN event_type = 'rage_click' THEN 1.0 ELSE 0.0 END)
         / NULLIF(SUM(CASE WHEN event_type = 'click' THEN 1.0 ELSE 0.0 END), 0) AS rage_per_click
FROM ${catalog}.${schema}.silver_events
WHERE uxid IS NOT NULL AND event_type IN ('click', 'rage_click') AND COALESCE(region, '') <> 'aside:study-panel'
GROUP BY session_type, app_version, uxid;

-- Before/after for the iteration loop: v1 (current UI) vs v2 (proposed change), per session type and task.
CREATE OR REPLACE TABLE ${catalog}.${schema}.gold_version_comparison AS
SELECT a.session_type, a.task_id, a.task_category,
       a.success_rate AS success_rate_v1, b.success_rate AS success_rate_v2, b.success_rate - a.success_rate AS success_delta,
       a.abandon_rate AS abandon_rate_v1, b.abandon_rate AS abandon_rate_v2,
       a.avg_duration_ms AS avg_duration_ms_v1, b.avg_duration_ms AS avg_duration_ms_v2,
       a.avg_rage_clicks AS avg_rage_clicks_v1, b.avg_rage_clicks AS avg_rage_clicks_v2,
       a.overtrust_rate AS overtrust_rate_v1, b.overtrust_rate AS overtrust_rate_v2,
       a.n_trials AS n_trials_v1, b.n_trials AS n_trials_v2
FROM ${catalog}.${schema}.gold_task_summary a
JOIN ${catalog}.${schema}.gold_task_summary b ON a.task_id = b.task_id AND a.session_type = b.session_type
WHERE a.app_version = 'v1' AND b.app_version = 'v2';
