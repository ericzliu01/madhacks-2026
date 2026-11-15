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
propose.OUT, propose.PROPOSALS = tmp / "out", tmp / "proposals" / "latest.json"
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

class A: dry_run = False
propose.cmd_draft(A, call=fake)
out = json.loads(propose.PROPOSALS.read_text())
check("only the valid change survives, as pending", [c["title"] for c in out["changes"]] == [good["title"]]
      and out["changes"][0]["status"] == "pending" and out["changes"][0]["id"] == "P1")
check("simulated evidence is labeled from the row", out["changes"][0]["evidence"][0]["session_type"] == "simulated"
      and out["changes"][0]["simulated_only"] is True)
reasons = {c["title"]: " ".join(c["problems"]) for c in out["rejected_by_validator"]}
check("wrong value rejected with the reason", "cited 99" in reasons.get("wrong value", ""))
check("unknown element rejected", "unknown element" in reasons.get("bad target", ""))
check("unverified literature rejected", "not verified" in reasons.get("unverified paper", ""))
check("no verified literature is stated", "No literature rows are verified" in (out["literature_note"] or ""))

propose.main(["review", "P1", "--approve", "--by", "UX dev", "--note", "ship it"])
out = json.loads(propose.PROPOSALS.read_text())
check("review records approval, reviewer and note", out["changes"][0]["status"] == "approved"
      and out["changes"][0]["reviewed_by"] == "UX dev" and out["changes"][0]["review_note"] == "ship it")

sys.exit(0 if all(results) else 1)
