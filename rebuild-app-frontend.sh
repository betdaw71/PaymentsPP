#!/bin/sh
# VPS 4GB: never build app and frontend in one compose command.
#   cd ~/project && sh rebuild-app-frontend.sh
set -eu
export COMPOSE_PARALLEL_LIMIT=1
export BUILDX_NO_DEFAULT_ATTESTATIONS=1
export DOCKER_BUILDKIT=1

echo "=== build app ==="
docker compose build app
docker compose up -d --no-deps --no-build --force-recreate app

echo "=== build frontend (after app is up) ==="
docker compose build frontend
docker compose up -d --no-deps --no-build --force-recreate frontend

echo "=== done ==="
docker compose ps app frontend
