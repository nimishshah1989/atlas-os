#!/usr/bin/env bash
# Pragma finance-critical coverage gate (CI-vendored copy).
#
# Files tagged `# pragma: finance-critical` MUST have 100% line coverage.
# This is the same gate as the global pre-commit hook
# (~/.claude/gates/gate-pragma-coverage.sh), vendored into the repo so CI can
# run it without the developer's global ~/.claude install. The local
# pre-commit hook can't run on the Mac venv (no pytest-cov); CI is where this
# now executes for real. See docs/engineering-process.md (Pillar 2).
#
# Requires: pytest + pytest-cov (dev extra), jq, GNU realpath (coreutils).
# Run under `uv run --extra dev` so pytest/coverage resolve.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

PRAGMA_FILES=$(grep -rlE "# *pragma: *finance-critical" --include="*.py" \
  --exclude-dir=.venv --exclude-dir=venv --exclude-dir=__pycache__ \
  --exclude-dir=.mypy_cache --exclude-dir=dist --exclude-dir=build \
  --exclude-dir=node_modules --exclude-dir=.git \
  . 2>/dev/null || true)

if [ -z "$PRAGMA_FILES" ]; then
  echo "pragma coverage gate: no finance-critical files found — nothing to check"
  exit 0
fi

command -v pytest >/dev/null || { echo "pytest not installed"; exit 1; }

# One --cov= flag per unique dir (pytest-cov rejects comma-separated paths).
# Strip leading ./ so coverage.json keys match (e.g. atlas/compute not ./atlas/compute).
COV_FLAGS=$(echo "$PRAGMA_FILES" | xargs -n1 dirname | sort -u | sed 's|^\./||' | sed 's|^|--cov=|')

# tests/trading/ imports optuna + vectorbt (the `optimizer` / `simulation`
# extras) at collection time; those extras are NOT in the default dev install,
# so collecting them errors in CI. They cover none of the finance-critical
# files, so skipping them does not affect the coverage measured here. If a
# future pragma file is only exercised by trading tests, this gate will report
# <100% for it and we revisit (install the extras or move the test).
PYTEST_IGNORE="--ignore=tests/trading"

# shellcheck disable=SC2086
pytest $COV_FLAGS $PYTEST_IGNORE --cov-report=json --cov-report=term -q -m "not integration" > /tmp/pragma-cov.out 2>&1 || {
  cat /tmp/pragma-cov.out >&2
  echo "" >&2
  echo "BLOCKED: pragma coverage gate — the pytest run itself failed." >&2
  exit 1
}

[ -f coverage.json ] || { echo "no coverage.json produced" >&2; exit 1; }

FAILED=""
for FILE in $PRAGMA_FILES; do
  REL=$(realpath --relative-to="$(pwd)" "$FILE" 2>/dev/null || echo "$FILE")
  REL="${REL#./}"
  PCT=$(jq -r --arg f "$REL" '.files[$f].summary.percent_covered // empty' coverage.json)
  if [ -z "$PCT" ]; then
    FAILED="$FAILED\n  $REL: no coverage data (test it or remove the pragma)"
    continue
  fi
  if awk "BEGIN { exit !($PCT < 100) }"; then
    FAILED="$FAILED\n  $REL: ${PCT}% (need 100%)"
  fi
done

if [ -n "$FAILED" ]; then
  echo "BLOCKED: pragma coverage gate" >&2
  printf "Finance-critical files below 100%% coverage:%b\n" "$FAILED" >&2
  exit 1
fi

echo "pragma coverage gate: OK"
exit 0
