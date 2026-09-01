# Testing standards (.NET and frontend)

## Framework matrix — match the repo, never mix

Framework choice is per test project; a test written for the wrong framework
is **silently never discovered** (the suite stays green). Flag any PR that
introduces a second test or mocking framework into an existing project.

- **TUnit + NSubstitute on Microsoft.Testing.Platform (MTP)**:
  octo-communication-controller-services unit tests, octo-communication-operator,
  octo-bot-services (Jobs.Tests), octo-adapter-eda.
- **xUnit v3 (3.2.2)**: octo-ai-services, octo-asset-repo-services,
  octo-communication-sdk, octo-construction-kit-engine(+mongodb),
  octo-distributedEventHub, octo-identity-services, octo-sdk, and the
  communication controller's INTEGRATION tests.
- **Legacy xUnit v2**: mm-common, octo-cli, octo-common-services,
  octo-mcp-service (with Moq), octo-mesh-adapter, octo-platform-services,
  octo-plug-zenon, octo-report-services, octo-adapter-sap/-weclapp.
- Mocking: FakeItEasy in most xUnit repos, NSubstitute in the TUnit repos plus
  mm-common/identity/plug-zenon (the communication controller's xUnit v3
  integration tests also use NSubstitute); Moq only in named legacy spots
  (octo-mcp-service, octo-distributedEventHub UnitTests, the vendored
  SapNwRfc tests) — do not spread it further.
- Org-wide pins: TUnit 1.65.63, xunit.v3 3.2.2, FluentAssertions 8.10.0
  (AwesomeAssertions is not used). Flag single-repo version bumps — repos ship
  together on release trains, and xunit.v3's MTP major is load-bearing.

## Microsoft.Testing.Platform on .NET 10

- The communication controller, communication operator, and bot-services
  carry a repo-root `global.json` with
  `"test": { "runner": "Microsoft.Testing.Platform" }` — flag its removal.
  octo-adapter-eda has none (its TUnit tests are not yet wired into CI; a new
  test CI step there must add one).
- Under the .NET 10 SDK with the MTP runner, the classic ADO `DotNetCoreCLI
  command: 'test'` **silently ignores its positional projects glob** and falls
  back to cwd solution discovery — include/exclude globs are NOT enforced. The
  explicit shape is `command: 'custom'` + `custom: 'test'` +
  `--solution $(solutionFile) … -- --report-trx`
  (octo-communication-operator pattern); the communication controller and
  bot-services still ship the classic shape — flag ineffective glob filters
  there rather than calling the shape rejected. Locally use
  `dotnet test --solution <sln>` or `dotnet run --project <test.csproj>`;
  reporter/filter args go after `--`.
- Do NOT add `--report-trx` / Microsoft.Testing.Extensions.TrxReport to
  xunit.v3 projects: the private feed only carries TrxReport 2.x (MTP v2),
  which xunit.v3 3.2.2 (MTP v1) cannot load — the option fails as unknown
  (that is why some xUnit integration steps run with
  `publishTestResults: false`). TrxReport belongs only in TUnit projects.

## Test placement contracts

- `*SystemTests.csproj` is a CI contract: tests needing live external systems
  (real GitHub API, a running service stack) live there, and CI excludes them
  via the `!**/*SystemTests.csproj` glob (locally:
  `--filter "FullyQualifiedName!~SystemTests"`). Flag live-dependency tests in
  ordinary *Tests projects (breaks CI agents), pure unit tests inside
  SystemTests projects (never run in CI), and project renames that cross the
  glob boundary.
- In the communication controller, unit tests (TUnit) and integration tests
  (xUnit v3 + Testcontainers) are separate projects with separate CI steps and
  filters — a test in the wrong project is either not discovered or runs
  without Docker.

## Databases and parallelism

- DB-backed integration tests use **Testcontainers** (Testcontainers.MongoDb;
  RabbitMq in the event hub; a generic CrateDB container in the mesh
  adapter) — never a hardcoded localhost database without an explicit opt-out
  option. CI agents provide only Docker.
- MongoDB-backed integration-test projects serialize execution; two mechanisms
  exist and must not be weakened:
  - `xunit.runner.json` with `parallelizeAssembly: false` and
    `parallelizeTestCollections: false`
    (octo-construction-kit-engine-mongodb, identity, asset-repo integration
    tests) — flag deletion/edits, and require one in NEW *IntegrationTests
    projects.
  - Named collections: in octo-construction-kit-engine-mongodb, new
    integration-test classes join one of the named fixture collections under
    `tests/…/Collections/` (there is NO literal `[Collection("Sequential")]`
    there). The ad-hoc `[Collection("Sequential")]` idiom is used in
    identity/ai-services/mesh-adapter test folders — new DB-touching classes
    there must carry it.
- Allocation-gate and GC-counter tests (octo-communication-sdk) must carry
  `[Collection("AllocationGates")]` (`DisableParallelization = true`) —
  process-wide GC counters are corrupted by parallel tests; gates fail
  intermittently in the full suite while passing in isolation.

## Cross-repo test coupling

The Newtonsoft/STJ serialization parity suite that validates
octo-construction-kit-engine's serializers lives in
**octo-communication-sdk** (`Sdk.Common.PipelineParityTests`, Newtonsoft as
oracle with a named whitelist of irreducible divergences). A serializer change
in the engine repo is not covered by that repo's own CI — require a downstream
octo-communication-sdk build/test.

## Frontend

- octo-frontend-libraries and refinery-studio: Karma + Jasmine with the
  ChromeHeadlessCI launcher (`ng test --watch=false
  --browsers=ChromeHeadlessCI`) — flag Jest/Vitest introduction there.
- Custom-app repos (template-repo descendants): Vitest + Playwright.
- Passing Karma tests do not prove template type-safety — see `frontend.md`.
