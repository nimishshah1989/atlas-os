#!/usr/bin/env bash
# psql against an env-held DB URL, with the password masked out of ALL output.
#
# Two jobs, both learned the hard way on 2026-07-31:
#   1. Strip the SQLAlchemy driver prefix and query string. psql rejects
#      "postgresql+psycopg2://...?sslmode=require" and echoes the WHOLE URL —
#      password included — in the error. That leak is the reason this file exists.
#   2. Mask "://user:pass@" in every line of stdout AND stderr.
#
# Masking has to be structural, not a regex someone remembers to type: the leak
# happened in a session where the same command had been masked correctly eight
# times and once was not.
#
# Usage: scripts/ops/psql_masked.sh ATLAS_DB_URL -c "SELECT 1"
#        scripts/ops/psql_masked.sh MAAL_SOURCE_DB_URL -tAc "SELECT count(*) FROM cpp_holdings"
set -uo pipefail
[ $# -ge 1 ] || { echo "usage: $0 <ENV_VAR_NAME> [psql args...]" >&2; exit 2; }
VAR="$1"; shift
URL="${!VAR:-}"
[ -n "$URL" ] || { echo "$VAR is not set" >&2; exit 2; }
URL=$(printf '%s' "$URL" | sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#; s#\?.*##')
psql "$URL" "$@" 2>&1 | sed -E 's#://[^@/]+@#://***:***@#g'
exit "${PIPESTATUS[0]}"
