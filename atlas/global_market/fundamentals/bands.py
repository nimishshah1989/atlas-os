"""The 37 US fundamental bands, derived from the S&P 500's own cross-section.

WHY THIS EXISTS. ``atlas.lenses.compute.fundamental`` scores a company by where it sits on a
ladder: ROE at or above ``prof_roe_high`` earns eleven points, above ``prof_roe_good`` nine, and
so on. India's ladder starts at ROE 20 because that is where India's index sits. Applied to the
S&P 500 it is not merely wrong, it is uninformative in a specific direction — a ladder whose
rungs are all below the population puts every name on the top rung and the sub-score stops
discriminating, which reads on the board as "these companies are all excellent" rather than as
"this measure has been switched off".

SO THE RUNGS ARE THE POPULATION'S OWN PERCENTILES. ``prof_roe_high`` is the S&P 500's 90th
percentile ROE on the day it is set; ``prof_roe_ok`` its median. That is a DERIVED number under
rule #0 — computed by a stated formula over the real assembled filings in
``atlas_global.stock_financials_pit``, never typed in — and it is a methodology PARAMETER, so it
lands in ``atlas_global.atlas_thresholds`` (rule #1) where the FM edits it from
``/admin/thresholds``. plan.md §B says exactly this: "seeded from the actual S&P 500
cross-sectional quartiles on the first run, not India's numbers".

Seeding, never overwriting. A band the FM has tuned is his; this only fills a key the table has
never carried.

THE DIRECTION IS THE TRAP. For ROE the best rung is the HIGHEST value, so ``prof_roe_high``
takes P90. For debt/equity the best rung is the LOWEST value, so ``bs_de_low`` — the rung a
company clears by borrowing least — takes P25 and ``bs_de_high`` takes P90. The names run the
same way (low → high) in both families while the QUALITY they denote runs opposite, which is
why every ladder below states its direction and :func:`bands_from_cross_section` asserts the
resulting values are monotone in the direction claimed.

WHAT CANNOT BE DERIVED, AND WHY IT IS SAID OUT LOUD. ``bs_qr_{ok,good,high}`` grade a QUICK
ratio, which needs inventory; ``stock_financials_pit`` carries none, so ``Metrics`` has no
``quick_ratio`` field and India's balance-sheet sub-score skips the rung entirely. Three bands
nothing can read are not derived here and are not required by the scorer's gate — see
``stock_lenses.REACHABLE_KEYS``, and the test that ties that exclusion to the missing input so
the day inventory lands, the keys come back.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

import pandas as pd

__all__ = ["DERIVED_KEYS", "LADDERS", "bands_from_cross_section"]

Direction = Literal["higher_is_better", "lower_is_better"]

# (metric, direction, ((threshold key, percentile), … best rung first)).
#
# The metric names are ``cross_section.LENS_METRICS``' and the values are that table's, which
# means the six rates arrive already in PER CENT (cross_section multiplies a fraction by 100)
# and the ratios as plain multiples — exactly the units India's scorer compares against.
LADDERS: tuple[tuple[str, Direction, tuple[tuple[str, int], ...]], ...] = (
    # ── profitability: four rungs on ROE and ROCE, two on net margin ──
    (
        "roe",
        "higher_is_better",
        (("prof_roe_high", 90), ("prof_roe_good", 75), ("prof_roe_ok", 50), ("prof_roe_low", 25)),
    ),
    (
        "roce",
        "higher_is_better",
        (
            ("prof_roce_high", 90),
            ("prof_roce_good", 75),
            ("prof_roce_ok", 50),
            ("prof_roce_low", 25),
        ),
    ),
    ("net_margin", "higher_is_better", (("prof_nm_high", 90), ("prof_nm_ok", 50))),
    # ── margin ──
    (
        "operating_margin",
        "higher_is_better",
        (
            ("margin_op_high", 90),
            ("margin_op_good", 75),
            ("margin_op_ok", 50),
            ("margin_op_low", 25),
        ),
    ),
    (
        "net_margin",
        "higher_is_better",
        (("margin_net_high", 90), ("margin_net_good", 75), ("margin_net_ok", 50)),
    ),
    # ── growth ──
    (
        "revenue_growth",
        "higher_is_better",
        (("growth_rev_high", 90), ("growth_rev_good", 75), ("growth_rev_ok", 50)),
    ),
    (
        "eps_growth",
        "higher_is_better",
        (("growth_eps_high", 90), ("growth_eps_good", 75), ("growth_eps_ok", 50)),
    ),
    # ── balance sheet. Debt/equity is the inverted one: `bs_de_low` is the BEST rung, which is
    #    the LOWEST value, so it takes the 25th percentile and `bs_de_high` the 90th.
    (
        "debt_to_equity",
        "lower_is_better",
        (("bs_de_low", 25), ("bs_de_ok", 50), ("bs_de_med", 75), ("bs_de_high", 90)),
    ),
    (
        "current_ratio",
        "higher_is_better",
        (("bs_cr_high", 90), ("bs_cr_good", 75), ("bs_cr_ok", 50)),
    ),
    # ── operating leverage: four single-rung tests rather than a ladder. "High growth" is the
    #    top quartile of revenue growth, "moderate" the median, "expanding margin" the top
    #    quartile of operating margin, and "low debt" the bottom quartile of debt/equity.
    ("revenue_growth", "higher_is_better", (("olev_rev_high", 75), ("olev_rev_mod", 50))),
    ("operating_margin", "higher_is_better", (("olev_margin_expand", 75),)),
    ("debt_to_equity", "lower_is_better", (("olev_de_low", 25),)),
)

DERIVED_KEYS: frozenset[str] = frozenset(key for _m, _d, rungs in LADDERS for key, _p in rungs)


class UndeterminedBandError(Exception):
    """A rung whose percentile the cross-section could not produce.

    Raised rather than defaulted: a band silently filled with India's number is exactly the
    failure ``FUNDAMENTAL_KEYS`` exists to prevent, and a band filled with a number computed
    from an empty column is worse — it looks derived.
    """


def _percentile(table: pd.DataFrame, metric: str, percentile: int) -> Decimal | None:
    """One cell of ``cross_section``'s table, as a Decimal. ``None`` where it is empty."""
    row = table.loc[table["metric"] == metric]
    if row.empty:
        return None
    value = row.iloc[0].get(f"p{percentile}")
    if value is None or pd.isna(value):
        return None
    # Through str: the table holds floats, and Decimal(float) would carry the binary
    # representation's tail into a threshold the FM reads and edits.
    return Decimal(str(value))


def bands_from_cross_section(table: pd.DataFrame, *, min_names: int = 30) -> dict[str, Decimal]:
    """The derivable fundamental bands, from ``cross_section``'s own table.

    ``min_names`` is a floor on how many companies a metric must be reported by before its
    percentiles are used as a ladder. A 90th percentile over eleven filers is not the index's
    distribution, and a band cut from it would be a real number about the wrong population — so
    such a metric raises rather than quietly setting the market's methodology from a handful of
    names.

    Raises ``UndeterminedBandError`` naming the metric when a ladder cannot be cut. Every value
    returned is a percentile of a real assembled series, in the units India's scorer compares
    against (per cent for the rates, plain multiples for the ratios).
    """
    out: dict[str, Decimal] = {}
    for metric, direction, rungs in LADDERS:
        row = table.loc[table["metric"] == metric]
        names = 0 if row.empty else int(row.iloc[0]["names"])
        if names < min_names:
            raise UndeterminedBandError(
                f"{metric}: only {names} name(s) report it; a ladder needs at least {min_names}. "
                "Run the fundamentals ingest over more of the index, or set these bands by hand."
            )
        values: list[Decimal] = []
        for key, percentile in rungs:
            value = _percentile(table, metric, percentile)
            if value is None:
                raise UndeterminedBandError(
                    f"{metric}: no P{percentile} in the cross-section for {key}"
                )
            out[key] = value
            values.append(value)
        # The ladder must be monotone in the direction it claims, or the sub-score's if/elif
        # chain has rungs that can never be reached. Percentiles are monotone by construction,
        # so a failure here means the LADDER is declared in the wrong order — a code defect,
        # caught at the point it would otherwise become a silent scoring bug.
        ordered = values == sorted(values, reverse=direction == "higher_is_better")
        if not ordered:
            raise UndeterminedBandError(
                f"{metric}: rungs {[k for k, _ in rungs]} are not monotone {direction} — "
                f"got {values}. The ladder is declared in the wrong order."
            )
    return out


def undecidable(required: frozenset[str]) -> frozenset[str]:
    """The required bands this module cannot derive — today, the quick-ratio family, whose
    input ``stock_financials_pit`` does not carry. Callers report it rather than guessing."""
    return required - DERIVED_KEYS
