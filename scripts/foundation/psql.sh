#!/usr/bin/env bash
# Thin psql wrapper: extracts ATLAS_DB_URL from frontend/.env.local (no secret on disk),
# strips the SQLAlchemy +psycopg2 driver tag, and runs psql. Usage: psql.sh -c "select 1"
set -euo pipefail
ENVFILE="$(dirname "$0")/../../frontend/.env.local"
RAW=$(grep -E '^ATLAS_DB_URL=' "$ENVFILE" | head -1 | cut -d= -f2-)
RAW="${RAW%\"}"; RAW="${RAW#\"}"; RAW="${RAW%\'}"; RAW="${RAW#\'}"
PSQLURL="${RAW/+psycopg2/}"
export PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-20}"
exec psql "$PSQLURL" "$@"
