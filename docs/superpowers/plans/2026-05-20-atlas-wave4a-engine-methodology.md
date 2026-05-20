# Atlas v2 Wave 4A — Engine Methodology Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Stop the sector and fund classifiers collapsing to one constant label by replacing absolute thresholds with a hybrid rank + absolute-floor model, and audit (report-only) the stock state engine's Stage-2 thresholds.

**Architecture:** A new pure `hybrid_rank_labels` function ranks entities cross-sectionally each day and assigns a label by percentile band, then caps the top label by an absolute floor. The sector and fund daily aggregators call it. A migration repoints `atlas_sector_signal_unified` at the computed label. The state engine is NOT modified — Stage-2 thresholds are only audited.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Alembic, Postgres, pandas, pytest.

**Spec:** [2026-05-20-atlas-wave4a-engine-methodology-design.md](../specs/2026-05-20-atlas-wave4a-engine-methodology-design.md)

---

## Cross-cutting acceptance criteria (every task)

- **Zero synthetic data** — the Stage-2 audit cites real DB rows; no fabricated values.
- **Formulas tested** — the ranker and floor logic get unit tests asserting hand-computed labels.
- **Logic checks** — a regression test that the ranker NEVER returns all-one-label given varied input.
- Thresholds (band cut-points, floor values) live in `atlas.atlas_thresholds`, not hardcoded. Decimal for weights.

---

## File structure

- Create: `atlas/intelligence/ranking.py` — pure `hybrid_rank_labels` (≤200 LOC), shared by sector + fund.
- Create: `tests/intelligence/test_ranking.py`.
- Create: `docs/audits/2026-05-stage2-threshold-audit.md` — the audit output (Task 1).
- Modify: `atlas/intelligence/aggregations/sector.py` — call the ranker for `sector_state`.
- Modify: `atlas/intelligence/aggregations/fund.py` — call the ranker in `derive_fund_recommendation`.
- Modify: `atlas/compute/lens_holdings.py` — remove the `Weak-Holdings` short-circuit dependency.
- Create: `migrations/versions/094_sector_state_from_computed.py` — repoint `atlas_sector_signal_unified.sector_state` at the computed column.
- Tests under `tests/intelligence/aggregations/`.

---

## Task 1: Stage-2 threshold audit (report-only)

**Files:** Create `docs/audits/2026-05-stage2-threshold-audit.md`. This is an investigation task — no production code.

- [ ] **Step 1: Gather evidence.** Against the live DB (EC2, read-only), collect: (a) the latest-date count of stocks per `state` in `atlas_stock_state_daily`; (b) the 2023-01→2026-05 monthly time series of the Stage-2 share (`pct of universe in stage_2a/2b/2c`); (c) read `atlas/intelligence/states/classifier.py` — enumerate the Stage-2A/2B/2C entry conditions; (d) for each Stage-2 gate, the count of stocks that fail ONLY that gate (the near-miss cohort); (e) today's distribution of the gate inputs (breakout ratio, SMA-50/150/200 stack, ATR contraction).

- [ ] **Step 2: Write the audit.** Create `docs/audits/2026-05-stage2-threshold-audit.md` with: the evidence tables, and a verdict — `GENUINE THIN MARKET` (today's ~1% Stage-2 share is within the 2023-26 range for weak tapes; no action) or `UNDER-CLASSIFYING` (a large near-miss cohort at a specific gate; name the gate + threshold). If under-classifying, state explicitly that re-tuning is a separate IC-validated task, NOT part of Wave 4A.

- [ ] **Step 3: Commit.** `git add docs/audits/2026-05-stage2-threshold-audit.md && git commit -m "docs(audit): Stage-2 threshold audit — Wave 4A Part 1"`

## Task 2: The hybrid ranker — pure function

**Files:** Create `atlas/intelligence/ranking.py`, `tests/intelligence/test_ranking.py`.

- [ ] **Step 1: Write the failing test.**

```python
from decimal import Decimal
from atlas.intelligence.ranking import hybrid_rank_labels, RankConfig

# 4 labels, top->bottom; bands are cumulative percentile cut-points.
_CFG = RankConfig(
    labels=["Avoid", "Underweight", "Neutral", "Overweight"],
    band_pcts=[Decimal("0.20"), Decimal("0.50"), Decimal("0.80")],
    floor_label="Overweight",
    floor_min=Decimal("10"),
)

def test_always_produces_a_spread():
    scores = {f"s{i}": Decimal(i) for i in range(10)}
    floors = {f"s{i}": Decimal("50") for i in range(10)}  # all clear the floor
    out = hybrid_rank_labels(scores, floors, _CFG)
    assert len(set(out.values())) > 1  # never all-one-label

def test_percentile_bands_assign_expected_labels():
    # 5 entities, scores 1..5, all above floor
    scores = {"a": Decimal(1), "b": Decimal(2), "c": Decimal(3), "d": Decimal(4), "e": Decimal(5)}
    floors = {k: Decimal("99") for k in scores}
    out = hybrid_rank_labels(scores, floors, _CFG)
    # percentile rank: a=0.0,b=0.25,c=0.5,d=0.75,e=1.0
    assert out["a"] == "Avoid"          # <0.20
    assert out["b"] == "Underweight"    # 0.20-0.50
    assert out["c"] == "Neutral"        # 0.50-0.80  (0.5 falls here)
    assert out["e"] == "Overweight"     # >=0.80

def test_absolute_floor_caps_top_label():
    # e ranks top but fails the floor -> caps to the next label down
    scores = {"a": Decimal(1), "b": Decimal(2), "c": Decimal(3), "d": Decimal(4), "e": Decimal(5)}
    floors = {"a": Decimal("99"), "b": Decimal("99"), "c": Decimal("99"),
              "d": Decimal("99"), "e": Decimal("5")}  # e below floor_min 10
    out = hybrid_rank_labels(scores, floors, _CFG)
    assert out["e"] == "Neutral"  # would be Overweight, floored down one
```

- [ ] **Step 2: Run — expect FAIL** (`pytest tests/intelligence/test_ranking.py -v`).

- [ ] **Step 3: Implement `atlas/intelligence/ranking.py`.**

```python
"""Hybrid rank + absolute-floor classifier. Ranks entities cross-sectionally
by score, assigns a label by percentile band, then caps the top label when
the entity fails an absolute floor. Guarantees a label spread — never collapses
to one constant label."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RankConfig:
    """labels: ordered worst->best. band_pcts: ascending cumulative percentile
    cut-points, len == len(labels) - 1. floor_label: the top label that the
    floor can cap. floor_min: minimum floor-metric value to hold floor_label."""
    labels: list[str]
    band_pcts: list[Decimal]
    floor_label: str
    floor_min: Decimal


def hybrid_rank_labels(
    scores: dict[str, Decimal],
    floor_values: dict[str, Decimal],
    cfg: RankConfig,
) -> dict[str, str]:
    """Return {entity_id: label}. scores rank entities; floor_values gate the
    top label. Empty input -> empty dict. Single entity -> its label by a
    percentile rank of 0.0 (bottom band) — documented degenerate case."""
    if not scores:
        return {}
    n = len(scores)
    ordered = sorted(scores.items(), key=lambda kv: kv[1])
    out: dict[str, str] = {}
    for idx, (eid, _score) in enumerate(ordered):
        pct = Decimal(idx) / Decimal(n - 1) if n > 1 else Decimal(0)
        band = 0
        for cut in cfg.band_pcts:
            if pct >= cut:
                band += 1
        label = cfg.labels[band]
        # Absolute floor: if this entity holds floor_label but fails the
        # floor metric, cap it one label down.
        if label == cfg.floor_label:
            fv = floor_values.get(eid)
            if fv is None or fv < cfg.floor_min:
                label = cfg.labels[max(0, cfg.labels.index(label) - 1)]
        out[eid] = label
    return out
```

- [ ] **Step 4: Run — expect 3 PASS.**

- [ ] **Step 5: Commit.** `git add atlas/intelligence/ranking.py tests/intelligence/test_ranking.py && git commit -m "feat(ranking): hybrid rank + absolute-floor classifier"`

## Task 3: Sector classifier — use the ranker + migration 094

**Files:** Modify `atlas/intelligence/aggregations/sector.py`; create `migrations/versions/094_sector_state_from_computed.py`; test `tests/intelligence/aggregations/test_sector.py`.

- [ ] **Step 1: Write the failing test.** In `test_sector.py`, add a test that the sector aggregation, given a fixture of sector signal rows where every sector has low `pct_stage_2`, still produces a spread of `sector_state` values (not all "Neutral"), and that a sector failing the breadth floor never gets "Overweight". Use the real aggregation entry point — read `sector.py` first to find it.

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement.** In `sector.py`, after the per-sector signal rows are built, compute the cross-sectional `sector_state`: build a `scores` dict (composite = `pct_stage_2` · `mean_within_state_rank` · sector RS — use the real columns; Decimal) and a `floor_values` dict (`pct_stage_2` per sector), call `hybrid_rank_labels` with a `RankConfig` whose band cut-points and `floor_min` are loaded from `atlas.atlas_thresholds` (add the threshold keys: `sector_band_p20/p50/p80`, `sector_overweight_floor`). Write the resulting label into the `sector_state` column the aggregation persists.

- [ ] **Step 4: Write migration `094_sector_state_from_computed.py`.** `down_revision = "093_portfolio_targets_holdings"`. Drop and recreate `atlas_sector_signal_unified` so `sector_state` reads the computed column from the sector aggregation output table (instead of migration 084's CASE expression on `pct_stage_2`). Read migration 084 first to get the exact view definition; change only the `sector_state` derivation. `downgrade()` restores the 084 CASE.

- [ ] **Step 5: Run tests — expect PASS.** Apply the migration on EC2 (deferred — controller handles).

- [ ] **Step 6: Commit.** `git add atlas/intelligence/aggregations/sector.py migrations/versions/094_sector_state_from_computed.py tests/intelligence/aggregations/test_sector.py && git commit -m "feat(sectors): hybrid rank+floor sector_state — migration 094"`

## Task 4: Fund classifier — use the ranker, remove the short-circuit

**Files:** Modify `atlas/intelligence/aggregations/fund.py`, `atlas/compute/lens_holdings.py`; test `tests/intelligence/aggregations/test_fund.py`.

- [ ] **Step 1: Write the failing test.** In `test_fund.py`, add a test: given a fixture of funds where every fund has `holdings_state == "Weak-Holdings"`, `derive_fund_recommendation` (or the new cross-sectional fund classifier entry point) still produces a spread of recommendations (not all "Reduce"), and a fund failing the absolute floor never gets "Recommended". Hand-compute the expected labels.

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement.** In `fund.py`: remove the short-circuit `if holdings_state == "Weak-Holdings" or composition_state == "Deteriorating": return "Reduce"` at the head of `derive_fund_recommendation` (read the function first — exact lines). Replace the recommendation derivation with a cross-sectional pass: build a `scores` dict (composite = NAV-state rank · holdings quality / `strong_aum_pct` · fund RS) and `floor_values` (`strong_aum_pct`), call `hybrid_rank_labels` with `RankConfig(labels=["Exit","Reduce","Hold","Recommended"], ...)` and band/floor from `atlas.atlas_thresholds` (keys `fund_band_*`, `fund_recommended_floor`). In `lens_holdings.py`, leave `classify_holdings_state` intact (it is still a useful signal) but confirm nothing else depends on the removed short-circuit.

- [ ] **Step 4: Run tests — expect PASS.**

- [ ] **Step 5: Commit.** `git add atlas/intelligence/aggregations/fund.py atlas/compute/lens_holdings.py tests/intelligence/aggregations/test_fund.py && git commit -m "feat(funds): hybrid rank+floor fund recommendation — drop Weak-Holdings short-circuit"`

## Task 5: Threshold seed + nightly verification

**Files:** Modify the threshold seed (find it — `scripts/seed_*thresholds*` or a migration); no new schedule.

- [ ] **Step 1:** Add the new `atlas_thresholds` keys with defensible defaults: `sector_band_p20=0.20, sector_band_p50=0.50, sector_band_p80=0.80, sector_overweight_floor=10` (whole-percent pct_stage_2 floor); `fund_band_*` likewise; `fund_recommended_floor` = a sensible `strong_aum_pct` floor (e.g. 0.20). Confirm the sector + fund aggregations run inside `scripts/nightly_v2.sh` (they already do — no schedule change). Add a code comment in `nightly_v2.sh` noting the ranker runs as part of the aggregation step.
- [ ] **Step 2: Commit.** `git commit -m "feat(thresholds): seed hybrid-classifier band + floor thresholds"`

---

## Self-review

**Spec coverage:** Part 1 audit → Task 1 ✓; hybrid sector classifier → Tasks 2+3 ✓; hybrid fund classifier → Tasks 2+4 ✓; thresholds in atlas_thresholds → Task 5 ✓; never-collapses test → Task 2 Step 1 ✓.

**Placeholder scan:** Task 1 is an investigation task (no code) — its steps are concrete evidence-gathering, acceptable. Tasks 3/4 say "read the file first to find the real entry point" because the exact line numbers must be confirmed against the live code — this is a real instruction, not a placeholder; the code to write is fully specified.

**Type consistency:** `hybrid_rank_labels(scores, floor_values, cfg)` + `RankConfig` used identically in Tasks 3 and 4.
