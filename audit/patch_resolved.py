#!/usr/bin/env python3
"""Fill reviewThreads.isResolved/resolvedBy for REST-dumped PRs via a minimal GraphQL query (cheap: ~2 points per PR)."""
import json, glob, os, subprocess, sys, time

ORG = os.environ.get("CR_AUDIT_ORG", "meshmakers")
DATA = os.environ.get("CR_AUDIT_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

HERE = os.path.dirname(os.path.abspath(__file__))
Q = """
query($owner:String!,$repo:String!,$num:Int!){
  repository(owner:$owner,name:$repo){ pullRequest(number:$num){
    reviewThreads(first:50){nodes{isResolved isOutdated resolvedBy{login} comments(first:1){nodes{databaseId}}}}}}}
"""
patched = skipped = failed = 0
for f in sorted(glob.glob(os.path.join(DATA, "prs", "*.json"))):
    pr = json.load(open(f))
    if pr.get("source") != "rest" or pr.get("resolvedPatched") or not pr["reviewThreads"]["nodes"]:
        skipped += 1
        continue
    r = subprocess.run(["gh", "api", "graphql", "-f", f"query={Q}", "-f", f"owner={ORG}", "-f", f"repo={pr['repo']}", "-F", f"num={pr['number']}"], capture_output=True, text=True)
    if r.returncode != 0:
        print("FAILED", f, r.stderr[:120], file=sys.stderr)
        failed += 1
        if "rate limit" in r.stderr.lower():
            break
        continue
    nodes = json.loads(r.stdout)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    by_root = {n["comments"]["nodes"][0]["databaseId"]: n for n in nodes if n["comments"]["nodes"]}
    for t in pr["reviewThreads"]["nodes"]:
        n = by_root.get(t.get("rootDatabaseId"))
        if n:
            t["isResolved"] = n["isResolved"]
            t["isOutdated"] = n["isOutdated"]
            t["resolvedBy"] = n["resolvedBy"]
    pr["resolvedPatched"] = True
    json.dump(pr, open(f, "w"))
    patched += 1
    time.sleep(0.3)
print(f"patched={patched} skipped={skipped} failed={failed}")
