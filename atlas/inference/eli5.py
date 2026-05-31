"""Template-based ELI5 explanations for CellRule rows.

Pure function that translates a (CellRule, cap_tier, tenure, action)
tuple into a <=200-character human-readable explanation. Used by both:

* :mod:`atlas.discovery.persist_cells` — emits ELI5 text into
  ``atlas_cell_rule_candidates.eli5``.
* :mod:`atlas.inference.conviction_tape` — propagates ELI5 into the
  per-instrument daily verdict row.

The template library is keyed on the candidate's archetype (rule_dsl
notes carry the archetype name). Unknown archetypes fall back to a
generic descriptive sentence.

All templates render in <=200 chars; the renderer truncates to 200 if a
template + substitution somehow exceeds the budget (defensive — no
template should be that long, but the column is bounded).
"""

from __future__ import annotations

from atlas.decisions.rule_dsl import CellRule

_MAX_ELI5_LEN = 200

# Per-archetype template library. Templates may use the {cap_tier} and
# {tenure} placeholders. Direction (POSITIVE / NEGATIVE) is encoded by
# the archetype itself — POSITIVE archetypes never appear under a NEGATIVE
# action and vice versa (per atlas.discovery.deep_search_candidates).
_TEMPLATES: dict[str, str] = {
    # ---- POSITIVE archetypes -------------------------------------------------
    "mean_reversion": (
        "Pulled back from highs but still a {cap_tier}-cap leader — buyable "
        "dip in a strong stock over {tenure}."
    ),
    "deep_value": (
        "Battered {cap_tier}-cap with a clearing setup — high-conviction "
        "deep-value re-rate window of {tenure}."
    ),
    "quality_momentum": (
        "Consistent {cap_tier}-cap leaders with low volatility — quietly "
        "compounding winners over {tenure}."
    ),
    "inflection": (
        "Trend just inflected upward on a {cap_tier}-cap — early-stage "
        "momentum with {tenure} runway."
    ),
    "consolidation_breakout": (
        "{cap_tier}-cap broke out of a tight base on volume — clean breakout setup for {tenure}."
    ),
    "liquidity_expansion": (
        "Volume regime is expanding on a {cap_tier}-cap with positive RS — "
        "institutional accumulation visible over {tenure}."
    ),
    "structural": (
        "Long-duration {cap_tier}-cap winner — structural compounder thesis with {tenure} horizon."
    ),
    "low_vol_carry": (
        "Low-vol {cap_tier}-cap with positive carry — risk-adjusted alpha over {tenure}."
    ),
    "breakout_with_pullback": (
        "Broke out then pulled back to support on a {cap_tier}-cap — high-"
        "probability second-leg entry for {tenure}."
    ),
    "sector_relative_leadership": (
        "Top-ranked {cap_tier}-cap inside the strongest sector with broad "
        "participation — sustained outperformance over {tenure}."
    ),
    "bab_low_beta": (
        "Low-beta {cap_tier}-cap survivor with positive momentum — risk-"
        "adjusted alpha over {tenure}."
    ),
    "liquidity_thrust_mfi": (
        "Money Flow Index thrust on a {cap_tier}-cap — strong buying pressure over {tenure}."
    ),
    "obv_thrust": (
        "On-Balance Volume thrust on a {cap_tier}-cap — accumulation "
        "footprint visible over {tenure}."
    ),
    # ---- NEGATIVE archetypes -------------------------------------------------
    "mean_reversion_overbought": (
        "{cap_tier}-cap extended above its mean and showing reversal "
        "signs — likely fade over {tenure}."
    ),
    "distribution": (
        "Distribution footprint on a {cap_tier}-cap — large players "
        "exiting; drift lower likely over {tenure}."
    ),
    "volatility_spike": (
        "Volatility regime expanding on a {cap_tier}-cap with deteriorating "
        "RS — distribution signal over {tenure}."
    ),
    "breakdown": (
        "{cap_tier}-cap broke down through key support on volume — trend "
        "damage with {tenure} downside risk."
    ),
    "deep_value_avoid": (
        "Battered {cap_tier}-cap with still-negative RS and no inflection — "
        "value trap risk over {tenure}."
    ),
    "weak_quality": (
        "{cap_tier}-cap with elevated downside volatility and weak RS — "
        "low-quality drift over {tenure}."
    ),
    "overextension": (
        "{cap_tier}-cap over-extended on every dimension — mean reversion risk over {tenure}."
    ),
    "sector_drag": (
        "{cap_tier}-cap inside a weak sector with elevated vol — sector-"
        "drag headwind over {tenure}."
    ),
    "sector_breakdown": (
        "Top-ranked {cap_tier}-cap inside a now-failing sector — bull-"
        "trap pattern with {tenure} downside."
    ),
    "bab_high_beta_short": (
        "High-beta {cap_tier}-cap with deteriorating RS — leveraged downside over {tenure}."
    ),
    "mfi_overbought_distrib": (
        "Money Flow Index overbought with distribution on a {cap_tier}-cap "
        "— exhaustion signal over {tenure}."
    ),
    "obv_divergence_neg": (
        "Negative OBV divergence on a {cap_tier}-cap — accumulation "
        "rolling over; drift lower over {tenure}."
    ),
}


def _archetype_from_rule(rule: CellRule) -> str:
    """Extract the archetype from a CellRule.notes blob.

    Conviction-tape ELI5 is generated AFTER persist_cells has stamped the
    notes string in the form ``... | archetype=<name> | ...``.  Parse it
    out so the template lookup keys cleanly.
    """
    notes = rule.notes or ""
    for token in notes.split(" | "):
        if token.startswith("archetype="):
            return token.removeprefix("archetype=").strip()
    return ""


def eli5(
    rule: CellRule,
    cap_tier: str,
    tenure: str,
    action: str,
) -> str:
    """Render a <=200-char ELI5 string for a CellRule.

    Args:
        rule: the CellRule to explain.
        cap_tier: "Large" / "Mid" / "Small".
        tenure: "1m" / "3m" / "6m" / "12m".
        action: "POSITIVE" / "NEUTRAL" / "NEGATIVE".

    Returns:
        Human-readable explanation, truncated to 200 chars.
    """
    archetype = _archetype_from_rule(rule)
    template = _TEMPLATES.get(archetype)
    if template is None:
        # Generic fallback — preserves rule_type identity for downstream callers.
        rendered = (
            f"{archetype or rule.rule_type} signal at {tenure} for "
            f"{cap_tier} caps ({action.lower()}) — see rule details for math."
        )
    else:
        rendered = template.format(cap_tier=cap_tier, tenure=tenure)

    if len(rendered) > _MAX_ELI5_LEN:
        rendered = rendered[: _MAX_ELI5_LEN - 1] + "…"
    return rendered


__all__ = ["eli5"]
