# coderabbit

Central [CodeRabbit](https://docs.coderabbit.ai/configuration/central-configuration)
configuration for the `meshmakers` organization.

> The repository name must stay `coderabbit`. CodeRabbit resolves the central
> configuration by that exact name, and CodeRabbit must remain installed on
> this repository or the file below is never read.

## What this does

`.coderabbit.yaml` in this repository applies to **every repository in the
organization that does not ship its own `.coderabbit.yaml`**. Change the
review behaviour for all repositories by opening a pull request here, rather
than touching each repository individually.

`standards/` holds the distilled OctoMesh knowledge that spans repositories —
above all the cross-repo relationships (NuGet dependency chain, serialization
parity, blueprint/pipeline contracts, CI conventions) that a reviewer inside a
single repository cannot see. Each file is listed in
`knowledge_base.code_guidelines.filePatterns` as an entry with `files`
(`coderabbit:standards/<name>.md`) and `applyTo` (the globs of the files it
governs). `applyTo` is required: a guideline file from another repository has
no directory scope in the reviewed repository, and without it CodeRabbit
extracts the rules but applies none of them. A new standards file needs its own
entry. The review summary lists the applied files under "Additional context
used → Code guidelines" and any skipped source under "Skipped guideline
sources". This uses CodeRabbit's generic `repo:path` cross-repository guideline syntax
(this repo just happens to be named `coderabbit`); files are read from this
repository's **default branch**, and CodeRabbit reads at most 50 guideline
files per review — keep `standards/` well below that.

Repository-local `CLAUDE.md` files (and AGENTS.md, .cursorrules, …) are
auto-detected by CodeRabbit and applied **in addition**; matching is
case-sensitive, and custom patterns extend the defaults rather than replacing
them. Repo-specific rules therefore belong in the repo's own `CLAUDE.md`;
`standards/` carries only what spans repositories.

Cross-repository code context comes from `knowledge_base.automatic_linking_mode:
auto` (private repositories may link private and public ones, public
repositories only public ones). A manual `linked_repositories` list is not used:
the plan analyzes at most **10** linked repositories, a fixed list gives every
repository the same links whether relevant or not, and CodeRabbit warns on
every review once the list exceeds the limit. Check what a review actually used
in its walkthrough section "Linked repositories identified"; manual links are
additive and can be reintroduced per repository if auto-linking misses a
contract-owning repository.

## Approval and the merge gate

CodeRabbit is the approving reviewer of the organization
(`reviews.auto_approvals.enabled: true`). It requests changes when a review
has actionable findings and approves once they are resolved and the pre-merge
checks pass. The organization ruleset `require-pr-for-main` requires one
approving review on the default branch, so this approval is what normally
unblocks a merge; an approval by a person satisfies the rule as well.

- A title that does not match `AB#<id> <Fix|New|Chore|Refactor|Test|Docs>: …`
  fails the title check, and CodeRabbit then withholds its approval.
- After a push CodeRabbit reviews only the new commits. When nothing
  reviewable changed (for example a pure rebase) it skips, and no new approval
  follows — comment `@coderabbitai full review` on the pull request.
- After fixing or answering a finding, resolve the thread yourself or comment
  `@coderabbitai resolve` to mark all of CodeRabbit's threads resolved.

## Configuration precedence

CodeRabbit resolves settings top-down; **without inheritance, only the
highest-priority source that exists is used** (no merging). Global overrides
are the exception: they are applied per-key as a final layer on top of
whatever else resolved.

| Priority | Source |
| -------- | ------ |
| 1 | Organization global overrides (web UI, org admins only — per-key, always win) |
| 2 | A repository's own `.coderabbit.yaml` (read from the feature branch under review) |
| 3 | **This repository's `.coderabbit.yaml`** |
| 4 | Repository settings in the web UI |
| 5 | Organization settings in the web UI |
| 6 | Defaults (schema) |

(Enterprise workspace layers omitted — not in use here.) Prefer this file over
the web UI so that review configuration is versioned and reviewable like the
rest of the code.

## Overriding for a single repository

A repository that needs an exception adds its own `.coderabbit.yaml` with
`inheritance: true` **at root level** (any position in the file). With the
flag, the repo file merges on top of this configuration; without it, the local
file replaces the central configuration entirely.

Merge semantics with inheritance enabled: objects deep-merge (child wins per
key), arrays take the child's items first and append unique parent items
(deduplicated by `path`/`label`/`name`/`id`/`key` — so a repo
`path_instructions` entry with the same `path` replaces the central one),
scalars are child-wins.

```yaml
# yaml-language-server: $schema=https://coderabbit.ai/integrations/schema.v2.json
inheritance: true

reviews:
  path_filters:
    - "!**/*.snapshot.json"
```

## Verifying what is in effect

Comment `@coderabbitai configuration` on any pull request. CodeRabbit replies
with the resolved YAML, annotated with the source each value came from. On
repos without their own file, the review comment's configuration source should
read `Repository: coderabbit/.coderabbit.yaml`.

Other useful commands:

| Command | Effect |
| ------- | ------ |
| `@coderabbitai review` / `full review` | Review new changes / all files from scratch |
| `@coderabbitai pause` / `resume` | Stop and restart automatic reviews on one PR |
| `@coderabbitai generate configuration` | PR that adds the currently resolved config as `.coderabbit.yaml` |
| `@coderabbitai emit path instructions` | PR with CodeRabbit's suggested `path_instructions` from the last 7 days |
| `@coderabbitai resolve` | Mark all CodeRabbit comments resolved |
| `@coderabbitai rate limit` | Show the remaining review allowance |

## Maintaining this configuration

- **Observe first**: prefer harvesting real review gaps (via
  `@coderabbitai emit path instructions` on active PRs) over writing
  speculative rules.
- Learnings are shared org-wide (`learnings.scope: global`) and managed at
  app.coderabbit.ai/learnings — delete bad ones there.
- Azure Boards note: linked-work-item assessment is only documented for Azure
  DevOps-hosted PRs. Recognition of `AB#<n>` references on GitHub PRs is
  undocumented — the AB# title convention is enforced via
  `pre_merge_checks.title` instead.
- When updating `standards/`, keep claims verifiable and current; stale rules
  (e.g. superseded framework versions) actively mislead reviews. The files
  were last verified against the codebase on 2026-09-09.

## Editing the configuration

The file carries a `yaml-language-server` schema reference, so an editor with
YAML support validates it while you type. To check it from the command line:

```bash
curl -sL https://coderabbit.ai/integrations/schema.v2.json -o schema.json
python3 -c "
import json, yaml, jsonschema
jsonschema.Draft202012Validator(json.load(open('schema.json'))).validate(
    yaml.safe_load(open('.coderabbit.yaml')))
print('valid')"
```
