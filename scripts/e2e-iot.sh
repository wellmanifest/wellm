#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
PYTHONPATH=src python3 scripts/docker_network_preflight.py --scope iot --repair
cleanup() {
  docker compose --env-file .env -f compose.iot.yml --profile e2e down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
docker compose --env-file .env -f compose.iot.yml --profile e2e up -d --build
container_id=$(docker compose --env-file .env -f compose.iot.yml --profile e2e ps --all -q iot-e2e)
if [ -z "$container_id" ]; then
  echo "iot-e2e container was not created" >&2
  exit 1
fi
docker wait "$container_id" >/dev/null
status=$(docker inspect --format '{{.State.ExitCode}}' "$container_id")
if [ "$status" -ne 0 ]; then
  docker compose --env-file .env -f compose.iot.yml --profile e2e logs --no-color iot-e2e >&2 || true
  exit "$status"
fi
docker compose --env-file .env -f compose.iot.yml --profile e2e logs --no-color iot-e2e
