"""Run the medallion pipeline (sql/ux_pipeline_all.sql, copied in by scripts/build-app.sh) from the demo console,
one statement at a time on the SQL warehouse, so the room can watch Volume -> bronze -> silver -> gold happen.

Credentials: the signed-in user's token when the app has user authorization (Databricks Apps forward it as
X-Forwarded-Access-Token; needs the "sql" scope), so the statements run as the person who owns the tables. Without it
the app's service principal is used, which can only replace tables it owns (the run then stops at the first
statement it is not allowed to run, and the error says why).
"""
import re
import threading
import time
from pathlib import Path

HERE = Path(__file__).parent
SQL_FILE = HERE / "sql" / "ux_pipeline_all.sql"
STAGES = {"00_setup": "setup", "01_bronze_ddl": "bronze", "01b_bronze_load": "bronze", "02_silver": "silver",
          "06_silver_chat": "silver", "03_gold": "gold", "07_gold_chat": "gold", "05_comments": "comments"}


def _code(line):
    """The line without a trailing -- comment (quotes respected)."""
    q = False
    for i, ch in enumerate(line):
        if ch == "'":
            q = not q
        elif not q and line.startswith("--", i):
            return line[:i]
    return line


def split_statements(text):
    """[(stage, label, sql)] in file order. Statements end with ';' at the end of a line."""
    out, buf, stage = [], [], "setup"
    for line in text.splitlines():
        m = re.match(r"--\s*=+\s*(\w+)\.sql", line)
        if m:
            stage = STAGES.get(m.group(1), m.group(1))
            continue
        if not buf and line.strip().startswith("--"):
            continue
        if not buf and not line.strip():
            continue
        buf.append(line)
        if _code(line).rstrip().endswith(";"):
            sql = "\n".join(buf).rstrip().rstrip(";")
            buf = []
            out.append((stage, label(sql), sql))
    return out


def label(sql):
    s = " ".join(sql.split())
    for pat, fmt in [(r"CREATE OR REPLACE TABLE\s+([\w.]+)", "build {}"), (r"CREATE TABLE IF NOT EXISTS\s+([\w.]+)", "ensure {}"),
                     (r"CREATE (?:SCHEMA|VOLUME) IF NOT EXISTS\s+([\w.]+)", "ensure {}"),
                     (r"COMMENT ON (?:TABLE|COLUMN)\s+([\w.]+)", "describe {}"), (r"INSERT INTO\s+([\w.]+)", "insert into {}")]:
        m = re.search(pat, s, re.I)
        if m:
            return fmt.format(m.group(1).split(".", 2)[-1])
    return s[:60]


COUNTS = """
SELECT
  (SELECT COUNT(*) FROM {s}.bronze_events) AS bronze_events,
  (SELECT COUNT(DISTINCT _source_file) FROM {s}.bronze_events) AS bronze_files,
  (SELECT COUNT(DISTINCT sid) FROM {s}.bronze_events WHERE st = 'human') AS bronze_human_sessions,
  (SELECT COUNT(*) FROM {s}.silver_events WHERE session_type = 'human' AND app_version = 'v1') AS silver_human_v1_events,
  (SELECT COUNT(DISTINCT session_id) FROM {s}.silver_events WHERE session_type = 'human' AND app_version = 'v1') AS silver_human_v1_sessions,
  (SELECT COUNT(*) FROM {s}.silver_goals WHERE session_type = 'human' AND app_version = 'v1') AS silver_human_v1_goals,
  (SELECT MAX(_ingested_at) FROM {s}.bronze_events) AS bronze_built_at
"""
GOLD = """
SELECT goal_id, n_goals, success_rate, avg_chart_hovers FROM {s}.gold_goal_summary
WHERE session_type = 'human' AND app_version = 'v1' ORDER BY goal_id
"""
FRICTION = """
SELECT uxid, n_clicks, n_dead_clicks, n_rage_clicks FROM {s}.gold_element_friction
WHERE session_type = 'human' AND app_version = 'v1' ORDER BY n_dead_clicks + n_rage_clicks DESC LIMIT 3
"""


def explain(ex):
    """A readable error. Older databricks-sdk versions report a non-JSON error body as 'unable to parse response'
    followed by the request log; keep the server's reply lines (starting with '< ') so the real reason shows."""
    text = f"{type(ex).__name__}: {ex}"
    if "unable to parse response" in text:
        reply = [ln[2:].strip() for ln in text.splitlines() if ln.startswith("< ")]
        status = next((r for r in reply if r.startswith("HTTP") or r[:3].isdigit()), "")
        body = [r for r in reply if r and r != status and not r.startswith("*")]
        text = f"{type(ex).__name__} {status} {' '.join(body)[:600]}".strip() or text
    return text[:900]


class PipelineRun:
    """One run at a time. `reader` is a GoldReader-like object with .query(sql) bound to the chosen credentials."""

    def __init__(self, schema, sql_file=SQL_FILE):
        self.schema, self.sql_file = schema, Path(sql_file)
        self.lock = threading.Lock()
        self.state = {"status": "idle", "steps": [], "snapshots": {}, "as": None}

    def plan(self):
        if not self.sql_file.exists():
            return []
        return split_statements(self.sql_file.read_text())

    def steps(self, include_comments=False):
        """Statements the console runs: no setup (the schema and Volume already exist), no comments unless asked."""
        return [p for p in self.plan() if p[0] != "setup" and (include_comments or p[0] != "comments")]

    def snapshot(self, reader):
        s, snap = self.schema, {}
        for key, q in (("counts", COUNTS), ("gold", GOLD), ("friction", FRICTION)):
            try:
                snap[key] = reader.query(q.format(s=s))
            except Exception as ex:  # a table not built yet
                snap[key + "_error"] = f"{type(ex).__name__}: {ex}"[:200]
        return snap

    def start(self, reader, who, include_comments=False):
        with self.lock:
            if self.state["status"] == "running":
                return False
            plan = self.steps(include_comments)
            if not plan:
                self.state = {"status": "error", "error": f"{self.sql_file.name} is not in the app (run scripts/build-app.sh)",
                              "steps": [], "snapshots": {}, "as": who}
                return False
            self.state = {"status": "running", "as": who, "started": time.time(), "snapshots": {},
                          "steps": [{"stage": st, "label": lb, "status": "pending"} for st, lb, _ in plan]}
        threading.Thread(target=self._run, args=(reader, plan), daemon=True).start()
        return True

    def _run(self, reader, plan):
        st = self.state
        st["snapshots"]["before"] = self.snapshot(reader)
        for i, (stage, _, sql) in enumerate(plan):
            step = st["steps"][i]
            step["status"], t0 = "running", time.time()
            try:
                reader.query(sql)
                step["status"] = "done"
            except Exception as ex:
                step["status"], step["error"] = "failed", explain(ex)
                st["status"], st["error"] = "failed", f"stopped at '{step['label']}': {step['error']}"
                st["snapshots"]["after"] = self.snapshot(reader)
                return
            finally:
                step["ms"] = int((time.time() - t0) * 1000)
            nxt = plan[i + 1][0] if i + 1 < len(plan) else None
            if stage in ("bronze", "silver", "gold") and nxt != stage:  # a layer finished: show what it holds now
                st["snapshots"][stage] = self.snapshot(reader)
        st["snapshots"]["after"] = self.snapshot(reader)
        st["status"], st["finished"] = "done", time.time()

    def status(self):
        return self.state
