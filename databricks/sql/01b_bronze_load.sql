-- Load raw JSONL from the Volume into bronze. COPY INTO is idempotent: files already loaded are skipped.
-- Spark/Databricks SQL only. Verified on a Free Edition workspace (4087 rows loaded).
-- The column list is explicit on purpose. JSON inference types whole-number values as BIGINT, and Delta refuses to merge
-- BIGINT into the DOUBLE columns defined in 01_bronze_ddl.sql (DELTA_FAILED_TO_MERGE_FIELDS), so the DOUBLE columns are cast.
-- It also keeps the parser's _rescued_data column out of bronze. Trade-off: a new SDK field needs a DDL + select-list update.
COPY INTO ${catalog}.${schema}.bronze_events
FROM (
  SELECT
    t, recv_t,
    sid, st, app, task, tcat, pid,
    page, path, type, tab, frame,
    CAST(x AS DOUBLE) AS x, CAST(y AS DOUBLE) AS y, CAST(v AS DOUBLE) AS v, btn,
    tag, role, uxid, testid, label, region, dom, action,
    interactive, ptr, n,
    how, chars, words, hash, text,
    ctx, combo, del,
    CAST(dur AS DOUBLE) AS dur, CAST(pos AS DOUBLE) AS pos, CAST(ratio AS DOUBLE) AS ratio, state,
    status, satisfaction, answer, name,
    chart, series, prompt,
    w, h, CAST(dpr AS DOUBLE) AS dpr,
    _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
  FROM '/Volumes/${catalog}/${schema}/${volume}/raw/'
)
FILEFORMAT = JSON
COPY_OPTIONS ('mergeSchema' = 'true');
