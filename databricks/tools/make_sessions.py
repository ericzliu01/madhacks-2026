#!/usr/bin/env python3
"""Generate SIMULATED study sessions as JSONL in the SDK's event schema.

Purpose: exercise the Databricks pipeline (bronze -> silver -> gold) before real participants exist, and test
that planted UX flaws (see demo/README.md) are recoverable from the gold tables.

IMPORTANT: the behavior probabilities below encode our hypotheses about the flaws, so this data can only show that
the pipeline *detects what we planted*. It is not evidence about real users. Every event has st='simulated'.

Two kinds of sessions:
  task sessions (mode=tasks)   scripted chart-reading tasks T1-T5, planted chart flaws F1-F4
  chat sessions (mode=goals)   goals G1-G5 worked on with the stub assistant, planted assistant behaviors B1-B5.
                               Assistant replies come from the real stub (demo/dashboard/chatbot.py), so behavior and
                               correctness are the stub's ground truth; only the participant's choices are simulated.

Usage: python3 make_sessions.py --out data/sessions --per-version 30 --chat-per-version 30 --seed 7
"""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "demo/dashboard/static"
SCEN = json.loads((STATIC / "scenarios.json").read_text())
GOALS = json.loads((STATIC / "goals.json").read_text())
sys.path.insert(0, str(ROOT / "demo/dashboard"))
import chatbot  # noqa: E402
BOT = chatbot.Bot.load(STATIC)

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


# ------------------------------------------------------------------------------------------- chat sessions (goals)
# Participant choices per version. These numbers ARE the hypotheses: the pipeline should recover them, nothing more.
CHAT = {
    1: {"never_find_chat": 0.15, "find_chat_s": 40, "verify": 0.35, "notice_b1": 0.5, "notice_b2": 0.75,
        "resend_b3": 0.45, "abandon_b3": 0.25, "find_anomaly": 0.55, "repair_b5": 0.6},
    2: {"never_find_chat": 0.0, "find_chat_s": 0, "verify": 0.2, "notice_b1": 0.0, "notice_b2": 0.0,
        "resend_b3": 0.05, "abandon_b3": 0.03, "find_anomaly": 0.8, "repair_b5": 0.6},
}
ASK = {
    "G1": ["By what percentage did Brooklyn have more trips than Queens?", "how much more trips brooklyn vs queens in percent",
           "Compare Brooklyn and Queens total trips, % difference"],
    "G2": ["What was the average fare in the Bronx?", "avg fare bronx march", "What is the Bronx average fare?"],
    "G3": ["Which day did Queens have the fewest trips?", "lowest trips day for Queens", "When was Queens quietest?"],
    "G5": ["How much did Manhattan's daily trips vary, highest minus lowest?", "range of Manhattan daily trips",
           "Manhattan trips max minus min per day"],
}
REPHRASE = {"G2": ["average fare for Bronx trips only", "Bronx only: what was the average fare?", "avg fare in the Bronx borough only"]}
WHY = ["Why did this drop?", "why is this so low?", "what happened here?"]


class ChatSession(Session):
    def __init__(self, rnd, sid, version, pid, t0):
        super().__init__(rnd, sid, version, pid, t0)
        self.goal, self.gcats, self.turn, self.prev_text, self.prev_intents = None, None, None, None, []
        self.answers = []  # (turn, value, correct, answer_id) of the current goal

    def ev(self, type, gap=(80, 900), **kw):
        e = super().ev(type, gap, **kw)
        e.update({k: v for k, v in (("goal", self.goal), ("gcats", self.gcats), ("turn", self.turn)) if k not in kw})
        return e

    def ask(self, text, sel=None):
        """prompt_submit + assistant_response (via the real stub). Returns the reply."""
        r = self.r
        e = self.ev("prompt_submit", gap=(2000, 9000), how=r.choice(["enter", "click"]), chars=len(text),
                    words=len(text.split()), hash=hashlib.sha256(("taxi-ops-demo:" + text).encode()).hexdigest()[:16],
                    text=text, overlap=chatbot.overlap(text, self.prev_text) if self.prev_text else None, sel=bool(sel))
        turn, t_prompt = self.turn, e["t"]
        self.prev_text = text
        self.turn += 1
        rep = BOT.respond(text, self.v, sel, self.prev_intents)
        self.prev_intents.append(rep["intent"])
        latency = rep["delay_ms"] + r.randint(60, 400)
        rep["turn"], rep["t_reply"] = turn, t_prompt + latency
        self.pending = (rep, sel, latency)
        return rep

    def reply(self):
        """Emit the assistant_response for the last ask (call after any events that happen while waiting)."""
        rep, sel, latency = self.pending
        self.t = max(self.t, rep["t_reply"])
        self.ev("assistant_response", gap=(1, 5), turn=rep["turn"], latency_ms=latency, behavior=rep["behavior"],
                answer_id=rep["answer_id"], correct=rep["correct"], intent=rep["intent"],
                answer=None if rep["value"] is None else str(rep["value"]),
                mark_x=sel["x"] if sel else None, series=sel["series"] if sel else None)
        self.answers.append(rep)
        return rep

    def maybe_verify(self, p):
        if self.r.random() < p:
            self.ev("chart_hover", gap=(800, 6000), chart=self.r.choice(["bar-total-trips", "line-daily-trips"]),
                    series=self.r.choice(chatbot.BOROUGHS), dur=self.r.randint(300, 1500))
            return True
        return False

    def accept(self, rep):
        self.ev("answer_feedback", gap=(1500, 5000), turn=rep["turn"], feedback="accept", answer_id=rep["answer_id"])

    def finish(self, g, answer, turn=None, sat=None, abandoned=False):
        start = self.goal_start
        if abandoned:
            self.ev("goal_outcome", gap=(3000, 15000), status="abandoned", satisfaction=None, turn=None, dur=self.t - start)
            return
        ok = (abs(float(answer) - g["answer"]) <= g["tolerance"]) if g["type"] == "number" else answer == g["answer"]
        if sat is None:
            sat = self.r.choice([3, 4, 4, 5]) if ok else self.r.choice([1, 2, 2, 3])
        self.ev("goal_outcome", gap=(2000, 8000), status="correct" if ok else "incorrect", satisfaction=sat,
                answer=str(answer), turn=turn, dur=self.t - start)


def run_goal(s, g, chat_open_at):
    r, P = s.r, CHAT[s.v]
    s.goal, s.gcats, s.turn, s.prev_text, s.prev_intents, s.answers = g["id"], "|".join(g["categories"]), 1, None, [], []
    s.ev("goal_start", gap=(1500, 4000), prompt=g["prompt"][:200])
    s.goal_start = s.t
    for _ in range(r.randint(2, 5)):
        s.ev("mouse_move", x=r.randint(20, 1250), y=r.randint(20, 760), v=r.randint(80, 900))
    if chat_open_at is None or chat_open_at > s.t + 60000:  # no assistant for this goal: read the charts
        for _ in range(r.randint(2, 6)):
            s.ev("chart_hover", chart="line-daily-trips", series=r.choice(chatbot.BOROUGHS), dur=r.randint(200, 1500))
        s.t += r.randint(30000, 90000)
        if r.random() < 0.35:
            return s.finish(g, None, abandoned=True)
        wrong = round(g["answer"] * 1.4, 2) if g["type"] == "number" else "2026-03-10"
        return s.finish(g, g["answer"] if r.random() < 0.5 else wrong)
    if chat_open_at > s.t:
        s.t = chat_open_at
        s.ev("chat_open", gap=(0, 0), how="click", turn=None)

    gid = g["id"]
    if gid == "G1":  # B1: confident wrong percent in v1
        rep = s.ask(r.choice(ASK[gid])); s.reply()
        verified = s.maybe_verify(P["verify"])
        if rep["correct"] is False and verified and r.random() < P["notice_b1"]:
            return s.finish(g, g["answer"], sat=r.choice([3, 4]))  # checked the chart, noticed, computed it
        if r.random() < 0.05:
            return s.finish(g, None, abandoned=True)
        s.accept(rep)
        sat = r.choice([4, 5, 5, 4, 3]) if rep["correct"] is False and r.random() < 0.7 else None
        return s.finish(g, rep["value"], turn=rep["turn"], sat=sat)
    if gid == "G2":  # B2: borough ignored the first time in v1
        rep = s.ask(r.choice(ASK[gid])); s.reply()
        s.maybe_verify(P["verify"])
        if rep["correct"] is False:
            if r.random() < P["notice_b2"]:
                s.t += r.randint(3000, 20000)
                rep = s.ask(r.choice(REPHRASE[gid])); s.reply()
            elif r.random() < 0.4:
                return s.finish(g, None, abandoned=True)
        s.accept(rep)
        sat = r.choice([4, 5, 3]) if rep["correct"] is False else None
        return s.finish(g, rep["value"], turn=rep["turn"], sat=sat)
    if gid == "G3":  # B3: slow, no indicator in v1
        q = r.choice(ASK[gid])
        s.ask(q)
        replies = [s.pending]
        if r.random() < P["resend_b3"]:  # impatient re-send while waiting (same words: overlap 1.0)
            s.t += r.randint(2500, 5000)
            s.ask(q)
            replies.append(s.pending)
        if r.random() < P["abandon_b3"]:  # gives up while waiting; the late reply still arrives afterwards
            s.t += r.randint(1000, 3000)
            s.finish(g, None, abandoned=True)
            for p_ in replies:
                s.pending = p_; s.reply()
            return None
        for p_ in replies:
            s.pending = p_; rep = s.reply()
        s.maybe_verify(P["verify"])
        s.accept(rep)
        return s.finish(g, rep["value"], turn=rep["turn"])
    if gid == "G4":  # B5: selection ignored in v1
        for _ in range(r.randint(2, 6)):
            s.ev("chart_hover", chart="line-daily-trips", series=r.choice(chatbot.BOROUGHS), dur=r.randint(200, 1500))
        if s.v == 1 and r.random() < 0.7:
            s.click("menu-more", "div:toolbar", tag="button", label="More options")
        s.ev("custom", name="filter_change", series="Bronx")
        if r.random() >= P["find_anomaly"]:
            if r.random() < 0.5:
                return s.finish(g, None, abandoned=True)
            return s.finish(g, r.choice(["2026-03-14", "2026-03-18", "2026-03-08"]))
        sel = {"series": "Bronx", "x": g["answer"]}
        s.ev("chart_click", chart="line-daily-trips", series="Bronx")
        s.ev("selection", chart="line-daily-trips", series="Bronx", mark_x=g["answer"], mark_y=g["detail"]["trips"])
        rep = s.ask(r.choice(WHY), sel=sel); s.reply()
        if rep["correct"] is False:
            if r.random() < P["repair_b5"]:
                s.t += r.randint(3000, 15000)
                rep = s.ask("why is the Bronx so low on March 24?", sel=sel); s.reply()
            elif r.random() < 0.7:  # found the point themselves: answer with its date without the assistant
                return s.finish(g, g["answer"])
            else:
                return s.finish(g, None, abandoned=True)
        s.accept(rep)
        return s.finish(g, rep["value"], turn=rep["turn"])
    # G5 control: no planted behavior, identical in both versions
    rep = s.ask(r.choice(ASK["G5"])); s.reply()
    s.maybe_verify(0.25)
    if r.random() < 0.06:
        return s.finish(g, None, abandoned=True)
    s.accept(rep)
    return s.finish(g, rep["value"], turn=rep["turn"])


def make_chat_session(rnd, sid, v, pid, t0):
    s = ChatSession(rnd, sid, v, pid, t0)
    s.ev("session_start", w=1280, h=800, dpr=2)
    s.ev("consent", state="prompt_text")
    P = CHAT[v]
    if v == 2:
        s.ev("chat_open", how="auto")
        open_at = s.t
    else:
        open_at = None if rnd.random() < P["never_find_chat"] else s.t + int(rnd.expovariate(1 / (P["find_chat_s"] * 1000)))
    for g in GOALS:
        run_goal(s, g, open_at)
        if open_at is not None and open_at <= s.t:
            open_at = min(open_at, s.t)  # once open it stays open
    s.goal = s.gcats = s.turn = None
    s.ev("custom", name="study_done")
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/sessions")
    ap.add_argument("--per-version", type=int, default=30)
    ap.add_argument("--chat-per-version", type=int, default=30, help="simulated chat-assistant (goals) sessions")
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
    crnd = random.Random(a.seed + 1)  # separate stream: adding chat sessions must not change the task sessions
    n_chat = 0
    for v in (1, 2):
        for i in range(a.chat_per_version):
            sid = f"simchat-v{v}-{i:03d}"
            s = make_chat_session(crnd, sid, v, f"C{v}{i:03d}", t0 + crnd.randint(0, 86_400_000))
            n_chat += len(s.events)
            (out / f"{sid}.jsonl").write_text("\n".join(json.dumps(e) for e in s.events) + "\n")
    print(f"wrote {2 * a.per_version} task sessions ({n_events} events) and {2 * a.chat_per_version} chat sessions "
          f"({n_chat} events) -> {out}")


if __name__ == "__main__":
    main()
