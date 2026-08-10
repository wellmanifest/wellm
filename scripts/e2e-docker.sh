#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
PYTHONPATH=src python3 scripts/docker_network_preflight.py --scope e2e --repair
cleanup() {
  docker compose --env-file .env -f compose.e2e.yml down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
status=0
docker compose --env-file .env -f compose.e2e.yml up -d --build || status=$?
if [ "$status" -eq 0 ]; then
  container_id=$(docker compose --env-file .env -f compose.e2e.yml ps --all -q e2e)
  if [ -z "$container_id" ]; then
    printf '%s\n' 'E2E result container was not created.' >&2
    status=1
  else
    docker wait "$container_id" >/dev/null || status=$?
    if [ "$status" -eq 0 ]; then
      status=$(docker inspect --format '{{.State.ExitCode}}' "$container_id")
    fi
  fi
fi
docker compose --env-file .env -f compose.e2e.yml logs --no-color
exit "$status"
