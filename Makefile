# Atlas dev tasks. Local toolchain runs via uv (see docs/engineering-process.md).
# Requires: uv (https://docs.astral.sh/uv/) and Python >=3.12.
#
# Deploy/backup targets (make deploy / make backup) land with Pillar 3 of the
# engineering-process plan; not defined yet.

.PHONY: setup test test-int lint format typecheck check heads

# One-time (and after dependency changes): build the local .venv with dev deps.
setup:
	uv sync --extra dev

# Fast unit suite — no DB. Mirrors what CI/EC2 run.
test:
	uv run --extra dev pytest tests/unit -m unit -q

# Integration tests hit the live DB (read-only / rollback-wrapped). Run on EC2
# or locally with a direct (non-pooler) DB URL in .env.
test-int:
	uv run --extra dev pytest tests/integration -m integration -q

lint:
	uv run ruff check atlas tests scripts

format:
	uv run ruff format atlas tests scripts

typecheck:
	uv run --extra dev pyright atlas

# Pre-push gate: lint + types + unit tests. Run this before opening a PR.
check: lint typecheck test

# Read-only: what migration head the code is at (no DB connection).
heads:
	uv run alembic heads
