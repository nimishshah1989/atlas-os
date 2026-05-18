# Chunk v6-Task2 — Shared NSE Scraper Base: Approach

## Data scale
No database interaction in this chunk. Pure HTTP client abstraction.

## Chosen approach
Synchronous `requests.Session` wrapper. NSE APIs are not async-friendly (cookie
handshake must be sequential); synchronous is the right call here. The fetchers
that call this base run as batch scripts, not FastAPI handlers.

## Wiki patterns checked
- External API Format Drift (bug-patterns) — NSE changes URLs/formats without
  notice. Defence: session warming + browser headers + retry on 429/503.
- Transient vs Permanent Error Separation (staging) — 429/503 are transient
  (retry). 4xx (except 429) and 5xx (except 503) are permanent: let
  `raise_for_status()` propagate them.

## Existing code being reused
No existing scraper pattern in `atlas/`. First one. `requests` is already in
`pyproject.toml` dependencies. `structlog` is already a dependency. The
`responses` mock library needs to be added to dev dependencies.

## Package markers
`atlas/data_prereqs/__init__.py` and `atlas/data_prereqs/v6/__init__.py` do NOT
yet exist — they were intended to be created by Task 1 but are absent. Creating
them as empty package markers here.

## Edge cases
- `_warm_session()` is idempotent (guarded by `_warmed` flag)
- `_wait_for_interval()` first call: sets timestamp and returns immediately (no
  sleep on first request)
- 503 retry loop: attempt counter incremented before retry_max check so
  `retry_max=3` allows exactly 3 retries (4 total attempts)
- `raise_for_status()` called on success responses (non-429/503) to propagate
  404, 500 etc. as `requests.HTTPError`

## Expected runtime
All operations are I/O-bound HTTP calls. Unit tests use `responses` mock — no
real network. Test suite runtime < 1s.

## Files
- `atlas/data_prereqs/__init__.py` (new, empty marker)
- `atlas/data_prereqs/v6/__init__.py` (new, empty marker)
- `atlas/data_prereqs/v6/base.py` (new, ~80 LOC)
- `tests/data_prereqs/v6/test_base.py` (new, ~60 LOC)
