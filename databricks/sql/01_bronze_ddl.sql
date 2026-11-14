-- BRONZE: raw events exactly as the SDK sends them (one row per event), plus load metadata. No cleaning here.
-- Explicit schema so downstream SQL never breaks when a field is absent from a given batch.
-- Portable subset: also executed by the local SQLite test harness (STRING -> TEXT there).
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
  _source_file STRING, _ingested_at TIMESTAMP
);
