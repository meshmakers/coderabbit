# Frontend standards (Angular / TypeScript)

Two distinct Angular families exist — do not transplant rules between them:

1. **Core pair**: `octo-frontend-libraries` (the `@meshmakers/*` npm library
   workspace) and `octo-frontend-refinery-studio` (the main web UI). Vitest
   via `@angular/build:unit-test` (Karma was retired under AB#5071), LCARS
   theme, `/:tenantId` routing.
2. **Custom-app family** (descendants of `template-repo`):
   energy-landing-page, wwc26-landing-page, voest-app, maco-app ClientApp.
   Tailwind 4 + Kendo default theme (maco-app uses the Kendo Material theme
   instead), Vitest (with Playwright only as the Vitest browser provider —
   none of these repos has a standalone e2e suite), `/:lang` routing,
   single-tenant via `config.json`.

All are on **Angular 22** (CLAUDE.md files claiming Angular 21 are stale).

## The library ↔ consumer publishing contract

- In octo-frontend-libraries, inter-library imports resolve from **built
  dist** output; the `build`/`build:prod` scripts chain the libraries in
  dependency order (shared-services → shared-auth → shared-ui → … →
  demo-app). Building a single library in isolation compiles against stale
  sibling output — flag build/docs changes that suggest it when multiple libs
  changed.
- Consumer repos reference `@meshmakers/*` via `file:`/`"*"` locally, but
  **every Docker/CI image build swaps these for the npm-registry version**
  resolved from the OCTO_LIB_VERSION dist-tag. A consumer PR that uses a new
  library export/input must state that the library change is merged and
  published — otherwise local dev looks green while the built image breaks.
- Refinery Studio and maco-app image builds **delete package-lock.json and
  install locklessly**, so package.json semver ranges float straight into
  production images. Exact pins are deliberate (in the studio e.g.
  marked-katex-extension 5.1.10, @progress/kendo-* 24.1.0) — flag widening a
  pin to a range without justification.
- The studio's spec build compiles the library **sources** from the sibling
  repo: the two repos' locked `@angular/*` patch versions must stay identical,
  or `npm test` fails with nominal-type errors while `ng build` stays green.
  Flag an Angular bump in one repo that does not mention the other. This
  lock-step rule binds ONLY the core pair: custom-app repos consume the
  published packages and are not part of it — never ask an app PR to edit
  another repository's package.json.

## npm install scripts

`allowScripts` entries in package.json are **name-only** by decision
(AB#5071 D7): image and CI builds either install locklessly (package-lock.json
is deleted first) or run with `--ignore-scripts`, so a version-qualified
approval drifts out of coverage on every patch bump and the advisory returns.
Do not request version-pinned allowScripts entries or lock-file-based
hardening of that list.

## Library code rules

- No `instanceof` against Angular framework classes in `@meshmakers` library
  code — hosts compiling the library from source load two `@angular` copies
  and `instanceof` silently answers false; use structural checks (the
  HTTP-error interceptor documents the pattern).
- Libraries stay **theme-neutral**: no LCARS/brand colors, fonts, or class
  names in `projects/meshmakers/**` — expose CSS custom properties with
  neutral defaults that host apps override. LCARS lives only in the studio's
  token system; conversely, studio component SCSS uses the semantic
  `var(--theme-*)` tokens, not hardcoded colors (breaks the light theme).

## Error reporting

Callers that catch a failed HTTP request must check
`MmHttpErrorInterceptor.reportsToUser(error)` and stay silent when it returns
true — the interceptor (from @meshmakers/shared-services) already toasts
connection loss, 403, and 400/409 API-error bodies; a second toast overlaps
instead of stacking (AB#4255).

## GraphQL

- Codegen output is never hand-edited: the `.ts` sibling of each `.graphql`
  under `src/app/graphQL/` (plain `.ts` in studio/maco/libraries;
  `*.generated.ts` in the custom-app family) plus `possibleTypes.ts` and
  generated `globalTypes.ts` files. Fix path: edit the `.graphql`, run
  `npm run codegen`. Flag a `.graphql` edit whose generated sibling did not
  change. **Exception**: the studio's `src/app/graphQL/globalTypes.ts` is a
  hand-maintained re-export shim of `@meshmakers/octo-services` — there, flag
  NEW permanent type declarations (temporaries carry a TODO until the library
  publishes them).
- `schema.graphql` is a maintained snapshot of the asset-repo GraphQL
  contract: additions are surgical and annotated with the backend CK model
  version; flag wholesale regeneration inside a feature PR (tens of thousands
  of lines of unrelated drift). voest-app's codegen deliberately omits the
  `Dto` type suffix — do not add it there.

## Studio-specific

- Every feature route lives under `/:tenantId` with a per-tenant Apollo
  client. Flag absolute router links that drop the tenant segment and tenant
  reads that bypass the route.
- List views bound to `mm-list-view` follow the OctoGraphQlDataSource
  directive pattern (DataSourceBase via useExisting/forwardRef, cursor paging,
  sort/filter/search definitions, fetchPolicy network-only). Flag ad-hoc
  Apollo queries feeding a grid and client-side filtering of server-paged
  data.
- UI density is driven by root font-size plus the `--density-scale` custom
  property — never reintroduce CSS `zoom` or ancestor `transform: scale`
  (desynchronizes getBoundingClientRect from offsetWidth and breaks pointer
  hit-testing in Kendo components; removed under AB#4258).

## Tests

- All Angular repos run Vitest through `@angular/build:unit-test` (the core
  pair since AB#5071) — flag Karma/Jasmine idioms and any second test runner.
  Passing unit tests do NOT prove template type-safety (the spec build only
  compiles components reachable from specs) — `ng build --configuration
  development` is the strictTemplates gate for template-heavy PRs. In studio
  specs, stub `@meshmakers` components via TestBed.overrideComponent instead
  of instantiating them (NG0203); specs that share a Vitest chunk can see
  class fields initialised from relative imports as undefined — prefer
  structural checks over `instanceof`.
- Reporter configuration: the builder hands a target-level `outputFile` to
  every file-capable reporter, so `reporters: ["default", "junit"]` with one
  `outputFile` does write the JUnit XML that CI publishes (verified on
  published CI runs). Do not demand reporter tuples or a junit-first order.
- `await expect(promise).resolves.not.toThrow()` passes on any resolved
  promise: it is a weak assertion, not a failing test — suggest a stronger
  matcher at most, never claim the test fails. `vi.restoreAllMocks()` does not
  clear the call history of standalone `vi.fn()` stubs; describe-scoped stubs
  need `vi.clearAllMocks()` or per-test creation.
- Custom-app family: flag unit tests that instantiate components importing
  `@meshmakers/shared-ui` (cronstrue ESM breaks under Vitest; extract pure
  logic instead). Do not propose "an e2e test" as the fallback: these repos
  have no standalone e2e setup (Playwright is only the Vitest browser
  provider), and voest-app's CLAUDE.md explicitly forbids proposing one.

## Other frontends

`grafana-octo-mesh-datasource` (React + Go Grafana plugin, Jest + Playwright)
hand-builds GraphQL documents against the asset-repo runtime-query schema with
no codegen and no schema snapshot — changes to its query-builder fragments
must be justified against the current backend schema.
