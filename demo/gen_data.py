#!/usr/bin/env python3
"""Generate the synthetic taxi dataset and the scenario file (with ground-truth answers).

Deterministic (seeded). Outputs, relative to demo/dashboard/static/:
  data.json       daily trips and average fare per borough for 30 days
  scenarios.json  chart-reading tasks tagged with an Amar/Eagan/Stasko category and a known answer

Brooklyn and Queens totals are deliberately close, so a truncated bar-chart axis (planted flaw F1)
makes the gap look much bigger than it is.
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).parent / "dashboard" / "static"
random.seed(2026)

START = date(2026, 3, 1)
DAYS = 30
BOROUGHS = {
    # name: (base daily trips, base fare)
    "Manhattan": (5200, 16.8),
    "Brooklyn": (2600, 19.4),
    "Queens": (2450, 24.1),
    "Bronx": (900, 21.7),
}

dates = [(START + timedelta(days=i)).isoformat() for i in range(DAYS)]
data = {"dates": dates, "boroughs": {}}
for name, (base, fare) in BOROUGHS.items():
    trips, fares = [], []
    for i in range(DAYS):
        weekend = (START + timedelta(days=i)).weekday() >= 5
        t = base * (0.82 if weekend else 1.0) * random.uniform(0.9, 1.1)
        trips.append(int(round(t)))
        fares.append(round(fare * random.uniform(0.96, 1.04), 2))
    data["boroughs"][name] = {"trips": trips, "fare": fares}

# Force one clear minimum for Queens on a known date (task T3 needs an unambiguous answer).
q = data["boroughs"]["Queens"]["trips"]
q_min_i = 17
q[q_min_i] = int(min(q) * 0.7)

totals = {n: sum(v["trips"]) for n, v in data["boroughs"].items()}
avg_fare = {
    n: round(sum(t * f for t, f in zip(v["trips"], v["fare"])) / sum(v["trips"]), 2)
    for n, v in data["boroughs"].items()
}
manhattan = data["boroughs"]["Manhattan"]["trips"]
brooklyn_day = data["boroughs"]["Brooklyn"]["trips"][14]
pct_gap = round((totals["Brooklyn"] / totals["Queens"] - 1) * 100, 1)

scenarios = [
    {
        "id": "T1", "category": "retrieve_value",
        "prompt": f"How many trips were taken in Brooklyn on {dates[14]}?",
        "answer": brooklyn_day, "tolerance": 0, "type": "number",
    },
    {
        "id": "T2", "category": "compute_derived_value",
        "prompt": "Roughly what percentage higher are Brooklyn's total trips than Queens' total trips? (number, in %)",
        "answer": pct_gap, "tolerance": 2.0, "type": "number",
    },
    {
        "id": "T3", "category": "find_extremum",
        "prompt": "On which date did Queens have its lowest daily trips? (YYYY-MM-DD)",
        "answer": dates[q_min_i], "tolerance": 0, "type": "text",
    },
    {
        "id": "T4", "category": "filter",
        "prompt": "Filter the dashboard to the Bronx only. What is the Avg fare shown in the KPI card? (number)",
        "answer": avg_fare["Bronx"], "tolerance": 0.05, "type": "number",
    },
    {
        "id": "T5", "category": "determine_range",
        "prompt": "What is the range (max minus min) of Manhattan's daily trips over the month? (number)",
        "answer": max(manhattan) - min(manhattan), "tolerance": 150, "type": "number",
    },
]

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "data.json").write_text(json.dumps(data))
(OUT / "scenarios.json").write_text(json.dumps(scenarios, indent=1))
print("totals", totals, "| brooklyn vs queens gap %", pct_gap)
print("avg fare", avg_fare)
for s in scenarios:
    print(s["id"], s["category"], "->", s["answer"])
