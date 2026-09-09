#!/usr/bin/env python3
"""Aggregate the classification produced by classify-workflow.js.

Expects DATA/classification.json holding the workflow's return value
({"results": [...], "verify": {"verdicts": [...]}}) — copy the "result" object
from the workflow output file there. Applies the skeptic's corrections, writes
DATA/classified_findings.json and prints the tables used in the report.
"""
import json, os
from collections import Counter, defaultdict

DATA = os.environ.get("CR_AUDIT_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def main():
    data = json.load(open(os.path.join(DATA, "classification.json")))
    if "result" in data and "results" not in data:
        data = data["result"]
    findings = [dict(f, batch=r["batch"]) for r in data["results"] for f in r["findings"]]
    verify = {(v["pr"], v["id"]): v for v in data.get("verify", {}).get("verdicts", [])}
    for f in findings:
        v = verify.get((f["pr"], f["id"]))
        f["final_verdict"] = v["corrected_verdict"] if (v and not v["agree_invalid"]) else f["verdict"]
    json.dump(findings, open(os.path.join(DATA, "classified_findings.json"), "w"), indent=1)

    print(f"findings classified: {len(findings)}  by bot: {dict(Counter(f['bot'] for f in findings))}")
    print(f"skeptic pass: {len(verify)} 'invalid' verdicts re-checked, {sum(1 for v in verify.values() if not v['agree_invalid'])} overturned")
    for bot in ("CR", "Copilot"):
        sub = [f for f in findings if f["bot"] == bot]
        if not sub:
            continue
        n = len(sub)
        vc = Counter(f["final_verdict"] for f in sub)
        print(f"\n== {bot}: {n} threads ==")
        print("  verdict: " + ", ".join(f"{k}={v} ({100 * v // n}%)" for k, v in vc.most_common()))
        print("  substance:", dict(Counter(f["substance"] for f in sub)))
        print("  outcome:", dict(Counter(f["outcome_observed"] for f in sub)))
        print("  substantive by outcome:", dict(Counter(f["outcome_observed"] for f in sub if f["final_verdict"] == "valid-substantive")))
        print("  root cause of invalid:", dict(Counter(f["root_cause_if_invalid"] for f in sub if f["final_verdict"] == "invalid")))
        print("  config lever (all):", dict(Counter(f["config_lever"] for f in sub)))
    overlaps = sorted({tuple(sorted((f["id"], f["overlap_with"]))) + (f["pr"],) for f in findings if f["overlap_with"]})
    print(f"\n== overlapping CR/Copilot threads: {len(overlaps)} ==")
    for a, b, pr in overlaps:
        print(f"  {pr}: {a} <-> {b}")
    print("\n== patterns per batch ==")
    for r in data["results"]:
        print(f"[{r['batch']}] {r.get('guideline_effect', '')}")
        for p in r.get("patterns", []):
            print("   -", p)
    print("\n== findings judged invalid ==")
    for f in findings:
        if f["final_verdict"] == "invalid":
            print(f"  {f['pr']} {f['id']} [{f['substance']}/{f['root_cause_if_invalid']}] lever={f['config_lever']} | {f['note']}")
    print("\n== concrete rule proposals (lever_note) ==")
    by_lever = defaultdict(list)
    for f in findings:
        if f["lever_note"]:
            by_lever[f["config_lever"]].append(f)
    for lever, fs in by_lever.items():
        print(f"[{lever}]")
        for f in fs:
            print(f"  ({f['pr']} {f['id']} {f['final_verdict']}) {f['lever_note']}")


if __name__ == "__main__":
    main()
