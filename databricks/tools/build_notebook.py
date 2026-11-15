#!/usr/bin/env python3
"""Combine the prepared SQL files into one importable Databricks SQL notebook (one statement per cell)."""
import re, sys
from pathlib import Path
ready = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "data/ready"
files = ["00_setup.sql", "01_bronze_ddl.sql", "01b_bronze_load.sql", "02_silver.sql", "03_gold.sql", "05_comments.sql"]
cells = []
for f in files:
    text = (ready / f).read_text()
    # split on a semicolon that ends a line (comments may contain mid-line semicolons)
    for stmt in re.split(r";[ \t]*\n", text):
        if re.sub(r"--[^\n]*", "", stmt).strip():
            cells.append(f"-- {f}\n{stmt.strip()};")
cells.append("-- check: row counts per layer (bronze should be 4087)\n"
  "SELECT 'bronze_events' AS t, COUNT(*) AS n FROM workspace.ux_telemetry.bronze_events\n"
  "UNION ALL SELECT 'silver_events', COUNT(*) FROM workspace.ux_telemetry.silver_events\n"
  "UNION ALL SELECT 'silver_trials', COUNT(*) FROM workspace.ux_telemetry.silver_trials\n"
  "UNION ALL SELECT 'gold_trial_metrics', COUNT(*) FROM workspace.ux_telemetry.gold_trial_metrics;")
cells.append("-- check: v1 vs v2 (expect T4 abandon ~0.27 -> 0.00, T2 success ~0.37 -> 0.77)\n"
  "SELECT task_id, success_rate_v1, success_rate_v2, abandon_rate_v1, abandon_rate_v2\n"
  "FROM workspace.ux_telemetry.gold_version_comparison ORDER BY task_id;")
out = ready / "ux_pipeline.sql"
out.write_text("-- Databricks notebook source\n" + "\n\n-- COMMAND ----------\n\n".join(cells) + "\n")
print(f"wrote {len(cells)} cells -> {out}")
