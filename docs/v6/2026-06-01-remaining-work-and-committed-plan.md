# v6 — Remaining work + committed plan (stock-take 2026-06-01)

Written at the end of the M3 session as the handoff/commitment artifact. Read
this FIRST in the next session, then run the reconciliation pass (§2) before
building M4.

## 0. What just shipped (M3 — RS baselines + standardization) — DONE + LIVE

- Stock tier RS → relative form `(1+r)/(1+r_bench)-1`; Large anchor Nifty100→**Nifty50** (ADR-0001).
- Gold RS → **direct** stock-vs-gold `(1+r)/(1+r_gold)-1`, all 7 windows; column name `rs_{w}_tier_gold` kept (ADR-0002).
- RS windows 5→7 (`1d/1w/1m/3m/6m/12m/24m`); `primitives.RS_WINDOWS` added.
- Sector bottom-up RS extended to full 7 windows (`bottomup_rs_{w}_nifty500`).
- Index + stock `ret_24m` persisted; migration 123 (14 cols, applied to prod via MCP).
- **Backfill executed on prod**: 306,007 stock + 47,765 index + 13,485 sector rows; verified by formula-match; 5 RS MVs refreshed. PR #105 merged to main (`3a2126d`).
- ETFs ride the relative-form change automatically (no code change).

## 1. #1 FINDING — docs trail reality; reconcile before planning M4–M7

The authoritative 2026-05-24 CEO/eng plans describe a Phases 0.5–9 "discovery-first
48-cell scorecard" program as **not-started**. That is stale: migrations run to **123**
and the scorecard/signals/cells/conviction/portfolio/provenance/MV/frontend layers are
substantially built (080, 084, 087, 092, 096, 097, 102–122). The project has been moving
on the **8-page IA + RS-surfaces + trader-view/verdict** track, not the literal Phase
0.5–9 sequence. **No one has a single current source of truth for "what's done vs left."**
Producing that is the first job of the next session (§2).

Open scope question for the user (CEO-level, do not infer): is the remaining roadmap
(a) the formal Phase 0.5–9 discovery program (walk-forward research, 24-framework
discovery, SEBI RA, drift detector, continuous-improvement), or (b) finishing the
8-page product surfaces (Markets RS, Sectors, Stocks, ETFs, Funds, Calls Performance)
to "complete + correct" on the data already built? These imply very different M4–M7.

## 2. FIRST task next session — reconciliation pass (≤1h, read-only)

1. `ls docs/v6/phases/*/STATUS.md` + read any chunk specs.
2. Read migrations 080→123 titles; map each to a milestone/feature.
3. Query prod (Supabase MCP, project `nanvgbhootvvthjujkvs`) for which `atlas_*` tables
   + MVs are **populated** (row counts, latest date) — built ≠ populated.
4. Diff against the 8-page IA (CONTEXT.md "v6 frontend redesign locks 2026-05-26") and
   the eng-review deliverables — produce a true done/partial/left table per page + per
   milestone. Commit it as `docs/v6/STATUS.md` (the missing source of truth).
5. THEN scope M4–M7 + the "Fs" with the user.

## 3. Committed next chunk — M4 backend (clear, safe, buildable now)

ADR-0002 explicitly defers one M3-adjacent item to M4: **US/global RS is still in the
old excess form.** This is the cleanest next backend chunk — a direct mirror of M3,
already grilled/ADR'd, fully testable, no new product decisions:

- `atlas/compute/us_stocks.py` + `atlas/compute/global_pipeline.py`: switch RS to
  relative form `(1+r)/(1+r_bench)-1`; extend to the 7 RS windows; mirror the gold
  direct-form if those surfaces carry a gold variant.
- Markets RS grid lock is now **9 baselines × 7 windows** (CONTEXT.md) — verify
  `mv_markets_rs_grid` covers 7 windows; build `mv_markets_rs_detail_charts` (❌ not built).
- Per-chunk gstack process (runbook §04): mini eng-review → **/tdd** → vectorized impl →
  unit suite + pyright ratchet + ruff → **/review + /codex review** → PR (NO auto-merge).
- Migration for any new us_atlas/global_atlas columns (mirror 123); apply to prod via MCP
  AFTER review; backfill via a script modeled on `scripts/backfill_m3_rs.py` (temp-table
  UPDATE…FROM, non-finite guard, uuid-aware PK types — both bugs already fixed there).
- Watch the same traps M3 hit: temp-table PK type must match real column type;
  `NUMERIC(10,4)` rejects ±inf / |x|≥1e6; confirm the relevant benchmarks are active in
  `atlas_benchmark_master` before backfilling (MSCIWORLD, SP500 confirmed active).

## 4. Known operational follow-ups (not M-milestones; flagged, unowned)

- **Prod alembic stamp drift**: `public.alembic_version`=112 but schema is ~122 and
  migration **064** (`tv_signal_reports`) has an IMMUTABLE-index bug that breaks a fresh
  `alembic upgrade head`. Until re-baselined, apply prod DDL directly via MCP (as M3 did),
  NOT via the alembic chain. Owner decision needed.
- **EC2 deploy hygiene**: EC2 is parked on branch `feat/v6-m3-rs-baselines` with local
  edits stashed (`git stash -u`); nightly crons run the current checkout (no auto-pull),
  so they use the new code, but EC2 should be returned to `main` (`git checkout main &&
  git pull`; `git stash pop`/drop as decided). Needs SSH (was blocked for the agent).
- **ETF gold** (`rs_*_benchmark_gold`, etfs.py): degenerate under relative form; redefine
  as direct ETF-vs-gold (M4 follow-up, ADR-0002).
- **M3 full-history backfill (optional)**: backfill rewrote only the last 2yr; rows older
  than 2024-05-31 keep the old form (a seam on long charts). Re-run
  `scripts/backfill_m3_rs.py --start <series-start>` if full consistency is wanted.
- **Local pre-commit ruff** pinned `v0.7.4` vs CI `0.15.x` (mutually unsatisfiable on
  pre-existing lines) — Mac commits need `--no-verify`; bump the pin to fix permanently.

## 5. Process reminders for the building session (per user direction)

- Use the gstack per-chunk loop + **all** review protocols (`/review` + `/codex review`,
  both required), TDD, full test suite, pyright ratchet, ruff.
- Hooks gate `atlas/**`, `frontend/**`, `migrations/**` — invoke a planning skill first.
- **No unsupervised prod merge/deploy/backfill or blind frontend** — those are human
  gates (`.design-approved.json`, "see what you build", "no synthetic data — ask first").
  Open CI-green PRs; the user merges/deploys (same as M3).
- Decimal for money, tz-aware datetimes, file-size limits (600 src / 800 test).
