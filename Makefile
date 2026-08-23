# Atlas dev tasks. Local toolchain runs via uv (see docs/engineering-process.md).
# Requires: uv (https://docs.astral.sh/uv/) and Python >=3.12.
#
# Deploy/backup targets (make deploy / make backup) land with Pillar 3 of the
# engineering-process plan; not defined yet.

.PHONY: setup test test-int lint format typecheck gate check heads clean clean-hard

# One-time (and after dependency changes): build the local .venv with dev deps.
setup:
	uv sync --extra dev

# Fast unit suite — no DB. Mirrors what CI/EC2 run.
# tests/scripts holds unit tests for scripts/foundation modules (fund_rank_core,
# universe_core, ...). It was omitted here and in ci.yml, so 38 tests — including the
# fund-composite/frontend parity guard — never ran anywhere. Adding it costs 0.04s.
test:
	uv run --extra dev pytest tests/unit tests/scripts -m unit -q

# Integration tests hit the live DB (read-only / rollback-wrapped). Run on EC2
# or locally with a direct (non-pooler) DB URL in .env.
test-int:
	uv run --extra dev pytest tests/integration -m integration -q

lint:
	uv run ruff check atlas tests scripts
	uv run ruff format --check atlas tests scripts

format:
	uv run ruff format atlas tests scripts

typecheck:
	uv run --extra dev pyright atlas

# Pre-push gate — run this before opening a PR. Mirrors what CI enforces.
# Uses the pyright RATCHET, not raw pyright: ~848 pre-existing errors are
# grandfathered in ci/pyright-baseline.json and CI fails only when a file's
# count rises. Raw `make typecheck` therefore exits non-zero by design.
gate: lint test
	uv run --extra dev python scripts/ci/pyright_ratchet.py

# Raw pyright over everything, baseline ignored. EXITS NON-ZERO on the
# grandfathered debt — that is expected. Use it to see the debt, not as a gate.
check: lint typecheck test

# Read-only: what migration head the code is at (no DB connection).
heads:
	uv run alembic heads

# Sweep the local disk junk that clutters the file tree — SURGICAL: tool caches,
# build artifacts, coverage, and stale deploy backups only. Deliberately does NOT
# touch .venv / node_modules / frontend/.next — on the prod box those ARE the running
# app, and `git clean -fdX` would delete them and take the board down. Safe anywhere.
clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \
	  -o -name .mypy_cache -o -name '*.egg-info' \) -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage coverage.json htmlcov output 2>/dev/null || true
	rm -rf frontend/.next.bak.* 2>/dev/null || true      # stale deploy backups (keep .next itself)
	@echo "swept caches + build artifacts + stale .next backups (left .venv/.next/node_modules intact)"

# Full reset of ALL git-ignored files — for a LOCAL DEV machine only, NEVER the prod box
# (it deletes .venv/.next/node_modules → rebuild required, and would 500 the live board).
clean-hard:
	git clean -fdX
