# Construction Kit (CK) model standards

Applies to `ConstructionKit/` folders in any repository (YAML model
definitions under `types/`, `records/`, `attributes/`, `enums/`,
`associations/`, plus `ckModel.yaml` and `migrations/`).

## Naming

- `Ck` prefix means schema/type definitions, `Rt` prefix means runtime data
  instances — the source generator derives the prefixes from the bare typeId
  (`typeId: Asset` → runtime entity class `RtAsset`, DTOs `RtAssetDto`, and
  `Ck`-prefixed ID members like `CkAssetTypeId` in the model's CkIds class).
  Therefore a CK type name must **never** be prefixed with `Ck` itself (it
  would generate `RtCkFoo`).
- Never reuse platform-reserved names for domain types: `Pipeline`,
  `DataFlow`, `Adapter`, `Pool`, `Application` are owned by the
  System.Communication model; a domain type with the same name collides in
  generated code, Studio UI, and every conversation.
- Identifiers (typeId, recordId, attributeId, enum names) are PascalCase —
  compiler-validated.
- Same-model references use `${this}/`, cross-model references
  `${ModelName}/`. Element references may carry an optional element-version
  suffix (the element's own version, defaulting to 1 when omitted) —
  `${System}/Entity` and `${System}/Entity-1` are equivalent; do not require
  the suffix, and do not confuse it with the model's major version.

## Versioning (CI-gated)

- Any content change under `ConstructionKit/**` requires an honest SemVer bump
  of the `modelId` version in `ckModel.yaml`. In the platform repos
  (octo-construction-kit, the engine, and the CK-carrying service repos) CI
  runs `octo-ckc ValidateVersion` hard-blocking on every branch against the
  catalog a merge would publish to. App/demo repos carrying CK models
  (FamilyOS, one-time-ticket, demo-process-automation) currently have NO such
  CI gate — there the reviewer must flag an unbumped `ckModel.yaml` itself.
- Bump levels: removals of elements/attribute assignments, `valueType` /
  `valueCkEnumId` / `valueCkRecordId` changes, and dependency major switches
  are **MAJOR** (with a matching migration where the pipeline requires one);
  additive changes are at least **MINOR**.
- Published CK artifacts freeze their dependency ranges into exact pins at
  publish time — see `blueprints.md` for the floor/pin interaction.

## GraphQL

Importing a CK model generates the GraphQL schema automatically (per tenant,
in the asset repository). A PR that adds CK types needs **no** separate
GraphQL work — flag review comments or stories that ask for it.

## Migrations

- Layout: `ConstructionKit/migrations/` with `migration-meta.yaml` plus one
  `{from}-to-{to}.yaml` script per step.
- Internal consistency is unchecked by the compiler and must be reviewed: the
  script's `sourceVersion`/`targetVersion` must match its filename AND the
  meta entry's `fromVersion`/`toVersion`/`scriptPath`. A mismatch silently
  orphans the script (the engine indexes through the meta file and
  auto-bridges gaps with no data migration).
- Scripts declare `$schema: ck-migration.schema.json` and steps with
  `stepId`/`action`/`target`/`transform`.
- In blueprint-update migration scripts: target blocks need
  `blueprintSourceOnly: false` (the default filters on an attribute no
  existing entity carries yet — silent no-op), and transforms use
  `action: Transform` + `type: SetValue` (the `Update` + `data:` shape fails
  to deserialize).

## Where CK models live

- `octo-construction-kit` publishes the shared model libraries
  (`Octo.Sdk.Packages.*`, `Industry.*`) to the CK catalog.
- Service-owned models live next to their service (e.g.
  `SystemCommunicationCkModel` in the communication controller,
  `Persistence.IdentityCkModel` in identity).
- App/demo repos (FamilyOS, one-time-ticket, demo-process-automation) carry
  their own models and are subject to the same rules. energy-community does
  NOT: its CK model lives in octo-construction-kit
  (`Octo.Sdk.Packages.EnergyCommunity`); the repo carries only blueprints,
  pipelines, and frontend code.
