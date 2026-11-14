# Databricks pipeline (raw telemetry -> research-ready tables -> Genie)

```
SDK / extension  ->  JSONL  ->  Volume (raw)  ->  bronze  ->  silver  ->  gold  ->  Genie space + App
                                                    COPY INTO   dedupe,     research     Q&A, dashboard,
                                                                trials      metrics      Claude proposals
```

| File | Layer | Where it runs |
|---|---|---|
| `sql/00_setup.sql` | schema + Volume | Databricks (untested) |
| `sql/01_bronze_ddl.sql` | bronze table, explicit schema | Databricks + local SQLite test |
| `sql/01b_bronze_load.sql` | `COPY INTO` from the Volume | Databricks only (untested) |
| `sql/02_silver.sql` | typed, de-duplicated events; reconstructed trials | Databricks + local test |
| `sql/03_gold.sql` | trial metrics, task summary, element friction, v1-v2 comparison | Databricks + local test |
| `sql/04_ai_prompt_intent.sql` | LLM labels for prompts (task x intent) + human-agreement check | Databricks only (untested) |
| `sql/05_comments.sql` | Unity Catalog comments with the research definitions | Databricks only (untested) |
| `genie/GENIE_SPACE.md` | how to curate the Genie space (instructions, example SQL, benchmarks) | manual in the UI |
| `tools/make_sessions.py` | simulated sessions for pipeline testing | local |
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
- Spark-only files have not been run: the sandbox has no workspace access, no Databricks CLI, and no PySpark.
  Expect small syntax fixes on first run.
- Silver assumes each task is attempted once per session.
