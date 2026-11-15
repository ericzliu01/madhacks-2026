#!/usr/bin/env python3
"""Run the portable bronze/silver/gold SQL in SQLite and assert the planted flaws are recoverable.

Validates the *logic* of sql/01_bronze_ddl.sql, 02_silver.sql, 03_gold.sql (CTEs, windows, joins, aggregates).
It does NOT validate Spark-only files (01b COPY INTO, 04 AI functions, 05 comments) or Databricks type semantics.
Input is SIMULATED data (st='simulated'), so this tests the pipeline, not real user behavior.

Usage: python3 run_sql_local.py [sessions_dir]     (needs sqlite >= 3.25 for window functions)
"""
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
SQL = HERE.parent / "sql"
sessions = Path(sys.argv[1]) if len(sys.argv) > 1 else None

if sessions is None:  # generate a fresh simulated dataset
    sessions = Path(tempfile.mkdtemp(prefix="sim-sessions-"))
    subprocess.run([sys.executable, "-I", str(HERE.parent / "tools/make_sessions.py"), "--out", str(sessions),
                    "--per-version", "30", "--seed", "7"], check=True)


def prep(sql):
    sql = re.sub(r"--[^\n]*", "", sql)                       # strip comments
    sql = sql.replace("${catalog}.${schema}.", "")           # SQLite has no catalogs
    sql = re.sub(r"\bSTRING\b", "TEXT", sql)
    out = []
    for stmt in filter(None, (s.strip() for s in sql.split(";"))):
        m = re.match(r"CREATE OR REPLACE TABLE\s+(\w+)", stmt, re.I)
        if m:
            out.append(f"DROP TABLE IF EXISTS {m.group(1)}")
            stmt = re.sub(r"CREATE OR REPLACE TABLE", "CREATE TABLE", stmt, count=1, flags=re.I)
        out.append(stmt)
    return out


db = sqlite3.connect(":memory:")
db.row_factory = sqlite3.Row
print("sqlite", sqlite3.sqlite_version)

for stmt in prep((SQL / "01_bronze_ddl.sql").read_text()):
    db.execute(stmt)
cols = [r["name"] for r in db.execute("PRAGMA table_info(bronze_events)")]
n = 0
for f in sorted(sessions.glob("*.jsonl")):
    rows = []
    for line in f.read_text().splitlines():
        e = json.loads(line)
        e["_source_file"] = f.name
        rows.append([e.get(c) for c in cols])
        n += 1
    db.executemany(f"INSERT INTO bronze_events ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", rows)
# One simulated session relabelled as a human participant: gold must keep it apart from the simulated rows.
human_src = sorted(sessions.glob("*.jsonl"))[0]
hrows = []
for line in human_src.read_text().splitlines():
    e = json.loads(line)
    e.update(sid="human-check", st="human", _source_file="human-check.jsonl")
    hrows.append([e.get(c) for c in cols])
db.executemany(f"INSERT INTO bronze_events ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", hrows)
n += len(hrows)
print(f"loaded {n} bronze events from {sessions} (+1 session relabelled human)")

for name in ("02_silver.sql", "03_gold.sql"):
    for stmt in prep((SQL / name).read_text()):
        db.execute(stmt)

q = lambda s: [dict(r) for r in db.execute(s)]
count = lambda t: q(f"SELECT COUNT(*) AS c FROM {t}")[0]["c"]
print({t: count(t) for t in ("silver_events", "silver_trials", "gold_trial_metrics", "gold_task_summary", "gold_element_friction", "gold_version_comparison")})

SIM = "session_type = 'simulated'"
cmp = {r["task_id"]: r for r in q(f"SELECT * FROM gold_version_comparison WHERE {SIM}")}
friction = q(f"SELECT * FROM gold_element_friction WHERE {SIM} AND app_version = 'v1' ORDER BY n_rage_clicks DESC")
v2_kpi = q(f"SELECT COALESCE(SUM(n_rage_clicks), 0) AS r FROM gold_element_friction WHERE {SIM} AND app_version = 'v2' AND uxid = 'kpi-avg-fare'")[0]["r"]
human = q("SELECT SUM(n_trials) AS n FROM gold_task_summary WHERE session_type = 'human'")[0]["n"]
sim_n = q(f"SELECT SUM(n_trials) AS n FROM gold_task_summary WHERE {SIM}")[0]["n"]

checks = [
    ("silver dedupes nothing it shouldn't (events == bronze)", count("silver_events") == count("bronze_events")),
    ("one trial per session x task (60 simulated + 1 human sessions x 5)", count("silver_trials") == 305),
    ("gold keeps human trials apart from simulated (5 vs 300)", human == 5 and sim_n == 300),
    ("F4: top v1 rage element is kpi-avg-fare", friction and friction[0]["uxid"] == "kpi-avg-fare" and friction[0]["n_rage_clicks"] > 0),
    ("F4: v2 has no rage clicks on kpi-avg-fare", v2_kpi == 0),
    ("F1: T2 success v1 < 0.5 and v2 > 0.7", cmp["T2"]["success_rate_v1"] < 0.5 < 0.7 < cmp["T2"]["success_rate_v2"]),
    ("F1: T2 over-trust higher in v1 than v2", (cmp["T2"]["overtrust_rate_v1"] or 0) > (cmp["T2"]["overtrust_rate_v2"] or 0)),
    ("F3: T4 abandon rate v1 > v2 + 0.15", cmp["T4"]["abandon_rate_v1"] > cmp["T4"]["abandon_rate_v2"] + 0.15),
    ("F3: T4 duration v1 > 1.5x v2", cmp["T4"]["avg_duration_ms_v1"] > 1.5 * cmp["T4"]["avg_duration_ms_v2"]),
    ("F2: T3 success improves v1 -> v2", cmp["T3"]["success_delta"] > 0.15),
    ("study-panel clicks excluded from friction", q("SELECT COUNT(*) AS c FROM gold_element_friction WHERE uxid LIKE 'sat-%' OR uxid LIKE 'task-%'")[0]["c"] == 0),
]
for name, ok in checks:
    print("PASS" if ok else "FAIL", name)

print("\ngold_version_comparison (success rate / abandon rate / avg duration s):")
for tid in sorted(cmp):
    r = cmp[tid]
    print(f"  {tid} {r['task_category']:<22} success {r['success_rate_v1']:.2f}->{r['success_rate_v2']:.2f}"
          f"  abandon {r['abandon_rate_v1']:.2f}->{r['abandon_rate_v2']:.2f}"
          f"  dur {r['avg_duration_ms_v1'] / 1000:.0f}s->{r['avg_duration_ms_v2'] / 1000:.0f}s")
print("\ntop v1 friction elements:", [(r["uxid"], r["n_rage_clicks"], round(r["rage_per_click"] or 0, 2)) for r in friction[:3]])
sys.exit(0 if all(ok for _, ok in checks) else 1)
