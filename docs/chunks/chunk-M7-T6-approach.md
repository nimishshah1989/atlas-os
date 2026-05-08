# Chunk M7-T6 Approach: paper_trader.py

## Data Scale
No DB calls from pure functions. DB functions (fetch_decisions, load_current_holdings,
write_trades, update_holdings, record_daily_performance) are called by runner.py.
Decision tables expected to be <10K rows per tier per day.

## Chosen Approach
Pure function separation: apply_strategy_filter + compute_trades have zero DB calls,
are the unit-test targets. DB functions wrap bulk_upsert + open_compute_session from
atlas.compute._session — the established pattern in this codebase.

## Wiki Patterns Checked
- Idempotent Upsert (patterns/idempotent-upsert.md) — ON CONFLICT DO UPDATE on natural
  keys; used in write_trades and update_holdings
- PRD Golden Example Testing (patterns/prd-golden-example-testing.md) — test fixtures
  correspond to spec acceptance criteria

## Existing Code Reused
- atlas.compute._session.bulk_upsert — same signature already used across M3-M5
- atlas.compute._session.open_compute_session — standard compute session pattern
- atlas/simulation/core/ — new file added alongside overlap.py and signal_adapter.py

## Edge Cases
- Cold start (empty holdings dict) — entry-only behavior
- Risk-Off + pause_risk_off — all new entries blocked, exits still processed
- Risk-Off + scale_risk_off — scale existing positions to 0.4x, emit rebalance trades
- Risk-Off + hold_risk_off — no behavior change
- exit takes priority over entry for the same instrument_id
- state_filter=["investable"] maps to None (accept any rs_state)
- max_positions cap on new entries when portfolio is close to limit

## Expected Runtime
Pure functions: microseconds per call (in-memory DataFrame iteration over <10K rows).
DB functions: single round-trip per call, <<1 s on t3.large.

## Files
- atlas/simulation/core/paper_trader.py (new)
- tests/unit/simulation/test_paper_trader.py (new)
