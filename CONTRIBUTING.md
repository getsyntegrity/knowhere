# Contributing

Thanks for contributing to Knowhere. The project is split across several repositories — make sure you're working in the right one.

## Ecosystem

| Repository | Description |
|---|---|
| [knowhere](https://github.com/Ontos-AI/knowhere) | **This repo.** Backend API and worker — document ingestion, parsing, graph construction, and retrieval. |
| 🖥️ [knowhere-dashboard](https://github.com/Ontos-AI/knowhere-dashboard) | The web UI. Connects to the API for the full product experience. |
| 🐳 [knowhere-self-hosted](https://github.com/Ontos-AI/knowhere-self-hosted) | Docker Compose stack for self-hosted deployments. Packages the API, worker, and dashboard together. |
| 🐍 [knowhere-python-sdk](https://github.com/Ontos-AI/knowhere-python-sdk) | Official Python SDK for the Knowhere Cloud API. |
| 🦕 [knowhere-node-sdk](https://github.com/Ontos-AI/knowhere-node-sdk) | Official Node.js SDK for the Knowhere Cloud API. |

## Before You Start

- Open or confirm an issue before starting significant changes.
- Keep changes scoped and reviewable.
- Do not commit real secrets, deployment credentials, or environment-specific
  private data.

## Branching

- Do not push directly to `main` or `staging`.
- Use `main` as the default source branch and pull request target.
- Use `staging` only as a maintainer-managed environment branch for staging
  deployment validation before a production release.
- Use a dedicated feature or fix branch for each change.
- Name branches as `<type>/<user>/<description>`.
- Use a lowercase `type`, preferably one of `feat`, `fix`, `refactor`,
  `chore`, `docs`, `test`, `perf`, `ci`, `build`, or `revert`.
- Use the human owner or contributor name for `user`; do not use a generic
  tool name such as `codex`.
- Keep `description` short, lowercase, and kebab-case, for example
  `refactor/alice/extract-chunk-converter`.
- If you are working on publication cleanup, keep migration-only changes on the
  dedicated migration branch instead of flowing them back into normal private
  development by default.

## Release Flow

`main` is the public development trunk. Merging to `main` does not deploy the
managed production service.

Maintainers promote selected `main` commits to `staging` when they want staging
environment validation. Pushes to `staging` build and deploy the staging API and
worker services.

After the staged commit is validated, maintainers create a release tag from that
exact commit, for example `v2026.06.08.1` or `v1.2.3`. Release tags build and
deploy production images, then create or update the GitHub Release with the
deployed source archive and build metadata.

Hotfixes should be opened as pull requests to `main`. If `main` has already
moved beyond the production-safe commit, create the hotfix branch from the last
production tag, release that hotfix commit with a new tag, and merge or
cherry-pick the hotfix back to `main`.

Reverts follow the same rule: use a normal revert pull request for changes that
are only on `main`; promote the revert to `staging` if staging is affected; and
create a new release tag for any production rollback. Do not move or delete old
production tags.

## Development Setup

Sync the Python services and shared package:

```bash
cd packages/shared-python && uv sync
cd ../../apps/api && uv sync
cd ../worker && uv sync
```

Start the local services:

```bash
cd deploy/local-dev && ./start-dev.sh
```

## Pull Requests

- Write a clear title and summary.
- Explain API, schema, or behavior changes explicitly.
- Call out migration, workflow, and documentation impacts.
- Add or update tests when behavior changes.
- Keep documentation aligned with the implementation.
