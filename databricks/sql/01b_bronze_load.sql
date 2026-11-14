-- Load raw JSONL from the Volume into bronze. COPY INTO is idempotent: files already loaded are skipped.
-- Spark/Databricks SQL only (UNTESTED here: no workspace access from the sandbox). Check the COPY INTO syntax in the docs.
COPY INTO ${catalog}.${schema}.bronze_events
FROM (
  SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
  FROM '/Volumes/${catalog}/${schema}/${volume}/raw/'
)
FILEFORMAT = JSON
COPY_OPTIONS ('mergeSchema' = 'true');
