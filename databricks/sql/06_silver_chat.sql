-- SILVER (chat study, mode=goals): goals and assistant turns, rebuilt from silver_events.
-- Portable subset (Databricks SQL and the local SQLite harness). Keep comments free of semicolons.
-- silver_trials (scripted tasks) is untouched: a goal is not a task, and one goal has many turns.
-- correct / accepted / had_selection are 1 / 0 integers here (NULL correct = the assistant did not answer the question,
-- e.g. it asked which borough, or no reply arrived).
-- Turns outside a goal (the chat used outside study mode) have goal_id NULL and are not included.

-- One row per (session, goal). outcome: correct | incorrect | abandoned | no_outcome (left without finishing).
-- final_turn = the assistant turn whose answer the participant submitted (NULL if they typed their own answer).
CREATE OR REPLACE TABLE ${catalog}.${schema}.silver_goals AS
SELECT s.session_id, s.session_type, s.app_id, s.app_version, s.participant_id, s.goal_id, s.goal_cats,
       s.start_ms,
       o.end_ms,
       COALESCE(o.outcome, 'no_outcome') AS outcome,
       o.satisfaction,
       o.final_answer,
       o.final_turn,
       o.duration_ms
FROM (
  SELECT session_id, session_type, app_id, app_version, participant_id, goal_id, MAX(goal_cats) AS goal_cats,
         MIN(ts_ms) AS start_ms
  FROM ${catalog}.${schema}.silver_events
  WHERE event_type = 'goal_start' AND goal_id IS NOT NULL
  GROUP BY session_id, session_type, app_id, app_version, participant_id, goal_id
) s
LEFT JOIN (
  SELECT session_id, goal_id, MAX(ts_ms) AS end_ms, MAX(status) AS outcome, MAX(satisfaction) AS satisfaction,
         MAX(answer) AS final_answer, MAX(turn_id) AS final_turn, MAX(dur) AS duration_ms
  FROM ${catalog}.${schema}.silver_events
  WHERE event_type = 'goal_outcome'
  GROUP BY session_id, goal_id
) o ON o.session_id = s.session_id AND o.goal_id = s.goal_id;

-- One row per prompt / response pair, keyed by (session, goal, turn).
-- overlap = token overlap of this prompt with the previous prompt in the same goal, computed in the browser
-- (content tokens = lowercase alphanumerics minus stopwords, overlap coefficient |A and B| / min(|A|, |B|)), so the
-- reformulation metric works without storing prompt text. prompt_text is only present with the participant's consent.
-- goal_sim = Jaccard similarity of the prompt with the goal text (also computed in the browser) and pasted = something
-- was pasted into the chat box before this prompt: together they flag a pasted goal (see gold_turn_metrics).
CREATE OR REPLACE TABLE ${catalog}.${schema}.silver_turns AS
SELECT p.session_id, p.session_type, p.app_id, p.app_version, p.participant_id, p.goal_id, p.turn_id,
       p.prompt_ms, r.response_ms, r.latency_ms,
       p.prompt_hash, p.prompt_text, p.chars, p.words, p.overlap, p.had_selection, p.goal_sim, p.pasted,
       r.intent, r.behavior, r.answer_id, r.correct, r.bot_answer, r.mark_x,
       CASE WHEN COALESCE(f.n_accept_copy, 0) > 0 THEN 1 ELSE 0 END AS accepted,
       COALESCE(f.n_thumbs_up, 0) AS n_thumbs_up,
       COALESCE(f.n_thumbs_down, 0) AS n_thumbs_down
FROM (
  SELECT session_id, session_type, app_id, app_version, participant_id, goal_id, turn_id,
         MIN(ts_ms) AS prompt_ms, MAX(prompt_hash) AS prompt_hash, MAX(prompt_text) AS prompt_text,
         MAX(chars) AS chars, MAX(words) AS words, MAX(overlap) AS overlap,
         MAX(CASE WHEN had_selection = TRUE THEN 1 ELSE 0 END) AS had_selection,
         MAX(goal_sim) AS goal_sim,
         MAX(CASE WHEN pasted = TRUE THEN 1 ELSE 0 END) AS pasted
  FROM ${catalog}.${schema}.silver_events
  WHERE event_type = 'prompt_submit' AND goal_id IS NOT NULL AND turn_id IS NOT NULL
  GROUP BY session_id, session_type, app_id, app_version, participant_id, goal_id, turn_id
) p
LEFT JOIN (
  SELECT session_id, goal_id, turn_id, MIN(ts_ms) AS response_ms, MAX(latency_ms) AS latency_ms,
         MAX(intent) AS intent, MAX(behavior) AS behavior, MAX(answer_id) AS answer_id,
         MAX(CASE WHEN correct = TRUE THEN 1 WHEN correct = FALSE THEN 0 END) AS correct,
         MAX(answer) AS bot_answer, MAX(mark_x) AS mark_x
  FROM ${catalog}.${schema}.silver_events
  WHERE event_type = 'assistant_response'
  GROUP BY session_id, goal_id, turn_id
) r ON r.session_id = p.session_id AND r.goal_id = p.goal_id AND r.turn_id = p.turn_id
LEFT JOIN (
  SELECT session_id, goal_id, turn_id,
         SUM(CASE WHEN feedback IN ('accept', 'copy') THEN 1 ELSE 0 END) AS n_accept_copy,
         SUM(CASE WHEN feedback = 'thumbs_up' THEN 1 ELSE 0 END) AS n_thumbs_up,
         SUM(CASE WHEN feedback = 'thumbs_down' THEN 1 ELSE 0 END) AS n_thumbs_down
  FROM ${catalog}.${schema}.silver_events
  WHERE event_type = 'answer_feedback'
  GROUP BY session_id, goal_id, turn_id
) f ON f.session_id = p.session_id AND f.goal_id = p.goal_id AND f.turn_id = p.turn_id;
