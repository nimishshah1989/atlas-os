#!/usr/bin/env bash
# Atlas Strategy Lab — one-shot deployment to EC2 .214 (13.206.34.214).
#
# Runs on the consolidated EC2 host that serves both compute and frontend.
# Idempotent: re-running is safe. Stops on first failure (set -e).
#
# Usage (from local Mac):
#   ssh jsl-wealth-server 'cd ~/atlas-os && bash scripts/strategy_lab_deploy_214.sh'
#
# Or directly on .214:
#   cd ~/atlas-os && bash scripts/strategy_lab_deploy_214.sh
#
# Steps:
#   1. Pull feat/atlas-strategy-lab (or main once merged)
#   2. Install optimizer extras (optuna + deap)
#   3. Apply migration 067
#   4. Smoke-test imports
#   5. Print Phase 0 burn-in command (NOT auto-run — user kicks off explicitly)

set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/ubuntu/atlas-os}"
TARGET_BRANCH="${TARGET_BRANCH:-feat/atlas-strategy-lab}"

cd "$REPO_DIR"

echo "==> [1/4] Sync branch ${TARGET_BRANCH}"
git fetch origin
git checkout "$TARGET_BRANCH"
git pull --ff-only origin "$TARGET_BRANCH"

echo "==> [2/4] Install optimizer + simulation dependencies"
# optimizer brings optuna + deap; simulation brings vectorbt + PyPortfolioOpt.
# Strategy Lab uses both: optuna/deap drive the search, vectorbt runs the
# walk-forward portfolio simulation inside each trial.
source .venv/bin/activate
pip install -e ".[optimizer,simulation]" --quiet

echo "==> [3/4] Apply migration 067 (atlas_strategy_lab tables)"
# Alembic is idempotent: if 067 already applied, this is a no-op.
alembic upgrade head

echo "==> [4/5] Smoke-test trading module imports + DB tables"
python - <<'PY'
from atlas.trading.config import PortfolioConfig
from atlas.trading.genome import Genome, GenomeFactory
from atlas.trading.simulator import simulate_genome  # noqa: F401
from atlas.trading.evolver import Evolver  # noqa: F401
from atlas.trading.tournament import TournamentEvaluator  # noqa: F401
from atlas.trading.incubator import run_nightly  # noqa: F401
from atlas.db import get_engine
from sqlalchemy import text

cfg = PortfolioConfig()
print(f"  PortfolioConfig OK — starting_capital={cfg.starting_capital}")
g = GenomeFactory.random()
print(f"  Genome OK — id={g.genome_id[:8]}...")

engine = get_engine()
expected = [
    "atlas_strategy_genomes",
    "atlas_strategy_performance_daily",
    "atlas_strategy_positions_daily",
    "atlas_strategy_leaderboard",
    "atlas_strategy_insights",
    "atlas_universe_membership_daily",
    "atlas_strategy_evolution_log",
    "atlas_portfolio_config",
]
with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'atlas' AND tablename = ANY(:names)
    """), {"names": expected}).scalars().all()
missing = sorted(set(expected) - set(rows))
if missing:
    raise SystemExit(f"  MISSING tables: {missing}")
print(f"  All 8 strategy lab tables present: {sorted(rows)}")
PY

echo "==> [5/5] Integration test — verify leaderboard upsert path"
# Runs the integration tests added in review-fix B1. The
# uq_leaderboard_genome_id check fails fast if migration 067 was applied
# from an older revision (without the unique constraint).
python -m pytest tests/integration/trading/ -v --tb=short

cat <<'EOF'

==> DEPLOYMENT OK.

Next step — Phase 0 burn-in (one-time, ~3–6 hours on xlarge):

  cd /home/ubuntu/atlas-os
  source .venv/bin/activate
  export $(grep -E "^(GROQ_API_KEY|ATLAS_DB_URL)" .env | xargs)
  ATLAS_INCUBATOR_TRIALS=3000 nohup python -m atlas.trading.incubator \
    > /home/ubuntu/logs/strategy_lab_phase0_burnin.log 2>&1 &
  disown
  tail -f /home/ubuntu/logs/strategy_lab_phase0_burnin.log

After burn-in completes, verify leaderboard:

  psql "$ATLAS_DB_URL" -c "SELECT rank, sortino_oos, max_drawdown FROM atlas.atlas_strategy_leaderboard ORDER BY rank LIMIT 5;"

Then wire the nightly cron (already present in run_atlas_intelligence_nightly.sh
as the strategy_lab_incubator step — nothing extra needed; the existing cron
at 0 22 * * 1-5 will pick it up).

EOF
