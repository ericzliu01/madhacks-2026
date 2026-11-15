# Demo script: Friction Atlas (4 minutes)

One story: **find where users struggle, have an AI designer propose fixes, a person signs off, and the re-test shows
whether it worked.** Everything runs on Databricks Free Edition.

## Before judging (Sunday morning checklist)
- [ ] **Redeploy the app** (Free Edition apps stop 24 h after deploy): Compute > Apps > your app > Deploy, from the Git
      folder (branch `feat/sdk-demo-dashboard`, path `databricks/app`).
- [ ] `<app-url>/status`: `sink` VolumeSink, `flush_errors` 0, `warehouse` true.
- [ ] `<app-url>/results` loads: human goals (P01-P06), rage elements, proposal sets incl. `ai-gen-loop1` with sign-off.
- [ ] SQL warehouse is running (open the SQL Editor once so it is warm; a cold start takes about a minute).
- [ ] Genie space open in a tab, benchmarks evaluation (10/10) open in another.
- [ ] Two browser tabs on the app: `?v=1` and `?v=3` (build-1). Plain URL otherwise remembers your version.
- [ ] Catalog Explorer open on `workspace.ux_telemetry` (Volume `raw_events` + tables).

## Script

**0:00 - The problem (20 s).** "Dashboards and AI assistants fail people silently: a filter nobody finds, a chart that
exaggerates, an assistant that is confidently wrong. Analytics tells you *that* people leave, not *why*."

**0:20 - Capture (40 s).** Console, v1. Hover the line chart (no tooltip), click the Avg fare card a few times (looks
clickable, does nothing), open the "..." menu (the borough filter hides there). "Our SDK records clicks, hovers and
chart interactions, never what you type." Show `/status`: events written to a Unity Catalog Volume.

**1:00 - Raw to gold (40 s).** Console > Run pipeline: Volume, bronze, silver, gold light up in turn on the SQL
warehouse. "Silver keeps only human trials: real people on this design who finished all three goals. Every metric is
defined in the table comments."

**1:40 - Genie (40 s).** Ask a question from the console list, e.g. *"Which element gets the most rage clicks in v1?"*
"Genie answers from the same gold tables. Before curation it invented a weighted score; instructions and example SQL
fixed that." (Rehearse: the 10/10 benchmark run was on the earlier mixed data, see Genie note below.)

**2:20 - AI designer + sign-off (50 s).** `/results` > Design proposals, set `ai-gen-loop1`. "Six real people used v1
(P01-P06, 3 goals each). Databricks' `ai_gen`, running inside the pipeline, saw only their gold rows: no flaw list, no
v2. Every citation is checked in code: the number, the n, and that it comes from the right element or goal. One of six
drafted changes failed the check. Unprompted, it proposed **tooltips on the line chart** (v1 has none) and **an easier
borough filter** (G2: 0 of 6 people correct; five answered the all-borough fare). A UX developer approved those two and
rejected three, each with a reason: a bigger font on a card that only *looks* clickable doesn't fix it."

**3:10 - Re-test (40 s).** Console: v1 | v3 side by side (build-1: v1 plus only the two approved changes; the
truncated axis, look-alike colors and fake-clickable card are still there). Hover the line in v3: tooltip. Point at the
inline filter. "The re-test is with people: after the pitch, try v3 yourself. A finished trial lands in the same
pipeline as P01-P06." All tables hold human trials only; no bot or simulated numbers are shown.

**3:50 - Close (10 s).** "Capture, Databricks medallion, Genie, AI designer with checks and sign-off, re-test. All on
Free Edition."

## Live trial (outside the 4 minutes)
Full instructions: `docs/LIVE_TRIAL.md`. Run everything from `<app-url>/demo`. **Live trial** starts a normal 3-goal session (v1 or v3) with participant id
`DEMO-...`. It counts as a **human** trial only if all three goals are finished (answered or given up); otherwise silver
drops it. Hand the laptop to someone who hasn't seen the answers, not a team member. Rerun `ux_pipeline_all.sql`
afterwards to see it in `/results`. Pitch-step clicks in the console (no goals) never reach the study tables.

## Bot re-test (not in the tables)
An earlier bot run (15 bots per build, real UI) is kept outside the tables, in `databricks/data/agent_run_b1/`: G3 went
2/15 -> 15/15 with line tooltips. Mention only if asked, and say it is bots, not people.

## What not to say
- No statistical significance, no "users preferred". Six people is an anecdote-scale sample.
- No eye tracking. Cursor position is a rough proxy for attention at best.
- `ai_gen`'s model is chosen by Databricks: we do not know which model it is.
- v2 is our hand-built fix of every planted flaw (used in earlier simulated runs). The loop's build is v3: only what the
  designer proposed and a person approved. Three planted flaws are still in v3 because no proposal addressed them.
- 6 people is an anecdote-scale sample. Don't call the human results a finding.
