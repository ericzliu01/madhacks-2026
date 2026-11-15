# Live trial (demo console > Live trial)

A normal 3-goal study session (charts only) started from `<app-url>/demo`, with participant id `DEMO-…`.

## Who
Hand the laptop to someone who hasn't seen the answers (a judge or a visitor), not a team member: we know the answers,
so our own sessions would make the human results look better than they are.

## Say
1. "Answer three questions using only this dashboard. Take your time; giving up is fine."
2. Then don't help or point at anything while they work.

## After
1. The session is written to the Volume within a few seconds.
2. Rerun `ux_pipeline_all.sql` (or the console's Run pipeline): it appears under **human**, participant `DEMO-…`.
3. Not finished = not counted. All of G1, G2 and G3 need an answer or a give-up (same rule as P01-P06; partial sessions
   are dropped in silver).

## Timing and version
- Takes about 5 minutes: run it outside the 4-minute pitch, before or after.
- Default is **v3** (build-1): every human so far used v1, and only people on v3 can show whether the inline filter fixes
  G2. v1 is one click away in the console.
