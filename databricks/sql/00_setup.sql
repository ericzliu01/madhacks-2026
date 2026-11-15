-- Run once. Replace ${catalog} / ${schema} / ${volume} with your workspace values
-- (Free Edition: use your own catalog, NOT `system`; e.g. catalog=workspace, schema=ux_telemetry, volume=raw_events).
-- Spark/Databricks SQL (not run by the local test harness).
CREATE SCHEMA IF NOT EXISTS ${catalog}.${schema} COMMENT 'UX telemetry research pipeline (bronze/silver/gold)';
CREATE VOLUME IF NOT EXISTS ${catalog}.${schema}.${volume} COMMENT 'Landing zone for raw JSONL telemetry from the uxtelemetry SDK / extension';
-- Upload JSONL files to: /Volumes/${catalog}/${schema}/${volume}/raw/
