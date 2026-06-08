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

## Development and Release Flow

`main` is the public development trunk. Contributors and maintainers develop
against `main`, and merging to `main` does not deploy the managed production
service.

### Contributor workflow

1. Fork the repository or create a branch from the latest `main`.
2. Use a dedicated branch such as `docs/alice/add-faq` or
   `fix/alice/retrieval-timeout`.
3. Open the pull request against `main`.
4. Wait for review and required checks.
5. Keep the pull request focused; split unrelated changes into separate pull
   requests.

Pull requests to `main` run CI, secret scanning, and CodeQL. Pull request
workflows do not build deployment images, push images, deploy environments, or
create GitHub Releases.

### Maintainer development workflow

Internal changes follow the same trunk workflow unless the work is explicitly a
release-promotion operation:

1. Create a branch from `main`.
2. Open a pull request to `main`.
3. Merge after review and green checks.
4. Promote selected `main` commits to `staging` only when staging environment
   validation is needed.

Do not ask external contributors to target `staging` for normal changes.
`staging` is an environment branch, not the public contribution trunk.

### Staging deployment workflow

`staging` is managed by maintainers. Use it to validate a selected `main` commit
against the hosted staging environment before production release.

Recommended promotion options:

- Open a maintainer-owned promotion pull request from `main` into `staging`.
- Fast-forward or sync `staging` to a selected `main` commit when the repository
  policy allows it.

Pushing to `staging` builds and publishes staging API and worker images, then
deploys them to the staging namespace. Manual workflow dispatch is also
staging-only and can be used to rebuild or redeploy staging without creating a
production release.

### Production release workflow

Production deployment is controlled by publishing a GitHub Release. After a
commit has been validated in staging:

1. Open the repository Releases page and choose **Draft a new release**.
2. Create or select an immutable release tag on the exact validated commit, for
   example `v2026.06.08.1` or `v1.2.3`.
3. Use GitHub's release note generation to preserve the pull request and commit
   summary in the release body.
4. Publish the release.

Publishing the GitHub Release builds and publishes production API and worker
images, deploys them to the production namespace, and uploads the deployed
source archive and build metadata back to that same GitHub Release.

Do not move or delete production tags. If a production release needs to change,
draft and publish a new release with a new tag.

### Hotfix workflow

If `main` is safe to release from, hotfixes use the normal path:

1. Create a hotfix branch from `main`.
2. Open a pull request to `main`.
3. Promote the merged commit to `staging` if staging validation is needed.
4. Draft and publish a new GitHub Release from the validated hotfix commit.

If `main` already contains unreleased or risky changes, branch from the latest
production tag instead:

1. Create a hotfix branch from the latest production tag.
2. Apply the minimal fix.
3. Draft and publish a GitHub Release from the hotfix commit.
4. Merge or cherry-pick the hotfix back to `main` so the trunk retains the fix.

### Revert and rollback workflow

Use normal revert pull requests for changes that are only on `main`. If the bad
change reached staging, promote the revert commit to `staging` after it merges
to `main`.

If the bad change reached production, draft and publish a new GitHub Release
whose tag points to a revert commit or a known-good hotfix commit. Do not retag
an old release. For example, if `v2026.06.08.1` is bad, release
`v2026.06.08.2` with the rollback commit.

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
