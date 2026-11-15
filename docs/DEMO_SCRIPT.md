# Demo script: Friction Atlas (4 minutes)

One story: **find where users struggle, have an AI designer propose fixes, a person signs off, and the re-test shows
whether it worked.** Everything runs on Databricks Free Edition.

## Before judging (Sunday morning checklist)
- [ ] **Redeploy the app** (Free Edition apps stop 24 h after deploy): Compute > Apps > your app > Deploy, from the Git
      folder (branch `feat/sdk-demo-dashboard`, path `databricks/app`).
- [ ] `<app-url>/status`: `sink` VolumeSink, `flush_errors` 0, `warehouse` true.
- [ ] `<app-url>/results` loads: goals (human v1; agent v1 vs v3), rage elements, proposal sets incl. `ai-gen-loop1` with sign-off.
- [ ] SQL warehouse is running (open the SQL Editor once so it is warm; a cold start takes about a minute).
- [ ] Genie space open in a tab, benchmarks evaluation (10/10) open in another.
- [ ] Two browser tabs on the app: `?v=1` and `?v=3` (build-1). Plain URL otherwise remembers your version.
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

**2:20 - AI designer + sign-off (50 s).** `/results` > Design proposals, set `ai-gen-loop1`. "Six real people used v1
(P01-P06, 3 goals each). Databricks' `ai_gen`, running inside the pipeline, saw only their gold rows: no flaw list, no
v2. Every citation is checked in code: the number, the n, and that it comes from the right element or goal. One of six
drafted changes failed the check. Unprompted, it proposed **tooltips on the line chart** (v1 has none) and **an easier
borough filter** (G2: 0 of 6 people correct; five answered the all-borough fare). A UX developer approved those two and
rejected three, each with a reason: a bigger font on a card that only *looks* clickable doesn't fix it."

**3:10 - Re-test (40 s).** Open `?v=3` (build-1: v1 plus only the two approved changes; the truncated axis, look-alike
colors and fake-clickable card are still there). "Bots with one fixed strategy use the real dashboard in a browser,
same strategy for both builds. Nothing about the outcome is scripted." Numbers (agent, 15 bots per build, 2026-11-15):
**G3 (line chart) 2/15 -> 15/15 correct** (without tooltips the bots read values by eye and picked the wrong day);
**G1 0/15 -> 0/15** (bar-chart question; the truncated axis was not fixed, so no change is the expected result);
**G2 14/15 -> 15/15** (bots search menus until they find the filter, so they don't reproduce the human failure: the
G2 result needs people on v3). "Bots are not people, and n=15 bots is not a sample of anyone."

**3:50 - Close (10 s).** "Capture, Databricks medallion, Genie, AI designer with checks and sign-off, re-test. All on
Free Edition."

## Live trial (outside the 4 minutes)
Run everything from `<app-url>/demo`. **Live trial** starts a normal 3-goal session (v1 or v3) with participant id
`DEMO-...`. It counts as a **human** trial only if all three goals are finished (answered or given up); otherwise silver
drops it. Hand the laptop to someone who hasn't seen the answers, not a team member. Rerun `ux_pipeline_all.sql`
afterwards to see it in `/results`. Pitch-step clicks in the console (no goals) never reach the study tables.

## Re-test caveats (say them if asked)
- The strategy is ours (salience-ordered exploration, a click budget, patience for replies). It is the same in both
  versions, so differences come from the designs, but a different strategy would give different numbers.
- Several bot bugs were found and fixed before the run (clipped bar heights, tooltip parsing, a re-send that gave up
  too early, ticking a consent box that is hidden when the assistant is off); the fixed run is the one reported.

## What not to say
- No statistical significance, no "users preferred". Simulated and agent results show the pipeline and the designs
  behave as expected, not what people do. One human session is an anecdote.
- No eye tracking. Cursor position is a rough proxy for attention at best.
- `ai_gen`'s model is chosen by Databricks: we do not know which model it is.
- v2 is our hand-built fix of every planted flaw (used in earlier simulated runs). The loop's build is v3: only what the
  designer proposed and a person approved. Three planted flaws are still in v3 because no proposal addressed them.
- 6 people is an anecdote-scale sample. Don't call the human results a finding.
