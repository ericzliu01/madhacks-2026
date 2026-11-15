# Protocol: 3-5 real sessions with the chat assistant (goals mode)

Goal: a handful of real sessions next to the simulated ones. With n = 3-5 the results are **descriptive only**: report
counts, never significance. Cursor and chart events are not eye tracking and only loosely track attention.

## Before
- Redeploy the app (Free Edition apps stop 24 h after deploy). Check `<app-url>/status` shows `"sink": "VolumeSink"`.
- Each participant uses their own device and browser (the page remembers pid and version per browser: the version is
  randomly assigned 1 or 2 on first visit, so a mix of v1 and v2 is expected).
- Participants need to be able to sign in to the workspace (Databricks Apps require it).

## Consent (read aloud, about 30 s)
"This is a hackathon usability study of a demo dashboard. We record clicks, cursor movement, typing counts (not what you
type), and your answers. If you tick the box on the first screen, we also record the text of the questions you ask the
assistant; otherwise only their length and a one-way hash. No name or account is stored: you get a random id. The
assistant is a scripted bot that is sometimes wrong on purpose. You can stop at any time."

## During (about 10 minutes)
1. Open the plain app URL (no parameters). Click **Start**.
2. Work through the 5 goals. Don't help or hint; if asked, say "do what you would do at work".
3. Note anything surprising on paper (pid from `/status` is not shown; note the time instead).

## After
1. Ask 2 questions: "Did you trust the assistant's answers? Why?" and "Was anything hard to find?" (notes only).
2. Debrief: tell them the bot was wrong on purpose in some cases.
3. Run `databricks/sql/ux_pipeline_all.sql`, then check `/results`: human rows appear in their own sections.

## What not to claim
The planted behaviors (B1-B5) and the simulation encode our hypotheses. Simulated results show the pipeline recovers
what we planted. Human sessions are anecdotes at this n.
