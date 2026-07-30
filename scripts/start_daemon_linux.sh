#!/usr/bin/env bash
# @ETHER Linux daemon launcher (cousin / strong box)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export ETHER_ROOT="$ROOT"
export ETHER_GIT_RESET_OK="${ETHER_GIT_RESET_OK:-1}"
export ETHER_PULL_SOFT="${ETHER_PULL_SOFT:-1}"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONIOENCODING="utf-8"

# B1: preserve an operator-set ETHER_SANDBOX_BACKEND (e.g. the systemd
# unit's explicit =docker pin in deploy/ether.service) across the .env
# sourcing below — local override config must not silently clobber a
# deliberate security decision.
_sandbox_backend_pin="${ETHER_SANDBOX_BACKEND-}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -n "$_sandbox_backend_pin" ]]; then
  export ETHER_SANDBOX_BACKEND="$_sandbox_backend_pin"
elif ! command -v docker >/dev/null 2>&1; then
  # Prefer local sandbox if Docker not present (visible via the
  # sandbox_fallback:local marker; non-penalizing per ADR 0002).
  export ETHER_SANDBOX_BACKEND="${ETHER_SANDBOX_BACKEND:-local}"
fi

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

echo "@ETHER Linux daemon root=$ROOT sandbox=${ETHER_SANDBOX_BACKEND:-auto}"
exec "$PY" "$ROOT/scripts/ether_daemon.py"
