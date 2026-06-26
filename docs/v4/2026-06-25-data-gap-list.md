# Atlas — what data we DON'T have (cleanly, in the DB), 2026-06-25

Measured against the LIVE DB, not assumed. "Source" = where the real data exists; the gap is
ingestion/derivation/cleaning into the tables the frontend reads. Sorted by board impact.

## 🔴 A. Corporate-action adjustment — NOT APPLIED (highest impact)
- **State:** `foundation_staging.ohlcv_stock.close_adj == close` for **100% of 1,125,230 rows** (0 differ).
  Splits/bonuses are NOT adjusted — `adj` just copies raw.
- **Corrupts:** every price-derived number for any stock with a split/bonus — returns (Defence +112%
  via MTARTECH), P/E, P/B, EV/EBITDA, ROE-via-price. This is the root of the "dirty tails."
- **Source:** NSE corporate-actions feed (splits/bonus/dividends) — available. (The `atlas_v6_clean_ohlcv`
  NSE-Bhavcopy rebuild was meant to fix this; it's paused, blocker = corp-action source.)
- **To close:** ingest NSE corp-actions → adjustment factors → apply to `ohlcv_stock` so `adj ≠ raw`.

## 🔴 B. Fundamentals not extracted from XBRL (5 empty, 1 dirty)
Coverage of the derived fundamental frame at 06-19 (n=2,036):
- `roic` **0% EMPTY** · `roa` **0% EMPTY** · `gross_margin` **0% EMPTY** · `current_ratio` **0% EMPTY**
  · `quick_ratio` **0% EMPTY**
- `roe` 84.8% but **DIRTY**: range −3,754% … +1,598% (near-zero/negative equity denominators)
- `debt_to_equity` 81.2% · `eps_growth_yoy` 81.8% (~18% missing)
- **Healthy (not gaps):** operating_margin 96.9%, net_margin 98.5%, revenue_growth_yoy 93.3%,
  revenue_ttm 97.9%, eps_diluted_ttm 97.6%
- **Source:** XBRL balance sheet — total assets (roa), current assets/liabilities + inventory
  (current/quick), gross profit (gross_margin), invested capital + tax (roic). All in XBRL.
- **To close:** extend XBRL extraction to those balance-sheet line items; add sane bounds + valid-equity
  guard to ROE.

## 🔴 C. Valuation multiples not derived (2 empty, 1 sparse)
At 06-19 (n≈2,090):
- `val_pb` **0 non-null EMPTY** → needs book value/share (XBRL equity ÷ shares)
- `val_ev_ebitda` **0 non-null EMPTY** → needs EV (mkt cap + debt − cash) + EBITDA (XBRL)
- `val_pe_vs_sector` only **674/2,090 (32%) populated**, 5 distinct → sector-median P/E sparse (thin /
  unmapped sectors) + 5-bucket step. Needs sector-median fallback + the A2 mapping + continuous score.
- **Healthy:** val_absolute_pe 1,748 non-null, val_52w_position 2,090.

## 🟠 D. Foundation OHLCV freshness — stale 06-19 (you're handling)
- `ohlcv_stock` / `technical_daily` / lens journal stuck at **06-19**; raw atlas + `de_equity_ohlcv` are
  06-24. Blocked on Kite auth (`KITE_TOKEN_ENCRYPTION_KEY` + token). FM refreshing now.

## 🟡 E. Institutional flow — data PRESENT, just UNWIRED (not missing)
- `de_mf_holdings`: **6 monthly snapshots** (2026-01-31 → 05-04), ~1,376 stocks/snapshot. Month-on-month
  fund-flow delta IS computable. Today `flow_institutional` ignores it → modal 50 for ~95% of stocks.
- **To close:** wire MoM Σ(weight_pct) delta into the institutional sub-score. (~1,000 stocks legitimately
  have no MF holding → genuine 0/neutral, not "missing".)

## 🟡 F. Sector taxonomy fold — 126 unmapped + wrong fold map
- 126 active stocks still sector-less (15 thin-tail: Services/Diversified/Telecom/MNC/Power; 111 with no
  `de_instrument` row). The "locked" CONTEXT.md fold map is the wrong vocabulary vs live NSE names.
  Needs the real 31→≤21 fold (FM) + a source for the 111 (industry / index membership).

## ⚪ Reframed — NOT a data gap to fill
- **policy_tailwind:** scrap the 15-item placeholder score. Policy → informational **alert layer**
  (flag a policy counterproductive to an otherwise-green sector) + future **news-monitoring agent**.

## ✅ Confirmed REAL / working (no gap)
Technicals (EMA21/50/200, RS, momentum, RSI), catalyst (1,992 non-null / 1,600 distinct), returns
(once corp-action-adjusted), 52-week position, operating & net margins, revenue & EPS TTM, revenue growth.

---
### Board-readiness read
The two that make-or-break "every number validated": **A (corp-action adjustment)** and **B/C (XBRL
balance-sheet extraction)**. Without A, displayed returns/P/E are wrong for split stocks. Without B/C,
profitability + valuation lenses are partly empty/collapsed. E and F are quick wiring/decisions. Policy is
reframed out of the score.
