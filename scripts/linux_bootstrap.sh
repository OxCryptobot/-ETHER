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

# B1: deliberately NOT writing ETHER_SANDBOX_BACKEND into .env. The daemon
# fails closed to docker (deploy/ether.service pins =docker, and an explicit
# docker backend refuses host re-run). Host-side execution on a dockerless
# host requires deliberate operator opt-in: edit .env yourself and accept
# the visible sandbox_fallback:local marker on every run.

chmod +x scripts/start_daemon_linux.sh scripts/linux_bootstrap.sh || true

echo "=== doctor ==="
python -m cli.main doctor || true
echo "=== smoke ==="
python scripts/smoke_test.py
echo "=== pytest ==="
pytest -q
echo "Bootstrap OK. Edit .env PRIMARY_MODEL then: python -m cli.main run 'assert is_even'"
