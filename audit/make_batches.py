#!/usr/bin/env python3
"""Build compact per-PR finding dossiers for the classification agents."""
import json, os, re, glob

ORG = os.environ.get("CR_AUDIT_ORG", "meshmakers")
DATA = os.environ.get("CR_AUDIT_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DATA, "batches")
CHECKOUTS = os.environ.get("CR_AUDIT_CHECKOUTS", "")  # workspace folder holding one checkout per repo, optional
os.makedirs(OUT, exist_ok=True)
CR, CP = "coderabbitai", "copilot-pull-request-reviewer"


def clean(body, limit):
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"<details>\s*<summary>🤖 Prompt for AI Agents</summary>.*?</details>", "", body, flags=re.S)
    body = re.sub(r"<details>\s*<summary>🧩 Analysis chain</summary>.*?</details>", "[analysis chain omitted]", body, flags=re.S)
    body = re.sub(r"<details>\s*<summary>🔎 Supported by static analysis</summary>.*?</details>", "[static-analysis script omitted]", body, flags=re.S)
    body = re.sub(r"<details>\s*<summary>✏️ Learnings added</summary>.*?</details>", "[Learnings added]", body, flags=re.S)
    body = re.sub(r"_You are interacting with an AI system\._", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body if len(body) <= limit else body[:limit] + " …[truncated]"


per_pr = json.load(open(os.path.join(DATA, "per_pr.json")))
reviewed = [r for r in per_pr if r["cr_status"] == "reviewed" and r["cr_threads"] > 0]
reviewed.sort(key=lambda r: (r["repo"], r["num"]))

dossiers = []
for r in reviewed:
    pr = json.load(open(os.path.join(DATA, "prs", f"{r['repo']}-{r['num']}.json")))
    lines = [f"# {r['repo']} PR #{r['num']} — {pr['title']}",
             f"author={r['author']} state={pr['state']} commits={r['commits']} +{r['adds']}/-{r['dels']} files={r['files']} visibility={r['vis']}",
             f"merged={pr['merged']} createdAt={pr['createdAt']}" + (f" local checkout: {CHECKOUTS}/{r['repo']}" if CHECKOUTS else ""),
             f"commits: " + "; ".join(f"{c['commit']['oid'][:7]} {c['commit']['messageHeadline'][:60]}" for c in pr["commits"]["nodes"][:12]), ""]
    idx = 0
    for t in pr["reviewThreads"]["nodes"]:
        cs = t["comments"]["nodes"]
        if not cs or not cs[0]["author"]:
            continue
        who = cs[0]["author"]["login"]
        if who not in (CR, CP):
            continue
        idx += 1
        tag = "CR" if who == CR else "COPILOT"
        lines.append(f"## [{tag}-{idx}] {t.get('path')}:{t.get('line')}  resolved={t.get('isResolved')} outdated={t.get('isOutdated')} resolvedBy={(t.get('resolvedBy') or {}).get('login')}")
        lines.append(clean(cs[0]["body"], 1400 if who == CR else 700))
        for c in cs[1:]:
            a = c["author"]["login"] if c["author"] else "?"
            lines.append(f"  > reply by {a}: " + clean(c["body"], 500).replace("\n", "\n    "))
        lines.append("")
    dossiers.append((r["repo"], r["num"], idx, "\n".join(lines)))

# pack into batches of roughly equal thread counts
BATCH_TARGET = 22
batches, cur, cur_n = [], [], 0
for d in dossiers:
    if cur and cur_n + d[2] > BATCH_TARGET:
        batches.append(cur); cur, cur_n = [], 0
    cur.append(d); cur_n += d[2]
if cur:
    batches.append(cur)
for i, b in enumerate(batches, 1):
    with open(os.path.join(OUT, f"batch-{i:02d}.md"), "w") as f:
        f.write("\n\n---\n\n".join(d[3] for d in b))
    print(f"batch-{i:02d}: {len(b)} PRs, {sum(d[2] for d in b)} threads: " + ", ".join(f"{d[0]}#{d[1]}" for d in b))
print(f"total PRs {len(dossiers)}, threads {sum(d[2] for d in dossiers)}")
