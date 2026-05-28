# Stream A3 — Sector Confluence (L5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Layer Weinstein's missing rule 6 ("buy leaders in leading groups") on top of Stream A2's winning candidates. Test whether sector-level RS confirmation (L5) lifts any (cap × lookback × confluence-subset) above the production gate — IC ≥ 0.05 in-sample AND ≥ 50 events/yr AND positive min OOS IC.

**Hypothesis:** L5 is the missing 6th confluence. Stream A2 maxed out at in-sample IC ~0.06 because every other layer was tested EXCEPT sector context. If L5 lifts IC by 2-3× on Mid/Large UP events (per A2 report recommendation §"Next moves"), it could clear the floor on at least 1-2 cap_tier × event_type combinations.

**Counter-hypothesis (must also test):** L5 is just another low-signal filter. If after L5 layering NO rule clears the gate, Weinstein is genuinely under-powered for Indian equities given current data. That's a valid result — would inform the downstream change in the verdict composer (demote Weinstein from hard veto to context chip; see spec §4 update once A3 lands).

**Source design:** `docs/v6/2026-05-28-weinstein-deep-dive-methodology.html` §4.2 (L5 row).
**Predecessor:** Stream A2 outputs at `docs/v6/2026-05-28-weinstein-a2-*` — read those first.

---

### Task 1: Sector RS panel SQL

**Files:**
- Create: `scripts/research/sector_rs_panel.sql`

- [ ] **Step 1: Verify data sources**

```sql
SELECT MIN(date), MAX(date), COUNT(DISTINCT date) AS n_days
FROM atlas.atlas_sector_metrics_daily
WHERE rs_3m IS NOT NULL OR bottomup_rs_3m_nifty500 IS NOT NULL;
```

If `n_days >= 1800` (≈8 years), proceed. If less, document and use whatever's available.

- [ ] **Step 2: Build per-sector daily RS rank**

```sql
CREATE OR REPLACE VIEW atlas.v_sector_rs_rank_daily AS
SELECT
  date,
  sector_name,
  bottomup_rs_3m_nifty500 AS rs_3m,
  RANK() OVER (PARTITION BY date ORDER BY bottomup_rs_3m_nifty500 DESC NULLS LAST) AS rs_rank,
  COUNT(*) OVER (PARTITION BY date) AS n_sectors_today,
  PERCENT_RANK() OVER (PARTITION BY date ORDER BY bottomup_rs_3m_nifty500 NULLS FIRST) AS rs_pctile
FROM atlas.atlas_sector_metrics_daily
WHERE bottomup_rs_3m_nifty500 IS NOT NULL
  AND date >= '2018-01-01';
```

- [ ] **Step 3: Smoke-test sector rank stability**

Confirm Energy + IT consistently in top quartile during 2025, Realty + Capital Goods in bottom quartile during 2022. The agent should pick 2-3 named regimes and verify rank movement makes intuitive sense.

- [ ] **Step 4: Commit**

```bash
git add scripts/research/sector_rs_panel.sql
git commit -m "research(weinstein-a3): sector RS rank daily panel SQL (per-date PERCENT_RANK)"
```

---

### Task 2: L5 confluence computation

**Files:**
- Create: `scripts/research/weinstein_l5_feature.sql`

- [ ] **Step 1: Define L5 boolean per event**

For each event in `atlas.weinstein_event_features` (Stream A2's output):
- Look up the linked sector from `atlas.atlas_universe_stocks` (use the event's `instrument_id` → `sector_name`)
- Get `sector_rs_pctile` at event_date and at (event_date − 4 weeks) from `v_sector_rs_rank_daily`
- L5 boolean for UP events: `pctile_at_event > pctile_4w_ago` AND `pctile_at_event >= 0.50` (sector in top half AND improving)
- L5 boolean for DOWN events: `pctile_at_event < pctile_4w_ago` AND `pctile_at_event <= 0.50` (sector in bottom half AND degrading)

The dual-condition is important — RS trend ALONE isn't enough; the sector must also be on the correct side of the median.

```sql
ALTER TABLE atlas.weinstein_event_features
  ADD COLUMN IF NOT EXISTS conf_l5_sector_rs boolean;

UPDATE atlas.weinstein_event_features e
SET conf_l5_sector_rs = CASE
  WHEN e.event_type = 'UP' THEN (
    sector_pctile_now > sector_pctile_4w_ago AND sector_pctile_now >= 0.50
  )
  WHEN e.event_type = 'DOWN' THEN (
    sector_pctile_now < sector_pctile_4w_ago AND sector_pctile_now <= 0.50
  )
  ELSE NULL
END
FROM (
  SELECT
    e2.event_date,
    e2.instrument_id,
    rs_now.rs_pctile  AS sector_pctile_now,
    rs_old.rs_pctile  AS sector_pctile_4w_ago
  FROM atlas.weinstein_event_features e2
  JOIN atlas.atlas_universe_stocks u
    ON u.instrument_id = e2.instrument_id AND u.effective_to IS NULL
  LEFT JOIN atlas.v_sector_rs_rank_daily rs_now
    ON rs_now.date = e2.event_date AND rs_now.sector_name = u.sector
  LEFT JOIN atlas.v_sector_rs_rank_daily rs_old
    ON rs_old.date = e2.event_date - INTERVAL '28 days' AND rs_old.sector_name = u.sector
) joined
WHERE e.event_date = joined.event_date AND e.instrument_id = joined.instrument_id;
```

- [ ] **Step 2: Smoke-test L5 pass rate per (cap_tier × event_type)**

```sql
SELECT cap_tier, event_type, COUNT(*) AS n, AVG(conf_l5_sector_rs::int) AS pass_rate
FROM atlas.weinstein_event_features
WHERE conf_l5_sector_rs IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 2;
```

Expected: 25-50% pass rate. If <10% or >80%, the thresholds are mis-calibrated — adjust the median (0.50) cutoff up or down to 0.40 or 0.60.

- [ ] **Step 3: Commit**

```bash
git add scripts/research/weinstein_l5_feature.sql
git commit -m "research(weinstein-a3): L5 sector RS confluence boolean per event"
```

---

### Task 3: Re-run IC + walk-forward with L5

**Files:**
- Create: `scripts/research/weinstein_l5_ic.sql`
- Create: `docs/v6/2026-05-28-weinstein-a3-ic-results.csv`

- [ ] **Step 1: Extended confluence subsets**

Test L5 layered on the A2 winners and a few promising A2 near-misses:

| Subset code | Rules |
|---|---|
| A2_base | Base alone (A2 baseline) |
| A3_L5  | Base + L5 |
| A3_L5_L6 | Base + L5 + L6 (matches A2's best DOWN candidates with L5 added) |
| A3_L5_L4 | Base + L5 + L4 (matches A2's Small DOWN winner with L5 added) |
| A3_L5_L2 | Base + L5 + L2 (the "Weinstein full" minus L1/L3 — best in-sample IC if it fires) |
| A3_L5_L2_L4 | Base + L5 + L2 + L4 |

6 subsets × 3 cap_tiers × 4 lookbacks × 2 event_types = 144 rows.

- [ ] **Step 2: Compute IC + hit-rate + event count per subset**

Same compute as Stream A2 Task 4. Output to CSV.

- [ ] **Step 3: Walk-forward per-year for any rule that clears in-sample IC ≥ 0.05 AND ≥ 25 events/yr**

Same compute as Stream A2 Task 5.

- [ ] **Step 4: Commit + write A3 report**

```bash
git add scripts/research/weinstein_l5_ic.sql docs/v6/2026-05-28-weinstein-a3-ic-results.csv docs/v6/2026-05-28-weinstein-a3-report.md
git commit -m "research(weinstein-a3): L5 IC + walk-forward results + report"
```

---

### Task 4: Write the A3 report

**Files:**
- Create: `docs/v6/2026-05-28-weinstein-a3-report.md`

- [ ] **Step 1: Structured report**

```markdown
# Weinstein A3 — Sector Confluence Report

## Headline
[Did adding L5 produce a rule combination that clears all 3 production gates? Yes/No, plus best (cap × lookback × subset) result.]

## L5 lift vs A2 baseline
Comparison table: for each (cap × lookback × event_type), show A2_base IC vs A3_L5 IC vs A3_L5_LX best IC. Lift > 0 means L5 helped.

## Rules now locked-eligible (if any clear the gate)
Same format as A2 report — provisional pending PIT cap_tier.

## Surprises
[Did sector RS improve in the direction we expected? Were there unexpected regime effects? Did L5 hurt some rules?]

## Honest limitations
- Same survivor-bias caveat from A2 (static cap_tier)
- Sector RS data quality (if any gaps surfaced during compute)
- 2020-2022 bull market still dominates in-sample

## Next moves
[If A3 cleared the floor: recommend migration 113 with the locked rule. If A3 also failed: recommend demoting Weinstein from hard veto to context-chip in the verdict composer.]
```

---

### Definition of Done

- [ ] 3-4 commits on local main
- [ ] `docs/v6/2026-05-28-weinstein-a3-ic-results.csv` saved (144 rows)
- [ ] `docs/v6/2026-05-28-weinstein-a3-report.md` written
- [ ] Clear binary verdict in the report headline: "L5 made the difference" OR "L5 did not clear the floor either"

### Self-review checklist

- [ ] L5 boolean correctly applies the dual-condition (trend AND level) per UP/DOWN
- [ ] Sector RS lookup joins correctly via `atlas_universe_stocks.sector` (NOT `atlas_universe_stocks.industry`)
- [ ] cap_tier still uses static fallback (PIT backfill not in scope)
- [ ] No Micro cap_tier in the analysis (Q5 spec lock)
- [ ] Event-count floor relaxed to 25/yr per A2's documented stance

### Status reporting

DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT. Report under 500 words covering: did L5 clear the floor, best rule with numbers, surprises, recommended single next move.
