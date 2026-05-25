"""Template-based ELI5 explanations for fund + ETF scorecard rows.

Sibling to :mod:`atlas.inference.eli5` (which covers cell-rule ELI5 for
the conviction tape). Kept separate so the cell-rule template library
doesn't grow into a kitchen-sink module — the fund/ETF scorers have
fundamentally different inputs (categories, archetypes, layer scores)
and their templates are easier to evolve in isolation.

All renderers cap output at 200 characters (the column width on the
scorecard tables). All money uses Indian formatting (lakh/crore, ₹
prefix). Numeric values are pre-formatted by the caller — these helpers
do not do float math on monetary values.
"""

from __future__ import annotations

_MAX_ELI5_LEN = 200


# ---------------------------------------------------------------------------
# ETF archetype templates (keyed on etf_category)
# ---------------------------------------------------------------------------
#
# Each template renders for a *leader* — the API surfaces the leader
# blurb when ``is_atlas_leader=TRUE``. Non-leader rows fall through to
# the generic composite-score sentence.

_ETF_ARCHETYPE_TEMPLATES: dict[str, str] = {
    "passive_broad": (
        "Top broad-index ETF — clean tracking, deep liquidity, and a "
        "fee that compounds in your favour over years."
    ),
    "passive_sector": (
        "Top sector ETF — {sector} leading on relative strength with "
        "healthy AUM and tight tracking."
    ),
    "smart_beta": (
        "Top smart-beta ETF — factor tilt is working in the current "
        "regime; cost-efficient way to lean into the style."
    ),
    "thematic": (
        "Top thematic ETF — theme momentum is sustained, liquidity is "
        "adequate, and tracking is competitive within the category."
    ),
    "commodity": (
        "Top commodity ETF — diversifier role intact, low tracking error, "
        "and AUM in a healthy bracket for entry/exit."
    ),
    "international": (
        "Top international ETF — geographic diversifier with manageable "
        "cost; suitable for non-INR exposure without forex headaches."
    ),
    "debt": (
        "Top debt ETF — duration positioning and spread look favourable; "
        "credit profile clean, expense ratio reasonable."
    ),
}


# ---------------------------------------------------------------------------
# Public ELI5 renderers
# ---------------------------------------------------------------------------


def _truncate(s: str) -> str:
    """Trim to 200 chars with an ellipsis."""
    if len(s) <= _MAX_ELI5_LEN:
        return s
    return s[: _MAX_ELI5_LEN - 1] + "…"


def _fmt_aum_cr(aum_cr: float | None) -> str:
    """Indian-currency-style AUM formatting: ₹X Cr."""
    if aum_cr is None:
        return ""
    if aum_cr >= 1.0:
        return f"₹{aum_cr:,.0f} Cr"
    # Sub-crore — show in lakh
    lakh = aum_cr * 100
    return f"₹{lakh:,.1f} L"


def _fmt_ter(ter_pct: float | None) -> str:
    if ter_pct is None:
        return ""
    return f"{ter_pct:.2f}% TER"


def eli5_etf_leader(
    category: str,
    primary_strength: str | None,
    aum_cr: float | None,
    ter_pct: float | None,
    underlying_sector: str | None = None,
) -> str:
    """Render the ELI5 string for an Atlas-Leader ETF.

    Args:
        category: etf_category enum value (broad_index, sector, ...).
        primary_strength: name of the strongest component (e.g.
            'tracking_quality', 'liquidity') — used for the generic
            fallback when category isn't in the template library.
        aum_cr: AUM in INR crore (passed through Indian-formatter).
        ter_pct: total expense ratio in percent.
        underlying_sector: sector name when category=='sector'.

    Returns:
        <=200 char human-readable string.
    """
    archetype = _category_to_archetype(category)
    sector = underlying_sector or "the underlying sector"
    template = _ETF_ARCHETYPE_TEMPLATES.get(archetype)
    if template is None:
        base = (
            f"Top {category.replace('_', ' ')} ETF — strongest on "
            f"{primary_strength or 'composite'}."
        )
    else:
        base = template.format(sector=sector)
    aum_blurb = _fmt_aum_cr(aum_cr)
    ter_blurb = _fmt_ter(ter_pct)
    suffix_bits = [b for b in (aum_blurb, ter_blurb) if b]
    if suffix_bits:
        return _truncate(f"{base} ({', '.join(suffix_bits)}).")
    return _truncate(base)


def eli5_fund_leader(
    category: str,
    sharpe: float,
    max_dd: float,
    hc_score: float,
) -> str:
    """Top-quartile MF — emphasise risk-adjusted return + holdings score.

    Args:
        category: fund_category string from the scorecard row.
        sharpe: 3y annualized Sharpe (raw float, not percentile).
        max_dd: max drawdown as a positive fraction (0.25 = 25% dd).
        hc_score: holdings_conviction_score 0-100.
    """
    base = (
        f"Top-quartile {category} over 3y — Sharpe {sharpe:.2f}, "
        f"max drawdown {max_dd:.1%}, holds {hc_score:.0f}/100 "
        f"conviction stocks."
    )
    return _truncate(base)


def eli5_fund_avoid(category: str, primary_weakness: str | None) -> str:
    """Bottom-quartile MF — call out the dominant weakness archetype.

    Args:
        category: fund_category string.
        primary_weakness: short label of the dominant weak layer
            ('risk_adjusted', 'holdings', 'cost_manager', 'style_sector').
    """
    weakness_map = {
        "risk_adjusted": "weak risk-adjusted returns vs category",
        "holdings": "low-conviction holdings overlap",
        "cost_manager": "high cost / short manager tenure",
        "style_sector": "style drift / sector tilt against the leaders",
    }
    weakness_text = weakness_map.get(primary_weakness or "", "broad underperformance vs category")
    base = (
        f"Bottom-quartile {category} — {weakness_text}. Better "
        f"alternatives exist; see top picks for this category."
    )
    return _truncate(base)


def eli5_fund_low_confidence(months_to_3y: int) -> str:
    """Fund < 3y old — set expectations: best-effort score, re-evaluate later.

    Args:
        months_to_3y: how many months until the fund has 3y track record.
                     ``<= 0`` means we have 3y but flag is set for another
                     reason (e.g. NAV history gaps).
    """
    if months_to_3y > 0:
        base = (
            f"Limited track record — composite is best-effort. "
            f"Re-evaluate in ~{months_to_3y} months when 3y history is in."
        )
    else:
        base = (
            "Limited track record — composite is best-effort. "
            "Re-evaluate as a longer history accumulates."
        )
    return _truncate(base)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _category_to_archetype(category: str) -> str:
    """Map ETF category → archetype template key."""
    if category in ("broad_index",):
        return "passive_broad"
    if category == "sector":
        return "passive_sector"
    if category == "smart_beta":
        return "smart_beta"
    if category == "thematic":
        return "thematic"
    if category == "commodity":
        return "commodity"
    if category == "international":
        return "international"
    if category == "debt":
        return "debt"
    return ""


__all__ = [
    "eli5_etf_leader",
    "eli5_fund_avoid",
    "eli5_fund_leader",
    "eli5_fund_low_confidence",
]
