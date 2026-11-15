#!/usr/bin/env python3
"""Tiny collector + static server for the demo "customer" dashboard (stdlib only).

  GET  /...        serves static/ (dashboard, scenarios.json, data.json, SDK files)
  POST /events     appends each event of a JSON array to a JSONL file (one event per line)
  POST /chat       stub assistant (chatbot.py): {prompt, v, selection?, prev_intents?} -> reply with planted behaviors

Run:  python3 app.py --port 8765 --out events.jsonl [--latency-scale 0.1]
Port to FastAPI for a Databricks App later: same two routes, write to a Volume instead of a file.
"""
import argparse
import json
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # chatbot.py sits next to this file (also under python -I)
import chatbot  # noqa: E402

HERE = Path(__file__).parent
LOCK = threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    out_path = HERE / "events.jsonl"
    bot = None
    latency_scale = 1.0

    def do_POST(self):
        if self.path not in ("/events", "/chat"):
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
        if self.path == "/chat":
            try:
                body = json.dumps(chatbot.chat_reply(self.bot, batch, self.latency_scale)).encode()
            except ValueError as ex:
                self.send_error(400, str(ex))
                return
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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


def make_server(port=8765, out=None, static=None, latency_scale=1.0):
    Handler.out_path = Path(out) if out else HERE / "events.jsonl"
    Handler.bot = chatbot.Bot.load(static or HERE / "static")
    Handler.latency_scale = latency_scale
    handler = partial(Handler, directory=str(static or HERE / "static"))
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--out", default=str(HERE / "events.jsonl"))
    ap.add_argument("--latency-scale", type=float, default=1.0, help="multiply the stub's planted reply delays")
    a = ap.parse_args()
    srv = make_server(a.port, a.out, latency_scale=a.latency_scale)
    print(f"dashboard: http://127.0.0.1:{a.port}/?pid=P01&v=1  (goals mode; &mode=tasks for the task panel)"
          f"   events -> {a.out}")
    srv.serve_forever()
