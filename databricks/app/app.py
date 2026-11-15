#!/usr/bin/env python3
"""Databricks App: serves the demo "customer" dashboard and collects its telemetry into a Unity Catalog Volume.

  GET  /...        static/ (dashboard, scenarios.json, data.json, SDK files)
  POST /events     JSON array of events -> buffered -> one JSONL file per flush in the Volume
  GET  /healthz    "ok"

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


class Handler(SimpleHTTPRequestHandler):
    collector = None

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
        if self.path.split("?")[0] == "/status":  # where events go and whether uploads work (no secrets)
            c = self.collector
            body = json.dumps({"sink": type(c.sink).__name__, "where": c.sink.where(), "buffered": len(c.buf),
                               "written": c.written, "flush_errors": c.errors,
                               "last_error": c.last_error}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
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


def make_server(collector, host="127.0.0.1", port=8000, static=None):
    Handler.collector = collector
    return ThreadingHTTPServer((host, port), partial(Handler, directory=str(static or HERE / "static")))


def build_sink():
    vol = os.environ.get("EVENTS_VOLUME_PATH")
    return VolumeSink(vol) if vol else LocalSink(os.environ.get("EVENTS_DIR", HERE / "events"))


if __name__ == "__main__":
    port = int(os.environ.get("DATABRICKS_APP_PORT") or os.environ.get("PORT") or 8000)
    host = "0.0.0.0" if os.environ.get("DATABRICKS_APP_PORT") else "127.0.0.1"
    sink = build_sink()
    col = Collector(sink, float(os.environ.get("FLUSH_SECS", 3)), int(os.environ.get("FLUSH_EVENTS", 200)))
    col.start()
    srv = make_server(col, host, port)
    print(f"dashboard on {host}:{port}  events -> {sink.where()}", flush=True)
    try:
        srv.serve_forever()
    finally:
        col.stop()
