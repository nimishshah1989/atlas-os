# Global Atlas — runbook (Phase 1)

Everything an operator does by hand for the US platform. Keys and passwords live in `.env` on the
laptop/box and in Vercel env — never in this repo (it is public). Steps whose producer has not
landed yet are marked with their chunk (P1-B, P1-D, P1-E); everything else is actionable now.

## 1. Keys and environment

| Variable | Where | What it is |
|---|---|---|
| `ATLAS_DB_URL` | laptop/box `.env` | `postgresql+psycopg2://…` — the same Supabase project as India (session pooler on the box; the `aws-1-ap-south-1` pooler works from the laptop, `aws-0-` does not) |
| `GLOBAL_PRICE_PROVIDER` | laptop/box `.env` | `tiingo` — no default on purpose; a missing value stops `ingest_prices` |
| `TIINGO_API_KEY` | laptop/box `.env` | the FREE key first (`validate_global --check FEED` runs on it); upgrade the plan only after the gate passes (`docs/global/phase1.md` §1) |
| `EDGAR_IDENTITY` | laptop/box `.env` | `"Firstname Lastname email@domain"` — the SEC fair-access User-Agent; `build_identity.py` refuses to run without it |
| `FRED_API_KEY` | laptop/box `.env` | India's key works (same account) |
| `ATLAS_GLOBAL_DB_URL` | Vercel env | `postgresql://atlas_global_app:<pw>@…pooler.supabase.com:6543/postgres?sslmode=require` — the **transaction** pooler (6543), never the session pooler |
| `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Vercel env | Supabase Auth (magic link) |
| `GLOBAL_REVALIDATE_SECRET` | Vercel env + box `.env` | bearer token the orchestrator's publish step sends to `/api/revalidate` (`openssl rand -hex 32`; the same value on both sides) |
| `GLOBAL_REVALIDATE_URL` | box `.env` | `https://<vercel-origin>/api/revalidate` — where the publish step POSTs `{"tag":"eod"}`; unset = the step is skipped and the log says so |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | box `.env` | gate-failure pushes (India's values) |

## 2. Prod schema (one-off, then per DDL change)

```
uv run python scripts/global_market/apply_ddl.py --dry-run      # lists 00_core … 06_baskets
uv run python scripts/global_market/apply_ddl.py                # idempotent; 41 tables
uv run python scripts/global_market/seed_thresholds.py --dry-run # READ the 60 rows first
uv run python scripts/global_market/seed_thresholds.py           # ON CONFLICT DO NOTHING
python -m atlas.db                                               # atlas_global_exists True
```
`liquidity_min_traded_value_usd` and the four `cls_*` thresholds are NOT seeded — set them from
`/admin/thresholds` once the Phase 1 ADV$ table (P1-E) and the Phase 2 taxonomy work exist.

## 3. The board's database role (one-off, psql as the project owner)

The DDL files create no roles (cluster-level, and the files forbid `$`). Run once:

```sql
CREATE ROLE atlas_global_app LOGIN PASSWORD '<generate a long one>';
GRANT USAGE ON SCHEMA atlas_global TO atlas_global_app;
GRANT SELECT ON ALL TABLES IN SCHEMA atlas_global TO atlas_global_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA atlas_global GRANT SELECT ON TABLES TO atlas_global_app;
-- writes only where the board writes (admin edits, overrides, users; baskets in M2):
GRANT INSERT, UPDATE ON atlas_global.atlas_thresholds, atlas_global.atlas_thresholds_audit,
  atlas_global.etf_classification_override, atlas_global.app_user TO atlas_global_app;
GRANT INSERT, UPDATE, DELETE ON atlas_global.basket_master, atlas_global.basket_constituents,
  atlas_global.basket_trades TO atlas_global_app;
-- and nothing on atlas_foundation:
REVOKE ALL ON SCHEMA atlas_foundation FROM atlas_global_app;
```
The India role gets no grant on `atlas_global`. Verify: `psql -U atlas_global_app -c "select count(*) from atlas_foundation.instrument_master"` must fail with permission denied.

## 4. Vercel + Supabase Auth (one-off)

1. Vercel project → Git integration on this repo, **root directory `frontend-global`**, region `bom1`
   (`vercel.json`; fall back to `sin1` if bom1 is not offered), env vars from §1.
2. Supabase → Authentication → enable Email (magic link); add `<vercel-origin>/login/callback` to the
   redirect allowlist; disable public sign-ups if the dashboard offers it (the board's own allowlist
   is `atlas_global.app_user`).
3. Insert the FM's row: `insert into atlas_global.app_user (email, role, display_name) values ('<lowercase email>', 'fm', '<name>');`
   (emails are stored lowercase — a CHECK enforces it).
4. Open `/health` on the preview URL: with the DB reachable it shows the ops tables (empty until the
   first nightly); `/` redirects to `/login`; a magic link to the FM's email signs in.

## 5. Identity, prices, first backfill (order matters)

```
uv run python scripts/global_market/validate_global.py --check FEED            # Tiingo free key; PASS before any spend
uv run python scripts/global_market/build_identity.py --stooq-zip ~/Downloads/d_us_txt.zip --report identity.csv
uv run python scripts/global_market/seed_benchmarks.py
uv run python scripts/global_market/ingest_index_membership.py --history --eod <eod>
uv run python scripts/global_market/ingest_prices.py --backfill --since 2016-01-04     # (P1-B) ~6,200 calls, run overnight
uv run python scripts/global_market/import_stooq.py --zip ~/Downloads/d_us_txt.zip     # cross-check rows, labelled by label_stooq
uv run python scripts/global_market/ingest_macro.py --since 2016-01-01
uv run python scripts/global_market/compute_technicals.py                              # (P1-D)
uv run python scripts/global_market/build_universe_snapshot.py                         # (P1-E) prints the ADV$ table, exits 2 until the floor is set
uv run python scripts/global_market/validate_global.py --check A
```

## 6. Cron on the box

```
# 01:00 UTC Tue–Sat daily (= 21:00 ET), Sat 01:30 UTC weekly after the daily. One lock: the weekly waits up to
# two hours for Saturday's daily, the daily never starts twice. Weekly rc 75 = the lock was still held after
# two hours; any other rc is the script's own exit.
# Install these two lines only after ingest_prices (P1-B) has landed and SPY bars exist: the freshness gate
# needs the SPY session anchor, and ingest_macro refuses to write without it (exit 2; --allow-raw-dates is dev-only).
0 1 * * 2-6   flock -n /tmp/atlas_global.lock /home/ubuntu/atlas-os/scripts/ops/atlas_global_daily.sh >> /home/ubuntu/logs/atlas_global_daily_cron.log 2>&1
30 1 * * 6    flock -w 7200 -E 75 /tmp/atlas_global.lock /home/ubuntu/atlas-os/scripts/ops/atlas_global_weekly.sh >> /home/ubuntu/logs/atlas_global_weekly_cron.log 2>&1 || echo "$(date -Is) weekly skipped: lock held (rc=$?)" >> /home/ubuntu/logs/atlas_global_weekly_cron.log
```
The same two lines sit in `scripts/ops/crontab.txt` (the box's tracked crontab). Both scripts are
Python-only (no pm2, no `.next`) and cannot collide with the India runs (07:00 / 10:30 UTC). A failed
step never aborts the chain; the snapshot is written whether or not a gate failed, so a bad night is
visible on `/health` (§7); a failed gate pushes to Telegram. Each run writes
`$ATLAS_LOG_DIR/atlas_global_<daily|weekly>_<timestamp>.log`; cron's own output lands in the
`_cron.log` files above.

**Identity snapshots.** The weekly saves the directories it fetched under
`$ATLAS_LOG_DIR/identity/<EOD>/` (the six files,
`MANIFEST.json` with sha256 + fetched-at, `build_identity_<EOD>.csv` with every row's outcome —
a run without `--snapshot-dir` writes the report to `$ATLAS_LOG_DIR`, never the working directory),
keeping the newest 8 dated directories (`--keep`). `build_identity` exits 2 with
`REFUSED: refusing to deactivate N of M active rows` when a directory would delist more than
min(2 percent, 200) of the active rows — a truncated or wrong download, nothing is written: check
the saved files, re-fetch, and pass `--allow-mass-deactivation` only when the delistings are real. A
Nasdaq file without its `File Creation Time` trailer does not parse at all. The report's
`sec_conflict` (four tickers on 2026-09-04: IA, SPCX, AEMC, ISRL carry two CIKs across the SEC
files) and `name_agrees` columns are the FM's review list; `source = 'manual'` rows are never
auto-deactivated, they are reported.

**Environment overrides** (all optional; the box uses the defaults):

| Variable | Default | Effect |
|---|---|---|
| `ATLAS_REPO` | `/home/ubuntu/atlas-os` | the checkout to run from. Set = **dry-run mode**: `.env` is never sourced, `ATLAS_DB_URL` must be exported, and its host must be `localhost`/`127.0.0.1` (else the script exits 1 naming the host). Unset = the box: `.venv` and `.env` are mandatory |
| `ATLAS_ALLOW_REMOTE_DB` | unset | `1` lets a dry run use a non-localhost `ATLAS_DB_URL` — deliberate, never the default |
| `ATLAS_LOG_DIR` | `/home/ubuntu/logs` | where logs and the weekly's identity snapshots (`identity/<EOD>/`) go |
| `ATLAS_IDENTITY_SNAPSHOT` | unset | weekly: replay a saved `identity/<EOD>` directory (`build_identity --from-snapshot`) instead of fetching — a dry run, or the SEC's ten-minute 429 window |
| `STOOQ_ARCHIVE` | `/home/ubuntu/data/stooq/d_us_txt.zip` | weekly: the Stooq archive for delisted names; passed only if the file exists |

**Dry run on a laptop** — a scratch database with the DDL applied (§2), e.g. a clone of the identity
database. With `ATLAS_REPO` set the scripts never source `.env`: `ATLAS_DB_URL` must be exported, and
one whose host is not `localhost`/`127.0.0.1` is refused (exit 1, host printed) unless
`ATLAS_ALLOW_REMOTE_DB=1` — a laptop run cannot write prod by accident.

```
export ATLAS_REPO=$PWD ATLAS_LOG_DIR=/tmp/atlas-logs
export ATLAS_DB_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/atlas_scratch   # exported, localhost
export EDGAR_IDENTITY="Firstname Lastname email@domain"        # + FRED_API_KEY for ingest_macro
bash scripts/ops/atlas_global_weekly.sh                         # identity (live fetch), benchmarks, S&P 500, gate, snapshot
bash scripts/ops/atlas_global_daily.sh                          # macro, gate, publish (skipped: no URL), snapshot
psql postgresql://postgres:postgres@localhost:5432/atlas_scratch \
  -c "select script_name, milestone, status from atlas_global.atlas_pipeline_runs order by started_at"
```
Without a FRED key the gate fails on `macro_daily: EMPTY` (the honest outcome) and publish is skipped;
both snapshots still land, one row per step, and a re-run over the same runfile updates its rows in
place (only `updated_at` / `computed_at` move). To exercise the publish step against a local board:
`cd frontend-global && npm run build && GLOBAL_REVALIDATE_SECRET=<s> npm run start -- -p 3100`, then
`GLOBAL_REVALIDATE_URL=http://localhost:3100/api/revalidate GLOBAL_REVALIDATE_SECRET=<s>` in the
daily's environment — it fires only once every gate passes; `ok: publish` is HTTP 200, anything else
`FAIL: publish (http NNN)` (a 308 = a trailing slash in the URL).

## 7. Reading `/health`

Every row on the page is a real row in `atlas_global`; nothing is computed in the browser.

| Panel | Table | What a row means |
|---|---|---|
| Headline + tiles | `atlas_pipeline_runs`, `atlas_validator_results`, `atlas_health_daily` | the newest run row's status in words; scripts with a run; failures in the last 30 runs; validators passing; metrics flagged on the latest snapshot |
| Latest run per script · Recent runs | `atlas_pipeline_runs` | one row per orchestrator **step** (`script_name` = the step name in the `.sh`; `publish` = the revalidate POST), `milestone` daily/weekly, `status` = the step's exit code (`success`/`failed`), started/ended, host, git sha — one row per step; re-runs update in place |
| Validators | `atlas_validator_results` | one row per **gate** step: `freshness_guard`, `gate_A` (`validate_global --check A`). PASS/FAIL is the gate's exit code; any FAIL withholds publish. Pass rate is over the 30-day window |
| Freshness | `atlas_health_daily` (`freshness_lag_sessions`) | one row per tracked table (`instrument_master`, `index_membership`, `macro_daily`, `ohlcv_daily`, `technical_daily`, `universe_snapshot`): lag in SPY sessions (0 = the table has the EOD), tolerance and tier from `freshness_guard.py`'s registries — **critical** withholds publish, **warn** only reports, "not guarded yet" = the producer chunk has not landed; `EMPTY` = no rows; a blank lag with "no SPY bar" = `ohlcv_daily` has no anchor bar yet |
| Flagged metrics | `atlas_health_daily` (`is_anomaly`) | the subset above that breached its tolerance, plus any other flagged metric a later snapshot adds |
| Provider calls | `provider_calls` | requests per (provider, endpoint) on the latest run date — every script adds its adapter's counter when it commits, so a re-run within the day accumulates. Compare against the plan limits in `phase1.md` §1 (Tiingo) and the SEC fair-access ceiling (10 req/s) |

**When a gate fails** (the Telegram push says "GLOBAL BOARD NOT UPDATED"):

1. `/health` → the failed validator row, the critical freshness row, the failed step's log line.
2. The log names the check; fix the data (never the assertion), re-run the step, re-run the gate.
3. The board keeps its last-good data until every gate passes; nothing is republished by hand
   — the publish step is the only caller of `/api/revalidate`.

## 8. First night checklist

1. Box `.env` carries `ATLAS_DB_URL`, `EDGAR_IDENTITY`, `FRED_API_KEY`, `TIINGO_API_KEY`,
   `GLOBAL_PRICE_PROVIDER`, `GLOBAL_REVALIDATE_URL`, `GLOBAL_REVALIDATE_SECRET`,
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`; `python scripts/global_market/_gdb.py` prints the
   pooler host and today's EOD; `python -m atlas.db` says `atlas_global_exists True`.
2. §5 has been run through `ingest_macro` at least once (the gate fails on an empty
   `macro_daily`, by design).
3. Run the weekly by hand, then the daily, and read both logs end to end:
   `bash scripts/ops/atlas_global_weekly.sh; bash scripts/ops/atlas_global_daily.sh`.
4. `select script_name, milestone, status from atlas_global.atlas_pipeline_runs order by started_at`
   shows one row per step; `/health` on the Vercel deployment renders them, the validator
   rows, the freshness table and the provider-call counts.
5. `curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$GLOBAL_REVALIDATE_URL" -H 'Authorization: Bearer wrong' -d '{"tag":"eod"}'`
   → `401`; with the real secret → `200` and `{"revalidated":true,"tag":"eod",…}`.
6. Install the two cron lines (§6). Next morning: the log, `/health`, and — only if a gate
   failed — the Telegram push.
