# Fund + ETF ranking methodology

> **Audience:** Atlas v6 developers + advisors using the `/v1/rank.*`
> endpoints. Source files: `atlas/inference/etf_scorecard.py`,
> `atlas/inference/fund_scorecard.py`, `atlas/api/rank.py`, migration
> `093_atlas_fund_etf_scorecard.py`. ELI5 templates:
> `atlas/inference/eli5_fund_etf.py`.

Atlas ranks ETFs and mutual funds with a composite score on top of the
24-cell deep-search matrix. ETFs use 6 components; mutual funds use 4
layers (with sub-metrics inside each layer). All weights live in
`atlas_thresholds` so methodology can be re-tuned without a redeploy.

Top 25% per category are flagged `is_atlas_leader`. For funds, the
bottom 25% are flagged `is_avoid`. Both flags are suppressed when
`confidence_low=TRUE`.

## ETF composite (6 components)

| Component | Weight | Threshold key |
|---|---|---|
| Matrix conviction (POSITIVE-leaning across 4 tenures) | 30% | `etf_weight_matrix` |
| Sector strength overlay | 25% | `etf_weight_sector` |
| Tracking quality (TE for passive / alpha for active) | 15% | `etf_weight_tracking` |
| AUM bracket (sweet spot 100-50,000 Cr) | 10% | `etf_weight_aum` |
| Liquidity (log median traded value, 60d) | 10% | `etf_weight_liquidity` |
| Expense ratio (inverse percentile, lower is better) | 10% | `etf_weight_expense` |

Each component is 0-100. Missing components degrade gracefully to the
category median (50) and stamp the reason in `raw_metrics.reasons`.

### Component math

- **matrix_conviction_score** — Walk the conviction tape rows for the
  ETF's instrument_id. Tenure-weighted sum (1m=0.10, 3m=0.25, 6m=0.35,
  12m=0.30) of `sign(verdict) × |friction_adjusted_excess|`. Map
  [-1, +1] → [0, 100].
- **sector_strength_score** — For `sector`/`thematic`/`smart_beta`, look
  up the underlying sector's `sector_strength_rank` (1 = strongest).
  For `broad_index`, use the average rank across all sectors. For
  `commodity`/`international`/`debt`, return 50 (no domestic sector
  mapping).
- **tracking_quality_score** — Passive: `100 - min(TE/5, 1) × 100` (TE
  in pct). Active: linear map `alpha ∈ [-0.10, +0.10] → [0, 100]`.
- **aum_bracket_score** — 100 inside the sweet spot, log-decay below,
  gentle taper above (capped at 40).
- **liquidity_score** — Percentile rank of `log_med_tv_60d` within
  category.
- **expense_ratio_score** — `100 - percentile_rank(TER)` within category
  (lower TER → higher score).

## Mutual fund composite (4 layers)

| Layer | Weight | Threshold key |
|---|---|---|
| Risk-adjusted return (Sharpe, Sortino, Alpha, MaxDD, Calmar, captures) | 50% | `mf_weight_risk_adj` |
| Holdings conviction (top-N holdings × conviction tape verdict) | 25% | `mf_weight_holdings` |
| Style + sector (style drift + sector tilt vs leaders) | 15% | `mf_weight_style_sector` |
| Cost + manager (TER 40% / tenure 30% / AUM 20% / age 10%) | 10% | `mf_weight_cost_manager` |

### Layer 1 — risk-adjusted return

Equal-weighted blend of 7 percentile ranks within the fund's category
cohort:

1. Sharpe (annualized, daily rf = 6%/252)
2. Sortino (downside-only deviation; capped at 5.0 when no downside)
3. Jensen alpha (mean of `fund_returns - bench_returns`, annualized)
4. Max drawdown (lower is better → inverted)
5. Calmar (annual return / max drawdown)
6. Up-capture (higher = better)
7. Down-capture (lower = better → inverted)

### Layer 2 — holdings conviction

For the fund's top-N holdings (N = `mf_holdings_top_n`, default 20),
look up each holding's 6m conviction verdict and weight by position
size. POSITIVE = +1, NEUTRAL = 0, NEGATIVE = -1. Weighted average
(over covered weight) is mapped from [-1, +1] → [0, 100].

When zero holdings match the universe (`survivorship_exposure_pct = 0`),
`holdings_unjoinable=TRUE` is set and the layer falls back to neutral
(50).

### Layer 3 — style + sector

`score = max(0, min(100, 100 - style_drift_pct + sector_tilt_bonus))`.
Sub-inputs default to 30% drift / 0% tilt when unavailable.

### Layer 4 — cost + manager

Weighted blend (TER 40% / tenure 30% / AUM 20% / age 10%):

- TER: inverse percentile rank within category cohort.
- Manager tenure: capped at 10y, linear to 100.
- AUM: 100 inside sweet spot (`mf_aum_sweet_spot_min_cr`,
  `mf_aum_sweet_spot_max_cr`), log-decay below, gentle taper above.
- Fund age: capped at 10y, linear to 100.

## Disclaimers (always surface)

Every fund row carries these flags; the list endpoint also exposes a
`meta.disclaimers` array with the same text.

1. **Holdings conviction inherits survivorship caveat from the 24-cell
   matrix.** Conviction lookups only resolve for instruments in the
   curated universe — `survivorship_exposure_pct` tells you what
   fraction of the fund's top-N weight is covered.
2. **NAV staleness: T-1 to T-3 typical for Indian MFs.** `nav_as_of`
   shows when the NAV was last published.
3. **Holdings disclosure: 30-day SEBI lag.** `holdings_as_of` is the
   monthly disclosure date.
4. **Style drift penalty softened for sub-₹500Cr AUM funds.** Small
   funds drift not by choice but by liquidity. (Tunable via
   `mf_aum_sweet_spot_min_cr`.)
5. **`confidence_low=TRUE` means < 3y track record.** Both
   `is_atlas_leader` and `is_avoid` are suppressed; the ELI5 string
   surfaces an explicit "re-evaluate in ~X months" note.

## Threshold tuning guide

All knobs live in `atlas_thresholds` (category `etf_rank` or `mf_rank`).
Update via `UPDATE atlas.atlas_thresholds SET threshold_value = … WHERE
threshold_key = '…'` — no redeploy required. The scorecard pipeline
reads the table on every run.

- Tightening the leader cutoff: lower `etf_atlas_leader_pct` /
  `mf_atlas_leader_pct` (range 5-50).
- Loosening the avoid cutoff: lower `mf_avoid_pct`.
- Shrinking the holdings drilldown: lower `mf_holdings_top_n` (5-50).
- Shifting the AUM sweet spot: edit
  `etf_aum_sweet_spot_{min,max}_cr` / `mf_aum_sweet_spot_{min,max}_cr`.
- All layer weights MUST sum to 1.0 (per asset class). The pipeline
  rescales when weights don't sum to 1 but logs `total_weight` so the
  drift is visible.

## ELI5 examples

```
Top broad-index ETF — clean tracking, deep liquidity, and a fee that
compounds in your favour over years. (₹12,000 Cr, 0.10% TER).

Top sector ETF — Banking leading on relative strength with healthy AUM
and tight tracking. (₹4,500 Cr, 0.25% TER).

Top-quartile Flexi Cap over 3y — Sharpe 1.45, max drawdown 18.0%,
holds 78/100 conviction stocks.

Bottom-quartile Large Cap — weak risk-adjusted returns vs category.
Better alternatives exist; see top picks for this category.

Limited track record — composite is best-effort. Re-evaluate in ~14
months when 3y history is in.
```

All ELI5 strings are capped at 200 characters.

## API contract

### GET /v1/rank.etfs

```
GET /v1/rank.etfs?category=sector&min_aum_cr=100&limit=50
```

Returns paginated ETF rows with the 6 component scores, composite,
ranking, leader flag, and ELI5. `meta.next_cursor` is set when more
data exists. Filter params:

- `category` — one of `broad_index|sector|thematic|commodity|international|debt|smart_beta`
- `min_aum_cr` — INR Cr minimum (filters `raw_metrics.aum_cr`)
- `cursor` — opaque base64 from a previous response's `meta.next_cursor`
- `limit` — 1-200 (default 50)

### GET /v1/rank.etfs/{instrument_id}

Single-ETF detail: full scorecard row + `raw_metrics` (with per-component
reasons, AUM, TER, tracking error, alpha) + placeholder
`tracking_error_series` / `sector_overlay` (filled when SP02 MV
publishes them).

### GET /v1/rank.funds

```
GET /v1/rank.funds?category=Flexi%20Cap&style=Growth&min_aum_cr=500
```

Returns paginated fund rows with the 4 layer scores, composite,
ranking, leader/avoid flags, **and all 5 disclaimer fields per row**.
`meta.disclaimers` carries the user-facing version of the five caveats.

### GET /v1/rank.funds/{scheme_code}

Single-fund detail: scorecard row + `sub_metrics` (per-layer raw
numbers: Sharpe, Sortino, alpha, max-DD, Calmar, captures, AUM, TER,
manager tenure, fund age) + `top_holdings` drilldown (per-holding
verdict, weight_pct, symbol). Placeholders for `rolling_sharpe_3y` and
`holdings_by_sector` (filled when SP02 MVs publish them).

## Degraded-mode contract

When the scorecard table is missing (migration 093 not applied) or
empty (backfill not yet run), the list endpoints return:

```
{
  "data": [],
  "meta": {
    "data_as_of": null,
    "fetched_at": "…",
    "source": "atlas_etf_scorecard",
    "degraded": true,
    "note": "atlas_etf_scorecard not yet present — apply migration 093"
  }
}
```

Detail endpoints raise 503 with the same note. This lets the frontend
contract stay stable from day-1; the data fills in once the backfill
runs.

## Backfill commands

```bash
# After migration 093 is applied on EC2:
alembic upgrade head
python -m atlas.inference.etf_scorecard \
    --date 2026-05-22 --backfill \
    --output-dir /tmp/atlas-sql
python -m atlas.inference.fund_scorecard \
    --date 2026-05-22 --backfill \
    --output-dir /tmp/atlas-sql
```

When the `.supabase-write-approved` marker is present at the repo
root, the CLI writes directly to the live DB. Otherwise it emits a
SQL file under `--output-dir` that can be reviewed before applying.
