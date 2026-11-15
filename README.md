# Friction Atlas

**Find where users struggle. Prove the fix worked.**

Friction Atlas records how people actually use a UI, turns the raw telemetry into research-grade metrics on Databricks,
finds the friction, proposes a concrete design change, and re-tests it through the same pipeline. Built for MadHacks 2026
(Best Use of Databricks).

```
capture  ->  land  ->  refine (bronze -> silver -> gold)  ->  serve and act  ->  sign-off  ->  re-test v2
SDK /        App +      typed, de-duplicated,                 Genie, /results,    UX developer   same pipeline
extension    Volume     research metrics                      Claude drafts       approves
```

## Where things are
| Path | What it is |
|---|---|
| `packages/core/` | the telemetry SDK (single source of truth) and Plotly adapter |
| `dbx-telemetry-ext/` | Chrome extension for UIs we do not own (consent-gated, privacy defaults) |
| `demo/` | "Taxi Ops" mock-company dashboard: v1 has planted flaws, v2 fixes them; Playwright e2e |
| `databricks/` | bronze/silver/gold SQL, the Databricks App (collector + `/results`), Genie space design |
| `docs/literature/` | signal-by-paper matrix grounding the metrics in HCI / visualization research |
| `docs/` | briefs for the follow-on sessions (build brief, chat-assistant study layer) |

## Run and test
```bash
python3 databricks/tests/run_sql_local.py        # bronze -> gold in SQLite, simulated data
./scripts/sync-core.sh --check                   # SDK copies match packages/core
python3 databricks/app/test/test_app.py          # App collector
python3 demo/gen_data.py && python3 demo/dashboard/app.py --port 8765    # try the dashboard locally
```
Details: `demo/README.md`, `dbx-telemetry-ext/README.md`, `databricks/README.md`, `databricks/app/README.md`.

## Honest status
- Bronze, silver and gold have run on a Databricks Free Edition workspace with **simulated** sessions. Simulated data encodes
  our hypotheses about the planted flaws: it shows the pipeline can recover them, not that they exist for real users.
  Every simulated row is labeled `simulated`, and human and simulated results are never averaged together.
- Not yet done or not yet verified live: real human sessions in gold, the Genie space, the Claude designer step, the chat-assistant
  study layer (spec in `docs/NEXT_SESSION_PROMPT_CHAT.md`).
- No claims of statistical significance (samples are small) or eye tracking (cursor position only loosely tracks attention).
