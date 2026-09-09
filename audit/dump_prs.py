#!/usr/bin/env python3
"""Dump every PR of the org created since SINCE (argv[1] or CR_AUDIT_SINCE) via GraphQL: reviews, review threads, comments, commits.
Keep the per-level first: limits small — the GraphQL cost is the product of nested limits and the hourly budget is 5000 points."""
import json, subprocess, sys, os, time

ORG = os.environ.get("CR_AUDIT_ORG", "meshmakers")
DATA = os.environ.get("CR_AUDIT_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

OUT = None  # set below once DATA is known
SINCE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CR_AUDIT_SINCE", "2026-08-20")

def gh(args, stdin=None):
    r = subprocess.run(["gh"] + args, capture_output=True, text=True, input=stdin)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r.stdout

# 1. enumerate PRs via search API
prs = []
page = 1
while True:
    out = gh(["api", "-X", "GET", "search/issues", "-f", f"q=org:{ORG} is:pr created:>={SINCE}", "-f", "per_page=100", "-f", f"page={page}"])
    data = json.loads(out)
    items = data["items"]
    for it in items:
        repo = it["repository_url"].split(f"/repos/{ORG}/")[1]
        prs.append((repo, it["number"]))
    if len(items) < 100:
        break
    page += 1
OUT = os.path.join(DATA, "prs")
os.makedirs(OUT, exist_ok=True)
print(f"{len(prs)} PRs enumerated", file=sys.stderr)

QUERY = """
query($owner:String!,$repo:String!,$num:Int!){
  repository(owner:$owner,name:$repo){
    isPrivate
    pullRequest(number:$num){
      number title state merged mergedAt createdAt closedAt isDraft
      author{login}
      additions deletions changedFiles
      baseRefName headRefName
      reviewDecision
      commits(first:60){totalCount nodes{commit{committedDate messageHeadline oid}}}
      comments(first:60){totalCount nodes{author{login} body createdAt}}
      reviews(first:60){totalCount nodes{author{login} state body createdAt}}
      reviewThreads(first:50){totalCount nodes{isResolved isOutdated isCollapsed path line resolvedBy{login}
        comments(first:8){nodes{author{login} body createdAt outdated reactions(first:3){nodes{content user{login}}}}}}}
    }
  }
}
"""

done = 0
for repo, num in prs:
    path = os.path.join(OUT, f"{repo}-{num}.json")
    if os.path.exists(path):
        done += 1
        continue
    for attempt in range(3):
        try:
            out = gh(["api", "graphql", "-f", f"query={QUERY}", "-f", f"owner={ORG}", "-f", f"repo={repo}", "-F", f"num={num}"])
            data = json.loads(out)
            pr = data["data"]["repository"]["pullRequest"]
            pr["repo"] = repo
            pr["repoIsPrivate"] = data["data"]["repository"]["isPrivate"]
            with open(path, "w") as f:
                json.dump(pr, f)
            done += 1
            break
        except Exception as e:
            print(f"retry {repo}#{num}: {e}", file=sys.stderr)
            time.sleep(20)
    if done % 25 == 0:
        print(f"{done}/{len(prs)}", file=sys.stderr)
print(f"done: {done}/{len(prs)}", file=sys.stderr)
