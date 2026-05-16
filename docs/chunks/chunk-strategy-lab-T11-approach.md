---
chunk: strategy-lab-T11
project: atlas-os
date: 2026-05-16
task: Tournament Evaluator — genome promotion
---

## Data scale

No DB reads in this chunk. The tournament evaluator is pure in-process logic —
it calls a caller-supplied `sim_fn(genome, start, end) -> SimResult` and gates
on thresholds. No table scans, no pandas, no SQL.

## Approach

Two new files only:

1. `atlas/trading/tournament.py` — `TournamentEvaluator`, `PromotionResult`,
   `promote_to_leaderboard()`, `_auto_name()`.
2. `tests/trading/test_tournament.py` — 5 tests covering every round-failure
   path plus the happy path and `_auto_name`.

### Three-round gauntlet

- Round 1: recent 90-day OOS window. Sortino >= 0.7.
- Round 2: prior 90-day window (recent_start - 1 day, back 89 days). Sortino >= 0.5 (consistency gate).
- Round 3: three named stress periods (COVID crash, 2022 bear, 2023 bull).
  - COVID: max_drawdown <= 25%.
  - Bear: Sortino >= 0.0 (must not lose money).
  - Bull: Sortino >= 1.0 (must compound well).

### DB write path

`promote_to_leaderboard()` takes a SQLAlchemy connection and executes an
UPSERT against `atlas_strategy_leaderboard` (UUID PK schema, migration 067).
ON CONFLICT target: `(genome_id)`.

### Why pure-Python / no pandas

No data aggregation needed. All metrics come pre-computed from `sim_fn`.
Zero-pandas approach keeps memory at O(1) per evaluation.

## Wiki patterns checked

- Existing trading modules use `@dataclass` + `structlog` — matches.
- No cross-context imports. `tournament.py` only imports from `atlas.trading.*`.
- `from __future__ import annotations` on all new files.

## Existing code reused

- `Genome`, `GenomeFactory` from `atlas/trading/genome.py`.
- `SimResult` from `atlas/trading/simulator.py`.
- `structlog.get_logger()` pattern from every other trading module.

## Edge cases

- `sim_fn` returning all zeros: Sortino 0.0 < 0.7 → fails Round 1 cleanly.
- Missing stress period key in dict: `.get()` with default date tuple.
- `max_drawdown` is stored as a positive fraction (0.10 = 10%) per SimResult schema.

## Expected runtime

Single evaluation: 5 sim_fn calls (R1, R2, COVID, bear, bull). Pure Python.
Sub-millisecond per evaluation. Full 200-genome night run: negligible CPU.
