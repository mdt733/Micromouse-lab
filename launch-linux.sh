#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f .venv/bin/python ]; then
  python3 -m venv .venv
fi
# Reinstall only when dependencies changed, including upgrades to uvicorn[standard].
expected="$(sha256sum requirements.txt | cut -d' ' -f1)"
actual="$(cat .venv/.requirements.sha256 2>/dev/null || true)"
if [ "$expected" != "$actual" ]; then
  .venv/bin/python -m pip install -r requirements.txt
  printf '%s\n' "$expected" > .venv/.requirements.sha256
fi
exec .venv/bin/python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000
