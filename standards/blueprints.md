# Blueprint standards

Applies to blueprint folders (`blueprint.yaml` + `seed-data/`) in any
repository. Blueprints are versioned CK+seed bundles installed via
`octo-cli InstallBlueprint`; published versions are immutable and land in a
GitHub-hosted catalog.

## Catalogs

Two GitHub-hosted catalogs exist — the private `blueprint-libraries-build` and
the public `meshmakers.github.io` — and every environment reads both. Neither
is a superset of the other: which catalog(s) a repository publishes to is a
per-repository CI decision. Do not derive a missing-publish finding from the
assumption that the private catalog contains the public one.

## Dependencies

- `blueprint.yaml` `ckModelDependencies` and the `dependencies` header inside
  `seed-data/entities.yaml` must declare **identical** CK version ranges. The
  two lists are resolved independently at install time; drift between them has
  broken every fresh install from the shared catalog before (AB#4688). Flag a
  PR that moves a range in one file but not the other.
- The blueprint engine installs the **floor** of each `ckModelDependencies`
  range (everything else in the platform resolves the highest), while
  published CK artifacts freeze their dependency ranges into **exact pins** at
  publish time. When one model's floor moves, the floors of models that pair
  with it must move too — an unsatisfiable floor pairing fails every fresh
  install with a cryptic "required CK model dependencies may be missing"
  error.
- `blueprintDependencies` is for **sibling application blueprints only**
  (e.g. `EnergyCommunity.Base-[2.0,3.0)`). Never name a `System.*` platform
  blueprint there (e.g. System.Communication): those are embedded in the
  services, published only as `.MainLatest`/`.Release`, and never
  catalog-resolvable — the install fails on every tenant. Declaring `System.*`
  CK **models** under `ckModelDependencies` is fine (service-managed models
  are redirected at install).

## Seed data

- rtIds are stable and hand-assigned, and **quoted as strings** — an unquoted
  all-digit rtId parses as a YAML integer and fails schema validation.
- Re-install is an idempotent upsert keyed on rtId: flag rtId churn on
  existing entities (a changed id creates a parallel duplicate tree), and
  remember that removing an entity from the seed does NOT delete it on
  installed tenants.
- Application/Adapter workload entities associate to the default Pool
  (`670…001`) and a channel HelmRepositoryConfiguration (`670…003` dev /
  `670…005` apps-release), reference the default Mesh Adapter (`670…002`,
  never seed a custom one), and never pin an image tag (the chart appVersion
  drives it).
- **No credentials, no tenant-specific data**: adapter configuration blocks
  ship empty Host/User/Password with `IsSimulationMode: true`; notification
  templates use placeholders, never real names or IBANs. Everything under a
  blueprint folder is uploaded to the shared catalog and is effectively
  public.
- Use current System.Communication type names (`Pipeline-1`, `DataFlow-1`,
  `Adapter-1`, `Application-1`) — never the legacy
  `MeshPipeline-1`/`DataPipeline-1`/`MeshAdapter-1`.

## Export round-trips (common source of broken seeds)

- The Rt export tooling drops all non-parent-child associations:
  `ExportRtByQuery` emits none at all, and `ExportRtByDeepGraph` follows only
  the parent-child role. An exported Application/Adapter entity therefore
  loses its Pool/HelmRepositoryConfiguration edges — they must be hand-restored
  before the entity enters a seed or import file. `ImportRt` does not
  existence-check association targets, so the omission only surfaces later at
  `DeployWorkload`.
- Flag tenant re-export noise entering curated seeds: runtime-state
  attributes (StatusMessage, LastDeploymentError*, CommunicationState),
  `RtBlueprint*` ownership attributes, `rtCreationDateTime`/`rtChangedDateTime`
  churn, and unversioned type ids replacing the seed's versioned ones.
  DeploymentState changes must be shown to be intentional.
- Attributes marked `isRuntimeState` (Hostname, Values, ChartVersion,
  IngressEnabled, Archive Status) are applied on FRESH installs only — a seed
  edit to them does not reach existing tenants.

## Folder hygiene

Blueprint folders are deployable-only: `blueprint.yaml`, `seed-data/`, and
declared migration scripts. Flag Excel templates, report definitions, fixup
scripts, pipeline mirrors, or docs inside a blueprint folder. Note the
enforcement split: non-entity content **inside** `seed-data/entities.yaml`
fails schema validation, but extra files elsewhere in the folder pass
validation and are simply ignored by install — they are dead weight published
publicly, and only review catches them (CI will not).

## Repo-specific invariants

- **energy-community**: pipeline definitions inside the seed are single-line
  escaped scalars; never hand-edit them — changes go through the
  `pipelines/<Blueprint>/<name>.yaml` mirror and `sync-pipelines.py`
  (extract → edit → inject; `check` must pass). A change only in `pipelines/`
  is not installed; the seed is the deployment artifact. Flag PRs touching one
  side without the other.
- **FamilyOS**: the `FamilyOs.MainLatest` and `FamilyOs.Release` blueprint
  variants may differ ONLY in the Application's HelmRepository association
  (003 vs 005) and its comments — flag a seed edit in one variant without the
  mirrored change.
