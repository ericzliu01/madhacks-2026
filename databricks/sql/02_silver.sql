-- SILVER: typed, de-duplicated, human-readable names; trials reconstructed from task_start/outcome events.
-- Portable subset (runs in Databricks SQL and in the local SQLite harness). Keep comments free of semicolons.

-- Events may be re-sent (keepalive retries), so keep one row per (session, time, type, element, position, goal, turn).
-- goal and turn are in the key: two assistant replies for different turns can arrive in the same millisecond.
CREATE OR REPLACE TABLE ${catalog}.${schema}.silver_events AS
SELECT session_id, session_type, app_id, app_version, participant_id, task_id, task_category, page, path, event_type,
       ts_ms, uxid, testid, label, region, action, tag, role, interactive, ptr, x, y, v, n, dur,
       status, satisfaction, answer, chart, series, prompt_text, how, chars, words, prompt_hash, ctx, combo, name,
       goal_id, goal_cats, turn_id, latency_ms, behavior, answer_id, correct, intent, feedback, mark_x, mark_y, overlap,
       had_selection, goal_sim, pasted
FROM (
  SELECT sid AS session_id,
         -- Design revision 2 (2026-11-15): no hover tooltips in v1 (F5), assistant visible in both versions
         -- (B4 retired). Human and agent sessions recorded on the earlier design get their own session type
         -- (human_r1, agent_r1) so they are never pooled with revision-2 data. Simulated data is generated, not recorded.
         CASE WHEN st IN ('human', 'agent') AND app NOT LIKE '%-r2-%' THEN st || '_r1' ELSE st END AS session_type,
         app AS app_id, substr(app, -2) AS app_version, pid AS participant_id,
         task AS task_id, tcat AS task_category, page, path, type AS event_type,
         CAST(t AS BIGINT) AS ts_ms, uxid, testid, label, region, action, tag, role, interactive, ptr, x, y, v, n, dur,
         status, satisfaction, answer, chart, series, text AS prompt_text, how, chars, words, hash AS prompt_hash, ctx, combo, name,
         goal AS goal_id, gcats AS goal_cats, turn AS turn_id, latency_ms, behavior, answer_id, correct, intent, feedback,
         mark_x, mark_y, overlap, sel AS had_selection, goal_sim, pasted,
         ROW_NUMBER() OVER (
           PARTITION BY sid, t, type, COALESCE(uxid, ''), COALESCE(x, -1), COALESCE(y, -1), COALESCE(goal, ''), COALESCE(turn, -1)
           ORDER BY recv_t
         ) AS rn
  FROM ${catalog}.${schema}.bronze_events
  WHERE sid IS NOT NULL AND t IS NOT NULL
) d
WHERE rn = 1;

-- One row per (session, task) trial. Assumes each task is attempted once per session.
-- outcome: correct | incorrect | abandoned | no_outcome (the participant left without finishing)
CREATE OR REPLACE TABLE ${catalog}.${schema}.silver_trials AS
SELECT s.session_id, s.session_type, s.app_id, s.app_version, s.participant_id, s.task_id, s.task_category,
       s.start_ms,
       o.end_ms,
       COALESCE(o.outcome, 'no_outcome') AS outcome,
       o.satisfaction,
       o.answer,
       o.duration_ms
FROM (
  SELECT session_id, task_id, task_category, app_id, app_version, participant_id, session_type, MIN(ts_ms) AS start_ms
  FROM ${catalog}.${schema}.silver_events
  WHERE event_type = 'task_start'
  GROUP BY session_id, task_id, task_category, app_id, app_version, participant_id, session_type
) s
LEFT JOIN (
  SELECT session_id, task_id, MAX(ts_ms) AS end_ms, MAX(status) AS outcome,
         MAX(satisfaction) AS satisfaction, MAX(answer) AS answer, MAX(dur) AS duration_ms
  FROM ${catalog}.${schema}.silver_events
  WHERE event_type = 'outcome'
  GROUP BY session_id, task_id
) o ON o.session_id = s.session_id AND o.task_id = s.task_id;
