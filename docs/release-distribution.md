# Release Distribution Policy

The first public Knowhere API releases should be source-code-only GitHub
releases.

## GitHub Release Assets

- Use the default GitHub-generated source archives
- Do not attach Docker images, Python packages, Node packages, or prebuilt
  binaries unless that distribution path is explicitly approved later
- Keep release notes clear that the release contains source code and repository
  documentation, not a complete hosted runtime bundle

## Docker Distribution

Docker images are a separate registry distribution path from GitHub Release
assets.

- GHCR is the only retained public container registry target in this
  publication-preparation branch
- container publication should happen through `.github/workflows/build-images.yml`
- the published image names are `ghcr.io/ontos-ai/knowhere-backend` and
  `ghcr.io/ontos-ai/knowhere-worker`
- GitHub Release notes can link to GHCR tags, but the images themselves should
  not be duplicated as release attachments
- self-hosting guidance for pulling and running those images lives in
  `docs/self-hosting.md`

## Review Expectation

Release notes should make it clear that:

- self-hosting still requires environment configuration
- public images still require external PostgreSQL, Redis, and S3-compatible
  storage
- public releases do not bundle private infrastructure or managed service access
- source-code-only GitHub Release assets are the default public baseline
