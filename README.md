# coderabbit

Central [CodeRabbit](https://docs.coderabbit.ai/configuration/central-configuration)
configuration for the `meshmakers` organization.

> The repository name must stay `coderabbit`. CodeRabbit resolves the central
> configuration by that exact name, and CodeRabbit must remain installed on this
> repository or the file below is never read.

## What this does

`.coderabbit.yaml` in this repository applies to **every repository in the
organization that does not ship its own `.coderabbit.yaml`**. Change the review
behaviour for all repositories by opening a pull request here, rather than
touching each repository individually.

`standards/` holds review criteria that span repositories. They are pulled in
through `knowledge_base.code_guidelines.filePatterns` as
`coderabbit:standards/*.md`, so every repository is reviewed against them.
Repository-local `CLAUDE.md` files are read in addition and need no
configuration.

## Configuration precedence

CodeRabbit resolves settings top down and **does not merge sources by default** —
the highest source that exists wins outright:

| Priority | Source |
| -------- | ------ |
| 1 | Organization global overrides (web UI, org admins only) |
| 2 | A repository's own `.coderabbit.yaml` |
| 3 | **This repository's `.coderabbit.yaml`** |
| 4 | Repository settings in the web UI |
| 5 | Organization settings in the web UI |
| 6 | Defaults |

Prefer this file over the web UI so that review configuration is versioned and
reviewable like the rest of the code.

## Overriding for a single repository

A repository that needs an exception adds its own `.coderabbit.yaml` whose
**first line** is `inheritance: true`. Without that line the local file replaces
this configuration entirely instead of merging on top of it.

```yaml
inheritance: true

reviews:
  path_filters:
    - "!**/*.snapshot.json"
```

## Verifying what is in effect

Comment `@coderabbitai configuration` on any pull request. CodeRabbit replies
with the resolved YAML, annotated with the source each value came from.

Other useful commands:

| Command | Effect |
| ------- | ------ |
| `@coderabbitai review` | Review new changes (required on public repositories with fewer than 10 stars, where reviews are not triggered automatically) |
| `@coderabbitai full review` | Review all files from scratch |
| `@coderabbitai pause` / `resume` | Stop and restart automatic reviews on one pull request |
| `@coderabbitai rate limit` | Show the remaining review allowance |

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
