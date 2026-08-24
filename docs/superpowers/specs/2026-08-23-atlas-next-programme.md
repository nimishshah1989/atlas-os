# Atlas Next — programme sequencing

Status: **decisions locked, specs in progress** · FM sign-off 2026-08-23

Five independent projects. Each gets its own spec → plan → build cycle. This file
holds only the sequence, the locked decisions, and the cross-project constraints.

## Baseline, measured 2026-08-23 (not estimated)

| | Live |
|---|---|
| Stocks scored | **739** of 747 active (`atlas_lens_scores_daily`, 2026-08-07) |
| Stocks ingested but unscored | **1,673** inactive; **994** meet the full data floor |
| Funds ranked | **389** of 592 universe (`fund_rank_daily`) |
| Funds in master | 4,206 active — **100% Equity. Zero hybrid, zero debt.** |
| Lens score history | 1,895 dates, 2019-01-01 → 2026-08-18 |
| News / RSS | does not exist |
| NL query surface | does not exist |
| Forward-return / IC evaluation | **does not exist** |

## Sequence

| # | Project | Rationale for position |
|---|---|---|
| 1 | Stock universe 739 → 1,050 | Widest leverage; sets the universe every later project measures against |
| 2 | Funds — all Regular/Growth: **equity + hybrid** | The worst coverage number; ingestion-gated, not universe-gated |
| 3 | Contextual news → holdings | Independent, greenfield |
| 4 | "Ask anything" NL layer | Benefits most from a wide, stable base |
| 5 | Signal validation (IC / decile spread) | **Last.** Baseline gets frozen once, on the final universe |

### Why validation is last (FM decision, 2026-08-23)

Originally sequenced first. Reordered on FM instruction, and the reorder is
technically correct for a reason beyond the commercial one:

- The IC gate freezes a per-lens baseline. Freezing on 739 names then adding 311
  moves trailing IC for reasons unrelated to signal decay — the gate would fire on
  a change we caused. IC-first means freezing the baseline twice.
- Rank-IC standard error scales ~1/sqrt(N). 739 → 1,050 tightens it ~16%, and most
  where `decile_core.MIN_COHORT = 20` currently binds hardest (micro cohort).

**Accepted risk:** projects 1–4 scale a methodology whose predictive power is
unmeasured. FM is aware; scores are already read "with a pinch of salt".

**Standing offer, not taken up:** a ~1-day engine-only IC probe (no table, no gate,
no UI) over the current 739 would de-risk this without changing the sequence.

## Cross-project constraint — act in project 1, not project 5

`de_index_constituents` has **no reconstitution history**: every row is
`effective_to IS NULL` (500 live of 500 total). Today's index membership is being
applied to 2019 data. That is survivorship bias, and it will inflate any IC measured
in project 5.

Cheap to fix now (snapshot the universe daily going forward), unrecoverable if we
wait. **The universe-snapshot table is chunk 1 of project 1**, deliberately ahead of
everything else, so the history clock starts immediately.

## Locked decisions

| Decision | Choice | Where |
|---|---|---|
| Stock universe rule | **One liquidity floor**: trailing 60-day median traded value ≥ ₹2.5 cr → ~1,271 names | P1 |
| Universe history | Daily snapshot table, from day one | P1 |
| Fund scope | All **Regular / Growth**: equity + hybrid. **Debt dropped** (FM, 2026-08-23) | P2 |
| Hybrid ranking | Existing composite, ranked within category — no new methodology needed | P2 |
| Validation shape | Nightly gate + `/admin` surface | P5 |
| Validation failure mode | Baseline + ratchet — block regressions only | P5 |
| Validation scope | Stocks first, engine written universe-agnostic | P5 |

## Rejected alternatives

- **External MCP (screener.in / TradingView) as the NL data path.** Atlas already
  ingests screener.in via `ingest_screener.py`, with XBRL reconciliation at 2% on PAT
  and quarantine of divergent symbols — discipline the MCP has none of. TradingView's
  screener returns technicals Atlas computes itself (`technical_daily`, 7.0M rows).
  Routing queries through either creates two versions of every number. Project 4 is a
  semantic layer + text-to-SQL over `atlas_foundation`, not an MCP passthrough.
  *Narrow exception worth revisiting in P4:* `analyze_annual_report` /
  `analyze_earnings_call` / `analyze_red_flags` cover unstructured text Atlas has
  never ingested. That is genuinely new signal and a much smaller integration.
- **Index-union + manual add list to reach 1,050.** Maximum control, silent rot.
- **Eligibility gates on the stock universe** (OHLCV history, financials, filings).
  Measured against the current 747 it would have evicted 94 — 82 of them recent
  listings. It also duplicated `compute_composite()`'s coverage-adjusted weighting,
  which already returns NULL for a lens with no inputs. Liquidity decides membership;
  data sufficiency decides which lenses may speak, and that half already exists.
- **A debt-fund composite.** Dropped with debt itself.
- **Auto-demoting lens weights on IC decay.** A data outage looks identical to signal
  decay. Surface it; let the FM decide.

## Project 2 — unblocked by dropping debt

An earlier revision chose "ingest all, build a debt-specific composite". That needed
yield-to-maturity, modified duration, credit-quality mix and maturity profile — **none
of which exist in Atlas**. `ingest_fund_master.py` parses one field from that family
(`ARF-NetExpenseRatio`); `de_mf_holdings` has no rating or maturity columns. It would
have opened with an open-ended discovery chunk.

**Debt is dropped (FM, 2026-08-23). That blocker is gone.** Hybrid needs no new
methodology either:

- `fund_rank_core.rank_in_category()` already ranks **within category**, so each hybrid
  category forms its own peer group automatically. An aggressive hybrid is never
  compared against a pure equity fund.
- `fund_rank_core.composite()` uses the same coverage-adjusted renormalisation as
  stocks — a NULL lens does not participate.

So project 2 reduces to: widen the Morningstar MASTER universe to include hybrid, let
NAV follow (mfapi.in already carries every AMFI scheme), and let category-relative
ranking do its job.

**Carry-forward caveat.** The composite's inputs (`v_tech`, `v_fund`, `v_flow`,
`v_cat`) derive from NAV technicals plus look-through equity holdings. A
debt-dominant hybrid has little look-through equity, so `v_fund` / `v_flow` will be
thin or NULL and it will score mostly on NAV momentum. Coverage-adjusted weighting
handles that honestly, but `lenses_active` must be surfaced on the funds board so an
FM can see a two-lens score is not a six-lens score.

**Separate, still real:** only **953 of 4,206** active schemes have any NAV at all and
**441** have three years of current NAV. Widening the master does not fix that — there
is an `mstar_id → amfi_code` mapping gap underneath. Size it before writing chunks.

## Specs

- P1 — `2026-08-23-stock-universe-1050-design.md`
- P2 — unblocked; spec next
- P3, P4 — not yet started
- P5 — `2026-08-23-lens-signal-validation-design.md` (complete, shelved until P1–P4 land)
