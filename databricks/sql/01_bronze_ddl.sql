-- BRONZE: raw events exactly as the SDK sends them (one row per event), plus load metadata. No cleaning here.
-- Explicit schema so downstream SQL never breaks when a field is absent from a given batch.
-- Portable subset: also executed by the local SQLite test harness (STRING -> TEXT there).
-- This is the single list of raw columns: databricks/tools/gen_bronze_load.py writes 01b's read_files schema from it.
-- Chat-study columns (goal .. sel) come from the goals mode: see packages/core/uxtelemetry.js and chatbot.py.
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.bronze_events (
  t BIGINT, recv_t BIGINT,
  sid STRING, st STRING, app STRING, task STRING, tcat STRING, pid STRING,
  page STRING, path STRING, type STRING, tab BIGINT, frame BIGINT,
  x DOUBLE, y DOUBLE, v DOUBLE, btn BIGINT,
  tag STRING, role STRING, uxid STRING, testid STRING, label STRING, region STRING, dom STRING, action STRING,
  interactive BOOLEAN, ptr BOOLEAN, n BIGINT,
  how STRING, chars BIGINT, words BIGINT, hash STRING, text STRING,
  ctx STRING, combo STRING, del BIGINT,
  dur DOUBLE, pos DOUBLE, ratio DOUBLE, state STRING,
  status STRING, satisfaction BIGINT, answer STRING, name STRING,
  chart STRING, series STRING, prompt STRING,
  w BIGINT, h BIGINT, dpr DOUBLE,
  goal STRING, gcats STRING, turn BIGINT,
  latency_ms BIGINT, behavior STRING, answer_id STRING, correct BOOLEAN, intent STRING, feedback STRING,
  mark_x STRING, mark_y DOUBLE, overlap DOUBLE, sel BOOLEAN, goal_sim DOUBLE, pasted BOOLEAN,
  _source_file STRING, _ingested_at TIMESTAMP
);
