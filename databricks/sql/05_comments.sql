-- Unity Catalog comments carry the research context to Genie (and to anyone browsing the catalog).
-- Genie reads table/column descriptions, so definitions written here steer how it answers.
-- Spark/Databricks SQL only. UNTESTED (no workspace access from the sandbox).

COMMENT ON TABLE ${catalog}.${schema}.gold_trial_metrics IS
  'One row per (session, task) trial with friction metrics. Behavior counts exclude the study panel. session_type: human = real participants, simulated = generated from assumed rates (test data), agent = bots using the real dashboard with one fixed strategy for v1 and v2. Only human is real users.';
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

-- ---------------------------------------------------------------- chat study (06_silver_chat.sql, 07_gold_chat.sql)
COMMENT ON TABLE ${catalog}.${schema}.silver_goals IS
  'One row per (session, goal) in the chat-assistant study. A goal is an open-ended need (e.g. the Bronx average fare) worked on with the dashboard assistant. outcome: correct | incorrect | abandoned | no_outcome. final_turn = the assistant turn whose answer was submitted (NULL if typed by the participant).';
COMMENT ON TABLE ${catalog}.${schema}.silver_turns IS
  'One row per prompt/response pair (session, goal, turn). correct is 1/0 testbed ground truth from the stub assistant (NULL = it did not answer the question). prompt_text only with participant consent. overlap = token overlap with the previous prompt of the goal, computed in the browser.';
COMMENT ON TABLE ${catalog}.${schema}.gold_turn_metrics IS
  'Per assistant turn: failed, reformulated, repair_attempt and verified flags. Proxies, not measurements: see the column comments for the exact rules. session_type=simulated rows are bot-generated.';
COMMENT ON COLUMN ${catalog}.${schema}.gold_turn_metrics.reformulated IS
  '1 if the next prompt in the same goal came within 60 s of this prompt and its token overlap with this prompt is >= 0.6 (overlap coefficient over lowercase content tokens, stopwords removed).';
COMMENT ON COLUMN ${catalog}.${schema}.gold_turn_metrics.repair_attempt IS
  '1 if this turn failed (wrong reply, or no answer to the question) and another prompt in the same goal followed within 60 s of the reply, whatever its overlap.';
COMMENT ON COLUMN ${catalog}.${schema}.gold_turn_metrics.verified IS
  '1 if the participant interacted with a chart (hover, click, legend, zoom, point selection) or changed the borough filter within 10 s after the reply.';
COMMENT ON COLUMN ${catalog}.${schema}.gold_turn_metrics.behavior IS
  'Planted assistant behavior that fired on this turn: B1 confident wrong percent, B2 borough ignored, B3 slow reply, B5 chart selection ignored (v1 = flawed, v2 = fixed). NULL = no planted behavior.';
COMMENT ON TABLE ${catalog}.${schema}.gold_goal_metrics IS
  'Per goal attempt: turns, failed turns, over-trust and drop-off flags. overtrust = a wrong assistant answer was accepted, copied or submitted, satisfaction 4-5, and the final answer is not correct. dropoff_after_failure = abandoned or no outcome after at least one failed turn.';
COMMENT ON TABLE ${catalog}.${schema}.gold_goal_summary IS
  'Per session_type, design version and goal: success, abandonment, turns, time to first prompt, over-trust (share of goals that showed a wrong answer) and drop-off (avg_failed_turns_at_dropoff = k). Small samples: descriptive only.';
COMMENT ON TABLE ${catalog}.${schema}.gold_bot_behavior IS
  'Per planted assistant behavior (B1-B5) and design version (v1 flawed, v2 fixed): wrong-answer, reformulation, repair and verification rates, latency, and outcomes of the goals where the behavior fired. B4 (chat entry point hidden in v1) reports avg_ms_to_chat_open and never_opened_rate per session instead.';
COMMENT ON COLUMN ${catalog}.${schema}.gold_turn_metrics.pasted_goal IS
  '1 if the participant pasted into the chat box and the prompt has Jaccard similarity >= 0.8 with the goal text (the goal was handed to the assistant rather than phrased by the participant). Columns ending in _excl_pasted in the other chat tables repeat a metric without these.';
