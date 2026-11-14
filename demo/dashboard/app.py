#!/usr/bin/env python3
"""Tiny collector + static server for the demo "customer" dashboard (stdlib only).

  GET  /...        serves static/ (dashboard, scenarios.json, data.json, SDK files)
  POST /events     appends each event of a JSON array to a JSONL file (one event per line)

Run:  python3 app.py --port 8765 --out events.jsonl
Port to FastAPI for a Databricks App later: same two routes, write to a Volume instead of a file.
"""
import argparse
import json
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
LOCK = threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    out_path = HERE / "events.jsonl"

    def do_POST(self):
        if self.path != "/events":
            self.send_error(404)
            return
        length = int(self.headers.get("content-length") or 0)
        if length <= 0 or length > 1_000_000:
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
        recv = int(time.time() * 1000)
        with LOCK, open(self.out_path, "a", encoding="utf-8") as f:
            for e in batch:
                if isinstance(e, dict):
                    e["recv_t"] = recv
                    f.write(json.dumps(e) + "\n")
        self.send_response(204)
        self.end_headers()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):  # keep the console quiet
        pass


def make_server(port=8765, out=None, static=None):
    Handler.out_path = Path(out) if out else HERE / "events.jsonl"
    handler = partial(Handler, directory=str(static or HERE / "static"))
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--out", default=str(HERE / "events.jsonl"))
    a = ap.parse_args()
    srv = make_server(a.port, a.out)
    print(f"dashboard: http://127.0.0.1:{a.port}/?study=1&pid=P01&st=human&v=1   events -> {a.out}")
    srv.serve_forever()
