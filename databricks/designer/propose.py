#!/usr/bin/env python3
"""Claude as the designer: evidence from the gold tables -> concrete, cited UI change proposals -> UX developer sign-off.

  python3 propose.py evidence --source local                # simulated data via the local SQLite pipeline
  python3 propose.py evidence --source warehouse --warehouse-id <id>   # gold tables on Databricks (your CLI login)
  python3 propose.py evidence --source json --rows rows.json  # gold rows exported some other way, {table: [row, ...]}
  python3 propose.py draft [--dry-run]                      # one Claude API call; every citation is checked
  python3 propose.py draft --from-file d.json --name claude-session --designer "Claude (Claude Code session)"
  python3 propose.py draft --from-ai-gen row.json           # the row 08_ai_design_proposals.sql wrote (draft + evidence)
  python3 propose.py sql                                     # regenerate sql/08_ai_design_proposals.sql from the rules here
  python3 propose.py review P1 --set claude-api --approve --by "Name" --note "why"   # or --reject

Files (databricks/designer/out/): evidence.json (the pack Claude sees), draft-<timestamp>.json (raw model output).
Each designer writes its own proposal set, databricks/app/proposals/<name>.json; the App shows every set side by side.
Evidence ids are stable: table|session_type|key values (e.g. gold_bot_behavior|simulated|B1|v1), the same in SQL.

Guardrails, enforced in code, not just asked for in the prompt:
  * a change may cite only evidence rows in the pack; its value and n must match the row, and the session type is copied
    from the row (so simulated evidence is always labeled simulated)
  * a change must target a real dashboard element (data-ux-id) or a planted assistant behavior (B1-B5)
  * literature may be cited only from rows marked verified in docs/literature/signal_paper_matrix.csv
  * anything that fails a check goes to `rejected_by_validator` with the reason; nothing is silently dropped
  * every valid change starts as status "pending": only a UX developer's `review --approve` makes it eligible for the
    v1 -> proposed re-test
Claude credentials: the SDK's default chain (ANTHROPIC_API_KEY, or an `ant auth login` profile). Never paste keys here.
"""
import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "out"
PROPOSALS_DIR = ROOT / "databricks/app/proposals"
SQL_08 = ROOT / "databricks/sql/08_ai_design_proposals.sql"
INDEX_HTML = ROOT / "demo/dashboard/static/index.html"
LITERATURE = ROOT / "docs/literature/signal_paper_matrix.csv"
MODEL = "claude-opus-5-5"

# study chrome, not part of the product UI being redesigned
CHROME = re.compile(r"^(sat-\d|gsat-\d|task-|goal-|consent-)")
BEHAVIORS = {
    "B1": "derived values (percent difference) stated confidently but computed from the truncated v1 axis: wrong",
    "B2": "ignores the borough the first time a goal asks a borough-specific aggregate, answers for all boroughs",
    "B3": "slow reply (7 s) with no progress indicator",
    "B4": "chat entry point is a small, unlabeled, low-contrast icon",
    "B5": "ignores the chart point the user selected when asked why it looks odd",
}
FLAWS = {
    "F1": "bar chart y-axis truncated just below the smallest value (exaggerates differences)",
    "F2": "line chart uses four near-identical muted colors and a tiny pale legend",
    "F3": "borough filter only reachable through the '...' menu",
    "F4": "Avg fare KPI card looks clickable (pointer cursor, hover ring) but does nothing",
}
TABLES = {  # table -> (key columns, n columns)
    "gold_version_comparison": (["session_type", "task_id", "task_category"], ["n_trials_v1", "n_trials_v2"]),
    "gold_task_summary": (["session_type", "app_version", "task_id", "task_category"], ["n_trials"]),
    "gold_element_friction": (["session_type", "app_version", "uxid"], ["n_sessions", "n_clicks"]),
    "gold_goal_summary": (["session_type", "app_version", "goal_id", "goal_cats"], ["n_goals", "n_wrong_answer_shown", "n_goals_pasted_goal"]),
    "gold_bot_behavior": (["session_type", "behavior", "app_version"], ["n_turns", "n_goals", "n_sessions"]),
}


# ------------------------------------------------------------------------------------------------- evidence pack
def elements():
    ids = sorted(set(re.findall(r'data-ux-id="([^"]+)"', INDEX_HTML.read_text())))
    return [i for i in ids if not CHROME.match(i)]


def verified_literature():
    with LITERATURE.open() as f:
        rows = [r for r in csv.DictReader(f) if (r.get("verified_by") or "").strip()]
    return [{"bib_key": r["bib_key"], "cite": r["cite"], "year": r["year"], "relevance_note": r["relevance_note"],
             "validated_against": r.get("validated_against", ""), "verified_by": r["verified_by"]} for r in rows]


def rows_local():
    """Simulated sessions through the portable SQL in SQLite (databricks/tests/run_sql_local.py)."""
    import contextlib
    import io
    import runpy
    argv, exit_ = sys.argv, sys.exit
    sys.argv, sys.exit = ["run_sql_local.py"], (lambda *a: None)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            g = runpy.run_path(str(ROOT / "databricks/tests/run_sql_local.py"))
    finally:
        sys.argv, sys.exit = argv, exit_
    # The local test relabels one SIMULATED session as 'human' to check that gold keeps the two apart. Those rows are
    # not human data, so they are dropped here: the local pack is simulated only.
    return {t: g["q"](f"SELECT * FROM {t} WHERE session_type = 'simulated'") for t in TABLES}


def rows_warehouse(warehouse_id, schema):
    """Read-only SELECTs on the gold tables through a SQL warehouse (databricks-sdk, your Databricks CLI login)."""
    sys.path.insert(0, str(ROOT / "databricks/app"))
    from app import GoldReader  # noqa: E402  (same reader the App uses)
    reader = GoldReader(warehouse_id, schema)
    return {t: reader.query(f"SELECT * FROM {schema}.{t}") for t in TABLES}


def evidence_id(table, row):
    """table|session_type|key values, skipping NULLs: the same rule as concat_ws('|', ...) in 08_ai_design_proposals.sql."""
    keys = TABLES[table][0]
    return "|".join([table] + [str(row[k]) for k in keys if row.get(k) is not None])


def build_pack(rows, source):
    evidence = []
    for table, (keys, ns) in TABLES.items():
        for r in rows[table]:
            evidence.append({"id": evidence_id(table, r), "table": table, "session_type": r.get("session_type"),
                             "keys": {k: r.get(k) for k in keys if k != "session_type"},
                             "n": {k: r[k] for k in ns if r.get(k) is not None},
                             "metrics": {k: v for k, v in r.items()
                                         if k not in keys and k not in ns and isinstance(v, (int, float)) and v is not None}})
    return {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "source": source,
            "evidence": evidence, "elements": elements(), "planted_flaws": FLAWS, "planted_behaviors": BEHAVIORS,
            "literature_verified": verified_literature()}


# ------------------------------------------------------------------------------------------------- Claude call
SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "changes": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "target_kind": {"type": "string", "enum": ["element", "behavior"]},
                "target": {"type": "string"},
                "change": {"type": "string"},
                "evidence": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"evidence_id": {"type": "string"}, "metric": {"type": "string"},
                                   "value": {"type": "number"}, "n_field": {"type": "string"}, "n": {"type": "number"}},
                    "required": ["evidence_id", "metric", "value", "n_field", "n"], "additionalProperties": False}},
                "rationale": {"type": "string"},
                "literature": {"type": "array", "items": {"type": "string"}},
                "expected_effect": {"type": "string"},
                "retest_metric": {"type": "string"},
            },
            "required": ["title", "target_kind", "target", "change", "evidence", "rationale", "literature",
                         "expected_effect", "retest_metric"],
            "additionalProperties": False}},
    },
    "required": ["summary", "changes"],
    "additionalProperties": False,
}

SYSTEM = """You are the UX designer on a usability study of a small analytics dashboard ("Taxi Ops") that also has a chat
assistant. You propose concrete changes to the current design (v1), each backed by evidence from the study's gold tables.

Rules:
- Cite only evidence rows from the pack, by id. For each citation give the metric name exactly as it appears in that
  row's `metrics`, the value as given, and one of that row's `n` fields with its value. A change with no valid citation
  will be discarded.
- Target exactly one dashboard element (one of `elements`, by its data-ux-id) or one assistant behavior (B1-B5).
- Describe the change concretely enough to build: what the element looks like or does after the change.
- Prefer v1-vs-v2 differences and rates with their n over single values. Do not claim statistical significance.
- session_type 'simulated' rows come from bots whose behavior encodes the study's own hypotheses: they show a measurable
  pattern, not that real people behave this way. Say so in the rationale when you rely on them. Prefer human rows when
  they exist, and say when n is tiny.
- Cite literature only by bib_key from `literature_verified`. If that list is empty, leave `literature` empty and do not
  name papers or findings in the rationale.
- `retest_metric` names the gold metric that should move if the change works, so it can be re-tested.
- Propose at most 6 changes, the strongest first. A UX developer reviews each one before anything is built."""


def call_claude(pack):
    import anthropic
    client = anthropic.Anthropic()  # credentials from the environment or an `ant auth login` profile
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # server-side fallback if the request is declined by a safety classifier
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": "Evidence pack (JSON):\n" + json.dumps(pack)}],
    )
    if response.stop_reason == "refusal":
        raise SystemExit(f"Claude declined the request (request id {response._request_id})")
    if response.stop_reason == "max_tokens":
        raise SystemExit("output hit max_tokens: raise it or ask for fewer changes")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text), response.model, response._request_id


# ------------------------------------------------------------------------------------------------- validation
def close(a, b):
    return a is not None and b is not None and abs(float(a) - float(b)) <= max(0.005, 0.005 * abs(float(b)))


def validate(draft, pack):
    by_id = {e["id"]: e for e in pack["evidence"]}
    lit = {r["bib_key"] for r in pack["literature_verified"]}
    ok, rejected = [], []
    for c in draft.get("changes", []):
        problems, cites = [], []
        if c["target_kind"] == "element" and c["target"] not in pack["elements"]:
            problems.append(f"unknown element {c['target']!r}")
        if c["target_kind"] == "behavior" and c["target"] not in pack["planted_behaviors"]:
            problems.append(f"unknown behavior {c['target']!r}")
        for e in c["evidence"]:
            row = by_id.get(e["evidence_id"])
            if row is None:
                problems.append(f"{e['evidence_id']}: no such evidence row")
                continue
            if e["metric"] not in row["metrics"]:
                problems.append(f"{e['evidence_id']}: metric {e['metric']!r} not in that row")
            elif not close(e["value"], row["metrics"][e["metric"]]):
                problems.append(f"{e['evidence_id']}.{e['metric']}: cited {e['value']}, row has {row['metrics'][e['metric']]}")
            if e["n_field"] not in row["n"] or not close(e["n"], row["n"][e["n_field"]]):
                problems.append(f"{e['evidence_id']}: n {e['n_field']}={e['n']} does not match the row")
            cites.append({"evidence_id": row["id"], "table": row["table"], "session_type": row["session_type"],
                          **row["keys"], "metric": e["metric"], "value": row["metrics"].get(e["metric"]),
                          "n_field": e["n_field"], "n": row["n"].get(e["n_field"]),
                          "uxid": row["keys"].get("uxid")})
        if not c["evidence"]:
            problems.append("no evidence cited")
        bad_lit = [k for k in c["literature"] if k not in lit]
        if bad_lit:
            problems.append(f"literature not verified: {bad_lit}")
        item = {"title": c["title"], "target_kind": c["target_kind"], "target": c["target"],
                "uxid": c["target"] if c["target_kind"] == "element" else None, "change": c["change"],
                "evidence": cites, "rationale": c["rationale"], "literature": c["literature"],
                "expected_effect": c["expected_effect"], "retest_metric": c["retest_metric"],
                "simulated_only": all(x["session_type"] == "simulated" for x in cites) if cites else None}
        (rejected if problems else ok).append({**item, **({"problems": problems} if problems else {})})
    for i, c in enumerate(ok, 1):
        c.update(id=f"P{i}", status="pending", reviewed_by=None, reviewed_at=None, review_note=None)
    return ok, rejected


# ------------------------------------------------------------------------------------------------- commands
def cmd_evidence(a):
    if a.source == "local":
        rows, label = rows_local(), "local SQLite, simulated sessions"
    elif a.source == "warehouse":
        rows, label = rows_warehouse(a.warehouse_id, a.schema), f"warehouse {a.schema}"
    else:
        rows, label = json.loads(Path(a.rows).read_text()), f"exported gold rows ({Path(a.rows).name})"
        missing = [t for t in TABLES if t not in rows]
        if missing:
            raise SystemExit(f"{a.rows} lacks tables {missing}")
    pack = build_pack(rows, label)
    OUT.mkdir(exist_ok=True)
    (OUT / "evidence.json").write_text(json.dumps(pack, indent=1))
    by = {}
    for e in pack["evidence"]:
        by[e["session_type"]] = by.get(e["session_type"], 0) + 1
    print(f"wrote {OUT / 'evidence.json'}: {len(pack['evidence'])} rows {by}, {len(pack['elements'])} elements, "
          f"{len(pack['literature_verified'])} verified papers")


def parse_draft(text):
    """A model's JSON reply; tolerates a ```json fence. Raises ValueError if it is not the expected shape."""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    d = json.loads(t)
    if not isinstance(d, dict) or not isinstance(d.get("changes"), list):
        raise ValueError("expected an object with a 'changes' list")
    for c in d["changes"]:
        missing = [k for k in SCHEMA["properties"]["changes"]["items"]["required"] if k not in c]
        if missing:
            raise ValueError(f"change {c.get('title')!r} lacks {missing}")
    return d


def write_set(name, designer, draft, pack, extra=None):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    OUT.mkdir(exist_ok=True)
    (OUT / f"draft-{name}-{stamp}.json").write_text(json.dumps(draft, indent=1))
    ok, rejected = validate(draft, pack)
    out = {"name": name, "designer": designer, "generated_at": stamp, "evidence_source": pack["source"],
           "summary": draft.get("summary", ""),
           "literature_note": None if pack["literature_verified"] else
           "No literature rows are verified yet, so no papers are cited.",
           "changes": ok, "rejected_by_validator": rejected, **(extra or {})}
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    path = PROPOSALS_DIR / f"{name}.json"
    path.write_text(json.dumps(out, indent=1))
    print(f"wrote {path}: {len(ok)} pending, {len(rejected)} rejected by the validator")
    for c in rejected:
        print(f"  rejected {c['title']!r}: {'; '.join(c['problems'])}")
    return out


def cmd_draft(a, call=call_claude):
    if a.from_ai_gen:  # the row written by 08_ai_design_proposals.sql: {draft_json, evidence_json, generated_at}
        row = json.loads(Path(a.from_ai_gen).read_text())
        rows = json.loads(row["evidence_json"])
        pack = build_pack({t: rows.get(t) or [] for t in TABLES}, f"gold tables as of {row.get('generated_at')} (snapshot stored with the draft)")
        try:
            draft = parse_draft(row["draft_json"])
        except (ValueError, json.JSONDecodeError) as ex:
            draft = {"summary": "", "changes": []}
            print(f"the ai_gen reply was not valid proposal JSON ({ex}); writing an empty set with the error")
            return write_set(a.name or "ai-gen", "Databricks ai_gen (model chosen by Databricks)", draft, pack,
                             {"error": f"reply was not valid proposal JSON: {ex}"})
        return write_set(a.name or "ai-gen", "Databricks ai_gen (model chosen by Databricks)", draft, pack)
    pack = json.loads((OUT / "evidence.json").read_text())
    if a.from_file:
        return write_set(a.name or "file", a.designer or "unspecified", parse_draft(Path(a.from_file).read_text()), pack)
    if a.dry_run:
        print(f"dry run: would send {len(json.dumps(pack))} chars of evidence to {MODEL}; no API call made")
        return None
    draft, served_by, request_id = call(pack)
    return write_set(a.name or "claude-api", f"Claude ({served_by}, API)", draft, pack, {"request_id": request_id})


def ai_gen_prompt():
    """The instructions for ai_gen: same rules as the Claude path, plus the output format spelled out (ai_gen has no
    schema enforcement, so the checker rejects anything malformed)."""
    fmt = json.dumps({"summary": "one paragraph", "changes": [{
        "title": "...", "target_kind": "element or behavior", "target": "a data-ux-id or B1-B5",
        "change": "...", "evidence": [{"evidence_id": "an id from the rows", "metric": "a column of that row",
                                        "value": 0.0, "n_field": "an n_* column of that row", "n": 0}],
        "rationale": "...", "literature": [], "expected_effect": "...", "retest_metric": "..."}]})
    lit = "literature_verified is empty: leave literature empty." if not verified_literature() else \
        "literature_verified: " + json.dumps([r["bib_key"] for r in verified_literature()])
    return "\n".join([
        SYSTEM, "",
        "Reply with ONLY one JSON object, no prose and no code fence, in exactly this shape:", fmt, "",
        "elements (data-ux-id): " + ", ".join(elements()),
        "planted_behaviors: " + json.dumps(BEHAVIORS),
        "planted_flaws (chart and page): " + json.dumps(FLAWS),
        lit, "",
        "Evidence rows grouped by table. Each row has an id (cite it as evidence_id); the n fields are the columns "
        "starting with n_. Rows:",
    ])


def sql_08():
    def lit(text):  # Spark string literal: no single quotes, newlines as \n
        return "'" + text.replace("'", "\u2019").replace("\n", "\\n") + "'"
    parts = []
    for table, (keys, _) in TABLES.items():
        idexpr = "concat_ws('|', '" + table + "', " + ", ".join(keys) + ")"
        parts.append(f"    '{table}', (SELECT collect_list(struct(*)) FROM (SELECT {idexpr} AS id, * "
                     f"FROM ${{catalog}}.${{schema}}.{table}))")
    return f"""-- GENERATED by databricks/designer/propose.py sql. Do not edit by hand: change the rules in propose.py.
-- AI DESIGNER inside Databricks: ai_gen drafts UI change proposals from the gold tables. Spark/Databricks SQL only.
-- ai_gen uses a model chosen and managed by Databricks (not selectable, not necessarily Claude) and has no output-format
-- enforcement. The raw reply and the exact evidence it saw are stored together; propose.py draft --from-ai-gen checks
-- every citation against that snapshot (value, n, element) and only then shows changes, as pending, for sign-off.
-- Run after ux_pipeline_all.sql. Calls a model once per run.
CREATE OR REPLACE TABLE ${{catalog}}.${{schema}}.gold_design_proposals_raw AS
WITH ev AS (
  SELECT to_json(named_struct(
{(","+chr(10)).join(parts)}
  )) AS evidence_json
)
SELECT current_timestamp() AS generated_at,
       'ai_gen' AS designer,
       evidence_json,
       ai_gen(concat({lit(ai_gen_prompt())}, ' ', evidence_json)) AS draft_json
FROM ev;
"""


def cmd_sql(a):
    out = sql_08()
    if getattr(a, "check", False):
        raise SystemExit(0 if SQL_08.exists() and SQL_08.read_text() == out else f"{SQL_08} is stale: run propose.py sql")
    SQL_08.write_text(out)
    print(f"wrote {SQL_08}")


def cmd_review(a):
    path = PROPOSALS_DIR / f"{a.set}.json"
    data = json.loads(path.read_text())
    c = next((x for x in data["changes"] if x["id"] == a.id), None)
    if c is None:
        raise SystemExit(f"no proposal {a.id}; have {[x['id'] for x in data['changes']]}")
    c.update(status="approved" if a.approve else "rejected", reviewed_by=a.by,
             reviewed_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), review_note=a.note)
    path.write_text(json.dumps(data, indent=1))
    print(f"{a.id} -> {c['status']} by {a.by}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("evidence")
    e.add_argument("--source", choices=["local", "warehouse", "json"], default="local")
    e.add_argument("--rows", help="with --source json: file of {table: [row, ...]}")
    e.add_argument("--warehouse-id")
    e.add_argument("--schema", default="workspace.ux_telemetry")
    d = sub.add_parser("draft")
    d.add_argument("--dry-run", action="store_true")
    src = d.add_mutually_exclusive_group()
    src.add_argument("--from-file", help="a draft JSON written elsewhere (e.g. in a Claude Code session)")
    src.add_argument("--from-ai-gen", help="the gold_design_proposals_raw row as JSON {draft_json, evidence_json, generated_at}")
    d.add_argument("--name", help="proposal set name (file name under databricks/app/proposals/)")
    d.add_argument("--designer", help="who drafted it, shown on /results (with --from-file)")
    q = sub.add_parser("sql")
    q.add_argument("--check", action="store_true")
    r = sub.add_parser("review")
    r.add_argument("id")
    r.add_argument("--set", required=True, help="proposal set name, e.g. claude-session or ai-gen")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--approve", action="store_true")
    g.add_argument("--reject", action="store_true")
    r.add_argument("--by", required=True)
    r.add_argument("--note", default="")
    a = ap.parse_args(argv)
    if a.cmd == "evidence" and a.source == "warehouse" and not a.warehouse_id:
        ap.error("--warehouse-id is required with --source warehouse")
    if a.cmd == "evidence" and a.source == "json" and not a.rows:
        ap.error("--rows is required with --source json")
    if a.cmd == "draft" and a.from_file and not a.designer:
        ap.error("--designer is required with --from-file (say who drafted it)")
    {"evidence": cmd_evidence, "draft": cmd_draft, "review": cmd_review, "sql": cmd_sql}[a.cmd](a)


if __name__ == "__main__":
    main()
