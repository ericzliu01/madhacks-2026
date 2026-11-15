#!/usr/bin/env python3
"""Databricks App: serves the demo "customer" dashboard and collects its telemetry into a Unity Catalog Volume.

  GET  /...        static/ (dashboard, scenarios.json, data.json, SDK files)
  POST /events     JSON array of events -> buffered -> one JSONL file per flush in the Volume
  GET  /healthz    "ok"
  GET  /status     sink, counts, last upload error
  GET  /results    v1 vs v2 results page (pages/results.html), data from GET /api/results
  GET  /api/results  gold tables through a SQL warehouse (DATABRICKS_WAREHOUSE_ID) + the designer's proposals

Where events go (first match wins):
  EVENTS_VOLUME_PATH set  -> Databricks Files API (databricks-sdk, app service principal credentials), e.g.
                             /Volumes/workspace/ux_telemetry/raw_events/raw
  otherwise               -> local directory EVENTS_DIR (default ./events), for running without Databricks

Each flush writes a NEW file (no appends), which is what COPY INTO expects. Events buffer in memory and flush every
FLUSH_SECS or FLUSH_EVENTS. Free Edition apps stop on their own, so keep FLUSH_SECS short: anything still buffered is lost.
"""
import io
import json
import os
import secrets
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
MAX_BODY = 1_000_000


class LocalSink:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def write(self, name, data: bytes):
        (self.dir / name).write_bytes(data)

    def where(self):
        return str(self.dir)


class VolumeSink:
    """Upload via the Databricks Files API. `client` is a WorkspaceClient (injectable for tests)."""

    def __init__(self, volume_dir, client=None):
        self.dir = volume_dir.rstrip("/")
        if client is None:
            from databricks.sdk import WorkspaceClient  # app runtime provides credentials through env vars
            client = WorkspaceClient()
        self.client = client

    def write(self, name, data: bytes):
        self.client.files.upload(f"{self.dir}/{name}", io.BytesIO(data), overwrite=False)

    def where(self):
        return self.dir


class Collector:
    def __init__(self, sink, flush_secs=3.0, flush_events=200):
        self.sink, self.flush_secs, self.flush_events = sink, flush_secs, flush_events
        self.buf, self.lock = [], threading.Lock()
        self.written, self.errors, self.last_error = 0, 0, None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._thread.start()

    def add(self, events):
        recv = int(time.time() * 1000)
        with self.lock:
            for e in events:
                if isinstance(e, dict):
                    e["recv_t"] = recv
                    self.buf.append(e)
            full = len(self.buf) >= self.flush_events
        if full:
            self.flush()

    def flush(self):
        with self.lock:
            batch, self.buf = self.buf, []
        if not batch:
            return
        name = f"app-{int(time.time() * 1000)}-{secrets.token_hex(3)}.jsonl"
        data = ("\n".join(json.dumps(e) for e in batch) + "\n").encode()
        try:
            self.sink.write(name, data)
            self.written += len(batch)
            self.last_error = None  # flush_errors keeps the history; last_error reflects the current state
        except Exception as ex:  # keep the events and retry on the next flush
            self.errors += 1
            self.last_error = f"{type(ex).__name__}: {ex}"[:300]
            print(f"flush failed ({type(ex).__name__}: {ex}); keeping {len(batch)} events", flush=True)
            with self.lock:
                self.buf = batch + self.buf

    def _loop(self):
        while not self._stop.wait(self.flush_secs):
            self.flush()

    def stop(self):
        self._stop.set()
        self.flush()


NUMERIC = {"BYTE", "SHORT", "INT", "LONG", "FLOAT", "DOUBLE", "DECIMAL"}
INTEGER = {"BYTE", "SHORT", "INT", "LONG"}


class GoldReader:
    """Reads the gold tables through a SQL warehouse (Statement Execution API, app service principal credentials).

    The service principal needs USE CATALOG, USE SCHEMA, SELECT on the gold tables and CAN USE on the warehouse.
    `client` is a WorkspaceClient (injectable for tests). Results are cached for `ttl` seconds so a page refresh
    does not start a warehouse query each time.
    """

    def __init__(self, warehouse_id, schema, client=None, ttl=30.0):
        self.warehouse_id, self.schema, self.ttl = warehouse_id, schema, ttl
        if client is None:
            from databricks.sdk import WorkspaceClient
            client = WorkspaceClient()
        self.client = client
        self._cache, self._at, self.lock = None, 0.0, threading.Lock()

    def queries(self):
        s = self.schema
        return {
            "tasks": f"SELECT session_type, app_version, task_id, task_category, n_trials, success_rate, abandon_rate, "
                     f"avg_duration_ms, overtrust_rate FROM {s}.gold_task_summary "
                     f"ORDER BY session_type, task_id, app_version",
            "elements": f"SELECT session_type, app_version, uxid, n_clicks, n_rage_clicks, n_dead_clicks, n_sessions, "
                        f"rage_per_click FROM {s}.gold_element_friction "
                        f"WHERE n_rage_clicks > 0 OR n_dead_clicks > 0 "
                        f"ORDER BY session_type, n_rage_clicks DESC, n_dead_clicks DESC LIMIT 40",
        }

    def query(self, sql):
        sx = self.client.statement_execution
        r = sx.execute_statement(statement=sql, warehouse_id=self.warehouse_id, wait_timeout="30s")
        deadline = time.time() + 90  # serverless warehouses can take a while to start
        while _state(r) in ("PENDING", "RUNNING") and time.time() < deadline:
            time.sleep(2)
            r = sx.get_statement(r.statement_id)
        state = _state(r)
        if state != "SUCCEEDED":
            err = getattr(getattr(r, "status", None), "error", None)
            raise RuntimeError(f"statement {state}: {getattr(err, 'message', err)}")
        cols = r.manifest.schema.columns
        rows = (r.result.data_array if r.result else None) or []
        return [{c.name: _convert(v, c) for c, v in zip(cols, row)} for row in rows]

    def results(self):
        with self.lock:
            if self._cache is None or time.time() - self._at > self.ttl:
                self._cache = {k: self.query(q) for k, q in self.queries().items()}
                self._at = time.time()
            return self._cache


def _state(r):
    st = getattr(getattr(r, "status", None), "state", None)
    return getattr(st, "value", st)


def _convert(v, col):
    if v is None:
        return None
    t = getattr(col.type_name, "value", col.type_name)
    if t in INTEGER:
        return int(v)
    if t in NUMERIC:
        return float(v)
    return v


def load_proposals(path):
    """The Claude designer's latest proposal file (databricks/designer/propose.py writes it), or None."""
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


class Handler(SimpleHTTPRequestHandler):
    collector = None
    gold = None
    proposals_path = HERE / "proposals" / "latest.json"

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def api_results(self):
        out = {"proposals": load_proposals(self.proposals_path), "configured": self.gold is not None}
        if self.gold is None:
            out["error"] = "No SQL warehouse configured: add a SQL warehouse resource to the app (see README)."
            return self.send_json(out)
        try:
            out.update(self.gold.results(), schema=self.gold.schema)
        except Exception as ex:
            out["error"] = f"{type(ex).__name__}: {ex}"[:400]
        self.send_json(out)

    def do_POST(self):
        if self.path != "/events":
            self.send_error(404)
            return
        length = int(self.headers.get("content-length") or 0)
        if length <= 0 or length > MAX_BODY:
            self.send_error(413 if length > 0 else 400)
            return
        try:
            batch = json.loads(self.rfile.read(length))
        except ValueError:
            self.send_error(400, "invalid json")
            return
        if not isinstance(batch, list):
            self.send_error(400, "expected a JSON array")
            return
        self.collector.add(batch)
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        route = self.path.split("?")[0]
        if route == "/status":  # where events go and whether uploads work (no secrets)
            c = self.collector
            return self.send_json({"sink": type(c.sink).__name__, "where": c.sink.where(), "buffered": len(c.buf),
                                   "written": c.written, "flush_errors": c.errors, "last_error": c.last_error,
                                   "warehouse": bool(self.gold)})
        if route == "/api/results":
            return self.api_results()
        if route in ("/results", "/results/"):
            body = (HERE / "pages" / "results.html").read_bytes()
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/healthz":
            body = b"ok"
            self.send_response(200)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass


def make_server(collector, host="127.0.0.1", port=8000, static=None, gold=None):
    Handler.collector, Handler.gold = collector, gold
    return ThreadingHTTPServer((host, port), partial(Handler, directory=str(static or HERE / "static")))


def build_gold():
    wh = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    return GoldReader(wh, os.environ.get("GOLD_SCHEMA", "workspace.ux_telemetry")) if wh else None


def build_sink():
    vol = os.environ.get("EVENTS_VOLUME_PATH")
    return VolumeSink(vol) if vol else LocalSink(os.environ.get("EVENTS_DIR", HERE / "events"))


if __name__ == "__main__":
    port = int(os.environ.get("DATABRICKS_APP_PORT") or os.environ.get("PORT") or 8000)
    host = "0.0.0.0" if os.environ.get("DATABRICKS_APP_PORT") else "127.0.0.1"
    sink = build_sink()
    col = Collector(sink, float(os.environ.get("FLUSH_SECS", 3)), int(os.environ.get("FLUSH_EVENTS", 200)))
    col.start()
    gold = build_gold()
    srv = make_server(col, host, port, gold=gold)
    print(f"dashboard on {host}:{port}  events -> {sink.where()}  results -> "
          f"{'warehouse ' + gold.warehouse_id if gold else 'no warehouse configured'}", flush=True)
    try:
        srv.serve_forever()
    finally:
        col.stop()
