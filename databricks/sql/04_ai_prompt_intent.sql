-- AI STEP: label each assistant prompt with an Amar, Eagan and Stasko (2005) low-level task, two ways:
--   llm_task   ai_classify (Databricks AI Functions) on the prompt text
--   rule_task  deterministic mapping from the stub assistant's keyword-parsed intent (chatbot.py), as a baseline
-- and check both against the categories each goal was designed to exercise (goal_cats).
-- Only prompts with text are labeled, i.e. sessions where the participant consented to prompt-text capture
-- (simulated sessions always carry text). Run it separately from ux_pipeline_all.sql: it calls a model per prompt.
--
-- Spark/Databricks SQL only. ai_classify(text, ARRAY(labels...)) returning a STRING was checked on this Free Edition
-- workspace (2026-11-15, two sample prompts). The full table has not been run yet.
-- LLM labels are not trusted unchecked: fill labels_human (two raters) and read the agreement query at the end.

CREATE OR REPLACE TABLE ${catalog}.${schema}.gold_prompt_labels AS
SELECT t.session_id, t.session_type, t.app_version, t.goal_id, t.turn_id, t.prompt_hash, t.prompt_text,
       g.goal_cats, t.intent AS stub_intent, t.behavior, t.correct,
       CASE WHEN t.pasted = 1 AND t.goal_sim >= 0.8 THEN 1 ELSE 0 END AS pasted_goal,
       ai_classify(t.prompt_text, ARRAY(
         'retrieve_value', 'filter', 'compute_derived_value', 'find_extremum', 'sort',
         'determine_range', 'characterize_distribution', 'find_anomalies', 'cluster', 'correlate', 'none')) AS llm_task,
       CASE t.intent
         WHEN 'value_on_date' THEN 'retrieve_value'
         WHEN 'pct_compare' THEN 'compute_derived_value'
         WHEN 'avg_fare' THEN 'compute_derived_value'
         WHEN 'total_trips' THEN 'compute_derived_value'
         WHEN 'extremum' THEN 'find_extremum'
         WHEN 'range' THEN 'determine_range'
         WHEN 'explain_point' THEN 'find_anomalies'
         ELSE 'none'
       END AS rule_task
FROM ${catalog}.${schema}.silver_turns t
LEFT JOIN ${catalog}.${schema}.silver_goals g ON g.session_id = t.session_id AND g.goal_id = t.goal_id
WHERE t.prompt_text IS NOT NULL;

-- Agreement summary: LLM vs rule label, and whether each label is one of the goal's designed categories.
-- Pasted goals are left out (they label our goal wording, not the participant's question) and counted.
CREATE OR REPLACE TABLE ${catalog}.${schema}.gold_prompt_label_agreement AS
SELECT session_type, goal_id, MAX(goal_cats) AS goal_cats,
       SUM(1 - pasted_goal) AS n_prompts,
       SUM(pasted_goal) AS n_pasted_goal_excluded,
       AVG(CASE WHEN pasted_goal = 0 THEN (CASE WHEN llm_task = rule_task THEN 1.0 ELSE 0.0 END) END) AS llm_rule_agreement,
       AVG(CASE WHEN pasted_goal = 0 THEN (CASE WHEN array_contains(split(goal_cats, '[|]'), llm_task) THEN 1.0 ELSE 0.0 END) END) AS llm_in_goal_cats,
       AVG(CASE WHEN pasted_goal = 0 THEN (CASE WHEN array_contains(split(goal_cats, '[|]'), rule_task) THEN 1.0 ELSE 0.0 END) END) AS rule_in_goal_cats
FROM ${catalog}.${schema}.gold_prompt_labels
GROUP BY session_type, goal_id;

-- Human-labeled subset (fill in by hand, two raters) so LLM labels are never trusted unchecked.
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.labels_human (
  prompt_hash STRING, rater STRING, human_task STRING
);

-- Agreement of LLM labels with each rater (accuracy; add Cohen's kappa in a notebook for the write-up).
SELECT h.rater,
       COUNT(*) AS n_labeled,
       AVG(CASE WHEN p.llm_task = h.human_task THEN 1.0 ELSE 0.0 END) AS llm_accuracy,
       AVG(CASE WHEN p.rule_task = h.human_task THEN 1.0 ELSE 0.0 END) AS rule_accuracy
FROM ${catalog}.${schema}.gold_prompt_labels p
JOIN ${catalog}.${schema}.labels_human h ON h.prompt_hash = p.prompt_hash
GROUP BY h.rater;
