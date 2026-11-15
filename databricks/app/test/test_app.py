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

# 4. /results + /api/results: warehouse reader via a fake Statement Execution client
from types import SimpleNamespace as NS
class FakeSX:
    def __init__(self): self.sql, self.polls = [], 0
    def execute_statement(self, statement, warehouse_id, wait_timeout):
        self.sql.append((statement, warehouse_id))
        return NS(statement_id="s1", status=NS(state=NS(value="PENDING")))  # force one poll
    def get_statement(self, sid):
        self.polls += 1
        cols = [NS(name="session_type", type_name=NS(value="STRING")), NS(name="n_trials", type_name=NS(value="LONG")),
                NS(name="success_rate", type_name=NS(value="DOUBLE")), NS(name="overtrust_rate", type_name=NS(value="DOUBLE"))]
        return NS(statement_id=sid, status=NS(state=NS(value="SUCCEEDED")), manifest=NS(schema=NS(columns=cols)),
                  result=NS(data_array=[["human", "5", "0.4", None], ["simulated", "30", "0.37", "0.5"]]))
sx = FakeSX()
gold = app.GoldReader("wh-1", "workspace.ux_telemetry", client=NS(statement_execution=sx), ttl=60)
app.time.sleep = lambda s: None  # skip the poll delay
res = gold.results()
check("gold reader polls PENDING to SUCCEEDED and types values",
      sx.polls >= 1 and res["tasks"][0] == {"session_type": "human", "n_trials": 5, "success_rate": 0.4, "overtrust_rate": None})
check("gold queries hit the configured schema and warehouse",
      all(w == "wh-1" and "workspace.ux_telemetry.gold_" in q for q, w in sx.sql))
gold.results()
check("results cached within ttl", len(sx.sql) == 2)

(tmp / "proposals").mkdir()
(tmp / "proposals" / "latest.json").write_text(json.dumps({"changes": [{"id": "P1", "uxid": "kpi-avg-fare"}]}))
app.Handler.proposals_path = tmp / "proposals" / "latest.json"
col = app.Collector(app.LocalSink(tmp / "out2"), flush_secs=60)
srv, port = serve(col, static)
app.Handler.gold = None
d = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/results").read())
check("/api/results without warehouse explains setup", d["configured"] is False and "warehouse" in d["error"])
app.Handler.gold = gold
d = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/results").read())
check("/api/results returns gold rows + proposals", d["configured"] and len(d["tasks"]) == 2 and d["proposals"]["changes"][0]["uxid"] == "kpi-avg-fare")
class BoomSX(FakeSX):
    def get_statement(self, sid): return NS(statement_id=sid, status=NS(state=NS(value="FAILED"), error=NS(message="PERMISSION_DENIED: no SELECT")))
app.Handler.gold = app.GoldReader("wh-1", "workspace.ux_telemetry", client=NS(statement_execution=BoomSX()))
d = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/results").read())
check("/api/results surfaces warehouse errors", "PERMISSION_DENIED" in d["error"])
page = urllib.request.urlopen(f"http://127.0.0.1:{port}/results").read().decode()
check("/results serves the results page", "/api/results" in page and "simulated" in page)
srv.shutdown()

sys.exit(0 if all(results) else 1)
