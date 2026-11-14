#!/usr/bin/env python3
"""Generate SIMULATED study sessions as JSONL in the SDK's event schema.

Purpose: exercise the Databricks pipeline (bronze -> silver -> gold) before real participants exist, and test
that planted UX flaws (see demo/README.md) are recoverable from the gold tables.

IMPORTANT: the behavior probabilities below encode our hypotheses about the flaws, so this data can only show that
the pipeline *detects what we planted*. It is not evidence about real users. Every event has st='simulated'.

Usage: python3 make_sessions.py --out data/sessions --per-version 30 --seed 7
"""
import argparse
import json
import random
from pathlib import Path

SCEN = json.loads((Path(__file__).parents[2] / "demo/dashboard/static/scenarios.json").read_text())

# Per version & task: P(correct), P(abandon) (remainder = incorrect), mean duration (s).
PROFILE = {
    1: {"T1": (0.85, 0.03, 22), "T2": (0.30, 0.05, 40), "T3": (0.55, 0.12, 55), "T4": (0.50, 0.35, 75), "T5": (0.80, 0.05, 35)},
    2: {"T1": (0.90, 0.02, 20), "T2": (0.80, 0.02, 25), "T3": (0.85, 0.03, 28), "T4": (0.92, 0.03, 24), "T5": (0.85, 0.03, 30)},
}
PANEL = "aside:study-panel"


class Session:
    def __init__(self, rnd, sid, version, pid, t0):
        self.r, self.sid, self.v, self.pid, self.t = rnd, sid, version, pid, t0
        self.events, self.task, self.cat = [], None, None

    def ev(self, type, gap=(80, 900), **kw):
        self.t += self.r.randint(*gap)
        e = {"t": self.t, "recv_t": self.t + 40, "sid": self.sid, "st": "simulated", "app": f"taxi-ops-demo-v{self.v}",
             "task": self.task, "tcat": self.cat, "pid": self.pid, "page": f"dashboard_v{self.v}", "path": "/", "type": type}
        e.update(kw)
        self.events.append(e)
        return e

    def click(self, uxid, region, **kw):
        base = {"x": self.r.randint(40, 1200), "y": self.r.randint(60, 700), "btn": 0, "tag": "div", "uxid": uxid,
                "region": region, "interactive": True, "ptr": False}
        base.update(kw)
        return self.ev("click", **base)


def run_trial(s, scen):
    r = s.r
    s.task, s.cat = scen["id"], scen["category"]
    p_ok, p_ab, mean_s = PROFILE[s.v][scen["id"]]
    start = s.t + r.randint(500, 1500)
    s.t = start
    s.ev("task_start", prompt=scen["prompt"][:200])
    for _ in range(r.randint(3, 7)):
        s.ev("mouse_move", x=r.randint(20, 1250), y=r.randint(20, 760), v=r.randint(80, 900))

    # chart reading: hovers / legend toggling scale with difficulty
    hovers = {"T2": (3, 6) if s.v == 1 else (1, 2), "T3": (4, 8) if s.v == 1 else (1, 3)}.get(scen["id"], (1, 3))
    chart = "bar-total-trips" if scen["id"] == "T2" else "line-daily-trips"
    for _ in range(r.randint(*hovers)):
        s.ev("chart_hover", chart=chart, series=r.choice(["Manhattan", "Brooklyn", "Queens", "Bronx"]), dur=r.randint(180, 1600))
    if scen["id"] == "T3":
        for _ in range(r.randint(1, 4) if s.v == 1 else r.randint(0, 1)):
            s.ev("chart_legend_click", chart="line-daily-trips", series=r.choice(["Manhattan", "Brooklyn", "Queens", "Bronx"]))

    # filter task: planted flaws F3 (hidden menu) and F4 (fake-clickable KPI)
    if scen["id"] == "T4":
        if s.v == 1:
            if r.random() < 0.6:
                x, y = r.randint(500, 560), r.randint(110, 140)
                for _ in range(r.randint(3, 5)):
                    s.ev("click", gap=(60, 200), x=x, y=y, btn=0, tag="div", uxid="kpi-avg-fare", region="div:kpi-row",
                         interactive=False, ptr=True)
                s.ev("rage_click", gap=(5, 20), x=x, y=y, n=r.randint(3, 5), tag="div", uxid="kpi-avg-fare",
                     region="div:kpi-row", interactive=False, ptr=True)
            if r.random() < 0.5:
                s.ev("idle_end", gap=(100, 300), dur=r.randint(31000, 55000))
            s.click("menu-more", "div:toolbar", tag="button", label="More options")
        s.click("filter-borough", "div:toolbar" if s.v == 1 else "div:toolbar", tag="select")

    if r.random() < (0.25 if s.v == 1 else 0.05) and scen["id"] in ("T2", "T3"):
        s.ev("idle_end", dur=r.randint(31000, 48000))

    # answer panel interactions (study chrome; excluded from friction metrics by region)
    s.click("task-answer", PANEL, tag="input")
    roll = r.random()
    status = "correct" if roll < p_ok else ("abandoned" if roll < p_ok + p_ab else "incorrect")
    target_ms = max(8000, int(r.gauss(mean_s, mean_s * 0.25) * 1000))
    s.t = max(s.t + 500, start + target_ms)
    if status == "abandoned":
        s.click("task-giveup", PANEL, tag="button", action="giveup")
        s.ev("outcome", status="abandoned", satisfaction=None, dur=s.t - start)
        return
    s.click("task-submit", PANEL, tag="button", action="submit")
    # over-trust: wrong answers on the misleading axis (v1 T2) are often rated satisfying
    if status == "correct":
        sat = r.choice([3, 4, 4, 5, 5])
    else:
        sat = r.choice([4, 4, 5, 3]) if (s.v == 1 and scen["id"] == "T2" and r.random() < 0.6) else r.choice([1, 2, 2, 3])
    s.click(f"sat-{sat}", PANEL, tag="button")
    s.ev("outcome", status=status, satisfaction=sat, answer="sim", dur=s.t - start)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/sessions")
    ap.add_argument("--per-version", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = 1_790_000_000_000
    n_events = 0
    for v in (1, 2):
        for i in range(a.per_version):
            sid = f"sim-v{v}-{i:03d}"
            s = Session(rnd, sid, v, f"S{v}{i:03d}", t0 + rnd.randint(0, 86_400_000))
            s.ev("session_start", w=1280, h=800, dpr=2)
            for scen in SCEN:
                run_trial(s, scen)
            n_events += len(s.events)
            (out / f"{sid}.jsonl").write_text("\n".join(json.dumps(e) for e in s.events) + "\n")
    print(f"wrote {2 * a.per_version} sessions, {n_events} events -> {out}")


if __name__ == "__main__":
    main()
