# Demo script: Friction Atlas (4 minutes)

One story: **find where users struggle, have an AI designer propose fixes, a person signs off, and the re-test shows
whether it worked.** Everything runs on Databricks Free Edition.

## Before judging (Sunday morning checklist)
- [ ] **Redeploy the app** (Free Edition apps stop 24 h after deploy): Compute > Apps > your app > Deploy, from the Git
      folder (branch `feat/sdk-demo-dashboard`, path `databricks/app`).
- [ ] `<app-url>/status`: `sink` VolumeSink, `flush_errors` 0, `warehouse` true.
- [ ] `<app-url>/results` loads: chat goals, B1-B5 table, tasks, rage elements, both proposal sets with sign-off.
- [ ] SQL warehouse is running (open the SQL Editor once so it is warm; a cold start takes about a minute).
- [ ] Genie space open in a tab, benchmarks evaluation (10/10) open in another.
- [ ] Two browser tabs on the app: `?v=1` and `?v=2` (plain URL otherwise remembers your version).
- [ ] Catalog Explorer open on `workspace.ux_telemetry` (Volume `raw_events` + tables).

## Script

**0:00 - The problem (20 s).** "Dashboards and AI assistants fail people silently: a filter nobody finds, a chart that
exaggerates, an assistant that is confidently wrong. Analytics tells you *that* people leave, not *why*."

**0:20 - Capture (40 s).** Open the app on v1. Click the Avg fare card a few times (it looks clickable, does nothing).
Ask the assistant a percentage question: it answers confidently and wrong. "Our SDK records clicks, hovers, chart
interactions and assistant turns, never what you type unless you opt in." Show `/status`: events written to a Unity
Catalog Volume.

**1:00 - Raw to gold (40 s).** Catalog Explorer: Volume `raw_events` (raw JSONL), `bronze_events`, `silver_turns`,
`gold_bot_behavior`. "One SQL file rebuilds the medallion pipeline; every metric (rage clicks, over-trust,
reformulation, drop-off) is defined in the table comments. Human, simulated and agent data never mix."

**1:40 - Genie (40 s).** In the Genie space ask: *"Which bot behavior hurts most?"* It compares v1 with v2 per metric:
slow replies drive abandonment, confident wrong answers drive over-trust. "Before curation Genie invented a weighted
score; after adding instructions and example SQL it passes 10 of 10 benchmarks."

**2:20 - AI designer + sign-off (50 s).** `/results` > Design proposals. "Two designers drafted fixes from the gold
tables: Claude, and Databricks' own `ai_gen` running inside the pipeline. Every citation is checked in code: the number,
the n, and that the evidence comes from the right study. `ai_gen` had 3 of 6 rejected, for example citing a chart task's
duration as evidence that chat replies are slow. A UX developer then approves or rejects each change, with a reason."

**3:10 - Re-test (40 s).** `/results` agent rows: "We re-tested with bots that use the real dashboard in a browser with one
fixed strategy for both versions. Nothing about the outcome is scripted: the truncated axis makes the bot misread the
bars, the hidden filter makes it give up, the hidden chat icon is never found." Numbers (agent, 15 bots per version,
2026-11-15 run): **T2 success 0% -> 100%** (v1 bots read the truncated bars: every wrong answer rated satisfied),
**T4 abandoned 27% -> 0%** (142 dead clicks on the fake-clickable KPI in v1), **60% of v1 bots never found the chat
-> 0%**, **G1 success 0% -> 100%** (v1's confident wrong percent accepted every time). "Bots are not people: v2 is easy
for this strategy by construction, and n=15 bots is not a sample of anyone. Then the human sessions."

**3:50 - Close (10 s).** "Capture, Databricks medallion, Genie, AI designer with checks and sign-off, re-test. All on
Free Edition."

## Re-test caveats (say them if asked)
- The strategy is ours (salience-ordered exploration, a click budget, patience for replies). It is the same in both
  versions, so differences come from the designs, but a different strategy would give different numbers.
- Several bot bugs were found and fixed before the run (clipped bar heights, tooltip parsing, a re-send that gave up
  too early); the fixed run is the one reported.

## What not to say
- No statistical significance, no "users preferred". Simulated and agent results show the pipeline and the designs
  behave as expected, not what people do. One human session is an anecdote.
- No eye tracking. Cursor position is a rough proxy for attention at best.
- `ai_gen`'s model is chosen by Databricks: we do not know which model it is.
- The approved changes match our hand-built v2, so the re-test compares v1 with v2.
