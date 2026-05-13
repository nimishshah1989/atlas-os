# Chunk: TV Signals Task 4 — Technical Cross-Check Module

## Data Scale
- `de_equity_ohlcv`: fetched with `LIMIT 300` (300 rows per ticker, not full table load)
- No full-table scan; join through `atlas_universe_stocks` for symbol → instrument_id resolution

## Chosen Approach
- Python + pandas-ta for RSI/MACD/EMA indicators (vectorized, ~300 rows per call)
- scipy.signal.find_peaks for HH/HL detection (algorithmic, avoids manual loop)
- All financial outputs as `Decimal`; floats used only for intermediate indicator math
- SQL via SQLAlchemy `text()` with parameterized query (no f-strings, S608 noqa on join line)

## Wiki Patterns Checked
- chunk-sp09-signals-approach.md: precedent for pandas-ta usage in this repo
- chunk-tv-signals-task2-approach.md: TV webhook signal pattern

## Existing Code Reused
- `atlas/signals/models.py` — existing package; new file added alongside
- numba stub in `tests/unit/conftest.py` — already handles pandas_ta import

## Edge Cases
- NULL close prices: counted and logged before ffill (pattern from CLAUDE.md guardrails)
- Missing EMA (insufficient history): falls back to `last["close"]` to avoid NaN propagation
- Missing vol SMA: falls back to 1.0 so ratio stays 1.0 (no division-by-zero)
- MACD NaN on first rows: `or 0` guard on float cast
- find_peaks with <2 peaks: length check before index comparison

## Expected Runtime
- 300-row fetch + pandas-ta on 300 rows: ~50ms per ticker on t3.large
- scipy find_peaks on 300 floats: <5ms
- Total: well under 500ms per call

## Files Created
- `atlas/signals/technical.py`
- `tests/unit/signals/test_technical.py`
