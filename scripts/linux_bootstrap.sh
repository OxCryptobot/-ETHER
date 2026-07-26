#!/usr/bin/env bash
# One-shot Linux cousin bootstrap
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env — set ETHER_PRIMARY_MODEL from: ollama list"
fi

# Prefer local sandbox when no docker
if ! command -v docker >/dev/null 2>&1; then
  if ! grep -q '^ETHER_SANDBOX_BACKEND=' .env 2>/dev/null; then
    echo 'ETHER_SANDBOX_BACKEND=local' >> .env
  fi
fi

chmod +x scripts/start_daemon_linux.sh scripts/linux_bootstrap.sh || true

echo "=== doctor ==="
python -m cli.main doctor || true
echo "=== smoke ==="
python scripts/smoke_test.py
echo "=== pytest ==="
pytest -q
echo "Bootstrap OK. Edit .env PRIMARY_MODEL then: python -m cli.main run 'assert is_even'"
