-- AI STEP (1 of 2): classify AI-assistant prompts on two axes, validated against a human-labeled subset.
--   axis 1 task:   Amar/Eagan/Stasko low-level tasks (+ 'none' for prompts that are not chart-reading tasks)
--   axis 2 intent: analyze | build | debug | explain | navigate     (our proposed extension: code/debug/wrangling prompts)
-- Needs raw prompt text, i.e. data recorded with captureText = true. The demo dashboard has no prompt box, so this
-- table stays empty until the Chrome extension records Databricks Assistant/Genie prompts with consent.
--
-- Spark/Databricks SQL only. UNTESTED: no workspace access from the sandbox, and I could not confirm AI Functions
-- availability on Free Edition. VERIFY ai_classify's current signature in the docs: newer versions may expect a JSON
-- map of label -> description and return a VARIANT, in which case adapt the calls below.

CREATE OR REPLACE TABLE ${catalog}.${schema}.gold_prompt_labels AS
SELECT session_id, task_id, ts_ms, prompt_hash, prompt_text,
       ai_classify(prompt_text, ARRAY(
         'retrieve_value', 'filter', 'compute_derived_value', 'find_extremum', 'sort',
         'determine_range', 'characterize_distribution', 'find_anomalies', 'cluster', 'correlate', 'none')) AS llm_task,
       ai_classify(prompt_text, ARRAY('analyze', 'build', 'debug', 'explain', 'navigate')) AS llm_intent
FROM ${catalog}.${schema}.silver_events
WHERE event_type = 'prompt_submit' AND prompt_text IS NOT NULL;

-- Human-labeled gold subset (fill in by hand, two raters, ~100 prompts) so LLM labels are never trusted unchecked.
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.labels_human (
  prompt_hash STRING, rater STRING, human_task STRING, human_intent STRING
);

-- Agreement of LLM labels with each rater (accuracy; add Cohen's kappa in a notebook for the write-up).
SELECT h.rater,
       COUNT(*) AS n_labeled,
       AVG(CASE WHEN p.llm_task = h.human_task THEN 1.0 ELSE 0.0 END) AS task_accuracy,
       AVG(CASE WHEN p.llm_intent = h.human_intent THEN 1.0 ELSE 0.0 END) AS intent_accuracy
FROM ${catalog}.${schema}.gold_prompt_labels p
JOIN ${catalog}.${schema}.labels_human h ON h.prompt_hash = p.prompt_hash
GROUP BY h.rater;
