-- Sessions left out of analysis, with the reason. Safe to re-run (only adds ids not yet listed).
-- Run once after ux_pipeline_all.sql has created the table, then run ux_pipeline_all.sql again.
CREATE TABLE IF NOT EXISTS workspace.ux_telemetry.excluded_sessions (session_id STRING, reason STRING);

INSERT INTO workspace.ux_telemetry.excluded_sessions
SELECT v.session_id, v.reason FROM VALUES
  ('a02c04fd-79ee-4547-9c16-8fb9e9dcc0f4', '2026-11-15 P01 restart: 5 events, no goal'),
  ('6ff3232b-7159-4621-aab0-8978919fa042', '2026-11-15 P01 restart: 2 goals started, 1 finished'),
  ('6abcfe2a-e6c8-4ca2-aed1-fe956ba7ed1a', '2026-11-15 P01 restart: 2 events, no goal'),
  ('47dc9c23-65f0-4d3e-a30c-001a0e26629a', '2026-11-15 P01 restart: 1 goal started, none finished'),
  ('bbe21a33-1eb8-44fb-9b32-646ef6d056e3', '2026-11-15 P02 on v2: no goal started (spot check or reload)'),
  ('8482f146-d5dc-42a5-b431-64dacbb0876b', '2026-11-15 P02 on v2: no goal started (spot check or reload)'),
  ('d5e5eab1-d450-4291-a6d2-ce53d6f891da', '2026-11-15 P02 on v2: no goal started (spot check or reload)')
AS v(session_id, reason)
WHERE v.session_id NOT IN (SELECT session_id FROM workspace.ux_telemetry.excluded_sessions WHERE session_id IS NOT NULL);
