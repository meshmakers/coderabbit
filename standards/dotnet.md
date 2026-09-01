# .NET / C# standards (backend services and shared libraries)

Applies to the C# repositories (`octo-*-services`, shared libraries, adapters,
octo-cli, octo-mcp-service).

## Compiler baseline

- `LangVersion latestmajor`, nullable reference types enabled,
  `TreatWarningsAsErrors` — org-wide via each repo's `Directory.Build.props`.
  Flag `#pragma warning disable` / `SuppressMessage` used to hide instead of
  fix.
- Target framework is `net10.0`, but several core projects **multi-target**:
  `net10.0;netstandard2.0` in octo-construction-kit-engine and octo-sdk (the
  netstandard leg runs inside the Roslyn/MSBuild host for source generation)
  and `net8.0;net9.0;net10.0` in mm-common. A net10-only BCL API compiles in
  the IDE's default view but breaks the older leg — and for source-gen
  packages that failure surfaces as a broken analyzer in ~20 downstream repos.

## Multi-tenancy and middleware

- Canonical ASP.NET pipeline order: `UseAuthentication` → `UseAuthorization` →
  `UseOctoTenantAuthorization` (→ `UseOctoTenants` where a per-tenant feature
  gate exists). The tenant middleware documents that it must run after
  auth; wrong order silently disables the route-tenant-vs-token check and lets
  a token for tenant A act on tenant B.
- Only the `tenant_id` claim authorizes API access to a tenant. The
  `allowed_tenants` claim is tenant-picker UX only — flag authorization
  decisions based on it. Client-credentials tokens (no `sub` claim) bypass the
  route-tenant check **by design**: they carry no user context and are how
  CI, octo-cli (`-apic`), MCP tools, and adapters reach child tenants — flag
  changes that subject them to the check. (RFC 8693 cross-tenant exchange
  tokens are user tokens with their own `sub` and `tenant_id` and pass the
  check normally; they are unaffected.)
- Configuration overrides bind via `AddEnvironmentVariables("OCTO_")` with
  section binding. Flag raw `Environment.GetEnvironmentVariable` reads for
  service config or new prefixes — Helm charts, Start-Octo, and docs all
  assume `OCTO_`.
- Tenant-data endpoints are tenant-routed (`{tenantId}/v1/...`). The
  system-scoped `api/v1` routes for StreamData/Reporting were removed
  (AB#4287) — flag reintroductions; SDK clients throw without a TenantId.

## Tenant capabilities (enable/disable features)

- Per-tenant capability keys (Communication, Reporting, AiServices) are
  single-sourced from `TenantCapabilityConfigurationKeys` in
  octo-common-services (Stream Data's key is engine-owned and deliberately
  separate). Flag any new string literal for these keys — a drifted literal
  blinds the tenant delete/detach guard and orphans cluster resources.
- Disable endpoints follow one contract:
  `catch (ConfigurationException e) when (e.IsConflict)` → **409** with
  `OperationFailedErrorDto(e.Message)`; other ConfigurationException → 400.
  CLI, MCP, and Refinery Studio surface the 409 reason verbatim — flag
  collapsing the conflict case into 400/500 or dropping the DTO body.

## Dependency injection

- Flag a second `AddRuntimeEngine()` call in one service host (duplicates
  IEnumerable-style registrations).
- Flag `AddMongoDbRuntimeRepository()` without `AddMongoBlueprintSupport()` in
  a service that applies blueprints — the fallback is an in-memory
  installation store: logs say "blueprints installed" but nothing lands in
  MongoDB.
- Do **not** flag the relative order of `AddCkModel*()` vs
  `AddMongoDbRuntimeRepository()`: BSON serializer setup is order-independent
  by design (module initializer in the engine); both orders ship in
  production services.

## Serialization (the Newtonsoft-parity machine)

The runtime-entity serialization spans two repos and three serializer
technologies; byte-level parity with the legacy Newtonsoft output is
load-bearing (hashes over serialized bytes, Mongo BSON type stability).

- **Two-layer null policy, deliberately different**: the CK-engine
  `RtSystemTextJsonSerializer` drops nulls (`WhenWritingNull`); the pipeline
  bundle `SystemTextJsonOptions` in octo-communication-sdk preserves them
  (`Never`) so nodes can distinguish DataKind.Null from DataKind.Undefined.
  Flag flipping either, and flag ad-hoc `new JsonSerializerOptions()` for
  Rt-model data.
- **Byte parity**: the encoder stays `UnsafeRelaxedJsonEscaping`; the
  NewtonsoftParity number converters keep emitting `.0` for whole-number
  reals (otherwise doubles round-trip as long → BsonInt64 regressions); plain
  CLR enums serialize as their underlying integer (read-tolerant of names).
  Raw `Utf8JsonWriter` use must pass the bundle's encoder.
- **The enforcing parity test suite lives in octo-communication-sdk**
  (`Sdk.Common.PipelineParityTests`, Newtonsoft as oracle) — a serialization
  PR in octo-construction-kit-engine is NOT validated by its own CI; require
  a downstream build/test of octo-communication-sdk.
- **Converter fan-out**: non-generic `Ck*Id` types carry `[JsonConverter]`
  attributes; the generic `RtCkId<T>` cannot, so exactly five closed
  `RtCkId*Converters` are registered per options bundle — STJ, the Newtonsoft
  twin, AND the YAML pipeline serializer in octo-communication-sdk (twice:
  serializer + deserializer). A new element-id type without the full fan-out
  silently serializes as an object.
- **Strict reads**: only number-from-string coercion is enabled. Newtonsoft's
  bool/DateTime/number-to-string coercions do NOT happen — code migrated from
  Newtonsoft must implement tolerance explicitly at the call site.
- **Case-sensitivity split** (pipeline engine): document/JSONPath navigation
  is case-SENSITIVE (`NodeNavigation` options — Newtonsoft SelectToken
  parity); typed `Get<T>`/`Deserialize<T>` CLR binding is case-INsensitive
  (camelCase constructor params vs PascalCase wire keys). Flag flipping
  `PropertyNameCaseInsensitive` on either bundle.
- Keep STJ converters co-located with their Newtonsoft counterparts in the
  same folder.

## Source generation (frozen contracts)

- Generated DI methods are `AddCkModel{Name}V{MajorVersion}()`; migration
  sources are `{Name}CkMigrationSource`. Hand-written code in ~20 repos calls
  these by name — flag generator changes that alter the naming or the
  version-suffix scheme.
- The compiled CK model file convention (`ck-*.yaml` / `ck-*.cache.json`) is a
  cross-repo contract: the SDK source generator matches files by exactly that
  naming. Flag output-shape or naming changes that currently-published
  generator versions cannot read.
- When a field is added to `CkAttributeDto` (or any CK schema DTO) in the
  engine, it must ALSO be threaded through three places in
  octo-construction-kit-engine-mongodb (persistence entity, import copy,
  read-back copy) or it silently reads as default at runtime — the runtime CK
  cache is rebuilt from MongoDB, not the compiled catalog (AB#4589).
  Already-imported tenants also need a model version bump.

## Wire contracts across services

- MassTransit message/command types in octo-common-services
  (`Contracts/DistributionEventHub/`) are frozen: MassTransit routes by CLR
  type identity, and rolling deployments always run mixed versions — flag
  renames, namespace moves, and non-additive property changes.
- SignalR hub contracts and DTOs in octo-sdk (`Communication.Contracts`) are
  consumed by the communication controller, the Kubernetes operator, and every
  deployed adapter — always a mixed-version fleet. New DTO properties must
  default to pre-existing behavior; new hub methods must tolerate peer
  rejection (catch HubException, degrade); removals/renames are breaking.
- The platform-services `_configuration` discovery DTO is a lockstep contract
  with Refinery Studio, Office Integration, and Power Query: field set, names,
  trailing-slash behavior, and "empty string = service not installed" must not
  drift; its contract snapshot test is updated intentionally, never to make CI
  green.
- Bot-services and asset-repo must register the same
  `IStreamDataCkModelDescriptor` — flag removal or version pinning on one side
  only.

## Asset repository GraphQL

- Schemas are generated per tenant from the CK model and cached — all GraphQL
  type/resolver classes must be thread-safe (no mutable instance state), and
  CK-model-affecting changes must invalidate via `SchemaContext.Invalidate`.
- Use `UtcDateTimeGraphType` (wire name `DateTime`), never the stock
  GraphQL.NET `DateTimeGraphType` — two scalars named DateTime break schema
  init, and the stock scalar emits naive strings for Unspecified-kind values.

## Known DI trap

Never add a host-side audit/notification bridge that constructor-captures
`IEventRepository` or `ISystemContext` — audit trails route through the
`IAuditEventSink` seam with lazy `IServiceProvider` resolution; a ctor capture
re-forms a DI bootstrap cycle that deadlocks service startup.

## CLI / MCP surface parity

octo-cli commands, octo-mcp-service tools, and SDK service clients form one
contract surface. A changed SDK DTO or CLI command surface normally implies a
matching MCP change (family-1 MCP tools mirror the CLI 1:1) — flag PRs that
change one surface without noting the counterpart.
