# OctoMesh workspace standards

Conventions that span repositories. Individual repositories carry their own
`CLAUDE.md`; this file holds the context that exists between them and is
therefore not visible from inside any single repository.

## Repository layout

OctoMesh is not a monorepo. Each `octo-*` repository is independent and ships
its own solution and NuGet packages. Developers check all of them out side by
side into one folder, but that folder is not a repository and nothing in it is
shared through source control.

Consequence for review: a change that removes or renames a public API in a
shared library (`mm-common`, `octo-sdk`, `octo-construction-kit-engine`,
`octo-common-services`, `octo-distributedEventHub`) breaks downstream
repositories that are not part of the pull request. Flag such changes and ask
which consumers were verified.

## Build dependency order

Libraries are consumed as NuGet packages, so changes land downstream only in
this order:

1. `mm-common`
2. `octo-distributedEventHub`
3. `octo-construction-kit-engine`
4. `octo-sdk`
5. `octo-construction-kit-engine-mongodb`
6. `octo-common-services`
7. `octo-mesh-adapter`
8. `octo-bot-services`
9. all remaining `octo-*` repositories

Local development always builds the `DebugL` configuration, which stamps
version `999.0.0` and resolves packages from the local `../nuget/` folder
instead of a remote feed.

## C# conventions

- Target framework `net10.0`; some projects also target `netstandard2.0`.
- Nullable reference types are enabled and warnings are errors. A change that
  suppresses a warning instead of fixing it deserves a comment.
- Latest C# language version.
- Configuration overrides use the `OCTO_` environment variable prefix.
- All services are multi-tenant and route by `{tenantId}`. Code that reaches
  tenant-scoped data without a tenant in scope is a defect.

## Construction Kit

- `Ck` prefix means schema and type definitions, `Rt` prefix means runtime data
  instances. The framework derives this split, so a CK type name must never be
  prefixed with `Ck` itself.
- A CK type must not be named `Pipeline`; it collides with ETL data flow
  pipelines.
- CK models must be registered in DI before `AddMongoDbRuntimeRepository()`, and
  base models before dependent ones, so that BSON class maps exist when typed
  entities are deserialized.
- Generated DI methods follow `AddCkModel{Name}V{MajorVersion}()`.
- Importing a CK model generates the GraphQL schema automatically. A pull
  request that adds CK types does not need separate GraphQL work.

## ETL pipelines

Pipeline YAML is deserialized strictly: an unknown key throws at load time.
Adding a key to a pipeline definition is therefore not backwards compatible and
requires the matching engine change to ship first.

## Pull requests

Commit messages and pull request titles follow `AB#<number> <Fix|New>:
<description>`, where the number is the Azure DevOps work item. A pull request
without a work item reference is missing its traceability link.

## Language

All artifacts are written in English: source code, identifiers, comments,
documentation, commit messages, work items, and user-facing output strings.
Mixed-language identifiers or output strings are treated as a defect.
