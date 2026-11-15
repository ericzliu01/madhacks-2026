#!/usr/bin/env python3
"""Split a local collector log (demo/dashboard/app.py --out events.jsonl) into one JSONL file per session, ready to
upload to /Volumes/<catalog>/<schema>/<volume>/raw/. Prints a per-session summary so test runs can be spotted and
left out before uploading.

Usage: python3 split_events.py events.jsonl --out databricks/data/human_upload [--prefix local] [--only-st human]
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("log")
ap.add_argument("--out", required=True)
ap.add_argument("--prefix", default="local")
ap.add_argument("--only-st", help="keep only sessions with this session type (e.g. human)")
a = ap.parse_args()

by_sid = defaultdict(list)
for line in Path(a.log).read_text().splitlines():
    if line.strip():
        by_sid[json.loads(line).get("sid")].append(line)

out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
for sid, lines in sorted(by_sid.items(), key=lambda kv: json.loads(kv[1][0])["t"]):
    ev = [json.loads(l) for l in lines]
    st, pid, app = ev[0].get("st"), ev[0].get("pid"), ev[0].get("app")
    goals = [f"{e['goal']}:{e['status']}" for e in ev if e["type"] == "goal_outcome"]
    tasks = [f"{e['task']}:{e['status']}" for e in ev if e["type"] == "outcome"]
    keep = not a.only_st or st == a.only_st
    print(f"{'KEEP' if keep else 'skip'} {sid[:8]} st={st} pid={pid} {app} events={len(ev)} {' '.join(goals + tasks)}")
    if keep:
        (out / f"{a.prefix}-{sid}.jsonl").write_text("\n".join(lines) + "\n")
print(f"files in {out}: {len(list(out.glob('*.jsonl')))}")
