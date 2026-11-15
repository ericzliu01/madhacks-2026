-- Load raw JSONL from the Volume into bronze, skipping files that are already loaded (by _source_file).
-- Spark/Databricks SQL only. UNTESTED in this form: replaces COPY INTO, whose column list failed on files that
-- lack optional fields (UNRESOLVED_COLUMN `tab`: app-recorded events have no tab/frame, only the extension sends them).
-- read_files with an EXPLICIT schema fixes both known COPY INTO problems:
--   * a field absent from a file comes back as NULL instead of a missing column
--   * whole numbers are parsed straight into the DOUBLE columns, so no BIGINT vs DOUBLE merge conflict
-- Re-running is safe: files whose path is already in bronze_events are not loaded again.
INSERT INTO ${catalog}.${schema}.bronze_events
SELECT t, recv_t, sid, st, app, task, tcat, pid, page, path, type, tab, frame, x, y, v, btn, tag, role, uxid, testid, label, region, dom, action, interactive, ptr, n, how, chars, words, hash, text, ctx, combo, del, dur, pos, ratio, state, status, satisfaction, answer, name, chart, series, prompt, w, h, dpr,
       _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM read_files(
  '/Volumes/${catalog}/${schema}/${volume}/raw/',
  format => 'json',
  schema => 't BIGINT, recv_t BIGINT, sid STRING, st STRING, app STRING, task STRING, tcat STRING, pid STRING, page STRING, path STRING, type STRING, tab BIGINT, frame BIGINT, x DOUBLE, y DOUBLE, v DOUBLE, btn BIGINT, tag STRING, role STRING, uxid STRING, testid STRING, label STRING, region STRING, dom STRING, action STRING, interactive BOOLEAN, ptr BOOLEAN, n BIGINT, how STRING, chars BIGINT, words BIGINT, hash STRING, text STRING, ctx STRING, combo STRING, del BIGINT, dur DOUBLE, pos DOUBLE, ratio DOUBLE, state STRING, status STRING, satisfaction BIGINT, answer STRING, name STRING, chart STRING, series STRING, prompt STRING, w BIGINT, h BIGINT, dpr DOUBLE'
)
WHERE _metadata.file_path NOT IN (
  SELECT DISTINCT _source_file FROM ${catalog}.${schema}.bronze_events WHERE _source_file IS NOT NULL
);
