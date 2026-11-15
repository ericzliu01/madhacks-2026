#!/usr/bin/env python3
"""Tests propose.py without calling the API: a fake designer returns one valid change and three invalid ones.
Uses the local (simulated) evidence pack and a temporary proposals file."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import propose  # noqa: E402

results = []
def check(name, ok): results.append(ok); print("PASS" if ok else "FAIL", name)

tmp = Path(tempfile.mkdtemp())
propose.OUT, propose.PROPOSALS_DIR = tmp / "out", tmp / "proposals"
propose.main(["evidence", "--source", "local"])
pack = json.loads((propose.OUT / "evidence.json").read_text())
check("pack has simulated evidence from all five gold tables",
      {e["table"] for e in pack["evidence"]} == set(propose.TABLES) and all(e["session_type"] for e in pack["evidence"]))
check("local pack is simulated only (the test's relabelled 'human' session is dropped)",
      {e["session_type"] for e in pack["evidence"]} == {"simulated"})
check("study chrome is not offered as a design target", "kpi-avg-fare" in pack["elements"]
      and not any(x.startswith(("sat-", "gsat-", "task-", "goal-")) for x in pack["elements"]))

kpi = next(e for e in pack["evidence"] if e["table"] == "gold_element_friction" and e["keys"]["uxid"] == "kpi-avg-fare"
           and e["keys"]["app_version"] == "v1" and e["session_type"] == "simulated")
good = {"title": "Make the Avg fare KPI look static", "target_kind": "element", "target": "kpi-avg-fare",
        "change": "Remove the pointer cursor and hover ring.",
        "evidence": [{"evidence_id": kpi["id"], "metric": "n_rage_clicks", "value": kpi["metrics"]["n_rage_clicks"],
                      "n_field": "n_sessions", "n": kpi["n"]["n_sessions"]}],
        "rationale": "Simulated sessions show rage clicks on it.", "literature": [],
        "expected_effect": "No rage clicks on it.", "retest_metric": "n_rage_clicks"}
wrong_value = dict(good, title="wrong value", evidence=[dict(good["evidence"][0], value=99)])
bad_target = dict(good, title="bad target", target="kpi-nonexistent")
bad_lit = dict(good, title="unverified paper", literature=["Huang2012UserSUV"])
fake = lambda p: ({"summary": "s", "changes": [good, wrong_value, bad_target, bad_lit]}, "claude-opus-5-5", "req_test")

class A: dry_run = False; from_file = None; from_ai_gen = None; name = None; designer = None
propose.cmd_draft(A, call=fake)
out = json.loads((propose.PROPOSALS_DIR / "claude-api.json").read_text())
check("only the valid change survives, as pending", [c["title"] for c in out["changes"]] == [good["title"]]
      and out["changes"][0]["status"] == "pending" and out["changes"][0]["id"] == "P1")
check("simulated evidence is labeled from the row", out["changes"][0]["evidence"][0]["session_type"] == "simulated"
      and out["changes"][0]["simulated_only"] is True)
reasons = {c["title"]: " ".join(c["problems"]) for c in out["rejected_by_validator"]}
check("wrong value rejected with the reason", "cited 99" in reasons.get("wrong value", ""))
check("unknown element rejected", "unknown element" in reasons.get("bad target", ""))
check("unverified literature rejected", "not verified" in reasons.get("unverified paper", ""))
check("no verified literature is stated", "No literature rows are verified" in (out["literature_note"] or ""))

propose.main(["review", "P1", "--set", "claude-api", "--approve", "--by", "UX dev", "--note", "ship it"])
out = json.loads((propose.PROPOSALS_DIR / "claude-api.json").read_text())
check("review records approval, reviewer and note", out["changes"][0]["status"] == "approved"
      and out["changes"][0]["reviewed_by"] == "UX dev" and out["changes"][0]["review_note"] == "ship it")

check("evidence ids are stable table|session_type|keys",
      kpi["id"] == "gold_element_friction|simulated|v1|kpi-avg-fare")

# --from-file: a draft written elsewhere (e.g. this Claude Code session), same checker
(tmp / "d.json").write_text(json.dumps({"summary": "s", "changes": [good, bad_target]}))
propose.main(["draft", "--from-file", str(tmp / "d.json"), "--name", "claude-session", "--designer", "Claude (session)"])
cs = json.loads((propose.PROPOSALS_DIR / "claude-session.json").read_text())
check("--from-file: valid change kept, bad one rejected, designer recorded",
      len(cs["changes"]) == 1 and len(cs["rejected_by_validator"]) == 1 and cs["designer"] == "Claude (session)")

# --from-ai-gen: the SQL row (reply may be fenced) + the evidence snapshot it saw, rows carrying SQL-built ids
rows = propose.rows_local()
snapshot = {t: [dict(r, id=propose.evidence_id(t, r)) for r in rs] for t, rs in rows.items()}
row = {"generated_at": "2026-11-15T12:00:00Z", "evidence_json": json.dumps(snapshot),
       "draft_json": "```json\n" + json.dumps({"summary": "s", "changes": [good, wrong_value]}) + "\n```"}
(tmp / "row.json").write_text(json.dumps(row))
propose.main(["draft", "--from-ai-gen", str(tmp / "row.json")])
ag = json.loads((propose.PROPOSALS_DIR / "ai-gen.json").read_text())
check("--from-ai-gen: fenced reply parsed, checked against the stored snapshot",
      len(ag["changes"]) == 1 and len(ag["rejected_by_validator"]) == 1 and "ai_gen" in ag["designer"])
(tmp / "bad.json").write_text(json.dumps(dict(row, draft_json="Here are my ideas: make it better.")))
propose.main(["draft", "--from-ai-gen", str(tmp / "bad.json"), "--name", "ai-gen-bad"])
bad = json.loads((propose.PROPOSALS_DIR / "ai-gen-bad.json").read_text())
check("--from-ai-gen: a non-JSON reply gives an empty set with the error, not a crash", bad["changes"] == [] and "error" in bad)
check("08_ai_design_proposals.sql is in sync with the rules in propose.py",
      propose.SQL_08.read_text() == propose.sql_08())

# relevance: right numbers, wrong study / wrong element
t2 = next(e for e in pack["evidence"] if e["table"] == "gold_version_comparison" and e["keys"]["task_id"] == "T2")
wrong_study = dict(good, title="B3 from a chart task", target_kind="behavior", target="B3",
                   evidence=[{"evidence_id": t2["id"], "metric": "avg_duration_ms_v1",
                              "value": t2["metrics"]["avg_duration_ms_v1"], "n_field": "n_trials_v1", "n": 30}])
menu = next(e for e in pack["evidence"] if e["table"] == "gold_element_friction" and e["keys"]["uxid"] == "menu-more")
wrong_elem = dict(good, title="KPI fix from menu clicks", evidence=[{"evidence_id": menu["id"], "metric": "n_dead_clicks",
                  "value": menu["metrics"]["n_dead_clicks"], "n_field": "n_sessions", "n": menu["n"]["n_sessions"]}])
ok, rej = propose.validate({"changes": [good, wrong_study, wrong_elem]}, pack)
why = {c["title"]: " ".join(c["problems"]) for c in rej}
check("relevance: chat target with task-study evidence rejected", "task study" in why.get("B3 from a chart task", ""))
check("relevance: friction row for another element rejected", "not kpi-avg-fare" in why.get("KPI fix from menu clicks", ""))
check("relevance: the matching change still passes", [c["title"] for c in ok] == [good["title"]])

# independence: designers get evidence, element names and neutral notes, never the planted flaw list
blob = json.dumps(pack) + propose.ai_gen_prompt()
check("designer inputs contain no planted-flaw descriptions",
      not any(desc in blob for desc in propose.FLAWS.values()) and "planted" not in propose.ai_gen_prompt().lower()
      and "tooltip" not in blob.lower() and "truncat" not in blob.lower())

sys.exit(0 if all(results) else 1)
