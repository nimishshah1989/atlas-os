# Global Atlas — runbook (Phase 1)

Everything an operator does by hand for the US platform. Keys and passwords live in `.env` on the
laptop/box and in Vercel env — never in this repo (it is public). Sections marked **(P1-F)** are
completed by that chunk; the rest is actionable now.

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
| `GLOBAL_REVALIDATE_SECRET` | Vercel env + box `.env` | bearer token the orchestrator's publish step sends to `/api/revalidate` **(P1-F)** |
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

## 6. Cron on the box **(P1-F)**

```
0 1 * * 2-6  /home/ubuntu/atlas-os/scripts/ops/atlas_global_daily.sh   # 01:00 UTC Tue–Sat = 21:00 ET
30 1 * * 6   /home/ubuntu/atlas-os/scripts/ops/atlas_global_weekly.sh  # Sat 01:30 UTC
```
Both scripts are Python-only (no pm2, no `.next`) and cannot collide with the India runs
(07:00 / 10:30 UTC). Logs: `/home/ubuntu/logs/atlas_global_*.log`.

## 7. When a gate fails (the Telegram push says "GLOBAL BOARD NOT UPDATED")

1. `/health` → the failed validator row and the flagged metrics.
2. The log names the check; fix the data (never the assertion), re-run the step, re-run the gate.
3. The board keeps its last-good data until every gate passes; nothing is republished by hand.
