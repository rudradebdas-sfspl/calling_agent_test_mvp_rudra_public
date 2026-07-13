#!/usr/bin/env bash
set -euo pipefail

: "${TAG:?TAG is required, example: export TAG=<github_sha>}"
: "${GHCR_IMAGE_PREFIX:?GHCR_IMAGE_PREFIX is required, example: ghcr.io/owner/repo}"

COMPOSE_FILE="ci_cd/docker-compose.prod.yml"

echo "Deploying voice-agent TAG=${TAG} IMAGE_PREFIX=${GHCR_IMAGE_PREFIX}"

docker compose --env-file .env -f "${COMPOSE_FILE}" pull
docker compose --env-file .env -f "${COMPOSE_FILE}" run --rm migrate
docker compose --env-file .env -f "${COMPOSE_FILE}" up -d --remove-orphans

echo "Waiting for backend health..."
for i in {1..30}; do
  if curl -fsS http://localhost:8000/health >/dev/null; then
    echo "Backend health OK"
    exit 0
  fi
  sleep 2
done

echo "Backend health failed"
docker compose --env-file .env -f "${COMPOSE_FILE}" ps
docker compose --env-file .env -f "${COMPOSE_FILE}" logs --tail=100 backend
exit 1
