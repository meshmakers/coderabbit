# ETL pipeline standards

Applies to OctoMesh data-flow pipeline YAML (in blueprint/app/adapter repos)
and to pipeline node implementations in C# (octo-communication-sdk,
octo-mesh-adapter, octo-adapter-* and octo-plug-* repos). Note: the repo named
`octo-pipeline-templates` contains Azure DevOps **CI** templates, not ETL
pipelines — see `ci-devops.md`.

## The strict contract between YAML and engine

- Pipeline YAML is deserialized **strictly**: the YamlDotNet deserializer is
  built without `IgnoreUnmatchedProperties`, so any unknown key throws at load
  time. A pipeline may only use nodes and configuration properties that the
  engine/adapter version deployed to the target environment already ships —
  the engine change must ship (and the adapter image be updated) BEFORE the
  YAML lands.
- `type: <Name>@<version>` binds to a `[NodeName("<Name>", <version>)]`
  attribute in the engine or an adapter repo. Engine-side renames/removals of
  a NodeName or a NodeConfiguration property without a version bump (`@2`)
  break every stored pipeline and published blueprint in OTHER repos at load
  time.
- Node configuration classes are a **persisted** external contract (pipeline
  definitions are stored in tenant MongoDB): property changes must be additive
  with defaults; renames/removals turn into tenant-data outages, not compile
  errors.

## Pipeline YAML review checklist

- `MakeHttpRequest@1` whose result later nodes depend on must set
  `onHttpError: Throw`. The default `LogAndStop` logs the failure, skips the
  following nodes, and reports the execution as **SUCCESS** — a silently green
  failed fetch.
- Enum handling: comparisons against enum-typed DATA (`Switch@1`/`If@1` with
  `valueType: Enum`, field filters on enum columns) use the **integer key**
  (the engine reads the value as int; a member name throws or never matches).
  Enum WRITES (`attributeValueType: Enum`) use the member **name** (e.g.
  `value: Inactive`).
- `DataMapping@1`: check `sourceValueType` against the actual runtime type of
  the source path — declaring `String` with mappings "True"/"False" against a
  real boolean never matches and silently writes null (shipped production
  bug).
- Data enums may be written as int or name in entity data, but
  node-configuration enum properties (`valueType:`, `onHttpError:`, …) are
  always member names.

## Node implementations (C#)

- A node executing child transformations must run them on the **same live
  IDataContext** (the SwitchNode/IfNode pattern via
  `ProcessChildTransformationsAsSequenceAsync`). Flag any new node that
  snapshots/`Select()`s the context into a sub-context or re-clones the
  document per iteration: that drops the synthetic `$.full` ForEach aliases
  (silently breaking grandparent reads in nested loops) and re-allocates the
  document per execution — both were real regressions, and allocation-gate
  tests pin the ceilings.
- The DataContext owns its JsonSerializerOptions — flag IDataContext surface
  changes that accept options from node code.
- JSONPath navigation is case-sensitive; typed CLR binding is
  case-insensitive. See `dotnet.md` (case-sensitivity split) before touching
  either.

## Scheduling and DataFlows

- `FromPolling@1` has no offset/jitter: every poller in the adapter process
  (across all its DataFlows) fires simultaneously on adapter config reload
  (timers start with dueTime zero).
  Pipelines sharing one DataFlow must each use a distinct, non-round polling
  interval no sibling already uses (energy-community documents its reserved
  set). Stream-data ingest pipelines keep their own DataFlow with
  `FromExecutePipelineCommand@1` active instead of polling.
- Archive/rollup seeds: keep the cascaded ladder (raw→hourly→daily→…) intact
  and never route legacy daily values into the raw archive — a row whose
  window is not fully contained silently vanishes from the whole rollup
  ladder.
