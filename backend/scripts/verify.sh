#!/usr/bin/env sh
set -eu

PYTHON_BIN="${PYTHON_BIN:-backend/.venv/bin/python}"
PYTEST_BIN="${PYTEST_BIN:-backend/.venv/bin/pytest}"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

if [ ! -x "$PYTEST_BIN" ]; then
  PYTEST_BIN="pytest"
fi

"$PYTHON_BIN" -m compileall backend/app backend/tests
"$PYTEST_BIN" -q

if [ "${RUN_DOCKER_SMOKE:-0}" = "1" ]; then
  docker compose up --build -d
  backend/scripts/smoke.sh
fi
