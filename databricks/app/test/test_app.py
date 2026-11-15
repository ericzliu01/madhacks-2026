#!/usr/bin/env python3
"""Tests the App collector without Databricks: local sink, volume sink via a fake Files client, retry on failure, static serving."""
import io, json, sys, tempfile, threading, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import app

results = []
def check(name, ok): results.append(ok); print("PASS" if ok else "FAIL", name)

def post(port, body, path="/events"):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method="POST")
    try:
        return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as e:
        return e.code

def serve(col, static):
    srv = app.make_server(col, "127.0.0.1", 0, static)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]

tmp = Path(tempfile.mkdtemp())
static = tmp / "static"; static.mkdir(); (static / "index.html").write_text("<h1>hi</h1>")

# 1. local sink: events land as one new JSONL file per flush, with recv_t stamped
col = app.Collector(app.LocalSink(tmp / "out"), flush_secs=60)
srv, port = serve(col, static)
check("POST /events -> 204", post(port, json.dumps([{"type": "click", "sid": "a"}, {"type": "key", "sid": "a"}]).encode()) == 204)
check("bad json -> 400", post(port, b"{nope") == 400)
check("non-array -> 400", post(port, b'{"a":1}') == 400)
check("wrong path -> 404", post(port, b"[]", "/nope") == 404)
col.flush(); col.flush()  # second flush is empty and must not create a file
files = list((tmp / "out").glob("*.jsonl"))
rows = [json.loads(l) for f in files for l in f.read_text().splitlines()]
check("one file for one flush", len(files) == 1)
check("both events written with recv_t", len(rows) == 2 and all("recv_t" in r for r in rows))
check("static served", urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html").read() == b"<h1>hi</h1>")
st = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/status").read())
check("/status reports sink and counts", st["sink"] == "LocalSink" and st["written"] == 2 and st["flush_errors"] == 0)
check("/healthz ok", urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz").read() == b"ok")
srv.shutdown()

# 2. volume sink via a fake client: files go to the Volume path, never overwrite
class FakeFiles:
    def __init__(self): self.up = {}; self.fail = 0
    def upload(self, path, fh, overwrite=False):
        if self.fail: self.fail -= 1; raise RuntimeError("boom")
        assert overwrite is False
        self.up[path] = fh.read()
class FakeClient: files = FakeFiles()
vol = app.VolumeSink("/Volumes/workspace/ux_telemetry/raw_events/raw/", client=FakeClient())
col = app.Collector(vol, flush_secs=60, flush_events=3)
col.add([{"type": "click"}] * 3)  # reaching flush_events flushes immediately
paths = list(FakeClient.files.up)
check("volume upload path", len(paths) == 1 and paths[0].startswith("/Volumes/workspace/ux_telemetry/raw_events/raw/app-") and paths[0].endswith(".jsonl"))
check("volume payload is JSONL", all(json.loads(l)["type"] == "click" for l in FakeClient.files.up[paths[0]].decode().splitlines()))

# 3. failed upload keeps events and retries
FakeClient.files.fail = 1
col.add([{"type": "key"}]); col.flush()
check("failure keeps events buffered", len(col.buf) == 1 and col.errors == 1 and "boom" in col.last_error)
col.flush()
check("retry delivers them", len(col.buf) == 0 and col.written == 4)

sys.exit(0 if all(results) else 1)
