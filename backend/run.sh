#!/usr/bin/env bash
# Start the mock backend. Ward clock runs 60x so demo deadlines fire in seconds.
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install -q -r requirements.txt
exec ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${SG_PORT:-8099} --no-access-log "$@"
