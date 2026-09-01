# OctoMesh organization standards

OctoMesh is an industrial data mesh platform built by meshmakers. These files
hold the knowledge that spans repositories — the context a reviewer inside one
repository cannot see. Individual repositories additionally carry their own
`CLAUDE.md`, which CodeRabbit reads automatically; repo-local rules are not
repeated here.

## Repository topology

OctoMesh is **not a monorepo**. Each `octo-*` repository is independent, ships
its own solution, and publishes NuGet packages (backend) or npm packages
(frontend) that sibling repositories consume. Developers check all repos out
side by side into one workspace folder, but nothing in that folder is shared
through source control.

Consequence for review: **a change in one repository can break other
repositories that are not part of the pull request**, and the break only
surfaces on the consumer's next build. This is the single most important review
lens for shared-library changes.

## The NuGet dependency chain

Shared libraries are consumed with floating package versions (999.0.0 locally
via the `DebugL` configuration, range-based or pipeline-injected in CI), so a
producing repo's PR never compile-checks its consumers. Blast radius of the
core packages (direct consumers, verified from project references):

- **mm-common** → octo-construction-kit-engine, octo-distributedEventHub,
  octo-communication-sdk, octo-construction-kit-engine-mongodb, octo-cli,
  octo-plug-zenon — and transitively everything.
- **octo-construction-kit-engine** (ConstructionKit.*, Runtime.Contracts,
  Runtime.Engine) → ~20 repos: octo-construction-kit,
  octo-construction-kit-engine-mongodb, octo-sdk, octo-communication-sdk,
  octo-common-services, all backend services, octo-cli.
- **octo-construction-kit-engine-mongodb** → octo-common-services and all
  backend services.
- **octo-sdk** (Sdk.Common, Sdk.ServiceClient, Communication.Contracts,
  Sdk.SourceGeneration) → octo-communication-sdk, octo-common-services,
  services, octo-cli, octo-mcp-service, octo-communication-operator, adapters.
- **octo-common-services** (Services.*) → all backend services and adapters.
- **octo-distributedEventHub** → octo-sdk, octo-common-services,
  octo-communication-sdk, transitively all services.
- **octo-communication-sdk** (Sdk.Pipeline, Sdk.Adapters, Sdk.Common.Web) →
  octo-mesh-adapter, octo-adapter-sap/-eda/-weclapp, octo-plug-zenon.

When a PR in one of these repos removes, renames, or changes the signature of a
public type or member, flag it as a cross-repo breaking change, name the
affected consumers, and ask whether all downstream repos were rebuilt.

The npm equivalent: `octo-frontend-libraries` publishes the `@meshmakers/*`
packages consumed by Refinery Studio and the custom-app repos — see
`frontend.md`.

## Build configurations

- `DebugL` is the local development configuration: it stamps version 999.0.0
  and resolves peer packages from the workspace-local `../nuget/` folder.
  `Debug`/`Release` resolve remote feeds instead.
- The build order across repos follows the dependency chain above; libraries
  must be rebuilt before consumers pick up changes.

## Releases

Releases flow through `r*` tags queued by the release trains in
`octo-mesh-deployment`; the trains inject concrete `octoCoreLibVersion` /
`octoCommVersion` pins into each repo's build. CI templates are shared from
`octo-pipeline-templates` and pinned by `tpl-vX.Y.Z` tag. See `ci-devops.md`.

## Pull requests and commits

- Titles and commit messages of functional changes follow
  `AB#<work item> <Fix|New|Chore|Refactor|Test|Docs>: <description>` — the
  number is an Azure Boards work item, and Fix/New are the dominant verbs. A
  functional PR without an AB# reference is missing its traceability link.
  Automated commits (release manifests, docs-harvest bots, dependabot) and
  merge commits are exempt.
- Work items live in Azure DevOps Boards, not GitHub Issues.

## Language

All artifacts are written in **English**: source code, identifiers, comments,
documentation, commit messages, work items, and user-facing output strings.
Mixed-language identifiers or output strings are a defect. Established
technical terms stay in their original English form.

## Documentation discipline

Docs and READMEs describe the target state. Flag notes documenting transient
problems ("currently broken", "known issue for now", workarounds for bugs that
are already tracked) — in-flight problems belong in the work-item tracker. A
known-issue note is acceptable only when the problem survives releases and no
fix is scheduled.

## Multi-tenancy (platform-wide)

All backend services are multi-tenant and route by `{tenantId}`; each tenant
has isolated data in its own MongoDB database. Configuration overrides use the
`OCTO_` environment-variable prefix everywhere. Code that reaches tenant-scoped
data without a tenant in scope is a defect. Details in `dotnet.md`.
