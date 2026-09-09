#!/usr/bin/env python3
"""REST fallback for dump_prs.py: same JSON shape, reviewThreads.isResolved = None (filled later via GraphQL)."""
import json, subprocess, sys, os, time

ORG = os.environ.get("CR_AUDIT_ORG", "meshmakers")
DATA = os.environ.get("CR_AUDIT_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DATA, "prs")
os.makedirs(OUT, exist_ok=True)
SINCE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CR_AUDIT_SINCE", "2026-08-20")
repo_private = {}


def gh(args):
    for attempt in range(4):
        r = subprocess.run(["gh"] + args, capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout
        if "rate limit" in r.stderr.lower():
            print("rate limited, sleeping 60s", file=sys.stderr)
            time.sleep(60)
            continue
        raise RuntimeError(r.stderr)
    raise RuntimeError("gave up: " + " ".join(args))


def get_json(path, paginate=False):
    args = ["api", path]
    if paginate:
        args += ["--paginate", "--slurp"]
    out = gh(args)
    data = json.loads(out)
    if paginate:
        merged = []
        for page in data:
            merged.extend(page)
        return merged
    return data


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
    time.sleep(2)
print(f"{len(prs)} PRs enumerated", file=sys.stderr)


def user(u):
    return {"login": u["login"].replace("[bot]", "")} if u else None


def dump(repo, num):
    base = f"repos/{ORG}/{repo}"
    if repo not in repo_private:
        repo_private[repo] = get_json(base)["private"]
    p = get_json(f"{base}/pulls/{num}")
    commits = get_json(f"{base}/pulls/{num}/commits?per_page=100", paginate=True)
    icomments = get_json(f"{base}/issues/{num}/comments?per_page=100", paginate=True)
    reviews = get_json(f"{base}/pulls/{num}/reviews?per_page=100", paginate=True)
    rcomments = get_json(f"{base}/pulls/{num}/comments?per_page=100", paginate=True)

    # group review comments into threads by root id
    by_id = {c["id"]: c for c in rcomments}
    roots = {}
    for c in rcomments:
        root = c
        seen = set()
        while root.get("in_reply_to_id") and root["in_reply_to_id"] in by_id and root["id"] not in seen:
            seen.add(root["id"])
            root = by_id[root["in_reply_to_id"]]
        roots.setdefault(root["id"], []).append(c)
    threads = []
    for root_id, cs in roots.items():
        cs.sort(key=lambda c: c["created_at"])
        root = cs[0]
        threads.append({
            "isResolved": None,
            "isOutdated": root.get("position") is None,
            "isCollapsed": None,
            "path": root.get("path"),
            "line": root.get("line") or root.get("original_line"),
            "resolvedBy": None,
            "rootDatabaseId": root["id"],
            "comments": {"nodes": [{
                "author": user(c.get("user")),
                "body": c.get("body") or "",
                "createdAt": c["created_at"],
                "outdated": c.get("position") is None,
                "reactions": {"nodes": [
                    {"content": k, "user": None}
                    for k, v in (c.get("reactions") or {}).items()
                    if k not in ("url", "total_count") and isinstance(v, int) and v > 0
                    for _ in range(v)
                ]},
            } for c in cs[:8]]},
        })
    threads.sort(key=lambda t: t["comments"]["nodes"][0]["createdAt"])

    return {
        "number": p["number"], "title": p["title"],
        "state": "MERGED" if p.get("merged") else p["state"].upper(),
        "merged": bool(p.get("merged")), "mergedAt": p.get("merged_at"),
        "createdAt": p["created_at"], "closedAt": p.get("closed_at"), "isDraft": p.get("draft", False),
        "author": user(p.get("user")),
        "additions": p.get("additions"), "deletions": p.get("deletions"), "changedFiles": p.get("changed_files"),
        "baseRefName": p["base"]["ref"], "headRefName": p["head"]["ref"],
        "reviewDecision": None,
        "commits": {"totalCount": len(commits), "nodes": [{"commit": {
            "committedDate": c["commit"]["committer"]["date"],
            "messageHeadline": c["commit"]["message"].split("\n")[0], "oid": c["sha"]}} for c in commits[:60]]},
        "comments": {"totalCount": len(icomments), "nodes": [{
            "author": user(c.get("user")), "body": c.get("body") or "", "createdAt": c["created_at"]} for c in icomments[:60]]},
        "reviews": {"totalCount": len(reviews), "nodes": [{
            "author": user(r.get("user")), "state": r["state"], "body": r.get("body") or "", "createdAt": r.get("submitted_at")} for r in reviews[:60]]},
        "reviewThreads": {"totalCount": len(threads), "nodes": threads[:50]},
        "repo": repo, "repoIsPrivate": repo_private[repo], "source": "rest",
    }


done = 0
for repo, num in prs:
    path = os.path.join(OUT, f"{repo}-{num}.json")
    if os.path.exists(path):
        done += 1
        continue
    try:
        pr = dump(repo, num)
        with open(path, "w") as f:
            json.dump(pr, f)
        done += 1
    except Exception as e:
        print(f"FAILED {repo}#{num}: {e}", file=sys.stderr)
    if done % 20 == 0:
        print(f"{done}/{len(prs)}", file=sys.stderr)
print(f"done: {done}/{len(prs)}", file=sys.stderr)
