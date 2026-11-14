#!/bin/sh
# Сборка фронта на маке, загрузка образа на VPS — без vite на 4GB.
#   ./deploy-frontend-from-mac.sh root@81.19.137.146
set -eu
HOST="${1:-root@81.19.137.146}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
IMAGE="project-frontend:latest"

echo "=== docker build frontend on $(hostname) ==="
# Mac Docker без buildx: только классический builder, без --provenance.
DOCKER_BUILDKIT=0 docker build \
  --build-arg VITE_API_URL="${VITE_API_URL:-https://api.avapay.net/api/v1}" \
  --build-arg VITE_AUTHORIZATION_HEADER=Bearer \
  --build-arg VITE_ASSETS_URL=/ \
  -t "$IMAGE" \
  "$ROOT/taserPayFrontend"

echo "=== upload image to $HOST ==="
docker save "$IMAGE" | gzip | ssh "$HOST" "gunzip | docker load"

echo "=== recreate frontend container (no build) ==="
ssh "$HOST" "cd ~/project && docker compose up -d --no-deps --no-build --force-recreate frontend"

echo "=== done ==="
ssh "$HOST" "docker compose -f ~/project/docker-compose.yml ps frontend"
