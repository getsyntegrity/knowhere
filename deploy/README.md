# Deploy Assets

This directory only contains application-owned deploy assets.

## What Stays Here

- `deploy/docker/`: Dockerfiles used to build CI images
- `deploy/local-dev/`: local development services and helper scripts

## What Does Not Stay Here

This repository does not store remote deployment ownership.

Do not add:

- cloud-specific deployment manifests
- Terraform state or plans
- SSH keys or PEM files
- runtime secrets
- cluster rollout or operator runbooks

Those assets belong in `knowhere-api-infra` so the application repository stays focused on source code and image builds.

## CI Scope

The GitHub Actions workflow in this repository builds container images only.

- GHCR publishing is part of the default build path
- ACR and ECR publishing remain secret-driven registry outputs
- no workflow in this repository should perform runtime deployment actions
