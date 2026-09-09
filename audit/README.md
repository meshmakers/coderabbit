# Review-bot audit

Measures how useful the AI reviews (CodeRabbit, GitHub Copilot) on the
organization's pull requests actually are, so that the central configuration
in this repository can be tuned on evidence instead of impressions. First run:
2026-09-09 (`reports/2026-09-09-first-weeks.html`).

## What is measured

Deterministic layer, from the GitHub API:

- **Coverage** — per human PR: reviewed by CodeRabbit, summary only, skipped
  (with the reason CodeRabbit gives: draft, base branch, star rule), absent;
  the same for Copilot.
- **Volume and noise** — review runs per PR (each push is one run and counts
  against the hourly allowance), actionable and nitpick counts, duplicate and
  outside-diff comments, rate-limit and overage markers, chat-limit hits.
- **Findings** — one row per inline thread: severity and category from the
  comment header, author reply, bot confirmation or withdrawal, resolution
  state, reactions, whether path instructions or learnings were cited.
- **Process signals** — pre-merge check results (title convention), learnings
  added and used, "couldn't resolve thread" messages, latency to the first
  review versus time to merge, human review presence.

Judgement layer, run by Claude Code agents over PR dossiers:

- every thread is classified as substantive, correct-but-minor, invalid or
  unverifiable, with the observed outcome, the root cause when invalid, and the
  configuration lever (path instruction, standards document, learning, path
  filter, quiet profile, tool toggle) that would have prevented or sharpened it;
- a skeptic agent then tries to refute every "invalid" verdict.

## Targets

| KPI | Definition | Target | Baseline 2026-09-09 |
| --- | --- | --- | --- |
| Coverage | human PRs with a CodeRabbit review | ≥ 90 % | 73 % (66 of 90 since the org rollout) |
| Substantive rate | threads judged substantive | ≥ 45 % | 38 % (43 of 112) |
| Wrong rate | threads judged invalid after the skeptic pass | ≤ 10 % | 18 % (20 of 112) |
| Overage | PRs billed beyond the hourly allowance | 0 | 7 |
| Repeat false positives | same wrong claim in ≥ 2 repos | 0 | 4 patterns (15 threads) |

## How to run

Prerequisites: `gh` authenticated for the organization, Python 3.9+, and for
the classification step a Claude Code session with the Workflow tool.

```bash
cd audit
export CR_AUDIT_DATA=$PWD/data          # default; git-ignored
export CR_AUDIT_SINCE=2026-09-09        # start of the window (PR creation date)

python3 dump_prs.py                     # GraphQL dump into data/prs/<repo>-<n>.json
python3 dump_rest.py                    # REST fallback when the GraphQL budget is exhausted (same layout, no resolved flags)
python3 patch_resolved.py               # fills resolved flags for REST-dumped PRs once the GraphQL budget is back
python3 metrics.py                      # coverage/noise/findings tables; writes data/per_pr.json + data/findings.json
python3 make_batches.py                 # PR dossiers for the agents: data/batches/batch-NN.md (prints the batch list)
```

Then, in Claude Code, run `classify-workflow.js` (usage header inside the
file), copy the workflow's `result` object to `data/classification.json`, and:

```bash
python3 aggregate_classification.py     # verdict tables, invalid findings, concrete rule proposals
```

The rule proposals printed at the end are the input for changes to
`../.coderabbit.yaml` and `../standards/`.

## Gotchas

- GraphQL cost is the product of the nested `first:` limits; the first attempt
  (threads 100 × comments 50 × reactions 20) burned the 5000-point hourly
  budget after about 96 PRs. The shipped query stays under ~20 points per PR.
  `dump_rest.py` exists for the rest of the hour.
- Both dump scripts skip PRs whose file already exists, so they can be re-run
  to continue.
- The agents need read-only checkouts to judge threads without an author
  reply; point `CR_AUDIT_CHECKOUTS` at the workspace folder (one checkout per
  repository) before running `make_batches.py`, and pass the same path as
  `checkouts` to the workflow.
- Acceptance measured from replies alone overstates value: on the first run
  53 % of threads were "fixed", but only 38 % were substantive — the rest were
  compliance with wording nits. Always run the judgement layer.
