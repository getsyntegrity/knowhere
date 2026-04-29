# Contributing

Thanks for contributing to Knowhere API.

## Before You Start

- Open or confirm an issue before starting significant changes.
- Keep changes scoped and reviewable.
- Do not commit real secrets, deployment credentials, or environment-specific
  private data.

## Branching

- Do not push directly to `main` or `staging`.
- Start from the agreed source branch for the work.
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
