# Global Atlas — runbook (Phase 1)

Everything an operator does by hand for the US platform. Keys and passwords live in `.env` on the
laptop/box and in the board's own `.env.local` — never in this repo (it is public).

Steps whose producer has not landed yet are marked with their chunk (P1-B, P1-D, P1-E);
everything else is actionable now.

> **Hosting: the board is served from the box at `atlas.jslwealth.in/global`, not from Vercel**
> (FM, 2026-09-07). `docs/global/deploy-subpath.md` is the deployment package and **supersedes the
> Vercel half of §4**; "board `.env.local`" in §1 is `frontend-global/.env.local` in the serving
> directory on the box. §2, §3 and §5–§8 are unchanged.

## 1. Keys and environment

| Variable | Where | What it is |
|---|---|---|
| `ATLAS_DB_URL` | laptop/box `.env` | `postgresql+psycopg2://…` — the same Supabase project as India (session pooler on the box; the `aws-1-ap-south-1` pooler works from the laptop, `aws-0-` does not) |
| `GLOBAL_PRICE_PROVIDER` | laptop/box `.env` | `alpaca` (the spine since the SIP gate passed, 2026-09-07) or `stooq_bulk`. **No default and no third value** — anything else raises rather than ingesting an untested feed |
| `ALPACA_API_KEY` / `ALPACA_API_SECRET` | laptop/box `.env` | the paper account's key pair from `app.alpaca.markets` (Home → Generate New Key). Free plan; the secret is shown once and regenerating invalidates the old pair |
| `EDGAR_IDENTITY` | laptop/box `.env` | `"Firstname Lastname email@domain"` — the SEC fair-access User-Agent; `build_identity.py` refuses to run without it |
| `FRED_API_KEY` | laptop/box `.env` | **OPTIONAL.** Unset, `ingest_macro` reads FRED's keyless CSV export (`graph/fredgraph.csv`) — same observations, no registration; the run prints which transport it used and `provider_calls` records it under that endpoint. Set it (India's key works, same account) for the JSON API's revision vintages |
| `ATLAS_GLOBAL_DB_URL` | board `.env.local` | `postgresql://atlas_global_app:<pw>@…pooler.supabase.com:6543/postgres?sslmode=require` — the **transaction** pooler (6543), never the session pooler; India's session pool already holds 14 of its 15 slots |
| `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | board `.env.local` | Supabase Auth (magic link) |
| `ATLAS_GLOBAL_BASE_PATH` | board `.env.local` + the deploy shell | `/global` on the box, unset at the root. Needed at BUILD time *and* RUN time, same value (`docs/global/deploy-subpath.md` §2) |
| `GLOBAL_REVALIDATE_SECRET` | board `.env.local` + box `.env` | bearer token the orchestrator's publish step sends to `/api/revalidate` (`openssl rand -hex 32`; the same value on both sides) |
| `GLOBAL_REVALIDATE_URL` | box `.env` | `http://127.0.0.1:<port>/global/api/revalidate` — loopback, so the publish cannot fail on the proxy; **no trailing slash** (a 308 fails the step). Unset = the step is skipped and the log says so |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | box `.env` | gate-failure pushes (India's values) |

## 2. Prod schema (one-off, then per DDL change)

```
uv run python scripts/global_market/apply_ddl.py --dry-run      # lists 00_core … 06_baskets
uv run python scripts/global_market/apply_ddl.py                # idempotent; 41 tables
uv run python scripts/global_market/seed_thresholds.py --dry-run # READ the 61 rows first
uv run python scripts/global_market/seed_thresholds.py           # ON CONFLICT DO NOTHING
python -m atlas.db                                               # atlas_global_exists True
```
The four `cls_*` thresholds are NOT seeded — set them from `/admin/thresholds` once the Phase 2
taxonomy work exists. `liquidity_min_traded_value_usd` IS seeded, at $1,000,000: the FM set the
floor on 2026-09-06 from the real P1-E distribution (`docs/global/reports/adv_usd_2026-09-03.md`),
and the seed row carries that decision in its `description`.

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

## 4. Serving the board + Supabase Auth (one-off)

**Steps 1 and 4 are superseded by `docs/global/deploy-subpath.md`** (pm2 + nginx on the box), and
in step 2 the redirect URL is `https://atlas.jslwealth.in/global/login/callback` — the Site URL
must move to `https://atlas.jslwealth.in/global` as well, or a link that fails the allow-list
check silently goes to Vercel. Steps 2 and 3 otherwise stand.

1. ~~Vercel project~~ → Git integration on this repo, **root directory `frontend-global`**, region `bom1`
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
uv run python scripts/global_market/validate_global.py --check SIP --stooq-file <archive>/spy.us.txt   # PASSED 2026-09-07; re-run only if the account changes
uv run python scripts/global_market/build_identity.py --stooq-zip ~/Downloads/d_us_txt.zip --report identity.csv
uv run python scripts/global_market/seed_benchmarks.py
uv run python scripts/global_market/ingest_index_membership.py --history --eod <eod>
uv run python scripts/global_market/ingest_prices.py --backfill --since 2016-01-04     # (P1-B) ~6,200 calls, run overnight
uv run python scripts/global_market/import_stooq.py --zip ~/Downloads/d_us_txt.zip     # cross-check rows, labelled by label_stooq
uv run python scripts/global_market/ingest_macro.py --since 2016-01-01
uv run python scripts/global_market/compute_technicals.py                              # (P1-D)
uv run python scripts/global_market/build_universe_snapshot.py                         # (P1-E) prints the ADV$ table, exits 2 until the floor is set
uv run python scripts/global_market/validate_global.py --check A                       # (P1-B) not landed yet; --check today accepts only SIP and BASIS
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
export EDGAR_IDENTITY="Firstname Lastname email@domain"        # FRED_API_KEY optional: unset = keyless CSV
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
4. `build_universe_snapshot` exits 2 (`REFUSED: liquidity_min_traded_value_usd …`,
   `universe_snapshot` EMPTY on `/health`) whenever that row is missing or inactive. Since
   2026-09-06 the floor SHIPS SEEDED at $1,000,000 (§2, the FM's decision from the P1-E ADV$
   table), so on a correctly provisioned schema this refusal means the seed never ran — run
   `seed_thresholds.py`. The refusal stays because it is the guard: nothing may cut the universe
   on a floor nobody chose. To change the floor, use `/admin/thresholds`, or an
   `atlas_thresholds` UPDATE (INSERT if the row is genuinely absent) plus an
   `atlas_thresholds_audit` row with `changed_by` and `change_reason`; never in code or a test.
   The next run writes the rows and prints the counts per exclusion reason.
   Name `is_active` in that insert — `load_thresholds()` reads only `is_active = TRUE`:

   ```sql
   INSERT INTO atlas_global.atlas_thresholds
       (threshold_key, threshold_value, category, description, units,
        last_modified_by, last_modified_at, is_active, created_at)
   VALUES ('liquidity_min_traded_value_usd', <floor>, 'universe',
           'ADV$ floor for scoring and basket eligibility', 'usd',
           '<email>', now(), true, now());
   ```

   The column defaults to `true` on a freshly applied schema, so an insert that omits it still
   works; naming it makes the row's visibility explicit. If a run still refuses after the row
   is in, it now prints whether the row is missing or merely inactive.

## 8. First night checklist

1. Box `.env` carries `ATLAS_DB_URL`, `EDGAR_IDENTITY`, `FRED_API_KEY`, `ALPACA_API_KEY`,
   `ALPACA_API_SECRET`, `GLOBAL_PRICE_PROVIDER=alpaca`, `GLOBAL_REVALIDATE_URL`, `GLOBAL_REVALIDATE_SECRET`,
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`; `python scripts/global_market/_gdb.py` prints the
   pooler host and today's EOD; `python -m atlas.db` says `atlas_global_exists True`.
2. §5 has been run through `ingest_macro` at least once (the gate fails on an empty
   `macro_daily`, by design).
3. Run the weekly by hand, then the daily, and read both logs end to end:
   `bash scripts/ops/atlas_global_weekly.sh; bash scripts/ops/atlas_global_daily.sh`.
4. `select script_name, milestone, status from atlas_global.atlas_pipeline_runs order by started_at`
   shows one row per step; `https://atlas.jslwealth.in/global/health` renders them, the validator
   rows, the freshness table and the provider-call counts. That page is reachable **without a
   session** by design — `docs/global/deploy-subpath.md` §6.2 is the decision about leaving it so
   on the public domain.
5. `curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$GLOBAL_REVALIDATE_URL" -H 'Authorization: Bearer wrong' -d '{"tag":"eod"}'`
   → `401`; with the real secret → `200` and `{"revalidated":true,"tag":"eod",…}`.
6. Install the two cron lines (§6). Next morning: the log, `/health`, and — only if a gate
   failed — the Telegram push.
