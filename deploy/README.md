# Deploy Assets

This directory contains only repository-owned deployment support files.

## What Lives Here

- `deploy/docker/`: Dockerfiles for the API and worker services
- `deploy/local-dev/`: local development infrastructure based on Docker Compose

## What Does Not Live Here

This repository does not own remote runtime infrastructure.

Do not add:

- cloud deployment manifests
- Terraform state or plans
- SSH keys or PEM files
- live environment secrets
- operator runbooks tied to a private environment

Keep runtime infrastructure and environment-specific rollout ownership in the
separate infra repository.

## CI Scope

The GitHub Actions workflows in this repository validate the retained backend
surface and build container images.

- GHCR is the only registry path kept in this publication-preparation branch
- no workflow in this repository should perform runtime deployment actions
