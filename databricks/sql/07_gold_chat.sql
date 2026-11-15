-- GOLD (chat study): turn, goal and planted-behavior metrics. Portable subset (Databricks SQL + local SQLite harness).
-- Keep comments free of semicolons. Every table keeps session_type so simulated and human rows are never mixed.
-- The rules below are proxies for constructs, not measurements of them, and samples are small.
--
--   reformulated    the NEXT prompt in the same goal comes within 60 s of this prompt AND its token overlap with this
--                   prompt is >= 0.6 (overlap = |A and B| / min(|A|, |B|) over content tokens, computed in the browser)
--   repair_attempt  this turn failed (wrong answer, or no answer to the question) and the participant sent another
--                   prompt in the same goal within 60 s of the reply, whatever the overlap
--   verified        a chart interaction (hover, click, legend, zoom, selection, borough filter change) within 10 s
--                   after the assistant's reply
--   failed turn     a reply arrived and correct = 0 or correct IS NULL (the stub did not answer the question)
--   relied_on_wrong a wrong reply (correct = 0) was accepted or copied, or its turn is the one whose answer was
--                   submitted as the final answer
--   overtrust       relied_on_wrong AND satisfaction 4-5 AND the final answer is not correct (a participant who
--                   accepted a wrong reply but then submitted the right answer is not counted)
--   dropoff         the goal ended abandoned or with no outcome after k >= 1 failed turns (k is reported)

-- One row per turn with the flags above.
CREATE OR REPLACE TABLE ${catalog}.${schema}.gold_turn_metrics AS
SELECT t.session_id, t.session_type, t.app_id, t.app_version, t.participant_id, t.goal_id, t.turn_id,
       t.prompt_ms, t.response_ms, t.latency_ms, t.intent, t.behavior, t.answer_id, t.correct, t.accepted,
       t.had_selection, t.overlap, t.chars, t.words,
       CASE WHEN t.response_ms IS NOT NULL AND (t.correct = 0 OR t.correct IS NULL) THEN 1 ELSE 0 END AS failed,
       CASE WHEN t.next_prompt_ms IS NOT NULL AND t.next_prompt_ms - t.prompt_ms <= 60000
                 AND t.next_overlap >= 0.6 THEN 1 ELSE 0 END AS reformulated,
       CASE WHEN t.response_ms IS NOT NULL AND (t.correct = 0 OR t.correct IS NULL)
                 AND t.next_prompt_ms IS NOT NULL AND t.next_prompt_ms - t.response_ms <= 60000 THEN 1 ELSE 0 END AS repair_attempt,
       CASE WHEN COALESCE(v.n_chart_after, 0) > 0 THEN 1 ELSE 0 END AS verified
FROM (
  SELECT s.*,
         LEAD(s.prompt_ms) OVER (PARTITION BY s.session_id, s.goal_id ORDER BY s.turn_id) AS next_prompt_ms,
         LEAD(s.overlap) OVER (PARTITION BY s.session_id, s.goal_id ORDER BY s.turn_id) AS next_overlap
  FROM ${catalog}.${schema}.silver_turns s
) t
LEFT JOIN (
  SELECT st.session_id, st.goal_id, st.turn_id, COUNT(*) AS n_chart_after
  FROM ${catalog}.${schema}.silver_turns st
  JOIN ${catalog}.${schema}.silver_events e
    ON e.session_id = st.session_id
   AND e.ts_ms > st.response_ms AND e.ts_ms <= st.response_ms + 10000
   AND (e.event_type IN ('chart_hover', 'chart_click', 'chart_legend_click', 'chart_legend_dblclick', 'chart_relayout',
                         'chart_select', 'selection')
        OR (e.event_type = 'custom' AND e.name = 'filter_change'))
  GROUP BY st.session_id, st.goal_id, st.turn_id
) v ON v.session_id = t.session_id AND v.goal_id = t.goal_id AND v.turn_id = t.turn_id;

-- One row per goal attempt with turn counts, over-trust and drop-off flags.
CREATE OR REPLACE TABLE ${catalog}.${schema}.gold_goal_metrics AS
SELECT g.session_id, g.session_type, g.app_id, g.app_version, g.participant_id, g.goal_id, g.goal_cats,
       g.outcome, g.satisfaction, g.duration_ms, g.final_turn,
       COALESCE(a.n_turns, 0) AS n_turns,
       COALESCE(a.n_failed_turns, 0) AS n_failed_turns,
       COALESCE(a.n_reformulations, 0) AS n_reformulations,
       COALESCE(a.n_verified, 0) AS n_verified_turns,
       a.first_prompt_ms - g.start_ms AS time_to_first_prompt_ms,
       CASE WHEN COALESCE(a.n_wrong, 0) > 0 THEN 1 ELSE 0 END AS wrong_answer_shown,
       COALESCE(w.relied_on_wrong, 0) AS relied_on_wrong,
       CASE WHEN COALESCE(w.relied_on_wrong, 0) = 1 AND g.satisfaction >= 4 AND g.outcome <> 'correct' THEN 1 ELSE 0 END AS overtrust,
       CASE WHEN g.outcome IN ('abandoned', 'no_outcome') AND COALESCE(a.n_failed_turns, 0) >= 1 THEN 1 ELSE 0 END AS dropoff_after_failure
FROM ${catalog}.${schema}.silver_goals g
LEFT JOIN (
  SELECT session_id, goal_id, COUNT(*) AS n_turns, SUM(failed) AS n_failed_turns, SUM(reformulated) AS n_reformulations,
         SUM(verified) AS n_verified, MIN(prompt_ms) AS first_prompt_ms,
         SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) AS n_wrong
  FROM ${catalog}.${schema}.gold_turn_metrics
  GROUP BY session_id, goal_id
) a ON a.session_id = g.session_id AND a.goal_id = g.goal_id
LEFT JOIN (
  SELECT t.session_id, t.goal_id,
         MAX(CASE WHEN t.correct = 0 AND (t.accepted = 1 OR t.turn_id = g2.final_turn) THEN 1 ELSE 0 END) AS relied_on_wrong
  FROM ${catalog}.${schema}.gold_turn_metrics t
  JOIN ${catalog}.${schema}.silver_goals g2 ON g2.session_id = t.session_id AND g2.goal_id = t.goal_id
  GROUP BY t.session_id, t.goal_id
) w ON w.session_id = g.session_id AND w.goal_id = g.goal_id;

-- Per session type x design version x goal.
CREATE OR REPLACE TABLE ${catalog}.${schema}.gold_goal_summary AS
SELECT session_type, app_version, goal_id, MAX(goal_cats) AS goal_cats,
       COUNT(*) AS n_goals,
       AVG(CASE WHEN outcome = 'correct' THEN 1.0 ELSE 0.0 END) AS success_rate,
       AVG(CASE WHEN outcome = 'abandoned' THEN 1.0 ELSE 0.0 END) AS abandon_rate,
       AVG(CASE WHEN outcome = 'no_outcome' THEN 1.0 ELSE 0.0 END) AS no_outcome_rate,
       AVG(n_turns * 1.0) AS avg_turns,
       AVG(CASE WHEN outcome = 'correct' THEN n_turns * 1.0 END) AS avg_turns_to_success,
       AVG(time_to_first_prompt_ms * 1.0) AS avg_time_to_first_prompt_ms,
       AVG(duration_ms * 1.0) AS avg_duration_ms,
       AVG(satisfaction * 1.0) AS avg_satisfaction,
       SUM(wrong_answer_shown) AS n_wrong_answer_shown,
       SUM(overtrust) * 1.0 / NULLIF(SUM(wrong_answer_shown), 0) AS overtrust_rate,
       AVG(dropoff_after_failure * 1.0) AS dropoff_rate,
       AVG(CASE WHEN dropoff_after_failure = 1 THEN n_failed_turns * 1.0 END) AS avg_failed_turns_at_dropoff
FROM ${catalog}.${schema}.gold_goal_metrics
GROUP BY session_type, app_version, goal_id;

-- Per planted assistant behavior (B1-B5) x design version: v1 = flawed, v2 = fixed.
-- Turn metrics for B1, B2, B3, B5 come from the turns where the behavior fired. Goal metrics come from the goals that
-- contain such a turn. B4 (hidden chat entry point) is a page behavior: its row reports time from the first goal to the
-- first chat_open per session (0 if the chat was already open) and the share of sessions that never opened it.
CREATE OR REPLACE TABLE ${catalog}.${schema}.gold_bot_behavior AS
SELECT t.session_type, t.behavior, t.app_version, t.n_turns, g.n_goals, NULL AS n_sessions,
       t.wrong_answer_rate, t.reformulation_rate, t.repair_rate, t.verification_rate, t.avg_latency_ms,
       g.goal_success_rate, g.goal_abandon_rate, g.overtrust_rate,
       NULL AS avg_ms_to_chat_open, NULL AS never_opened_rate
FROM (
  SELECT session_type, behavior, app_version, COUNT(*) AS n_turns,
         AVG(CASE WHEN correct = 0 THEN 1.0 ELSE 0.0 END) AS wrong_answer_rate,
         AVG(reformulated * 1.0) AS reformulation_rate,
         AVG(repair_attempt * 1.0) AS repair_rate,
         AVG(verified * 1.0) AS verification_rate,
         AVG(latency_ms * 1.0) AS avg_latency_ms
  FROM ${catalog}.${schema}.gold_turn_metrics
  WHERE behavior IS NOT NULL
  GROUP BY session_type, behavior, app_version
) t
JOIN (
  SELECT b.session_type, b.behavior, b.app_version, COUNT(*) AS n_goals,
         AVG(CASE WHEN m.outcome = 'correct' THEN 1.0 ELSE 0.0 END) AS goal_success_rate,
         AVG(CASE WHEN m.outcome IN ('abandoned', 'no_outcome') THEN 1.0 ELSE 0.0 END) AS goal_abandon_rate,
         SUM(m.overtrust) * 1.0 / NULLIF(SUM(m.wrong_answer_shown), 0) AS overtrust_rate
  FROM (SELECT DISTINCT session_type, behavior, app_version, session_id, goal_id
        FROM ${catalog}.${schema}.gold_turn_metrics WHERE behavior IS NOT NULL) b
  JOIN ${catalog}.${schema}.gold_goal_metrics m ON m.session_id = b.session_id AND m.goal_id = b.goal_id
  GROUP BY b.session_type, b.behavior, b.app_version
) g ON g.session_type = t.session_type AND g.behavior = t.behavior AND g.app_version = t.app_version
UNION ALL
SELECT s.session_type, 'B4' AS behavior, s.app_version, NULL AS n_turns, NULL AS n_goals, COUNT(*) AS n_sessions,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       AVG(CASE WHEN s.first_open_ms IS NULL THEN NULL
                WHEN s.first_open_ms < s.first_goal_ms THEN 0.0
                ELSE (s.first_open_ms - s.first_goal_ms) * 1.0 END) AS avg_ms_to_chat_open,
       AVG(CASE WHEN s.first_open_ms IS NULL THEN 1.0 ELSE 0.0 END) AS never_opened_rate
FROM (
  SELECT session_id, session_type, app_version,
         MIN(CASE WHEN event_type = 'goal_start' THEN ts_ms END) AS first_goal_ms,
         MIN(CASE WHEN event_type = 'chat_open' THEN ts_ms END) AS first_open_ms
  FROM ${catalog}.${schema}.silver_events
  GROUP BY session_id, session_type, app_version
  HAVING MIN(CASE WHEN event_type = 'goal_start' THEN ts_ms END) IS NOT NULL
) s
GROUP BY s.session_type, s.app_version;
