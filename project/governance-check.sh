#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPOSITORY_ROOT"

if [[ -x "$REPOSITORY_ROOT/.venv/bin/python" ]]; then
  PATH="$REPOSITORY_ROOT/.venv/bin:$PATH"
  export PATH
fi

exec scripts/verify.sh
