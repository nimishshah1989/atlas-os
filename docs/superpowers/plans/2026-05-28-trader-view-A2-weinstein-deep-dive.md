# Stream A2 — Weinstein Deep-Dive (Transition Events + Confluence) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find a Weinstein-style entry-signal rule per cap-tier that clears the 0.05 IC floor at 6m AND fires often enough to be actionable (≥50 events per cap_tier per year). Stream A1 measured stage tags and failed the floor — this stream measures transition events with confluence filters, which is what Weinstein actually meant.

**Source design:** `docs/v6/2026-05-28-weinstein-deep-dive-methodology.html` (canonical for this stream — read first).

**Supersedes:** Stream A1's Task 4-5 (walk-forward of the naive stage classifier). Stream A1 Tasks 1-3 output (`docs/v6/2026-05-28-weinstein-ic-raw.csv`) is kept as a baseline to compare against.

**Tech Stack:** PostgreSQL via Supabase MCP, Python 3.11 + pandas for analysis, no new dependencies.

---

### Task 1: Verify cap_tier point-in-time data is available (gate)

**Files:** read-only check.

- [ ] **Step 1: Check cap_tier history depth**

```sql
SELECT MIN(date), MAX(date), COUNT(DISTINCT date) AS n_days
FROM atlas.atlas_scorecard_daily
WHERE cap_tier IS NOT NULL;
```

- [ ] **Step 2: Decision branch**

If `n_days >= 1800` (≈8 years of trading days): proceed to Task 2 using `atlas_scorecard_daily.cap_tier`.

If `n_days < 1800`: a separate PIT-backfill workstream is in flight. Proceed with Task 2 using `atlas_universe_stocks.tier` (static, current snapshot) and add an `INVALID_FOR_PRE_2026` flag to every event row so we can re-run when the backfill lands. Document the limitation in the output CSV header.

- [ ] **Step 3: Commit the decision note**

```bash
git add docs/v6/2026-05-28-weinstein-a2-cap-tier-decision.md
git commit -m "research(weinstein-a2): cap_tier PIT availability check + decision"
```

---

### Task 2: Build the transition event detector

**Files:**
- Create: `scripts/research/weinstein_events_base.sql`

- [ ] **Step 1: Stage_1_persistence helper**

Compute, for each (instrument, week, MA-lookback), the fraction of the prior 4 weeks where stage was Stage 1 (or unclassified) — using the Stage 1 definition from Stream A1's classifier (`scripts/research/weinstein_stage_classify.sql`).

- [ ] **Step 2: Base event detector SQL**

Build `atlas.v_weinstein_events_base` (VIEW) that fires for each (instrument, date, MA_lookback) when:

```sql
-- Base rule for Stage 1 → Stage 2 transition
WHERE  close_today  >  ma_today
  AND  close_prev   <= ma_prev          -- crossover this week
  AND  ma_slope_4w  >= 0                -- MA flat or rising
  AND  stage_1_persistence_prior_4w >= 0.8  -- was in base, not V-bottom

-- Symmetric rule for Stage 3 → Stage 4 (anti-Weinstein, for SELL signals)
UNION ALL
WHERE  close_today  <  ma_today
  AND  close_prev   >= ma_prev
  AND  ma_slope_4w  <= 0
  AND  stage_3_persistence_prior_4w >= 0.8
```

Output columns: `instrument_id, event_date, event_type ('UP' | 'DOWN'), ma_lookback_weeks, cap_tier, close_at_event, volume_at_event`.

Read the full schema from `scripts/research/weinstein_stage_classify.sql` (committed in Stream A1, commit d52bd400). Reuse the `v_weinstein_stage_classify` view.

- [ ] **Step 3: Smoke-test event count**

```sql
SELECT cap_tier, ma_lookback_weeks, event_type, COUNT(*)
FROM atlas.v_weinstein_events_base
GROUP BY 1,2,3
ORDER BY 1,2,3;
```

Expected: 200-2000 events per (cap_tier × lookback × event_type) over 2018-2026. If event counts are <50 per year per cap-tier, the base rule is too tight — relax `stage_1_persistence_prior_4w` from 0.8 to 0.6 and re-test.

- [ ] **Step 4: Commit**

```bash
git add scripts/research/weinstein_events_base.sql
git commit -m "research(weinstein-a2): transition event detector — Stage 1↔2 + Stage 3↔4 crossovers with anti-V-bottom guard"
```

---

### Task 3: Confluence-layer feature computation

**Files:**
- Create: `scripts/research/weinstein_event_features.sql`

- [ ] **Step 1: Compute the 6 confluence booleans per event**

```sql
CREATE TABLE atlas.weinstein_event_features AS
WITH events AS (SELECT * FROM atlas.v_weinstein_events_base)
SELECT
  e.*,
  -- L1: Volume confirmation
  (vol_5d_avg(e.event_date)  >= 1.5 * vol_60d_avg(e.event_date)) AS conf_l1_volume,

  -- L2: Prior 13W close-high clearance (UP) / 13W close-low breakdown (DOWN)
  CASE WHEN e.event_type = 'UP'
       THEN e.close_at_event > max_close_prior_13w(e.event_date)
       ELSE e.close_at_event < min_close_prior_13w(e.event_date)
  END                                                            AS conf_l2_prior_extreme,

  -- L3: RS_3m improving (UP) / degrading (DOWN)
  CASE WHEN e.event_type = 'UP'
       THEN rs_3m(e.event_date) > rs_3m(e.event_date - INTERVAL '4 weeks')
       ELSE rs_3m(e.event_date) < rs_3m(e.event_date - INTERVAL '4 weeks')
  END                                                            AS conf_l3_rs_trend,

  -- L4: Base/top width — Stage 1 or Stage 3 persistence over PRIOR 12 weeks ≥ 0.7
  CASE WHEN e.event_type = 'UP'
       THEN stage_1_persistence_prior_12w(e.event_date) >= 0.7
       ELSE stage_3_persistence_prior_12w(e.event_date) >= 0.7
  END                                                            AS conf_l4_base_width,

  -- L5: Sector RS confirmation (skip for now; mark as NULL, fill in followup)
  NULL::boolean                                                  AS conf_l5_sector_rs,

  -- L6: Liquidity floor per cap-tier
  CASE
    WHEN e.cap_tier = 'Large' THEN avg_traded_value_20d(e.event_date) >= 5e7
    WHEN e.cap_tier = 'Mid'   THEN avg_traded_value_20d(e.event_date) >= 2e7
    WHEN e.cap_tier = 'Small' THEN avg_traded_value_20d(e.event_date) >= 5e6
    ELSE TRUE
  END                                                            AS conf_l6_liquidity
FROM atlas.v_weinstein_events_base e;
```

Use real SQL window functions / lateral joins to compute each confluence — do NOT use pseudo-function-calls like `vol_5d_avg(...)`. Write the inline SQL.

- [ ] **Step 2: Smoke-test confluence pass rates**

```sql
SELECT
  cap_tier, event_type,
  COUNT(*) AS n_events,
  AVG(conf_l1_volume::int)  AS pass_l1,
  AVG(conf_l2_prior_extreme::int) AS pass_l2,
  AVG(conf_l3_rs_trend::int) AS pass_l3,
  AVG(conf_l4_base_width::int) AS pass_l4,
  AVG(conf_l6_liquidity::int) AS pass_l6
FROM atlas.weinstein_event_features
GROUP BY 1,2;
```

Expected: each confluence should pass on 25-60% of events. If any layer passes <10% or >90%, the threshold is mis-calibrated.

- [ ] **Step 3: Commit**

```bash
git add scripts/research/weinstein_event_features.sql
git commit -m "research(weinstein-a2): 6-layer confluence feature compute per event"
```

---

### Task 4: Forward-IC per rule combination

**Files:**
- Create: `scripts/research/weinstein_event_ic.sql`
- Create: `docs/v6/2026-05-28-weinstein-a2-ic-results.csv`

- [ ] **Step 1: Forward return per event**

Compute `forward_excess_6m = close(D+126) / close(D) - bench(D+126) / bench(D)` for each event row. Persist as a column on `atlas.weinstein_event_features` (or join inline).

- [ ] **Step 2: IC per rule combination**

For each (cap_tier × ma_lookback × event_type × confluence_subset) compute:
- N events
- Hit rate (% with `forward_excess_6m > 0` for UP events, `< 0` for DOWN)
- Mean forward_excess_6m
- Spearman IC between `confluence_subset_sum::int` (always 1 for events passing the subset, 0 for non-passers) and forward_excess_6m
- Annualized event count (N / 8)

Confluence subsets to test (per design §5):
1. Base alone
2. + L1 (volume)
3. + L2 (prior extreme)
4. + L3 (RS trend)
5. + L4 (base width)
6. + L6 (liquidity)
7. + L1+L2
8. + L1+L3
9. + L2+L3
10. + L1+L2+L3 (Weinstein full minus L4)
11. + L1+L2+L3+L4 (full)
12. + L1+L2+L3+L4+L6 (full + liquidity)

12 subsets × 3 cap_tiers × 4 lookbacks × 2 event_types = 288 rows. Save to CSV.

- [ ] **Step 3: Rank winners**

For UP events:
- IC >= 0.05
- N_events / 8 >= 50 (≥ 50 events per year)
- Hit rate >= 0.60

Top result per cap_tier × event_type is the candidate locked rule.

For DOWN events, same thresholds but reversed direction.

- [ ] **Step 4: Commit + write summary**

```bash
git add scripts/research/weinstein_event_ic.sql docs/v6/2026-05-28-weinstein-a2-ic-results.csv
git commit -m "research(weinstein-a2): IC + hit-rate + event count per confluence subset"
```

---

### Task 5: Walk-forward (IF Task 4 has a winning combination)

**Files:**
- Create: `scripts/research/weinstein_a2_walk_forward.sql`
- Create: `docs/v6/2026-05-28-weinstein-a2-walk-forward.csv`

- [ ] **Step 1: Walk-forward only the winning combinations**

For each cap_tier's top-ranked rule from Task 4 (and only those), recompute IC across rolling 3-year-train / 1-year-test windows from 2018 to 2026.

If a rule's in-sample IC was 0.07 but OOS IC averages 0.02 with high variance, it's an in-sample fit. Don't lock it.

If multiple rules pass, prefer the one with the highest *minimum* OOS IC across windows (worst-case robust, not best-case greedy).

- [ ] **Step 2: Commit results**

```bash
git add scripts/research/weinstein_a2_walk_forward.sql docs/v6/2026-05-28-weinstein-a2-walk-forward.csv
git commit -m "research(weinstein-a2): walk-forward OOS validation of winning rules"
```

---

### Task 6: Write the research report

**Files:**
- Create: `docs/v6/2026-05-28-weinstein-a2-report.md`

- [ ] **Step 1: Structured report**

```markdown
# Weinstein A2 — Research Report

## Headline
[Did any rule combination clear the 0.05 IC floor with ≥50 events/year/cap_tier? Yes/No, plus key numbers.]

## Rules locked per cap_tier
| cap_tier | MA lookback | Confluences applied | In-sample IC | OOS IC mean | OOS IC min | Events/yr | Hit rate |

## Surprises
[Did volume help more than RS? Did base width matter more than prior-high clearance? What was the biggest IC lifter? What was a dud?]

## Limitations
- Survivor bias: [reflect cap_tier PIT status from Task 1]
- Sector confluence (L5) deferred to followup
- 2020-2022 bull market dominates the in-sample window

## Next moves
[E.g. "L5 sector confluence is the next layer to test", "small-cap events are too sparse — relax stage_1_persistence to 0.6 and retry", "lock and proceed to migration 113".]
```

- [ ] **Step 2: Commit**

```bash
git add docs/v6/2026-05-28-weinstein-a2-report.md
git commit -m "research(weinstein-a2): report + recommended thresholds for migration 113"
```

---

### Definition of Done for this dispatch

- [ ] 5-6 commits on local main (one per task)
- [ ] `docs/v6/2026-05-28-weinstein-a2-ic-results.csv` saved with 288 rows
- [ ] `docs/v6/2026-05-28-weinstein-a2-walk-forward.csv` saved (only if Task 4 found winners)
- [ ] `docs/v6/2026-05-28-weinstein-a2-report.md` written with the headline + locked rules table

### Self-review checklist

- [ ] Event detector uses the existing `v_weinstein_stage_classify` view from Stream A1; does not re-implement stage classification
- [ ] cap_tier source documented at top of each SQL file (PIT or static, per Task 1 decision)
- [ ] All financial math via SQL `numeric`, not float
- [ ] No CREATE VIEW / CREATE TABLE on production Supabase without the marker (per `feedback_supabase_mcp_gate`)
- [ ] Event counts reported alongside every IC number — IC of 0.10 with 5 events/year is useless

### Status reporting

End with DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT. Report under 600 words covering: which rule combinations cleared the bar, in-sample vs OOS IC, surprises, and the *single most important next move* if the locked-rules story is incomplete.
