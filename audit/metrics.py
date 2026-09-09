#!/usr/bin/env python3
"""Deterministic metrics over the PR dumps: CodeRabbit vs Copilot coverage, findings, outcomes, noise, timing."""
import json, glob, os, re, sys

ORG = os.environ.get("CR_AUDIT_ORG", "meshmakers")
DATA = os.environ.get("CR_AUDIT_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
from collections import Counter, defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CR = "coderabbitai"
CP = "copilot-pull-request-reviewer"
BOTS = {CR, CP, "Copilot", "dependabot", "github-actions", "azure-pipelines"}
HUMANS_OK = None  # any non-bot login counts as human

SEVERITY = {"🔴": "critical", "🟠": "major", "🟡": "minor", "🔵": "trivial"}
FIX_WORDS = re.compile(r"\b(fixed|done|addressed|applied|trimmed|removed|added|changed|updated|parenthesized|replaced|renamed|moved|restored|dropped|kept|implemented|switched|extracted|guarded|reverted|resolved) in\b|\bin ([0-9a-f]{7,40})\b|\bfixed\b|\bdone\b|\bapplied\b|\baddressed\b|\bgood catch\b|\bagreed\b|\bthanks\b|\bcorrect\b", re.I)
REJECT_WORDS = re.compile(r"\b(not applicable|false positive|intentional|by design|accepted trade-?off|acknowledged as|won'?t fix|wontfix|out of scope|not needed|unnecessary|disagree|incorrect|wrong|misread|no change|keep(ing)? as is|deliberate|expected)\b", re.I)
CR_WITHDRAW = re.compile(r"withdraw|retract|not applicable|inapplicable|you'?re right|you are right|my mistake|I stand corrected|no longer applies|is (correct|valid) as", re.I)
CR_CONFIRM = re.compile(r"confirmed|verified|acknowledged|addressed|resolved|looks good", re.I)


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ") if s else None


def login(x):
    return (x or {}).get("login") if isinstance(x, dict) else None


def thread_author(t):
    cs = t["comments"]["nodes"]
    return login(cs[0]["author"]) if cs else None


def parse_cr_finding(body):
    """Extract category/severity/effort from the first line of a CodeRabbit inline comment."""
    m = re.search(r"_([^_]+?)_ \| _([🔴🟠🟡🔵])\s*([A-Za-z]+)_(?: \| _([^_]+)_)?", body)
    if not m:
        return None, None, None
    return m.group(1).strip(), SEVERITY.get(m.group(2), m.group(3).lower()), (m.group(4) or "").strip()


def classify_thread(t, pr_author):
    """Outcome of one reviewer thread based on replies, resolution, reactions."""
    cs = t["comments"]["nodes"]
    root = cs[0]
    bot = login(root["author"])
    human_replies = [c for c in cs[1:] if login(c["author"]) not in BOTS]
    bot_replies = [c for c in cs[1:] if login(c["author"]) == bot]
    reactions = Counter(r["content"] for c in cs[:1] for r in c.get("reactions", {}).get("nodes", []))
    text = " ".join(c["body"] for c in human_replies)
    outcome = None
    if human_replies:
        if REJECT_WORDS.search(text) and not re.search(r"\bfixed in\b|\bdone in\b|\baddressed in\b", text, re.I):
            outcome = "rejected"
        elif FIX_WORDS.search(text):
            outcome = "accepted"
        else:
            outcome = "discussed"
    if bot_replies and CR_WITHDRAW.search(" ".join(c["body"] for c in bot_replies)):
        outcome = "withdrawn"
    if outcome is None:
        if reactions.get("THUMBS_DOWN") or reactions.get("-1"):
            outcome = "rejected"
        elif reactions.get("THUMBS_UP") or reactions.get("+1"):
            outcome = "accepted"
        elif t.get("isResolved") and login(t.get("resolvedBy")) not in BOTS and login(t.get("resolvedBy")):
            outcome = "resolved-silently"
        elif t.get("isOutdated"):
            outcome = "outdated-silently"
        elif t.get("isResolved") is None:
            outcome = "unknown-no-reply"
        else:
            outcome = "ignored"
    return outcome, human_replies, bot_replies


def main():
    files = sorted(glob.glob(os.path.join(DATA, "prs", "*.json")))
    prs = [json.load(open(f)) for f in files]
    print(f"PRs loaded: {len(prs)}")

    per_pr = []
    findings = []  # one row per reviewer thread
    for pr in prs:
        repo, num = pr["repo"], pr["number"]
        vis = "private" if pr["repoIsPrivate"] else "public"
        author = login(pr["author"])
        created = ts(pr["createdAt"])
        cr_comments = [c for c in pr["comments"]["nodes"] if login(c["author"]) == CR]
        cr_reviews = [r for r in pr["reviews"]["nodes"] if login(r["author"]) == CR]
        cp_reviews = [r for r in pr["reviews"]["nodes"] if login(r["author"]) == CP]
        human_reviews = [r for r in pr["reviews"]["nodes"] if login(r["author"]) not in BOTS and login(r["author"]) != author]
        cr_threads = [t for t in pr["reviewThreads"]["nodes"] if thread_author(t) == CR]
        cp_threads = [t for t in pr["reviewThreads"]["nodes"] if thread_author(t) == CP]
        human_threads = [t for t in pr["reviewThreads"]["nodes"] if thread_author(t) not in BOTS]

        # CodeRabbit status on this PR
        cr_status = "absent"
        skip_reason = None
        for c in cr_comments:
            b = c["body"]
            if "fewer than 10 stars" in b:
                cr_status = "skipped-lt10stars"
            elif "skip review by coderabbit" in b and cr_status == "absent":
                cr_status = "skipped-other"
                m = re.search(r"> (This repository[^\n]*|Review skipped[^\n]*|[^\n]*skipped[^\n]*)", b)
                skip_reason = m.group(1)[:120] if m else None
            elif "summarize by coderabbit" in b and cr_status == "absent":
                cr_status = "summarized"
        review_bodies = [r["body"] for r in cr_reviews if r["body"]]
        all_cr_text = "\n".join(review_bodies + [c["body"] for c in cr_comments])
        if any("Actionable comments posted" in b or "Nitpick comments" in b for b in review_bodies) or re.search(r"(Recent review info|ℹ️ Review info)", all_cr_text):
            cr_status = "reviewed"
        actionable = sum(int(m.group(1)) for b in review_bodies for m in [re.search(r"Actionable comments posted: (\d+)", b)] if m)
        nitpicks = sum(int(m.group(1)) for b in review_bodies for m in re.finditer(r"Nitpick comments \((\d+)\)", b))
        duplicates = sum(int(m.group(1)) for b in review_bodies for m in re.finditer(r"Duplicate comments \((\d+)\)", b))
        outside = sum(int(m.group(1)) for b in review_bodies for m in re.finditer(r"Outside diff range comments \((\d+)\)", b))
        all_thread_text = "\n".join(c["body"] for t in cr_threads for c in t["comments"]["nodes"])
        learnings_added = len(re.findall(r"Learnings added", all_thread_text + all_cr_text))
        learnings_used = len(re.findall(r"Learnt from:", all_thread_text + all_cr_text))
        guideline_refs = sum(len(re.findall(r"As per (path instructions|coding guidelines)|Based on (learnings|coding guidelines)", c["body"], re.I)) for t in cr_threads for c in t["comments"]["nodes"][:1])
        pm = re.search(r"Pre-merge checks \|([^<\n]*)", all_cr_text)
        premerge_summary = pm.group(1).strip() if pm else None
        premerge_fail = bool(pm and re.search(r"❌|⚠️", pm.group(1)))
        tm = re.search(r"(✅|❌|⚠️) (Passed|Failed|Warning)[^\n]*\| (The title[^\n]{0,200})", all_cr_text)
        title_verdict = (tm.group(1) + " " + tm.group(3)[:160]) if tm else None
        title_ok = bool(re.match(r"^AB#\d+ (Fix|New|Chore|Refactor|Test|Docs): ", pr["title"]))
        actions_performed = len(re.findall(r"Action performed", all_cr_text))
        review_skipped_reason = None
        rs = re.search(r"Review skipped[^\n]*\n+>?\s*([^\n]{0,160})", all_cr_text)
        if rs:
            review_skipped_reason = rs.group(1)
        cant_resolve = sum(1 for t in cr_threads for c in t["comments"]["nodes"] if "couldn't resolve this review thread" in c["body"])
        rate_limited = sum(1 for c in cr_comments if re.search(r"Review rate limited|Rate Limit Exceeded", c["body"]))
        overage_billed = sum(1 for c in cr_comments if "billed for reviews past your plan" in c["body"])
        chat_limited = sum(1 for c in cr_comments if "limit for the number of chat messages" in c["body"])

        first_cr = min([ts(r["createdAt"]) for r in cr_reviews] + [ts(c["createdAt"]) for c in cr_comments if "summarize by coderabbit" in c["body"]], default=None)
        first_cp = min([ts(r["createdAt"]) for r in cp_reviews], default=None)
        human_comments = [c for c in pr["comments"]["nodes"] if login(c["author"]) not in BOTS]
        cr_addressed_cmds = sum(1 for c in human_comments if "@coderabbitai" in c["body"])

        base = pr["baseRefName"]
        base_kind = "default" if base in ("main", "master") else ("release" if base.startswith("release/") else ("test" if base.startswith("test/") else "other"))
        row = dict(repo=repo, num=num, vis=vis, author=author, title=pr["title"], state=pr["state"], created=pr["createdAt"][:10], base=base, base_kind=base_kind,
                   merged=pr["merged"], commits=pr["commits"]["totalCount"], adds=pr["additions"], dels=pr["deletions"], files=pr["changedFiles"],
                   cr_status=cr_status, skip_reason=skip_reason, cr_reviews=len(cr_reviews), cr_actionable=actionable, cr_nitpicks=nitpicks,
                   cr_duplicates=duplicates, cr_outside=outside, cr_threads=len(cr_threads), cp_reviews=len(cp_reviews), cp_threads=len(cp_threads),
                   human_reviews=len(human_reviews), human_threads=len(human_threads), learnings_added=learnings_added, learnings_used=learnings_used,
                   guideline_refs=guideline_refs, premerge_flag=premerge_fail, premerge_summary=premerge_summary, title_verdict=title_verdict,
                   title_ok=title_ok, cant_resolve=cant_resolve, rate_limited=rate_limited, overage_billed=overage_billed, chat_limited=chat_limited,
                   actions_performed=actions_performed, review_skipped_reason=review_skipped_reason,
                   cr_latency_min=round((first_cr - created).total_seconds() / 60, 1) if first_cr else None,
                   cp_latency_min=round((first_cp - created).total_seconds() / 60, 1) if first_cp else None,
                   cr_commands=cr_addressed_cmds, source=pr.get("source", "graphql"))
        per_pr.append(row)

        for bot, threads in ((CR, cr_threads), (CP, cp_threads)):
            for t in threads:
                root = t["comments"]["nodes"][0]
                cat, sev, effort = parse_cr_finding(root["body"]) if bot == CR else (None, None, None)
                outcome, hr, br = classify_thread(t, author)
                title_m = re.search(r"\*\*(.+?)\*\*", root["body"])
                findings.append(dict(repo=repo, num=num, vis=vis, pr_author=author, bot="CR" if bot == CR else "Copilot", path=t.get("path"), line=t.get("line"),
                                     category=cat, severity=sev, effort=effort, outcome=outcome, human_replies=len(hr), bot_replies=len(br),
                                     resolved=t.get("isResolved"), outdated=t.get("isOutdated"), resolved_by=login(t.get("resolvedBy")),
                                     tool_backed=("Supported by static analysis" in root["body"] or "Script executed" in root["body"]),
                                     guideline_ref=bool(re.search(r"As per (path instructions|coding guidelines)|Based on learnings", root["body"], re.I)),
                                     title=(title_m.group(1)[:140] if title_m else root["body"].strip().split("\n")[0][:140]),
                                     created=root["createdAt"]))

    json.dump(per_pr, open(os.path.join(DATA, "per_pr.json"), "w"), indent=1)
    json.dump(findings, open(os.path.join(DATA, "findings.json"), "w"), indent=1)

    # ---- report ----
    def pct(a, b):
        return f"{100 * a / b:.0f}%" if b else "n/a"

    print("\n== Coverage (PRs created since 2026-08-20) ==")
    c = Counter((r["vis"], r["cr_status"]) for r in per_pr)
    for k in sorted(c):
        print(f"  {k[0]:8} {k[1]:20} {c[k]}")
    cp_cov = Counter((r["vis"], r["cp_reviews"] > 0) for r in per_pr)
    print("  Copilot reviewed:", dict(cp_cov))
    nondep_all = [r for r in per_pr if r["author"] != "dependabot"]
    print(f"  non-dependabot PRs: {len(nondep_all)}  CR reviewed: {sum(1 for r in nondep_all if r['cr_status'] == 'reviewed')}  Copilot reviewed: {sum(1 for r in nondep_all if r['cp_reviews'])}  both: {sum(1 for r in nondep_all if r['cp_reviews'] and r['cr_status'] == 'reviewed')}  neither: {sum(1 for r in nondep_all if not r['cp_reviews'] and r['cr_status'] != 'reviewed')}")
    print("  base branch kinds (non-dependabot):", dict(Counter((r["base_kind"], r["cr_status"]) for r in nondep_all if r["base_kind"] != "default")))
    print("  non-default-base PRs:", "; ".join(f"{r['repo']}#{r['num']} base={r['base']} cr={r['cr_status']}" for r in nondep_all if r["base_kind"] != "default"))
    repo_cov = defaultdict(Counter)
    for r in nondep_all:
        repo_cov[r["repo"]]["prs"] += 1
        repo_cov[r["repo"]]["cr"] += 1 if r["cr_status"] == "reviewed" else 0
        repo_cov[r["repo"]]["cp"] += 1 if r["cp_reviews"] else 0
    print("  per-repo coverage (prs/CR/Copilot): " + ", ".join(f"{k}={v['prs']}/{v['cr']}/{v['cp']}" for k, v in sorted(repo_cov.items(), key=lambda kv: -kv[1]['prs'])))
    by_week = defaultdict(Counter)
    for r in per_pr:
        by_week[r["created"][:10]][r["cr_status"]] += 1
    print("\n== CodeRabbit status per PR creation day ==")
    for d in sorted(by_week):
        print(f"  {d}: {dict(by_week[d])}")

    reviewed = [r for r in per_pr if r["cr_status"] == "reviewed"]
    print(f"\n== CodeRabbit reviewed PRs: {len(reviewed)} ==")
    tot = lambda k: sum(r[k] or 0 for r in reviewed)
    print(f"  reviews posted: {tot('cr_reviews')}  actionable: {tot('cr_actionable')}  nitpicks: {tot('cr_nitpicks')}  duplicates: {tot('cr_duplicates')}  outside-diff: {tot('cr_outside')}  inline threads: {tot('cr_threads')}")
    print(f"  PRs with 0 actionable: {sum(1 for r in reviewed if r['cr_actionable'] == 0)}  learnings added: {tot('learnings_added')}  learnings used: {tot('learnings_used')}  guideline refs: {tot('guideline_refs')}  cant-resolve msgs: {tot('cant_resolve')}")
    print(f"  rate-limited PRs: {sum(1 for r in per_pr if r['rate_limited'])}  overage-billed PRs: {sum(1 for r in per_pr if r['overage_billed'])} (files in those PRs: {sum(r['files'] or 0 for r in per_pr if r['overage_billed'])})  chat-limited PRs: {sum(1 for r in per_pr if r['chat_limited'])}")
    print("  reviews per PR (CR incremental): " + ", ".join(f"{r['repo']}#{r['num']}={r['cr_reviews']}" for r in sorted(reviewed, key=lambda r: -r['cr_reviews'])[:8]))
    print("  per-day CR review events: " + str(Counter(r['created'] for r in reviewed for _ in range(r['cr_reviews']))))
    nondep = [r for r in per_pr if r["author"] != "dependabot"]
    print(f"  title convention ok (non-dependabot): {sum(1 for r in nondep if r['title_ok'])}/{len(nondep)}  premerge flagged: {sum(1 for r in per_pr if r['premerge_flag'])}  premerge summaries: {Counter(r['premerge_summary'] for r in per_pr if r['premerge_summary'])}")
    print("  title-check verdicts on PRs whose title breaks the convention:")
    for r in nondep:
        if not r["title_ok"] and r["cr_status"] in ("reviewed", "summarized"):
            print(f"     {r['repo']}#{r['num']} '{r['title'][:50]}' -> {r['title_verdict']}")
    print(f"  manual actions performed (@coderabbitai cmds / checkbox): {sum(r['actions_performed'] for r in per_pr)} on {sum(1 for r in per_pr if r['actions_performed'])} PRs")
    lat = [r["cr_latency_min"] for r in reviewed if r["cr_latency_min"] is not None]
    latp = [r["cp_latency_min"] for r in per_pr if r["cp_latency_min"] is not None]
    if lat:
        lat.sort(); latp.sort()
        print(f"  latency to first CR review (min): median {lat[len(lat)//2]}  p90 {lat[int(len(lat)*0.9)]}   Copilot: median {latp[len(latp)//2] if latp else None}")

    print("\n== Findings by bot / outcome ==")
    for bot in ("CR", "Copilot"):
        fs = [f for f in findings if f["bot"] == bot]
        oc = Counter(f["outcome"] for f in fs)
        print(f"  {bot}: {len(fs)} threads  {dict(oc)}")
        print(f"     replied-to by human: {pct(sum(1 for f in fs if f['human_replies']), len(fs))}  accepted: {pct(oc['accepted'], len(fs))}  rejected+withdrawn: {pct(oc['rejected'] + oc['withdrawn'], len(fs))}")
    print("\n== CR findings by severity / outcome ==")
    sev = defaultdict(Counter)
    for f in findings:
        if f["bot"] == "CR":
            sev[f["severity"] or "?"][f["outcome"]] += 1
    for s in ("critical", "major", "minor", "trivial", "?"):
        if sev[s]:
            print(f"  {s:9} {sum(sev[s].values()):3}  {dict(sev[s])}")
    print("\n== CR findings by category ==")
    cat = defaultdict(Counter)
    for f in findings:
        if f["bot"] == "CR":
            cat[f["category"] or "?"][f["outcome"]] += 1
    for k, v in sorted(cat.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"  {k:40} {sum(v.values()):3}  {dict(v)}")
    print("\n== per PR author (CR threads / human reply rate / accepted) ==")
    au = defaultdict(lambda: Counter())
    for f in findings:
        if f["bot"] == "CR":
            au[f["pr_author"]]["threads"] += 1
            au[f["pr_author"]]["replied"] += 1 if f["human_replies"] else 0
            au[f["pr_author"]]["accepted"] += 1 if f["outcome"] == "accepted" else 0
            au[f["pr_author"]]["rejected"] += 1 if f["outcome"] in ("rejected", "withdrawn") else 0
    for a, v in sorted(au.items(), key=lambda kv: -kv[1]["threads"]):
        print(f"  {a:20} threads={v['threads']:3} replied={pct(v['replied'], v['threads'])} accepted={pct(v['accepted'], v['threads'])} rejected={pct(v['rejected'], v['threads'])}")

    # overlap CR vs Copilot: same PR, same path, |line diff| <= 8
    print("\n== CR vs Copilot overlap (same PR+path, lines within 8) ==")
    both = [r for r in per_pr if r["cr_threads"] and r["cp_threads"]]
    overlap = 0
    cr_only = 0
    cp_only = 0
    for r in both:
        crf = [f for f in findings if f["bot"] == "CR" and f["repo"] == r["repo"] and f["num"] == r["num"]]
        cpf = [f for f in findings if f["bot"] == "Copilot" and f["repo"] == r["repo"] and f["num"] == r["num"]]
        matched_cp = set()
        for a in crf:
            hit = None
            for i, b in enumerate(cpf):
                if i in matched_cp or a["path"] != b["path"] or a["line"] is None or b["line"] is None:
                    continue
                if abs(a["line"] - b["line"]) <= 8:
                    hit = i
                    break
            if hit is None:
                cr_only += 1
            else:
                overlap += 1
                matched_cp.add(hit)
        cp_only += len(cpf) - len(matched_cp)
    print(f"  PRs with both reviewers commenting inline: {len(both)}  overlap pairs: {overlap}  CR-only: {cr_only}  Copilot-only: {cp_only}")

    print("\n== PRs reviewed by CR (sorted by threads) ==")
    for r in sorted(reviewed, key=lambda r: -r["cr_threads"]):
        print(f"  {r['repo']}#{r['num']:<4} {r['vis'][:3]} {r['author']:<18} commits={r['commits']:<2} +{r['adds']:<5} CRrev={r['cr_reviews']:<2} act={r['cr_actionable']:<2} nit={r['cr_nitpicks']:<2} thr={r['cr_threads']:<2} CP={r['cp_threads']:<2} human={r['human_threads']:<2} learn+={r['learnings_added']} | {r['title'][:70]}")


if __name__ == "__main__":
    main()
