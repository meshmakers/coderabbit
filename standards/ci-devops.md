# CI / DevOps standards

Applies to `azure-pipelines*.yml`, `Directory.Build.props`, Helm charts,
deployment repos, PowerShell tooling, Docker base images, and documentation.

## Azure DevOps CI shape (uniform across ~26 repos)

- Build-number name format is fixed:
  `$(MajorVersion).$(MinorVersion).$(date:yyMM).$(DayOfMonth)$(rev:rrr)-$(Build.SourceBranchName)`
  — downstream templates parse it (chart-version derivation, versioninfo).
  Flag deviations. Pool is `meshmakers-ci-agents` (octo-documentation's
  hosted-pool pipelines are the deliberate exception). Triggers: `dev/*`,
  `test/*`, `main` with batch:true; releases flow through `r*` tags queued by
  the release trains in octo-mesh-deployment, which inject
  `octoCoreLibVersion`/`octoCommVersion` parameters — flag a missing parameter
  block.
- Shared CI templates come from `octo-pipeline-templates`, pinned as
  `ref: refs/tags/tpl-vX.Y.Z` — never a branch; a pin bump is a deliberate,
  reviewable change. Exception: `helm-chart-build` ci-templates are
  deliberately consumed from main. In octo-pipeline-templates itself, every
  template change needs a CHANGELOG entry and a `tpl-v*` tag; parameter-shape
  changes are MAJOR (~30 consumers).
- Repos containing ConstructionKit YAML wire
  `validate-ck-versions.yml@pipelineTemplates` AFTER
  update-build-number/set-version and BEFORE the dotnet build step, with every
  CK folder listed in `constructionKitPaths` in dependency order. Blueprint
  repos get `validate-blueprints.yml` (published blueprint versions are
  immutable; content change without a blueprint.yaml bump fails).
- Pipeline PowerShell gating dotnet tools (octo-ckc, octo-bpm): check
  `$LASTEXITCODE -ne 0`, never `-eq 1` (tools exit -6, surfacing as 250), and
  upload report artifacts BEFORE the gate.

## DebugL version contract

`Directory.Build.props` DebugL blocks pin Version/PackageVersion and all
Octo*Version properties to 999.0.0 and prepend the workspace `../nuget` to
RestoreSources. Never hardcode a concrete release version into
`OctoCoreLibVersion`/`OctoCommVersion` — those pins are injected by the CI
template and the release trains; the in-repo fallback stays a floating range.

## Helm charts and publishing

- `helm package` receives the 3-segment `$(ChartVersion)` (derived via
  derive-chart-version.yml) as chart version while `--app-version` stays the
  raw 4-segment `$(Build.BuildNumber)` — helm rejects 4-segment versions, and
  hand-rolled version math must preserve leading zeros / segment padding
  (un-padded patches sorted BELOW older ones and helm installed stale charts).
- Chart publish steps require explicit conditions: dev channel on
  `eq(variables.isMain, true)`, release channel on
  `eq(variables.isRelease, true)` plus the right chartCategory — the
  template's permissive default once shipped an unmerged PR chart to test-2.
  Published (chart, version) pairs are immutable: a SHA mismatch on republish
  hard-fails; the fix is a version bump, never a force overwrite.
- **Operator ↔ chart contract**: the communication operator passes its
  cluster-context YAML as the FIRST `-f` (lowest precedence), the workload's
  own ValuesYaml overrides it, structured per-value overrides win. Flag chart
  PRs (octo-helm-core/pro) renaming/removing keys the operator injects
  (image.*, tenantId, adapterRtId — kept for Applications too,
  communicationControllerServiceUri, clusterDependencies.*, secrets.rabbitmq,
  secrets.rootCa as a plain literal) and operator PRs adding context values
  without the paired chart change (the pattern is a paired AB# commit in both
  repos). The CommunicationPool CRD YAML ships from octo-helm-core
  (octo-mesh-crds) — operator spec changes need regeneration there.

## Deployment repos

- octo-mesh-deployment CD stacks helm values in fixed order:
  `base/values-<svc>.yaml` → `clusters/<cluster>/values-<svc>.yaml` → extras →
  secrets JSON (last -f wins). A new chart key that needs per-cluster values
  must land in EVERY cluster overlay directory that carries a values file for
  that chart (test-2, staging-1, prod-1, prod-2 — plus edge-test for the
  communication-operator chart) in one change — a missing overlay key
  silently falls back on that cluster only.
- Any PR touching octo-mesh-deployment `pipelines/` must include the matching
  Release-Trains wiki update; files under `manifests/` are append-only audit
  records — flag edits or deletions.
- Ansible: never use a Jinja expression as a dict KEY (registry pull-secret
  `auths` maps) — Ansible stores templated keys literally and kubelet falls
  back to anonymous pulls. Build the dict inside a single Jinja expression.

## PowerShell tooling (octo-tools)

- New `modules/*.psm1` must be added to the Import-Module list in
  `modules/profile.ps1` — modules are not auto-discovered.
- Machine-readable output goes through `Write-OctoJson`/`New-OctoActionResult`
  — raw `ConvertTo-Json` (default -Depth 2) silently truncates nested data.
- Confirmation prompts need a `-Force` bypass and must refuse to prompt in
  `-Json` mode; commands meant for agents/CI need a `-nonInteractive` path
  (Start-Octo pattern: stop-signal file, never a keypress).
- Never emit kubeconfigs or tokens in `-Json` output.
- Do not trust `Invoke-BuildAll`'s exit code or return value — success is only
  the `Percentage of successful builds: 100%` line (or
  `summary.percentSuccessful` in -Json mode).

## Docker base images (dockerimages)

Keep `linux/arm64,linux/amd64` multi-arch and pushes to BOTH Docker Hub and
the private registry (edge devices run arm64); build jobs need an explicit
`timeoutInMinutes` ≥ 120. The `http://` Hetzner APT-mirror rewrite is
deliberate (ca-certificates not yet installed; APT verifies signatures) — do
not "fix" it to https.

## Machine-owned catalog repos

blueprint-libraries-build, construction-kit-libraries-build, and
helm-chart-build's gh-pages content are written by CI and the release trains —
flag manual content commits (published versions are immutable). Their
`pages.yml` workflows must keep the serialization pattern (`concurrency:
group: pages, cancel-in-progress: false`, HEAD guard, retry-wrapped deploy).

## Documentation repo (octo-documentation)

Three directories are auto-harvested and overwritten by a scheduled pipeline
(apiReference, CK libraries, octo-cli command reference) — hand edits there
are lost; the fix belongs in the producing repo (e.g. octo-cli
`GetDocumentation()`). Handwritten pages linking into git-ignored generated
pages use `pathname:///docs/...` absolute links; everywhere else relative
`.md` links so the strict broken-link build keeps catching typos.
