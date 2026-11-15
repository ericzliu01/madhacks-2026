#!/usr/bin/env python3
"""Generate the synthetic taxi dataset and the scenario file (with ground-truth answers).

Deterministic (seeded). Outputs, relative to demo/dashboard/static/:
  data.json       daily trips and average fare per borough for 30 days
  scenarios.json  chart-reading tasks (mode=tasks) tagged with an Amar/Eagan/Stasko category and a known answer
  goals.json      goals for the chat-assistant study (mode=goals), each tagged with the Amar categories it is expected
                  to exercise, the planted bot behavior it exposes, and a ground-truth answer computed here

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

# Hidden anomaly for the exploration goal (G4): one Bronx weekday collapses to a quarter of its usual level.
# The Bronx line is the lowest and, in v1, the lowest-contrast series, so this is easy to miss without filtering.
BRONX_ANOMALY_I = 23
b = data["boroughs"]["Bronx"]["trips"]
b[BRONX_ANOMALY_I] = int(round(b[BRONX_ANOMALY_I] * 0.25))


def is_weekend(i):
    return (START + timedelta(days=i)).weekday() >= 5


def ratio_to_usual(name, i):
    """Trips on day i divided by the mean of the same borough's other days of the same kind (weekday/weekend)."""
    t = data["boroughs"][name]["trips"]
    peers = [t[j] for j in range(DAYS) if j != i and is_weekend(j) == is_weekend(i)]
    return t[i] / (sum(peers) / len(peers))


bronx_ratios = sorted((ratio_to_usual("Bronx", i), i) for i in range(DAYS))
anomaly_ratio, anomaly_i = bronx_ratios[0]
assert anomaly_i == BRONX_ANOMALY_I and bronx_ratios[1][0] - anomaly_ratio > 0.4, bronx_ratios[:3]  # unambiguous

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

# Goals for the chat study: a goal is a work situation, not a ready-made question, so a participant has to decide what to
# ask (pasting it into the assistant still works and is detected: see gold_turn_metrics.pasted_goal). `answer_format`
# is shown on its own line. `behavior` names the planted
# assistant behavior the goal is designed to expose (see demo/dashboard/chatbot.py); G5 is a control with none.
# B4 (hard-to-find chat entry point) affects every goal, so it is not tied to one.
q_min_date = dates[min(range(DAYS), key=lambda i: q[i])]
assert q_min_date == dates[q_min_i]
goals = [
    {
        "id": "G1", "categories": ["compute_derived_value", "retrieve_value"], "behavior": "B1",
        "prompt": "Brooklyn had more trips than Queens in March. How many percent more? "
                  "(Brooklyn's total divided by Queens' total, minus 1.)",
        "answer_format": "a percentage, e.g. 12.5 (within 2 points counts as correct)",
        "answer": pct_gap, "tolerance": 2.0, "type": "number",
    },
    {
        "id": "G2", "categories": ["filter", "compute_derived_value"], "behavior": "B2",
        "prompt": "What was the average fare for trips in the Bronx in March?",
        "answer_format": "dollars and cents, e.g. 18.40 (within 5 cents counts as correct)",
        "answer": avg_fare["Bronx"], "tolerance": 0.05, "type": "number",
    },
    {
        "id": "G3", "categories": ["find_extremum", "filter"], "behavior": "B3",
        "prompt": "On which day in March did Queens have the fewest trips?",
        "answer_format": "a date written as YYYY-MM-DD",
        "answer": q_min_date, "tolerance": 0, "type": "date",
    },
    {
        "id": "G4", "categories": ["find_anomalies", "filter", "retrieve_value"], "behavior": "B5",
        "prompt": "On one day in March, the Bronx had unusually few trips: far fewer than on any other day. Which day was it?",
        "answer_format": "a date written as YYYY-MM-DD",
        "answer": dates[anomaly_i], "tolerance": 0, "type": "date",
        "detail": {"borough": "Bronx", "trips": b[anomaly_i], "ratio_to_usual": round(anomaly_ratio, 3)},
    },
    {
        "id": "G5", "categories": ["determine_range"], "behavior": None,
        "prompt": "In Manhattan, how many more trips were there on its busiest day in March than on its quietest day?",
        "answer_format": "a whole number of trips (within 150 counts as correct)",
        "answer": max(manhattan) - min(manhattan), "tolerance": 150, "type": "number",
    },
]

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "data.json").write_text(json.dumps(data))
(OUT / "scenarios.json").write_text(json.dumps(scenarios, indent=1))
(OUT / "goals.json").write_text(json.dumps(goals, indent=1))
print("totals", totals, "| brooklyn vs queens gap %", pct_gap)
print("avg fare", avg_fare)
for s in scenarios + goals:
    print(s["id"], s.get("category") or "+".join(s["categories"]), "->", s["answer"])
print("Bronx anomaly", dates[anomaly_i], b[anomaly_i], "trips, ratio to usual", round(anomaly_ratio, 3),
      "| next lowest ratio", round(bronx_ratios[1][0], 3))
