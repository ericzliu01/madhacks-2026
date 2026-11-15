-- Unity Catalog comments carry the research context to Genie (and to anyone browsing the catalog).
-- Genie reads table/column descriptions, so definitions written here steer how it answers.
-- Spark/Databricks SQL only. UNTESTED (no workspace access from the sandbox).

COMMENT ON TABLE ${catalog}.${schema}.gold_trial_metrics IS
  'One row per (session, task) trial with friction metrics. Behavior counts exclude the study panel. Data with session_type=simulated is bot-generated test data, not real users.';
COMMENT ON COLUMN ${catalog}.${schema}.gold_trial_metrics.outcome IS
  'Objective result: correct, incorrect, abandoned (clicked I give up), or no_outcome (left without finishing). Success = correct.';
COMMENT ON COLUMN ${catalog}.${schema}.gold_trial_metrics.satisfaction IS
  'Self-reported 1-5 (5 = very satisfied) asked after answering. NULL when abandoned. Self-report, so compare with outcome rather than trusting it alone.';
COMMENT ON COLUMN ${catalog}.${schema}.gold_trial_metrics.task_category IS
  'Amar, Eagan and Stasko (2005) low-level analytic task the trial exercises: retrieve_value, filter, compute_derived_value, find_extremum, sort, determine_range, characterize_distribution, find_anomalies, cluster, correlate.';
COMMENT ON COLUMN ${catalog}.${schema}.gold_trial_metrics.n_rage_clicks IS
  'Bursts of 3+ clicks within 700 ms in the same spot. Proxy for frustration or a control that looks usable but does not respond.';
COMMENT ON COLUMN ${catalog}.${schema}.gold_trial_metrics.n_dead_clicks IS
  'Clicks on non-interactive elements that show a pointer cursor ("looks clickable but is not"). Affordance problem signal.';
COMMENT ON COLUMN ${catalog}.${schema}.gold_trial_metrics.idle_ms IS
  'Total time in pauses of 30 s or more with no input during the trial. Proxy for hesitation or confusion, not proof.';
COMMENT ON COLUMN ${catalog}.${schema}.gold_trial_metrics.chart_hover_ms IS
  'Total time hovering chart marks. Cursor-as-attention proxy: cursor position only loosely tracks gaze.';
COMMENT ON COLUMN ${catalog}.${schema}.gold_trial_metrics.first_action_ms IS
  'Milliseconds from trial start to the first click, key press, or chart interaction outside the study panel.';

COMMENT ON TABLE ${catalog}.${schema}.gold_task_summary IS
  'Aggregates of gold_trial_metrics per session_type (human or simulated, never mixed), design version (v1 = current UI, v2 = proposed change) and task. success_rate and abandon_rate are 0-1 fractions.';
COMMENT ON COLUMN ${catalog}.${schema}.gold_task_summary.overtrust_rate IS
  'Share of INCORRECT answers that were rated 4-5 for satisfaction ("satisfied but wrong"). NULL when no incorrect answers.';

COMMENT ON TABLE ${catalog}.${schema}.gold_element_friction IS
  'Rage and dead clicks per session_type, UI element (uxid) and design version. Highest rage_per_click flags elements with affordance problems.';

COMMENT ON TABLE ${catalog}.${schema}.gold_version_comparison IS
  'v1 vs v2 per session_type and task (human and simulated are separate rows): success_delta = success_rate_v2 - success_rate_v1. Used to judge whether a proposed UI change helped. Small samples: treat as descriptive.';
