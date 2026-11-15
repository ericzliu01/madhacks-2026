# Databricks pipeline (raw telemetry -> research-ready tables -> Genie)

```
SDK / extension  ->  JSONL  ->  Volume (raw)  ->  bronze  ->  silver  ->  gold  ->  Genie space + App
                                                    COPY INTO   dedupe,     research     Q&A, dashboard,
                                                                trials      metrics      Claude proposals
```

| File | Layer | Where it runs |
|---|---|---|
| `sql/00_setup.sql` | schema + Volume | Databricks (ran OK on Free Edition) |
| `sql/01_bronze_ddl.sql` | bronze table, explicit schema | Databricks (ran OK) + local SQLite test |
| `sql/01b_bronze_load.sql` | `COPY INTO` from the Volume (explicit columns, DOUBLE casts) | Databricks only (ran OK, 4087 rows) |
| `sql/02_silver.sql` | typed, de-duplicated events; reconstructed trials | Databricks (ran OK) + local test |
| `sql/03_gold.sql` | trial metrics, task summary, element friction, v1-v2 comparison | Databricks (ran OK) + local test |
| `sql/04_ai_prompt_intent.sql` | LLM labels for prompts (task x intent) + human-agreement check | Databricks only (untested) |
| `sql/05_comments.sql` | Unity Catalog comments with the research definitions | Databricks only (untested) |
| `genie/GENIE_SPACE.md` | how to curate the Genie space (instructions, example SQL, benchmarks) | manual in the UI |
| `tools/make_sessions.py` | simulated sessions for pipeline testing | local |
| `designer/propose.py` | Claude drafts design changes from the gold tables; every citation is checked; a UX developer approves (`review`) | local + Claude API |
| `tests/run_sql_local.py` | runs 01-03 in SQLite and asserts the planted flaws are recovered | local |

## Run locally (no workspace needed)
```bash
python3 databricks/tests/run_sql_local.py
```

## Run on Databricks
1. Pick a catalog you own (not `system`; on Free Edition typically `workspace`), a schema (`ux_telemetry`), and a volume name.
   Find/replace `${catalog}`, `${schema}`, `${volume}` in `sql/*.sql` or set them as widgets/parameters.
2. Run `00_setup.sql`, then upload JSONL files into `/Volumes/<catalog>/<schema>/<volume>/raw/` (Catalog UI -> Upload to this volume).
   Real data comes from the collector (`demo/dashboard/events.jsonl`) or the extension's export. For a dry run:
   `python3 databricks/tools/make_sessions.py --out databricks/data/sessions` and upload those files.
3. Run `01_bronze_ddl.sql`, `01b_bronze_load.sql`, `02_silver.sql`, `03_gold.sql`, `05_comments.sql` in order.
4. Create the Genie space following `genie/GENIE_SPACE.md`.

## Honest limits
- The local test uses **simulated** sessions whose behavior encodes our hypotheses about the planted flaws. It proves the
  pipeline can recover what was planted. It says nothing about real users.
- 00-03 and 05 were run on a Free Edition workspace with the simulated sessions (bronze 4087, silver trials 300; v1 vs v2
  matched the local run). That run was reported to us, not performed by us: the sandbox has no workspace access.
  Fix needed on first run: `COPY INTO` failed with DELTA_FAILED_TO_MERGE_FIELDS because JSON inference types whole numbers as
  BIGINT, so 01b casts the DOUBLE columns explicitly. `04` (AI functions) has not been run.
- Silver assumes each task is attempted once per session.
