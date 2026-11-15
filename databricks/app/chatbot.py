#!/usr/bin/env python3
"""Stub "Taxi Ops assistant" with planted, deterministic behaviors (stdlib only).

Deliberately NOT an LLM: the study needs ground truth about when the assistant is wrong. Every reply carries
`behavior` (which planted behavior fired, if any) and `correct` (whether the reply answers the question correctly).
Both are testbed ground truth, logged on the `assistant_response` event.

Planted behaviors: flawed in v1, fixed in v2 (mirroring the chart flaws F1-F4):
  B1  derived value (percent difference between two boroughs). v1 computes it from the bar heights above the v1
      chart's truncated axis floor (the F1 distortion) and states it confidently; v2 computes it from the totals and
      shows the working.
  B2  filter misparse. v1 ignores the borough the FIRST time a goal asks a borough-specific aggregate (average fare,
      total trips) and answers for all boroughs, so the user has to rephrase; v2 always applies the borough.
  B3  slow reply. Extremum questions take 7 s in v1 with no progress indicator; 1.5 s with an indicator in v2.
  B4  (retired in design revision 2: the assistant is open in both versions; in revision 1 the v1 entry point was a
      small unlabeled icon). Lived in the page, not here.
  B5  selection ignored. Asked "why" with a chart point selected, v1 ignores the selection and gives a generic
      weekend explanation; v2 explains the selected point.

Supported intents (keyword rules, checked in this order; first match wins):
  explain_point  why / what happened / explain / cause / reason, or unusual / anomaly / odd / weird / wrong / outlier /
                 stand out   (a borough + date named in the prompt, else the chart selection, else asks which point)
  pct_compare    two boroughs + percent / % / more than / exceed / compare / vs / difference / higher / bigger
  range          range / vary / variation / spread / minus / swing / "highest ... lowest" / "busiest ... quietest"
  extremum       lowest / fewest / least / min / quietest / highest / most / max / busiest / peak  (+ borough, metric)
  value_on_date  borough + a date (2026-03-24, March 24, 24 March, 3/24)
  avg_fare       fare / price / cost (+ optional borough)
  total_trips    total / how many / number of / count (+ optional borough)
  help           anything else
Metric is fare when the prompt says fare / price / cost / $, otherwise trips.

Prompt text received here is used to answer and is never stored or logged.
"""
import json
import re
import time
from datetime import date
from pathlib import Path

BOROUGHS = ["Manhattan", "Brooklyn", "Queens", "Bronx"]
STOPWORDS = set("""a an the of in on for to and or is are was were be been what which who how much many did do does
was me my i you your it its this that these those there their please can could would should tell show give find
get about with by from at as than then so any all""".split())
WHY = re.compile(r"\b(why|what happened|explain|cause|caused|reason)\b")
PCT = re.compile(r"(percent|%|more than|exceed|compare|\bvs\b|versus|difference|higher|bigger|larger|more trips)")
RANGE = re.compile(r"\b(range|vary|varied|variation|spread|minus|swing|swings)\b|highest.*lowest|lowest.*highest|"
                   r"busiest.*quietest|quietest.*busiest|max.*min")
EXT_MIN = re.compile(r"\b(lowest|fewest|least|minimum|min|quietest|slowest|worst)\b")
EXT_MAX = re.compile(r"\b(highest|most|maximum|max|busiest|peak|top|best)\b")
FARE = re.compile(r"(fare|price|cost|\$)")
TOTAL = re.compile(r"\b(total|how many|number of|count)\b")
ANOM = re.compile(r"(unusual|anomal|odd|weird|wrong|outlier|stand out|stands out)")
MONTHS = {"march": 3, "mar": 3}

LATENCY = {"default": 800, "B3": {1: 7000, 2: 1500}}  # ms the server waits before replying
OVERLAP_REFORMULATION = 0.6  # documented threshold used by the gold SQL (gold_turn_metrics.reformulated)


def tokens(text):
    """Content tokens: lowercase alphanumerics minus stopwords. Same rule as tokens() in the dashboard JS."""
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in STOPWORDS}


def overlap(a, b):
    """Overlap coefficient |A and B| / min(|A|, |B|) over content tokens (0 if either is empty)."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return round(len(ta & tb) / min(len(ta), len(tb)), 3)


def jaccard(a, b):
    """|A and B| / |A or B| over content tokens: how close a prompt is to a whole text (e.g. the goal, to spot a pasted
    goal). Unlike overlap(), a short prompt does not score high against a long text. Same rule as jaccard() in the JS."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return round(len(ta & tb) / len(ta | tb), 3)


def fmt_int(n):
    return f"{int(round(n)):,}"


class Bot:
    def __init__(self, data):
        self.dates = data["dates"]
        self.b = data["boroughs"]
        self.totals = {n: sum(v["trips"]) for n, v in self.b.items()}
        self.avg_fare = {n: sum(t * f for t, f in zip(v["trips"], v["fare"])) / sum(v["trips"]) for n, v in self.b.items()}
        all_trips = sum(self.totals.values())
        self.avg_fare_all = sum(self.avg_fare[n] * self.totals[n] for n in self.b) / all_trips
        wk = [i for i, d in enumerate(self.dates) if date.fromisoformat(d).weekday() >= 5]
        wd = [i for i in range(len(self.dates)) if i not in wk]
        day_tot = [sum(self.b[n]["trips"][i] for n in self.b) for i in range(len(self.dates))]
        self.weekend_dip = 1 - (sum(day_tot[i] for i in wk) / len(wk)) / (sum(day_tot[i] for i in wd) / len(wd))

    @classmethod
    def load(cls, static_dir):
        return cls(json.loads((Path(static_dir) / "data.json").read_text()))

    # ------------------------------------------------------------------ parsing
    def boroughs_in(self, p):
        found = [(p.find(n.lower()), n) for n in BOROUGHS if n.lower() in p]
        return [n for _, n in sorted(found)]

    def date_in(self, p):
        m = re.search(r"\b(2026)-(\d{2})-(\d{2})\b", p)
        if m:
            d = f"2026-{m.group(2)}-{m.group(3)}"
            return d if d in self.dates else None
        m = (re.search(r"\b(?:march|mar)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", p)
             or re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(?:march|mar)\b", p)
             or re.search(r"\b3/(\d{1,2})\b", p))
        if m:
            d = f"2026-03-{int(m.group(1)):02d}"
            return d if d in self.dates else None
        return None

    def ratio_to_usual(self, borough, i):
        t = self.b[borough]["trips"]
        weekend = lambda j: date.fromisoformat(self.dates[j]).weekday() >= 5
        peers = [t[j] for j in range(len(t)) if j != i and weekend(j) == weekend(i)]
        return t[i] / (sum(peers) / len(peers))

    # ------------------------------------------------------------------ main entry
    def respond(self, prompt, version, selection=None, prev_intents=()):
        """prompt: user text. version: 1 or 2. selection: {"series": borough, "x": "YYYY-MM-DD"} or None.
        prev_intents: intents of the earlier turns in the same goal (the B2 rule depends on them).
        Returns {text, answer_id, behavior, correct, value, intent, delay_ms, indicator}."""
        v = 2 if int(version) == 2 else 1
        p = " ".join((prompt or "").lower().split())
        bs, d = self.boroughs_in(p), self.date_in(p)
        metric = "fare" if FARE.search(p) else "trips"
        sel = selection if (selection and selection.get("series") in self.b and selection.get("x") in self.dates) else None

        if WHY.search(p) or ANOM.search(p):
            r = self._explain(v, p, bs, d, sel)
        elif len(bs) >= 2 and PCT.search(p):
            r = self._pct(v, bs[0], bs[1])
        elif RANGE.search(p):
            r = self._range(bs[0] if bs else None, metric)
        elif EXT_MIN.search(p) or EXT_MAX.search(p):
            r = self._extremum(v, bs[0] if bs else None, metric, "min" if EXT_MIN.search(p) else "max")
        elif bs and d:
            r = self._value_on(bs[0], d, metric)
        elif metric == "fare":
            r = self._aggregate(v, "avg_fare", bs[0] if bs else None, prev_intents)
        elif TOTAL.search(p) or bs:
            r = self._aggregate(v, "total_trips", bs[0] if bs else None, prev_intents)
        else:
            r = dict(intent="help", answer_id="help", behavior=None, correct=None, value=None,
                     text="I answer questions about March trips and fares by borough: totals, average fares, "
                          "percent differences, highest/lowest days, ranges, and why a selected point looks odd.")
        r["delay_ms"] = LATENCY["B3"][v] if r["behavior"] == "B3" else LATENCY["default"]
        r["indicator"] = v == 2
        r["selection_used"] = bool(sel) and r["intent"] == "explain_point" and v == 2
        return r

    # ------------------------------------------------------------------ intents
    def _pct(self, v, a, b):
        truth = (self.totals[a] / self.totals[b] - 1) * 100
        if v == 1:  # B1: bar heights above the truncated v1 axis floor (0.9 x smallest total), stated confidently
            floor = 0.9 * min(self.totals.values())
            val = ((self.totals[a] - floor) / (self.totals[b] - floor) - 1) * 100
            word = "more" if val >= 0 else "fewer"
            return dict(intent="pct_compare", answer_id=f"pct:{a}>{b}:axis", behavior="B1", value=f"{val:.1f}",
                        correct=abs(val - truth) <= 2.0,
                        text=f"{a} had {abs(val):.1f}% {word} trips than {b} in March.")
        word = "higher" if truth >= 0 else "lower"
        return dict(intent="pct_compare", answer_id=f"pct:{a}>{b}:exact", behavior="B1", value=f"{truth:.1f}", correct=True,
                    text=f"{a}: {fmt_int(self.totals[a])} trips; {b}: {fmt_int(self.totals[b])}. {a} is "
                         f"{abs(truth):.1f}% {word} ({fmt_int(self.totals[a])} / {fmt_int(self.totals[b])} - 1).")

    def _aggregate(self, v, intent, borough, prev_intents):
        ignored = v == 1 and borough is not None and not any(i in ("avg_fare", "total_trips") for i in prev_intents)
        behavior = "B2" if borough else None
        scope = None if ignored else borough
        if intent == "avg_fare":
            val = self.avg_fare[scope] if scope else self.avg_fare_all
            value = f"{val:.2f}"
            text = (f"The average fare for {scope} trips in March was ${val:.2f} (trip-weighted)." if scope
                    else f"The average fare in March was ${val:.2f}.")
        else:
            val = self.totals[scope] if scope else sum(self.totals.values())
            value = str(int(val))
            text = (f"{scope} had {fmt_int(val)} trips in March." if scope else f"There were {fmt_int(val)} trips in March.")
        return dict(intent=intent, answer_id=f"{intent}:{scope or 'all'}" + (":ignored_borough" if ignored else ""),
                    behavior=behavior, value=value, correct=not ignored, text=text)

    def _extremum(self, v, borough, metric, kind):
        if not borough:
            return dict(intent="extremum", answer_id="need_borough", behavior=None, correct=None, value=None,
                        text="For which borough? Manhattan, Brooklyn, Queens or the Bronx.")
        series = self.b[borough][metric]
        i = (min if kind == "min" else max)(range(len(series)), key=lambda j: series[j])
        shown = f"${series[i]:.2f}" if metric == "fare" else f"{fmt_int(series[i])} trips"
        word = {"min": {"trips": "fewest trips", "fare": "lowest average fare"},
                "max": {"trips": "most trips", "fare": "highest average fare"}}[kind][metric]
        return dict(intent="extremum", answer_id=f"ext:{kind}:{metric}:{borough}", behavior="B3", value=self.dates[i],
                    correct=True, text=f"{borough} had its {word} on {self.dates[i]} ({shown}).")

    def _range(self, borough, metric):
        if not borough:
            return dict(intent="range", answer_id="need_borough", behavior=None, correct=None, value=None,
                        text="For which borough? Manhattan, Brooklyn, Queens or the Bronx.")
        s = self.b[borough][metric]
        hi, lo = max(s), min(s)
        if metric == "fare":
            return dict(intent="range", answer_id=f"range:fare:{borough}", behavior=None, correct=True, value=f"{hi - lo:.2f}",
                        text=f"{borough}'s daily average fare ranged from ${lo:.2f} to ${hi:.2f}: a range of ${hi - lo:.2f}.")
        return dict(intent="range", answer_id=f"range:trips:{borough}", behavior=None, correct=True, value=str(hi - lo),
                    text=f"{borough}'s daily trips ranged from {fmt_int(lo)} to {fmt_int(hi)}: a range of {fmt_int(hi - lo)}.")

    def _value_on(self, borough, d, metric):
        i = self.dates.index(d)
        val = self.b[borough][metric][i]
        shown = f"${val:.2f}" if metric == "fare" else f"{fmt_int(val)} trips"
        return dict(intent="value_on_date", answer_id=f"value:{metric}:{borough}:{d}", behavior=None, correct=True,
                    value=f"{val:.2f}" if metric == "fare" else str(val), text=f"{borough} on {d}: {shown}.")

    def _explain(self, v, p, bs, d, sel):
        if bs and d:  # a borough and date named in the prompt win over any selection, in both versions
            sel = None
        if sel and v == 1:  # B5: the selected point is ignored
            return dict(intent="explain_point", answer_id="why:generic_weekend", behavior="B5", correct=False, value=None,
                        text=f"Trips are usually lower on weekends: weekend days average {self.weekend_dip * 100:.0f}% "
                             f"fewer trips than weekdays across all boroughs.")
        if bs and d:
            borough, day, behavior = bs[0], d, None
        elif sel:
            borough, day, behavior = sel["series"], sel["x"], "B5"
        elif v == 1:
            return dict(intent="explain_point", answer_id="why:generic_weekend", behavior=None, correct=None, value=None,
                        text=f"Trips are usually lower on weekends: weekend days average {self.weekend_dip * 100:.0f}% "
                             f"fewer trips than weekdays across all boroughs.")
        else:
            return dict(intent="explain_point", answer_id="need_selection", behavior=None, correct=None, value=None,
                        text="Which point? Click a point on the Daily trips chart, or name a borough and a date.")
        i = self.dates.index(day)
        t = self.b[borough]["trips"][i]
        r = self.ratio_to_usual(borough, i)
        kind = "weekend" if date.fromisoformat(day).weekday() >= 5 else "weekday"
        if r < 0.6:
            text = (f"{borough} on {day} had {fmt_int(t)} trips, {(1 - r) * 100:.0f}% below its usual {kind} level. "
                    f"Nothing else in the data explains it (other boroughs were normal that day), so it looks like a "
                    f"data gap or an outage worth checking with the source team.")
        else:
            text = (f"{borough} on {day} had {fmt_int(t)} trips, within {abs(1 - r) * 100:.0f}% of its usual {kind} "
                    f"level: not unusual.")
        return dict(intent="explain_point", answer_id=f"why:{borough}:{day}", behavior=behavior, correct=True,
                    value=day, text=text)


def chat_reply(bot, req, latency_scale=1.0, sleep=time.sleep):
    """Handle one POST /chat body: {prompt, v, selection?, prev_intents?}. Waits the planted latency (scaled; tests use
    a small scale), then returns the reply. The prompt is not stored or logged here."""
    if not isinstance(req, dict):
        raise ValueError("expected a JSON object")
    sel = req.get("selection")
    prev = req.get("prev_intents") or []
    r = bot.respond(str(req.get("prompt") or "")[:500], 2 if str(req.get("v")) == "2" else 1,
                    sel if isinstance(sel, dict) else None, [str(i) for i in prev][:50] if isinstance(prev, list) else [])
    sleep(r["delay_ms"] / 1000 * max(0.0, float(latency_scale)))
    return r


if __name__ == "__main__":  # quick manual check: python3 chatbot.py "why did this drop?" 1 Bronx 2026-03-24
    import sys
    bot = Bot.load(Path(__file__).parent / "static")
    sel = {"series": sys.argv[3], "x": sys.argv[4]} if len(sys.argv) > 4 else None
    print(json.dumps(bot.respond(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1, sel), indent=1))
