# CI/CD Status

This repository uses GitHub Actions for CI and Continuous Delivery.

Current mode:
- CI checks run on pull requests and pushes.
- Docker images are built after CI passes.
- Docker images are published to GHCR on main.
- Server deployment is disabled for now.
