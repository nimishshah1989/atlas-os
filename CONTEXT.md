# Atlas — Domain glossary

This file is the canonical glossary for Atlas v6 terms. It is updated as
ambiguities get resolved during planning sessions. It is NOT a spec, NOT
a scratch pad — only a glossary.

Authoritative upstream references (terms inherited from these are not
restated here unless eng review resolved an ambiguity):
- CEO plan: `~/.gstack/projects/atlas-os/ceo-plans/2026-05-24-atlas-v6-product-spec.md`
- Methodology lock: `<consolidation>/docs/atlas-signal-discovery/methodology-lock-2026-05-23.md`
- Product spec: `<consolidation>/docs/atlas-signal-discovery/ATLAS_PRODUCT_SPEC_2026-05-24.html`

---

## signal_call_id

A UUID that uniquely identifies one **trigger event** — a (instrument,
cell, tenure) pair transitioning from INACTIVE to ACTIVE on a specific
calendar date.

**Cadence:** minted ONCE per trigger. Days where the cell remains active
do NOT produce new `signal_call_id`s — the existing row stays "open"
(no `exit_date`) until the exit rule fires (tenure expiry, cell flip to
TRIM/AVOID/WATCH, user close, delisting, or cell deprecation).

**Lifetime:** a row's `signal_call_id` is the stable correlation key
across `atlas_brief_cache`, `atlas_paper_portfolio`, and `atlas_ledger`.
A position re-entered after exit (fresh INACTIVE→ACTIVE transition on
the same (iid, cell, tenure)) gets a NEW `signal_call_id`. Same domain
pair, distinct row; uniqueness on `atlas_paper_portfolio` includes
`entry_date` to permit this.

**Why this matters:** the alternative (daily snapshot rows) would inflate
`atlas_signal_calls` from ~50-100 rows/day to ~50,000 rows/day, change
every index, and break the eng review §4 perf budget.

Resolved 2026-05-24 in /grill-with-docs Q1.

---

## Cell deprecation

A cell is **deprecated** when its `atlas_cell_definitions.deprecated_at`
timestamp is non-null. Deprecated cells stop firing in daily inference;
open paper positions on that cell exit at the next EOD with
`exit_reason='cell_deprecated'`.

**Trigger:** drift-detector automatic. The `atlas/ledger/` drift monitor
compares realized excess vs predicted excess per cell. When the divergence
exceeds a Z-threshold for N consecutive trading days, the nightly cron
sets `deprecated_at`. No manual approval required.

**Interaction with single-maintainer risk (N1=B accepted in CEO plan):**
auto-deprecation is the system's safety valve when the maintainer hasn't
reviewed drift in time. The maintainer is still informed (PagerDuty +
audit log) and can revert by clearing `deprecated_at`, but the system
doesn't wait for them.

Resolved 2026-05-24 in /grill-with-docs Q2.

---

## Cell deprecation (REVISED post three-model adversarial review)

**The Q2 lock above is SUPERSEDED.** Three-model consensus (F3) flagged
automatic binding deprecation as a live-fire safety hazard. Revised
behavior:

**Trigger:** drift-detector flags + **maintainer-confirmed** deprecation.
When the drift monitor's Z exceeds the threshold for N consecutive days,
the nightly cron sets `drift_status='drift_warn'` and pages the maintainer
(PagerDuty). The maintainer then reviews and either clears `drift_warn`
(false positive — cell stays active) or sets `deprecated_at` (confirmed
methodology break — cell retires + open positions exit).

**Why advisory not binding:** if the drift detector is correctly catching
a methodology error, auto-exiting open positions forces realized losses
on retail users at exactly the moment validation is needed. The mechanism
is being designed for v7 broker-integration reality (real money) where
auto-close would be regulatorily fraught. Advisory mode in v6 preserves
the self-measurement signal while keeping human approval on the methodology-lock decision.

**Exit semantics on confirmed deprecation:** when the maintainer sets
`deprecated_at`, open paper positions exit at the next EOD with
`exit_reason='cell_deprecated'`. Discrete human-approved event, not cron.

**σ_predicted source (was unspecified):** **bootstrap standard deviation
of friction-adjusted excess across the cell's walk-forward windows** (3
OOS test years; ≥30 realized positions required by warmup gate).
Cross-section SD and time-series-on-realized-only are NOT used.

**Audit trail (G5 remediation):** every drift event writes a row to
`atlas_drift_event_log` with `(cell_id, date, Z, realized_window,
predicted_excess, σ_predicted, status_before, status_after, action,
actor)`. Required for SEBI inspection.

**Named-secondary fallback (F7 remediation):** when the primary
maintainer is unavailable (>72h unresponsive to PagerDuty), the named
secondary maintainer (documented in compliance binder, see new section)
holds operational authority to confirm or revert drift flags.

**Binding auto-deprecation deferred to v7** with explicit regulatory
review under the SEBI RA registration framework.

Revised 2026-05-24 post three-model adversarial review (F3 + G5 + F7).

---

## Drift detector parameters

The `atlas/ledger/` drift monitor (advisory mode per F3 revision above)
is parameterised as:

- **Z-threshold:** `|Z| > 2.5` (two-tailed ~1.2%) where
  `Z = (realized_excess − predicted_excess) / σ_predicted`
- **σ_predicted:** bootstrap standard deviation of friction-adjusted
  excess across the cell's walk-forward windows (see Cell deprecation
  above for full source spec)
- **Persistence:** Z must exceed threshold for **10 consecutive trading days**
- **Warmup gate:** cell × tenure pair must have **≥ 30 realized positions
  AND ≥ 6 months since first trigger** before drift is evaluated
- **Predicted excess:** uses the cell's **friction-adjusted** locked
  excess (Phase 0.5d output), not unconditional or regime-conditional
- **Trigger effect:** sets `drift_status='drift_warn'` + pages
  maintainer. Does NOT auto-set `deprecated_at` (v6 advisory mode).

**Immutable audit trail (adversarial review G5):** every drift event
writes a row to `atlas_drift_event_log` with `(cell_id, date, Z,
realized_window, predicted_excess, σ_predicted, status_before,
status_after, action, actor)`. Required for SEBI inspection + post-mortem.

Resolved 2026-05-24 in /grill-with-docs Q3; revised 2026-05-24 post
three-model adversarial review (F3 σ_predicted spec + G5 audit trail).

---

## Cell rule (`atlas_cell_definitions.rule_dsl`)

A cell rule is a Pydantic v2 `CellRule` model serialised as JSONB. The
shape is **flat-AND**, not a nested expression tree.

- `eligibility: list[FeaturePredicate]` — universe + per-cell filters
  (additive over the M1 baseline; cells MAY tighten but not loosen).
- `entry: list[FeaturePredicate]` — cell-entry predicates, AND-joined.
- `rule_type`, `tier`, `action`, `tenure`, `rule_version`,
  `methodology_lock_ref`.

**Each `FeaturePredicate`** is `(feature, cmp, value)` where:
- `feature` is from a Pydantic `Literal[...]` allowlist sourced from
  `atlas.features` exports (typo = compile-time error).
- `cmp` is from `Literal[">", ">=", "<", "<=", "==", "in_range",
  "in_top_quantile"]`.
- `value` is `Decimal | tuple[Decimal, Decimal]`.

**OR semantics:** there is none in-rule. If two predicate sets need
"a OR b", define two cells with the same `(tier, action, tenure)` —
methodology lock's "per-(tier × stage) state definitions are canonical"
treats cells as atomic.

**Evaluator** is a ~5-line `all(eval_predicate(p, scorecard) for p in
cell.entry)`. No expression-tree interpreter.

Validation on insert via SQLAlchemy event listener.

Resolved 2026-05-24 in /grill-with-docs Q4.

---

## Regime classifier thresholds

The 4-state regime classifier (Risk-On / Elevated / Risk-Off / Below-Trend)
is rule-based on 4 inputs: `smallcap_rs_z`, `breadth_pct_above_200dma`,
`vix_percentile`, `cross_sectional_dispersion`.

**Threshold storage:** `atlas_thresholds` config table, loaded via
`atlas.db.load_thresholds()`. Hook-enforced — no hardcoded constants.

**Threshold derivation (REVISED post-adversarial review F4):**

dedicated pre-step **Phase 0.5h-prime** added before Phase 0.5h.
Sweeps threshold combinations over the 4 inputs on a **held-out OOS
window** (2015-2017, isolated from cell-validation data). Locks the
combination that maximises **differentiation** (largest spread in
per-cell confidence across the 4 regimes on the held-out window),
subject to a **regime occupancy floor of ≥ 10% per regime**.

Phase 0.5h then consumes the locked classifier on a **DIFFERENT OOS
slice** (2018-2020, also held out from cell validation) for the
per-cell regime-conditional confidence measurement. This prevents
the in-sample optimization F4 flagged — threshold selection and
confidence measurement run on disjoint windows.

Cell-validation walk-forward (Phase 3 et seq.) uses 2021+ data — so
the three OOS windows are: regime threshold (2015-2017), per-regime
confidence (2018-2020), cell validation (2021+). No overlap.

**Pre-registered bar (methodology lock principle 1):** before running
the sweep, document the threshold ranges + the differentiation metric +
the occupancy floor. Sweep output validates against the pre-registered
bar; failure means no threshold combination ships.

Resolved 2026-05-24 in /grill-with-docs Q5; revised 2026-05-24 post
three-model adversarial review (F4 in-sample optimization).

---

## Universe (M1) — current and post-0.5a

The Atlas M1 universe is **727 instruments today**, defined as
"M1 raw 750 minus 23 blacklisted iids with unadjusted
merger/demerger/face-value anomalies" (methodology lock §0).

**Phase 0.5a — Large-cap price-quality fix** recovers **10-12 large-cap
names** (out of the 23 blacklisted) by fixing their adjusted prices
against cross-source agreement (Bhavcopy + screener-quality + manual
verification). On success the universe rises to **~737-739 instruments**.

**0.5a is a hard prerequisite for 0.5e** (Large-cap BUY signal research):
without the recovered names, 0.5e is running on a Large-tier universe
missing its largest, most-liquid 11 names — exactly where Large-cap BUY
signal is most likely to appear. The CEO plan's gate-failure table
treated 0.5a and 0.5e as independent; eng review /grill-with-docs Q6
sequences them: 0.5a → 0.5e.

**Gate-failure rule (locked):** if Phase 0.5a fails to reconstruct any
name with cross-source agreement, that name stays blacklisted and is
documented in the methodology lock. The universe count drops accordingly.

Resolved 2026-05-24 in /grill-with-docs (clarification mid-Q6).

---

## Test snapshot suite

Walk-forward determinism (eng review §3.2) is the load-bearing test
primitive. The snapshot suite is **tiered**:

- **Small snapshot** — 100 stratified instruments × 7-year history.
  - 33 Small / 33 Mid / 34 Large by trailing-60d traded value tercile at
    the fixture date.
  - Preserve ≥10 delisted names (per 0.5b survivorship rebuild) — without
    these the snapshot has zero survivorship signal.
  - Preserve cell-fire diversity: ≥3 instruments per defined cell type.
  - Used by PR CI; runtime budget < 2 minutes.

- **Full snapshot** — 727+ instruments × 10-year history (rises to ~738+
  post-Phase-0.5a).
  - Used by nightly integration + IC regression tests.
  - Runtime budget ~10 minutes.

**Snapshot dates maintained:** three — one each from 2024, 2020 (COVID
drawdown), and 2018 (mid/small crash). The 2018 + 2020 dates are
mandatory: the methodology lock added Phase 3g (2015-2020 walk-forward)
specifically because OOS validation against those regimes is the largest
risk in the spec.

**Storage:** parquet files in `tests/fixtures/snapshots/{small,full}/{date}/`.
SHA256 manifest catches drift. Generated by
`scripts/generate_test_snapshot.py --subset {small|full} --date {YYYY-MM-DD}`.

**CI gate on small snapshot (REVISED post adversarial review F6):**
the original `IC ± 0.005` tolerance is statistically meaningless at
n=100 (standard error ≈ 0.10, twenty times the tolerance). Replaced with:

- **Deterministic-output hash gate (small snapshot):** PR CI runs
  feature compute + cell evaluation on the small snapshot and verifies
  that the SHA256 of the (sorted) signal_call output matches the
  recorded hash. Any drift = fail, no statistical interpretation
  needed. Catches feature-formula changes deterministically.
- **IC regression gate (full snapshot, nightly):** the ±0.005 tolerance
  applies here, where n=727+ gives SE ≈ 0.037 — close enough to the
  tolerance for the gate to be statistically meaningful. Nightly cron
  runs the IC check; failure pages the maintainer.

Resolved 2026-05-24 in /grill-with-docs Q6; CI gate revised
2026-05-24 post three-model adversarial review (F6).

---

## Brief cache (`atlas_brief_cache`) invalidation

Briefs are cached for 24h TTL plus an **allowlist** of
`de_corporate_actions` event types that materially change the brief's
economic story:

**Invalidates on:** merger, demerger, scheme of arrangement, rights
issue, spin-off, special dividend, delisting, suspension, name change,
ISIN change.

**Does NOT invalidate on:** stock split, bonus issue, regular dividend
ex-date, face-value change. The adjusted-price pipeline already absorbs
these; the cell sees no semantic change.

**Implementation:** A2 — cron post-step. After `de_corporate_actions`
ingest completes, a batched UPDATE invalidates affected briefs. Keeps
the modulith dependency rule clean (ingest does not call into the brief
cache directly).

**Granularity:** invalidate briefs whose `signal_call_id` points to an
**active signal call** (`atlas_signal_calls.exit_date IS NULL`). This
is a property of the call, not of any user's paper portfolio — most
active signal calls have no user holdings but their briefs must still
be served by `/v1/recommendation/{iid}` and `/v1/today/buys`.

Briefs for already-exited signal calls (`exit_date IS NOT NULL`) are
historical artifacts and are not invalidated.

Resolved 2026-05-24 in /grill-with-docs Q7.

---

## Intraday surfaces in v6

The `atlas/intraday/` module (SP08 Live State Engine + SP10 Live Panels)
is **retained through v6 launch**.

- **SP10 panels** (Nifty strip, sector movers, live prices, stock badge)
  render as-is on `v6.atlas.jslwealth.in`. Lifted in Phase 1 inventory
  per CEO plan principle 1.
- **SP08 EC2 deploy** (migration 042 + systemd units) proceeds in
  parallel with v6 build, not after.
- Visual fit between SP10 panels and the new v6 scorecard cards is
  verified at `/plan-design-review`, not eng review.

Daily v6 and intraday are orthogonal on the data path: daily reads
`de_equity_ohlcv.close_adj` post-EOD; intraday reads Kite ticks during
market hours. Two release cadences but zero shared dependencies.

Resolved 2026-05-24 in /grill-with-docs Q8.

---

## `atlas_agent_readonly` ACL

The Postgres role used by SP07 Hermes specialists has SELECT grants on
an **explicit allowlist**; everything else is denied at connect-time.

**ALLOWED (methodology + market data, no PII):**

- `atlas_signal_calls`
- `atlas_scorecard_daily`
- `atlas_cell_definitions`
- `atlas_cell_walkforward_runs`
- `atlas_regime_daily`
- `atlas_drift_status`
- `de_corporate_actions`
- `de_news_events`
- `de_equity_ohlcv`
- `de_index_prices`
- `atlas_ledger_public` (a view over `atlas_ledger` that exposes
  `signal_call_id`, `realized_excess`, `realized_at` only — hides
  `drift_z` and `status` to keep internal monitoring out of briefs)

**DENIED (must NEVER appear in any grant to this role):**

- `atlas_paper_portfolio`, `atlas_user_lots`, `auth.users`,
  `atlas_feature_flags` — all user-scoped / PII
- `atlas_brief_cache` — agent does not read its own outputs
- `pg_*` system catalogs, `information_schema.tables` beyond the
  allowlist — schema introspection is recon for prompt injection
- `atlas_ledger` base table (only the public view) — drift_z + status
  are internal monitoring

**Defense in depth — enforce at TWO layers:**

1. **Postgres `GRANT SELECT ON {allowlist} TO atlas_agent_readonly`** —
   the load-bearing defense. Even a compromised agent process cannot
   read outside the grants.
2. **Application-layer SQL parse + allowlist check** in
   `atlas.db.agent_session()` — every query is parsed (sqlparse or
   sqlglot); referenced tables must be in the same allowlist hardcoded
   in the module. Catches accidental schema additions.

Resolved 2026-05-24 in /grill-with-docs Q9.

---

## Migration chain (v5 → v6 cutover)

**Path A locked** — branch v6 from current `main` at migration 079;
continue the chain as 080+. v5 `atlas_*` tables (stock_state,
conviction_composite, etc.) get deprecated but kept readable. NOT
multi-head Alembic.

**Cutover timeline:**

| Moment | What happens to v5 tables |
|---|---|
| Phase 4 ship (v6 decisions cron live) | v5 daily cron continues writing in parallel; both sources of truth coexist for data-consistency QA |
| **Phase 6 internal alpha** | v5 daily cron **STOPS**; v6 is the sole writer; v5 tables remain readable |
| **Phase 6 public launch** (post-SEBI cert) | v5 tables become **READ-ONLY** (REVOKE INSERT/UPDATE/DELETE on the v5 schema role); v5 frontend retired |
| **+6 months from public launch** | v5 tables **EXPORTED to `s3://atlas-archive/v5/` as parquet**, then **DROPPED** in a single migration |

Why 6 months: matches the Phase 5 live-ledger warmup. By month 6, v6 has
its own historical record; v5 is no longer load-bearing as a fallback.
SEBI RA registration archival requirement (Phase 0.5i) is satisfied by
the S3 parquet export, which is queryable on demand via Athena or
DuckDB.

`de_*` raw data tables are preserved as-is and never deprecated — they
remain the canonical OHLCV / corp-action / index source for both
streams.

Resolved 2026-05-24 in /grill-with-docs Q10.

---

## cap_tier (point-in-time semantics)

`cap_tier` is a **daily-computed** column on `atlas_scorecard_daily`
derived from trailing-60d median traded value at date T. The methodology
lock's "trailing-60d traded value terciles (Small/Mid/Large)" is applied
fresh each day.

**Position binding rule:** the cell rule a position triggered into is
the rule that governs its exit. A stock that drifts Mid→Large
mid-position **still exits** per the rule of the cell it triggered
into (i.e., a "Mid Pullback @ 12m" position exits per the Mid Pullback
exit conditions, even if the stock has since crossed into the Large
tier). This avoids cell-flip thrash from tier drift.

`atlas_signal_calls.cell_id` is the contract; the scorecard's current
`cap_tier` is just a feature snapshot.

Resolved 2026-05-24 in /grill-with-docs Q11 (D3).

---

## Friction model granularity

Friction coefficients are **per-tier** (Small / Mid / Large), NOT
per-instrument. Stored in `atlas_friction_params` (one row per tier per
component: bid-ask, impact, brokerage, slippage). Loaded via the same
`load_thresholds()`-style API as `atlas_thresholds`.

Per-instrument calibration is rejected: overfits at n≈700, is
unmaintainable, and doesn't match the Indian retail brokerage cost
reality (which IS tier-level — small-caps have wider spreads as a
structural fact).

Resolved 2026-05-24 in /grill-with-docs Q11 (D4).

---

## MF SWITCH rule (v6 launch scope)

Mutual fund SWITCH recommendations at v6 launch are **same-category
only**. A SWITCH fires when:

1. Current fund is in **Q3 or Q4** of its category peer-quartile, AND
2. A **Q1 or Q2** fund within the **same category** is available with
   **≥6 months of consistency** in that quartile.

**Tie-break:** lowest expense ratio.

Encoded in `atlas_mf_switch_rules` config table. Cross-category
switches (e.g., Large & Mid Cap → Multi-Cap) are **deferred to v7** —
they need tax + risk-tolerance discussion that doesn't land until v7
broker integration ships real lots.

Resolved 2026-05-24 in /grill-with-docs Q11 (D5).

---

## Look-ahead audit gate

CI gate runs on every PR plus a **nightly cron on production data**.
Three checks:

1. Every feature value at date T uses only OHLCV ≤ T.
2. Every walk-forward train window ends ≥ test window start.
3. Every `atlas_signal_calls.computed_at` ≥ market close on T and
   ≤ market close on T+1 minus 1ms.

Implemented as `pytest tests/ci/test_lookahead_audit.py` for the PR
gate; nightly cron raises a PagerDuty page on any violation.

Resolved 2026-05-24 in /grill-with-docs Q11 (D6).

---

## TODOS.md proposals (T1-T9) — all approved

The 9 TODOs surfaced in eng review §07 are all approved for capture
in `docs/TODOS.md` (which Phase 0 creates per T5):

- T1 — News-event cache invalidation (v7)
- T2 — E6 per-cell calibration plot UI (Phase 5 + 6mo data)
- T3 — TS enum codegen from Pydantic Literal (Phase 2)
- T4 — Function complexity gate (`radon cc`) (Phase 1)
- T5 — Create `docs/TODOS.md` skeleton (Phase 0)
- T6 — LLM judge for golden-case eval scoring (Phase 4)
- T7 — Per-user feature flag table (Phase 6)
- T8 — MF cross-category switch rules (v7)
- T9 — E3 + E5 (broker + tax) for v7

Resolved 2026-05-24 in /grill-with-docs Q11 (D7).

---

# v6 vocabulary + discovery model (post three-model adversarial review)

Added 2026-05-24 after the Claude+Groq+Gemini three-model adversarial
review surfaced F1 (48-cell matrix misrepresented; ACCUMULATE has no
validated cell) and F2 (multi-tenure extrapolated from 6m only). The
sections below SUPERSEDE the 6-action vocabulary previously implied by
the CEO plan + design plan.

## Cell state vocabulary (canonical)

The methodology validates cells into **three discrete states**:

- **POSITIVE** — cell predicts positive forward excess (was BUY/ACCUMULATE)
- **NEUTRAL** — cell predicts neither positive nor negative; signal absent or in residual zone (was HOLD/WATCH)
- **NEGATIVE** — cell predicts negative forward excess (was TRIM/AVOID/SELL)

The UI renders the appropriate display label depending on whether the
user holds the instrument:

| Cell state | Don't own | Own |
|---|---|---|
| POSITIVE | **BUY** | **ACCUMULATE** |
| NEUTRAL | **WATCH** | **HOLD** |
| NEGATIVE | **AVOID** | **SELL** |

`SELL` replaces the prior `TRIM` label (clearer for retail users).

**Why this kills F1:** ACCUMULATE no longer needs its own validated
cell. It is the display variant of POSITIVE for holders. Same for
WATCH/HOLD (NEUTRAL) and AVOID/SELL (NEGATIVE). The methodology
validates 3 categorical states per (cap_tier × tenure); the UI does
the ownership-aware rendering. This matches the v1-v5 failure mode in
reverse — methodology backs every label.

**Schema impact:** `atlas_signal_calls.action` enum collapses to
`('POSITIVE', 'NEUTRAL', 'NEGATIVE')`. Display label rendered in the
API layer at `/v1/recommendation/{iid}` based on the requesting user's
`atlas_paper_portfolio` or `atlas_user_lots` ownership state.

## 24-framework discovery model

Phase 0.5g is **NOT** "run existing rules at new tenures and see what
passes". It is **24 independent feature-discovery exercises** — one
per (cap_tier × tenure × actionable_state) where actionable_state is
POSITIVE or NEGATIVE (NEUTRAL is the residual, not a separate
discovery).

**The matrix to fill:**

|       | 1m POS | 1m NEG | 3m POS | 3m NEG | 6m POS | 6m NEG | 12m POS | 12m NEG |
|---|---|---|---|---|---|---|---|---|
| **Large** | discover | discover | discover | discover | partial (Phase 3e) | discover | discover | discover |
| **Mid** | discover | discover | discover | discover | ✓ Pullback | ✓ Severely Broken | ✓ Pullback | ✓ Severely Broken |
| **Small** | discover | discover | discover | discover | ✓ Pullback | discover | ✓ Pullback | discover |

≈18-20 of the 24 (cap × tenure × actionable state) cells need real
feature-discovery work (the same methodology that produced Mid Pullback
@ 12m at 75.2% TP and Mid Severely Broken @ 12m at 84.6% TN).

**Each cell discovery follows methodology lock principle 1**
(pre-register the bar before computing) and produces:
- Feature set (may differ from the 29-feature library; expansion
  allowed where data demands)
- Entry condition (analogous to "Pullback" or "Severely Broken")
- Walk-forward IC + TP/TN + percentile distribution
- Friction-adjusted excess

**Per-tenure IC floor (literature-backed):**

| Tenure | IC floor | Notes |
|---|---|---|
| 6m | ≥ 0.05 | Locked methodology bar; peak signal |
| 12m | ≥ 0.04 | Lock notes "decays at 12m"; Asness/Israelov 2020 |
| 3m | ≥ 0.04 | Intermediate horizon decay |
| 1m | ≥ 0.02 | Literature on monthly cross-sectional returns; honest floor |

Cells failing per-tenure floor → marked `no_conviction` and rendered
in UI as "insufficient validation — no recommendation available" for
that (cap_tier, tenure, state). NOT a fake recommendation.

**Discovery cadence:** semi-parallel. 1m discovery runs across all 3
caps in parallel, then 3m, then 12m for cells where 6m is already
done. Lets feature-space learnings propagate forward.

**Feature space expansion:** each discovery may propose feature
additions to the library. Additions require maintainer sign-off and
walk-forward validation on the candidate feature alone (avoid
feature-set contamination from in-sample fitting).

Locked 2026-05-24 post three-model adversarial review (F2 structural
remediation).

## Continuous self-improvement workstream

A new module — `atlas/discovery/continuous/` — runs nightly post-Phase 5
ledger ship, doing **detection-only** continuous self-validation. This
is the structural answer to "the system constantly checks if those
variables/metrics are making sense."

**Nightly cron does:**

1. **Per-cell IC stability:** recompute IC on rolling windows; flag
   cells where IC has decayed beyond a per-tenure stability bar
2. **Per-feature stability:** recompute feature-level IC contribution;
   flag features whose contribution has weakened
3. **Candidate feature scanning:** scan an expansion library + recent
   literature additions for candidate features that may improve cell
   X; rank by potential lift
4. **Weekly report:** generates a maintainer report flagging cells
   where features may need re-discovery + candidate feature additions
   ranked by lift potential

**Governance (detection-only mode B per /grill final):**

- System **proposes**, maintainer **decides**. No autonomous rule
  changes. Matches N1=B single-maintainer methodology-lock governance.
- Rule updates are PRs requiring maintainer review + walk-forward
  re-validation before merge.
- Detection-only mode keeps human in the loop on every load-bearing
  methodology change.

**Output:** `atlas_continuous_improvement_proposals` table with
`(cell_id, proposal_type, candidate_feature_id, expected_lift,
walk_forward_evidence, status)`. UI surface at `/admin/methodology/
proposals` for maintainer review.

**Cadence:** nightly compute; weekly summary; reviewed by maintainer
within 1 week of proposal. Stale proposals (>30 days unaddressed)
auto-expire.

**Why this is in v6 (not v7):** the user explicitly asked for the
engine to "automatically work to make sure attributes are constantly
getting measured and improved." Without this workstream, v6 is a
static snapshot of the methodology rather than a living system.

Locked 2026-05-24 post three-model adversarial review (F2 structural
remediation + user clarification on continuous-improvement).

## Data lineage + provenance

Adversarial review G1 (Groq) + Gemini P3 surfaced the absence of any
versioned data snapshot or provenance log. Required for auditability,
reproducibility, and SEBI inspection.

**Per-run provenance:** every walk-forward run, every cell validation,
every drift event records:
- Input dataset SHA256 (frozen snapshot identity)
- Universe definition SHA256 (which 727+ instruments at which date)
- Code commit SHA at execution time
- Friction parameter row IDs (from `atlas_friction_params`)
- Output table + row range produced

**Storage:** `atlas_provenance_log` (write-once; UUID PK +
foreign keys to outputs).

**Linked downstream:** every row in `atlas_cell_walkforward_runs`,
`atlas_signal_calls`, `atlas_drift_event_log`, and
`atlas_continuous_improvement_proposals` has an FK to
`atlas_provenance_log.run_id`. Anything user-facing can be traced
back to the exact code + data state that produced it.

**Versioned snapshots:** `tests/fixtures/snapshots/` parquet files are
content-addressed (filename includes SHA256). Old snapshots are never
deleted (immutable archive). New snapshots are generated by version
bump, never overwritten.

Locked 2026-05-24 post three-model adversarial review (G1 + P3).

## LLM factuality guard (replaces keyword-only SEBI guard)

Adversarial review G2 + Gemini P4 flagged that the existing SP07 SEBI
guard is a keyword filter only — it catches recommendation language
but does not verify factual claims in the brief (cell name, confidence
%, predicted excess, regime, ticker references).

**Replacement architecture:**

1. **Constrained generation:** brief generator receives a JSON
   skeleton with locked fields (cell_id, confidence_unconditional,
   stable_features, predicted_excess, regime_state_at_call). The LLM
   may only narrate ABOUT these fields; cannot generate alternative
   numeric values.
2. **Per-claim factuality check:** post-generation, parse the brief
   for numeric claims (X%, +Y%, dates, ticker names). Verify each
   against `atlas_cell_walkforward_runs` and `atlas_ledger_public`
   data joined via `signal_call_id`. Any mismatch = brief rejected.
3. **Hallucinated entity check:** any ticker symbol mentioned must
   appear in `atlas_universe_snapshot` at the call date. Any non-listed
   ticker = brief rejected.
4. **SEBI keyword guard:** retained as final layer.
5. **Fallback:** on any rejection, serve the deterministic template
   brief (assembled from `stable_features` + cell metadata; no LLM).
   Cache the fallback with shorter TTL (1h) so retry happens sooner.

**Governance:** factuality-check failures logged to
`atlas_brief_factuality_log` with `(signal_call_id, brief_text,
claim, claim_evidence_check_result, fallback_served)`. Weekly review.

Locked 2026-05-24 post three-model adversarial review (G2 + P4).

## Named secondary maintainer (regulatory continuity)

Adversarial review F7 surfaced that N1=B accepted single-maintainer
risk is also a regulatory continuity risk under SEBI RA registration.
Bus-factor 1 on a regulator-sensitive auto-deprecating cron system is
a regulatory liability, not just a personnel risk.

**Required before public launch:**

- **Named secondary maintainer** designated in writing with documented
  authority to:
  - Pause any v6 cron job (decision engine, ledger, drift detector,
    continuous-improvement)
  - Clear `drift_status='drift_warn'` or set/unset
    `atlas_cell_definitions.deprecated_at`
  - Communicate with SEBI compliance contact + issue user-facing
    disclosures
- **Compliance binder** documenting escalation protocol, SEBI contact,
  authority chain.
- **Documented in `docs/v6/compliance-binder.html`** before Phase 6
  public launch.

**Activation conditions for secondary authority:**

- Primary unresponsive to PagerDuty for >72 hours, OR
- Primary explicitly invokes secondary (sick leave, vacation), OR
- SEBI inquiry requiring response within compliance SLA

The secondary need not be the methodology-lock author (N1=B accepted
covers that single-maintainer methodology risk). The secondary holds
**operational authority** for the live system, not methodology
authorship.

Locked 2026-05-24 post three-model adversarial review (F7).


---

# Post-scoped-re-review additions (2026-05-24)

The scoped re-review of the 12 R-revisions returned SHIP WITH CONDITIONS,
listing 5 must-close-before-build findings. These additions close them.

## Maintainer-load cap

The continuous-improvement workstream (R6) + drift advisory triage (R3) +
corp-action anomaly triage (R8) + factuality fallback review (R10) + legal
opinion refresh (R5) all land on one named maintainer. Without a cap,
governance becomes theater.

**Hard caps (auto-pause when hit):**

- `atlas_continuous_improvement_proposals` open count > 10 → discovery
  cron pauses until count drops; new candidate-feature scans skipped
- `atlas_drift_event_log` open `drift_warn` count > 5 → drift monitor
  pages compliance contact; no new flags raised
- `atlas_brief_factuality_log` rejection rate > 20%/day → factuality guard
  defaults to deterministic-fallback for 24h while LLM prompt is reviewed

**Per-category time budget:** maintainer ≤ 4 hours/week on combined
v6 triage. Anything beyond auto-pauses the responsible cron.

Locked 2026-05-24 post scoped re-review (finding 1).

## Null-distribution baseline for IC floors

Per-tenure IC floors (6m≥0.05, 12m≥0.04, 3m≥0.04, 1m≥0.02) were declared
from literature, not derived from this universe's null distribution. The
scoped re-review (finding 3) flagged that random features can clear ≥0.02
IC on a 727-stock universe over 5 years more often than expected.

**Revised methodology — Phase 0.5g-pre runs before any cell-validation:**

1. Generate N=1000 random feature sets (same dimensionality as candidate
   features; preserve autocorrelation via block-bootstrap on dates)
2. Compute walk-forward IC for each random feature set at each tenure
3. Per-tenure null distribution = empirical CDF of those 1000 ICs
4. **Per-tenure IC floor = max(literature floor, 95th percentile of null
   distribution)**

Cells must clear BOTH bars to be validated. This makes the floor a real
discriminator, not a rubber stamp.

Locked 2026-05-24 post scoped re-review (finding 3).

## Methodology freeze rule

The scoped re-review (finding 4) flagged that R2 allows feature library
expansion during discovery while R6 continuously proposes new features —
without an explicit freeze, the OOS becomes IS through the back door.

**Freeze gate:**

- **Pre-cell-validation freeze (2021+ walk-forward):** once any cell
  enters the 2021+ walk-forward window, no new features may be added to
  that cell's feature library. The cell ships against the frozen feature
  set.
- **Continuous-improvement proposals during freeze:** queue into
  `atlas_continuous_improvement_proposals` with status `queued_for_next_retrain`.
  They do NOT modify active cells.
- **Quarterly retraining window:** every 90 days, frozen cells become
  eligible for proposed feature additions. Each addition triggers full
  walk-forward re-validation on a NEW disjoint OOS window (carved from
  most recent data). If passing, the cell is re-locked with new feature
  set; if not, the proposal is rejected.

This breaks the in-sample-via-back-door pathway and gives continuous
improvement an honest cadence.

Locked 2026-05-24 post scoped re-review (finding 4).

## Drift UI surface (24h propagation — option B5a)

The scoped re-review (finding 5) flagged that R3's advisory drift mode
has no user-facing surface. Silent drift on the user's recommendation
card is misrepresentation by omission.

**Resolution: 24-hour propagation to user UI.**

Within 24 hours of `drift_status='drift_warn'` being set on a cell, every
scorecard card that renders that cell's signal must display the
drift-warn variant treatment (per design plan §02 + post-adversarial
addendum):

> Drift flagged · maintainer reviewing  
> *This cell's realized excess is diverging from its locked prediction.
> Methodology team is reviewing. Position remains open; no automatic
> action.*

Universe page filters surface `drift_warn` cells with the same chip on
each row. Cells that exit drift_warn (cleared by maintainer) lose the
variant immediately on next page load.

This makes the trust loop two-way: the system's self-doubt is visible
to the user, not hidden until exit.

Locked 2026-05-24 post scoped re-review (finding 5).

## User research / WTP gating (F11 promoted from "noted but not blocking")

The scoped re-review (finding 9) flagged that running 20 interviews + WTP
survey *parallel to* Phase 0.5 means building for months before knowing
anyone wants this. Negative WTP at month 3 of Phase 0.5 burns the runway.

**Revised sequencing:**

User research + WTP survey now runs as **Phase 0.5-pre** — gates Phase 0.5g
(the 24-framework discovery, the longest workstream). Phases 0.5a (large-cap fix),
0.5b (survivorship), 0.5c (2015-2020 walk-forward), 0.5d (friction),
0.5h-prime (regime thresholds), 0.5i (SEBI legal), 0.5j (corp-action class)
can still proceed in parallel — they have value regardless of WTP outcome
(infrastructure + legal + data quality work that survives any scope pivot).

**WTP gate criterion:**

- ≥ 15 of 20 target-persona interviews completed
- ≥ 60% of interviewed users report willingness-to-pay ≥ ₹500/year for
  the v6 value proposition
- Documented in `~/.gstack/projects/atlas-os/user-research/2026-MM-DD-wtp-report.html`

If gate fails: pause Phase 0.5g; revisit v6 scope (lighter MF-focused
product? Premium-tier B2B? Free with affiliate model?) with CEO before
investing the 24-framework discovery effort.

Locked 2026-05-24 post scoped re-review (finding 9).

