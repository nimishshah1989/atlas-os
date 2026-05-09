# M14 — Decision Policy Admin (FM-grade levers)

**Date:** 2026-05-09
**Status:** Spec — pending plan-eng-review
**Goal:** Let the FM tune the high-level rules that decide what's investable — gate policies (which states pass), position-sizing multipliers, and state-defining cutoffs — via a plain-English UI. M13's raw thresholds become an Advanced tab.

---

## Why this exists

M13 shipped numeric threshold tuning (`stage1_weak_weeks_min=8`, `momentum_breakout_lookback_days=20`, etc) — useful for the methodology team but not the FM's mental model. Today (2026-05-05) the live system shows **0 of 681 stocks investable** because `direction_gate` requires `momentum_state == Accelerating` AND it's at 0.6% pass rate. The FM looks at Nifty 24,500 / VIX 17.9 and intuits "this isn't a bad market — my rules must be too tight." They are right. The fix is not to drop a sigma; it's to let the FM say "Improving counts too" or "loosen the Leader cutoff to top 10%" with a checkbox or slider.

---

## What ships

A page at `atlas.jslwealth.in/admin/policies` (replaces `/admin/thresholds` in nav, M13 view becomes Tab 4) where FM controls 3 layers of decision policy:

### Layer 1 — Gate Policies (which states pass each of the 6 gates)
| Gate | Currently (hardcoded frozenset) | FM-tunable target |
|---|---|---|
| `strength_gate` | `{Leader, Strong, Emerging}` | checkbox set across all rs_state values |
| `direction_gate` | `{Accelerating, Improving}` | checkbox set across all momentum_state values |
| `risk_gate` | `{Low, Normal}` | checkbox set across all risk_state values |
| `volume_gate` | `{Accumulation, Steady-Buying}` | checkbox set across all volume_state values |
| `sector_gate` | `{Overweight, Neutral}` | checkbox set across all sector_state values |
| `market_gate` | `regime != Risk-Off` | checkbox set across all regime_state values |

For ETFs and funds the policies are slightly different (no volume_gate for ETFs; fund recommendation logic). v0 ships stock policies only; ETF + fund policies appear as separate cards but read-only with "v0.1" badge.

### Layer 2 — Position-sizing multipliers
- `RISK_MULTIPLIERS`: 5 sliders (Low/Normal/Elevated/High/Below Trend → 0.0 to 2.0)
- `MARKET_MULTIPLIERS`: 4 sliders (Risk-On/Constructive/Cautious/Risk-Off → 0.0 to 1.0)

### Layer 3 — State-defining cutoffs (subset of atlas_thresholds, surfaced with state-mapping context)
The thresholds already in `atlas_thresholds` that DEFINE state boundaries. Examples (from migration 022 + M1 seed):
- `rs_quintile_top` (0.80) → "Top 20% RS = candidate for Leader/Strong"
- `rs_quintile_bottom` (0.20) → "Bottom 20% RS = candidate for Weak/Laggard"
- `sector_rs_quintile_top_pct` (80.0) → "Top 20% sector RS = Overweight"
- `sector_rs_quintile_bottom_pct` (20.0) → "Bottom 20% sector RS = Avoid"
- `stage1_weak_weeks_min` (8) → "Stage-1 base needs ≥8 of last 10 weeks weak"
- `momentum_ema_convergence_pct` (0.01) → "EMAs within 1% = Flat momentum"

These are already per-row-tunable in `atlas_thresholds`; M14 just **labels them** and surfaces them in a state-mapped tab. No schema change for Layer 3.

### Tabs
| Tab | What's there | Backed by |
|---|---|---|
| Gate Policies | 6 cards × ~5-7 checkboxes each | new `atlas_decision_policy` rows |
| Multipliers | 9 sliders | new `atlas_decision_policy` rows |
| State Cutoffs | ~12 sliders with state labels | existing `atlas_thresholds` rows (filtered) |
| Advanced | The full M13 view (~38 raw rows) | existing `atlas_thresholds` |
| Recompute / History | reuse M13 components verbatim | `atlas_pipeline_runs` / `atlas_decision_policy_history` + `atlas_threshold_history` |

---

## Architecture decisions (locked)

### 1. Storage — one new table for everything (D5 → A)

```sql
CREATE TABLE atlas.atlas_decision_policy (
    policy_key          VARCHAR(64)  NOT NULL PRIMARY KEY,
    policy_kind         VARCHAR(16)  NOT NULL,        -- 'gate_states' | 'multiplier_map'
    policy_value        JSONB        NOT NULL,        -- ['Leader','Strong'] OR {'Risk-On': 1.0}
    description         TEXT         NOT NULL,
    methodology_section VARCHAR(16),
    last_modified_by    VARCHAR(64)  NOT NULL DEFAULT 'system',
    last_modified_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_policy_kind CHECK (policy_kind IN ('gate_states', 'multiplier_map'))
);
```

State-cutoff layer reuses `atlas_thresholds` — no schema change for Layer 3.

### 2. Audit table parallel to M13's `atlas_threshold_history`

```sql
CREATE TABLE atlas.atlas_decision_policy_history (
    id               SERIAL       PRIMARY KEY,
    policy_key       VARCHAR(64)  NOT NULL REFERENCES atlas.atlas_decision_policy(policy_key),
    old_value        JSONB,                              -- NULL for initial seed
    new_value        JSONB        NOT NULL,
    changed_by       VARCHAR(64)  NOT NULL,
    changed_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    change_reason    TEXT,
    triggered_reclassify BOOLEAN  NOT NULL DEFAULT FALSE,
    reclassify_run_id UUID,
    user_ip          INET,
    user_agent       TEXT
);

CREATE INDEX idx_decision_policy_history_key
    ON atlas.atlas_decision_policy_history (policy_key, changed_at DESC);
```

Trigger reuses the M13 pattern — `current_setting('atlas.change_reason', true)` GUC, fires AFTER UPDATE only.

### 3. Code-default fallback (D7 → A)

`atlas/compute/_policy.py` — new module that loads decisions from DB with code-level fallback:

```python
DEFAULT_GATE_POLICIES: dict[str, frozenset[str]] = {
    "strength_gate": frozenset({"Leader", "Strong", "Emerging"}),
    "direction_gate": frozenset({"Accelerating", "Improving"}),
    "risk_gate": frozenset({"Low", "Normal"}),
    "volume_gate": frozenset({"Accumulation", "Steady-Buying"}),
    "sector_gate": frozenset({"Overweight", "Neutral"}),
    "market_gate": frozenset({"Risk-On", "Constructive", "Cautious"}),  # exclude Risk-Off
}

def load_gate_policy(gate_name: str, engine: Engine) -> frozenset[str]:
    """Load gate-policy from DB; fall back to code default if missing/malformed.
    Logs structured warning when fallback is used."""
    try:
        row = ... SELECT FROM atlas_decision_policy WHERE policy_key = :gate_name AND is_active
        if row is None:
            log.warning("policy_fallback_used", gate=gate_name, reason="row_missing")
            return DEFAULT_GATE_POLICIES[gate_name]
        states = set(row.policy_value)  # JSON array → Python set
        return frozenset(states)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        log.warning("policy_fallback_used", gate=gate_name, reason=type(exc).__name__)
        return DEFAULT_GATE_POLICIES[gate_name]
```

Pipeline never breaks. FM-tuned policies activate the moment a row exists.

### 4. Refactor target — replace frozensets/dicts with policy reads

| Current | After M14 |
|---|---|
| `decisions_stock.py:84` STRENGTH_PASS_STATES = frozenset(...) | `load_gate_policy('strength_gate', engine)` called once at run start |
| `decisions_stock.py:88` DIRECTION_PASS_STATES = frozenset(...) | same pattern |
| `decisions_stock.py:90` VOLUME_PASS_STATES = frozenset(...) | same |
| `decisions_stock.py:42` RISK_MULTIPLIERS = {...} | `load_multiplier_map('risk_multipliers', engine)` |
| `decisions_stock.py:51` MARKET_MULTIPLIERS = {...} | same |
| Same for `decisions_etf.py`, `decisions_fund.py` (ETF + fund policies seeded with current code values, marked v0.1 read-only in UI) |

Keep the DEFAULT_* constants as code fallback. Don't delete them.

### 5. UI — plain-English rule cards (D2 → C)

No live preview. Every change is "save → recompute → check public dashboard." Same model as M13.

**Gate Policies tab** — 6 cards, one per gate. Each card:
```
┌─ Strength Gate ────────────────────────────────────────────┐
│ A stock passes this gate if its rs_state is one of:        │
│  ☑ Leader    ☑ Strong    ☑ Emerging                        │
│  ☐ Consolidating  ☐ Average  ☐ Weak  ☐ Laggard             │
│  Locked (always excluded): INSUFFICIENT_HISTORY, ILLIQUID  │
│  Methodology §13.1 · Last modified: 09-May-2026 by FM       │
│  [Edit] · [History]                                         │
└────────────────────────────────────────────────────────────┘
```

Edit modal: same shape as M13's, but instead of a numeric input, it's a checkbox group. Required reason textarea. Diff preview shows added/removed states.

**Multipliers tab** — slider rows:
```
┌─ Risk Multipliers (position size scaling per stock risk_state) ─┐
│ Low      [────●────] 1.20x   default 1.20  range [0.5, 2.0]    │
│ Normal   [───●─────] 1.00x   default 1.00  range [0.5, 1.5]    │
│ ...                                                              │
└──────────────────────────────────────────────────────────────────┘
```

**State Cutoffs tab** — labeled sliders pulling from `atlas_thresholds` (no new schema). Each row labels what state boundary it controls.

**Advanced tab** — the M13 ThresholdsView (the existing 38-row table). FM rarely opens.

### 6. Methodology stance

Tunable values are not "the methodology" — methodology defines defaults; FM tunes within bounds. Specifically:
- Code-level `DEFAULT_*` constants ARE the methodology baseline.
- DB rows in `atlas_decision_policy` are FM-tuned overrides.
- min/max bounds in the UI prevent FM from setting nonsensical values (e.g., empty gate set is allowed but warned; multipliers >2x are blocked).
- Audit log preserves every change for SEBI compliance.

---

## File map

```
migrations/versions/024_create_decision_policy.py            [new]
  - CREATE TABLE atlas_decision_policy
  - CREATE TABLE atlas_decision_policy_history
  - CREATE TRIGGER trg_decision_policy_audit (AFTER UPDATE)
  - SEED atlas_decision_policy with current frozensets/dicts (gate_states + multiplier_map rows)
atlas/compute/_policy.py                                     [new]
  - DEFAULT_GATE_POLICIES, DEFAULT_MULTIPLIERS constants
  - load_gate_policy(name, engine) → frozenset[str]
  - load_multiplier_map(name, engine) → dict[str, Decimal]
  - Caching: load once per compute run, not per row
atlas/compute/decisions_stock.py                             [edit]
  - Replace frozensets + dicts with _policy loader calls
  - Defaults stay as fallback
atlas/compute/decisions_etf.py                               [edit] (same pattern)
atlas/compute/decisions_fund.py                              [edit] (same pattern)
tests/unit/migrations/test_decision_policy_trigger.py        [new]
tests/unit/compute/test_policy_loader.py                     [new]
tests/unit/compute/test_decisions_stock_with_policy.py       [new]   # golden test
frontend/src/lib/queries/policies.ts                         [new]
frontend/src/app/admin/policies/                             [new]
  page.tsx                                                   # RSC, fetches all policies + recent runs, <250 LOC
  PoliciesView.tsx                                           # client island, holds tab state + selected key
  layout.tsx                                                 # extends admin shell
  GatePoliciesTab.tsx                                        # 6 gate cards
  MultipliersTab.tsx                                         # slider rows
  StateCutoffsTab.tsx                                        # labeled sliders into atlas_thresholds
  AdvancedTab.tsx                                            # imports M13 ThresholdsView
  EditGatePolicyModal.tsx                                    # checkbox group + reason textarea
  EditMultiplierModal.tsx                                    # slider + reason textarea
  PolicyHistoryDrawer.tsx                                    # 20 most recent atlas_decision_policy_history rows
  RecomputePanel.tsx                                         # MOVE M13's RecomputePanel here, or import
  actions.ts                                                 # Server Actions: updateGatePolicy, updateMultiplier
frontend/src/__tests__/admin/policies-actions.test.ts        [new]
frontend/src/__tests__/admin/policies-page.test.ts           [new]
frontend/src/components/nav/TopNav.tsx                       [edit] (rename /admin/thresholds → /admin/policies)
prds/M14_DECISION_POLICY.md                                  [this file]
```

Also: redirect `/admin/thresholds` → `/admin/policies?tab=advanced` for compat (existing M13 bookmarks survive).

---

## Phasing (~5-6 hr CC, fits the user's 4-5 hr away window if I'm sharp)

| # | Chunk | Wall-clock |
|---|---|---|
| 0 | plan-ceo-review (this doc) → plan-eng-review on this doc | 0.5 hr |
| 1 | Migration 024 + seed + audit trigger + tests | 1.0 hr |
| 2 | atlas/compute/_policy.py + refactor decisions_stock/etf/fund.py + golden tests | 1.5 hr |
| 3 | /admin/policies page + tabs + edit modals + history drawer + Server Actions + tests | 2.5 hr |
| 4 | Deploy + smoke test + PR | 0.5 hr |

---

## Tests (boil-the-lake)

### Backend
- **Migration 024 unit + integration**: trigger fires on UPDATE, captures GUC reason, no fire on INSERT (parallel to M13 trigger tests).
- **Seed verification**: every default frozenset/dict is in atlas_decision_policy after migration runs.
- **`_policy.py` loader**:
  - Valid row → returns parsed value
  - Missing row → falls back to code default + logs `policy_fallback_used`
  - Malformed JSON → falls back + logs
  - Empty `[]` for gate_states → returns empty frozenset (intentional FM choice — UI warns; pipeline won't crash, will just produce 0% gate pass)
- **Refactored decisions_stock.py golden test**: with mocked policy returning loose set (`{Leader, Strong, Emerging, Consolidating}`), is_investable count goes UP vs default; with strict set (`{Leader}`) it goes DOWN.

### Frontend
- **Server Action `updateGatePolicy`**:
  - Empty allowed_states list → warns but accepts (FM intent)
  - Unknown state name in array → rejected with friendly error
  - Reason required (parallel to M13's updateThreshold)
  - Wrapped in `sql.begin` so SET LOCAL atlas.change_reason fires inside same tx as UPDATE
- **Server Action `updateMultiplier`**: out-of-range value → rejected; reason required
- **Middleware**: /admin/policies under existing site-cookie gate (parallel to M13)
- **E2E** (skipped without ATLAS_E2E_BASE_URL):
  - FM toggles Direction Gate to add `Flat` → save → audit row → next recompute → investable count goes from 0 to N
  - FM hits Multipliers slider → save → audit row

### Test scope: ~25-30 tests total. Same boil-the-lake bar as M13.

---

## Failure modes

| Failure | Test? | Handled? | User experience |
|---|---|---|---|
| Migration 024 fails partway | n/a | alembic transaction-mode is atomic | Migration rolls back; pipeline keeps running on code defaults |
| atlas_decision_policy row missing | ✓ test_policy_loader | code-default fallback, structured warning log | Pipeline runs on methodology defaults; FM unaffected unless they expected their tuning to apply |
| Malformed JSON in policy_value | ✓ | same fallback | Same |
| FM saves empty gate-policy (`[]`) | ✓ | accepted; UI shows warning before save | FM understands gate will block 100% of stocks |
| FM types unknown state name (only via raw SQL — UI uses checkboxes) | ✓ Server Action validates | rejected pre-DB | UI surfaces error |
| Multiplier set to negative | ✓ | rejected at min_allowed=0 | Slider can't go negative |
| Concurrent FM edits same policy | not tested | last-write-wins; audit captures both | Acceptable for v0 (1 FM); flock if multi-user lands |
| Site-cookie auth bypass | covered by M13 middleware tests | same gate as M13 | Same |
| Policy change mid-recompute | not tested | policy loaded at run start, not refreshed mid-run | FM understands "save → next recompute" semantics |

No critical gaps with code-default fallback in place.

---

## What already exists (reused)

- M13 audit-trigger pattern → reused for `atlas_decision_policy_history`
- M13 admin layout / middleware / Recompute panel / History drawer → reused or moved
- M13 Server Action transaction wrapper (`sql.begin` + `SET LOCAL atlas.change_reason`) → reused
- M13 `formatThreshold` + `formatIST` → reused in policies UI
- `atlas_thresholds` (M13) → unchanged for State Cutoffs tab
- `frontend/middleware.ts` → no edit (existing site-cookie covers `/admin/policies`)
- `atlas/health/runs.py` → no edit
- `atlas/api/internal_recompute.py` → no edit (recompute trigger works for any milestone)

---

## NOT in scope (deferred)

- **Live simulation preview** ("with these settings, X stocks would be investable today"). Most-requested by my own intuition but rejected by user (D2 → C plain-English cards). Defer to v0.1.
- **Preset modes** (Aggressive / Balanced / Conservative). Could collapse 30+ knobs to 3 buttons. Defer to v0.1 once we have signal on which knobs FM actually moves.
- **ETF and Fund gate policy editing** (read-only in v0). Code-level frozensets stay; UI shows them with "v0.1" badge. Tunable in v0.1.
- **Custom gate logic** (currently 6 gates ANDed; FM might want OR-of-gates or 5-of-6). Defer to M15 if desired — large architectural change.
- **Multi-FM policy isolation** (each FM has their own policy). Defer until second FM exists.
- **Policy versioning / branches** (FM works in a draft, then promotes). Defer.
- **Approval workflow** (FM proposes change, methodology team approves). Defer; v0 is single-FM trust model.
- **Real-time policy hot-reload mid-run** (changes apply instantly to in-flight recomputes). Defer; current model is "save → next recompute" which matches M13.
- **Bounded validation against methodology** (e.g., min_allowed/max_allowed on gate-state SETS). v0 trusts FM judgment within state allowlist.

---

## Success criteria

1. FM logs in at `/admin/policies`, sees 4 tabs (Gate Policies / Multipliers / State Cutoffs / Advanced)
2. FM clicks Direction Gate card, sees current allowed states, ticks `Flat` to add it
3. Saves with reason "loosen direction during Cautious regime"
4. Audit row appears in `atlas_decision_policy_history` with old=`['Accelerating','Improving']`, new=`['Accelerating','Improving','Flat']`, reason captured
5. Clicks "Re-run sectors" (M3 — wait, that's wrong; clicks "Re-run M5 decisions") → run starts
6. Within 5 min, status flips to success, `atlas_stock_decisions_daily` reflects loosened policy → investable count goes from 0 to 30+
7. Public dashboard at `/sectors` shows the recomputed states; live decisions page (M6) shows new investable list
8. Bumps a multiplier slider, same flow

---

## Branching / deployment

- New branch `feat/m14-decision-policy` off main (after M13 PR #1 merges OR off feat/m13 if not merged)
- Migration 024 stacks on 023 (M13)
- Same .214 / .196 deploy pattern as M13

## Open questions for plan-eng-review

- ETF and Fund seeding: should `atlas_decision_policy` be seeded with ETF + fund gate values too (even though they're read-only in v0 UI), so the loader path is uniform? (Probably yes.)
- State-cutoff tab: which exact `atlas_thresholds` keys appear there vs in Advanced? Need a curated list with state-mapping labels. Tractable but takes ~30 min of research into `decisions.jsonl` + methodology doc.
- The Recompute panel currently only triggers M3/M4/M5 backfills. For M14, the FM tuning the strength_gate cares about M5 decisions. The recompute panel UI labels should make clear which milestone re-runs which compute (e.g., "Re-run M5 decisions" updates is_investable based on new policy without re-running M3 sector states).
