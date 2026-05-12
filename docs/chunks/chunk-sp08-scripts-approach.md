# SP08 Scripts + Systemd — Approach

## Scope
Four deliverables:
1. `scripts/trading_calendar.py` — NSE holiday/half-day guard
2. `scripts/kite_daily_notify.py` — Telegram 08:55 IST reminder
3. `scripts/run_intraday.py` — ingester entry point
4. `systemd/atlas-intraday.service` + timer + notify service + notify timer

## Data scale
No DB queries needed for these files — they are orchestration scripts, not data transforms.

## Wiki patterns checked
- **Fail-Open Trading Calendar** (wiki/patterns/fail-open-trading-calendar.md): hardcoded
  holiday list defaults to trading day on missing entry. Applied here with inverse: we
  hardcode the known holidays and treat absence-of-entry as trading day. Script exits 1
  for holidays so systemd ExecStartPre blocks the service.
- **Module-Level Side Effect** (wiki/bug-patterns/module-level-side-effect.md):
  `main()` wrapped in `if __name__ == "__main__"` guard to prevent import-time execution.

## Existing code being reused
- `atlas.intraday.auth.get_valid_access_token` — token check in notify script
- `atlas.intraday.notify.send_message_sync` — Telegram dispatch
- `atlas.intraday.ingester.IntradayIngester` — instantiated in run_intraday.py
- `_IST_OFFSET = timezone(timedelta(hours=5, minutes=30))` pattern from auth.py and ingester.py

## Approach

### trading_calendar.py
- Hardcode NSE_HOLIDAYS as `frozenset[str]` of YYYY-MM-DD strings (2026 list)
- `is_trading_day(check_date=None)`: weekday check first (0-4 = Mon-Fri), then holiday set
- IST-aware: default date from `datetime.now(IST).date()`
- Exit code: 0 = trading day, 1 = holiday — systemd ExecStartPre uses this
- `market_open_time()` / `market_close_time()` return tz-aware datetimes in IST

### kite_daily_notify.py
- sys.path bootstrap + dotenv
- Try `get_valid_access_token` (needs DATABASE_URL): if succeeds → "Already Authenticated" message
- If RuntimeError (no valid token): send auth-required message
- Handle DatabaseURL missing gracefully: log warning, send auth-required anyway
- Exit 0 on success, sys.exit(1) on unhandled exception

### run_intraday.py
- sys.path bootstrap + dotenv
- Call `is_trading_day()` — exit 0 if not trading
- Read DATABASE_URL — exit 1 if missing
- Instantiate IntradayIngester
- SIGTERM/SIGINT → ingester.stop() → sys.exit(0)
- Block with `while not ingester._stop_event.is_set(): time.sleep(10)`

### systemd units
- atlas-intraday.service: ExecStartPre = trading_calendar.py (exit 1 blocks start)
- atlas-intraday.timer: OnCalendar=Mon-Fri 03:40:00 UTC (= 09:10 IST)
- atlas-intraday-notify.service: Type=oneshot, runs kite_daily_notify.py
- atlas-intraday-notify.timer: OnCalendar=Mon-Fri 03:25:00 UTC (= 08:55 IST)

## Edge cases
- `get_valid_access_token` raises RuntimeError when no DB row: caught explicitly
- `DATABASE_URL` absent in notify script: token check skipped, auth-required message sent
- IST vs UTC: all systemd timers use UTC with comment noting IST equivalent
- Weekend: `weekday()` returns 5/6 for Sat/Sun → False before holiday lookup

## Expected runtime
All scripts complete in <5s. No data loads. Systemd units have no memory footprint.
