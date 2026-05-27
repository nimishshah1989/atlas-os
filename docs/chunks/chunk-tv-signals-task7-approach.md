# Chunk: TV Signals Task 7 — Chart Screenshot Capture

## Data scale
No DB queries needed for this module. Pure async I/O — Playwright browser automation
writing PNG files to disk. No table row counts relevant.

## Approach

### Module: `atlas/signals/screenshot.py`
Playwright async API for TradingView chart capture with cookie-based auth.

Three public surfaces:
1. `_build_chart_url` — pure string construction, no I/O
2. `_screenshot_one` — async Playwright page.screenshot(); returns bool; never raises
3. `capture_chart_screenshots` — orchestrates 3 parallel captures; returns dict with 6 keys

Cookie auth pattern: inject `sessionid` + `sessionid_sign` into the browser context
before navigation. Domain `.tradingview.com`. This is the standard TV session cookie
pattern — same as what a logged-in browser holds.

### Wiki patterns checked
- "Subprocess Zombie on Timeout" (staging) — relevant for Playwright; we use asyncio
  properly via async_playwright context manager so cleanup is handled
- "Transient vs Permanent Error Separation" (staging) — `_screenshot_one` catches all
  exceptions and returns False; caller continues for remaining charts (capture-all semantics)

### Existing code being reused
- `Config.TV_SESSION_ID`, `Config.TV_SESSION_SIGN`, `Config.SIGNAL_SCREENSHOT_DIR` —
  already declared in `atlas/config.py`
- `structlog` logger pattern from `atlas/signals/processor.py`

### Edge cases
- Screenshot dir does not exist: `Path(path).parent.mkdir(parents=True, exist_ok=True)` before screenshot
- `_screenshot_one` raises any exception: log it, return False; caller sets path=None
- All 3 fail: dict has all path keys = None, all url keys populated
- Empty TV_SESSION_ID: Playwright still navigates; TV login page shown; screenshot saved but
  unusable — caller's responsibility (downstream narrative will lack chart image URLs but
  won't error)
- Timestamp collision: strftime to seconds is sufficient; single process, sequential calls

### Expected runtime
- Each screenshot: ~5-8s (3s explicit wait + navigation + render)
- All 3 total: ~20-25s sequential (Playwright chromium launch adds ~2s)
- On t3.large: well within FastAPI background task budget; called after DB writes complete

## Test approach
All tests mock Playwright entirely — no real browser. Mock `_screenshot_one` at module
level for the higher-level capture tests. `Path.mkdir` mocked to verify dir creation.
Five tests total, all async.
