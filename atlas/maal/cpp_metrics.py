"""The figures Atlas MIRRORS from CPP, and the two rules that govern them. Pure.

Atlas computes none of these. CPP (clients.jslwealth.in) already stores every one,
reconciled to the client's official PMS statement, and two systems computing the same
number always drift — one computing and one copying cannot. So this module holds the
LIST of what gets copied and the comparison that proves the copy is faithful; it holds
no arithmetic that produces a return.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

# Every figure the board renders for a MaaL book, in cpp_risk_metrics' own names.
#
# This tuple is the definition of "every MaaL figure Atlas displays": the DDL builds
# its columns from it, the sync copies it, and the nightly gate compares it. Adding a
# figure to a page without adding it here means it is displayed but never reconciled —
# which is exactly the state the 4,975% return lived in.
#
# `absolute_return` is the headline. It is CPP's Modified-Dietz "Adjusted Return
# [Weighted] %" (risk_engine.py ~line 420), the number the client's statement carries,
# and it equals return_inception in every row — so only one of the two is copied.
COPIED_FIELDS: tuple[str, ...] = (
    "absolute_return",
    "cagr",
    "xirr",
    "return_1m",
    "return_3m",
    "return_6m",
    "return_1y",
    "bench_return_inception",
    "bench_return_1m",
    "bench_return_3m",
    "bench_return_6m",
    "bench_return_1y",
    "max_drawdown",
    "volatility",
    "sharpe_ratio",
    "sortino_ratio",
    "alpha",
    "beta",
)

# The board renders 2dp; CPP stores 4dp. Half of the last displayed digit is the widest
# gap that cannot change what a client reads, so anything past it is a real divergence.
ROUNDING_TOLERANCE = Decimal("0.005")

# XIRR and CAGR annualise. Under a year that extrapolation is an artefact, not a
# return: IND11 at three months old reports an XIRR of -94.51% off a -2.23% loss.
_ANNUALISATION_MIN_DAYS = 365


def annualised_allowed(age_days: int | None) -> bool:
    """True once a book is old enough for an annualised figure to mean anything.

    None is False, not an error: a book whose age we do not know is a book whose
    annualised figures we must not publish.
    """
    return age_days is not None and age_days >= _ANNUALISATION_MIN_DAYS


def mismatches(
    cpp: Mapping[str, Any],
    atlas: Mapping[str, Any],
    fields: tuple[str, ...] = COPIED_FIELDS,
    tolerance: Decimal = ROUNDING_TOLERANCE,
) -> list[str]:
    """Every field where Atlas disagrees with CPP beyond display rounding.

    A NULL on one side only is always a mismatch. CPP leaves a figure NULL when it
    genuinely has no answer (IND11 has no 6-month return at three months old), and
    letting that pass as "equal enough" is how a missing figure becomes a silent zero.
    """
    out: list[str] = []
    for f in fields:
        a, b = _missing_to_none(cpp.get(f)), _missing_to_none(atlas.get(f))
        if a is None and b is None:
            continue
        if a is None or b is None:
            out.append(f"{f}: cpp={_show(a)} atlas={_show(b)} (one side has no value)")
            continue
        delta = abs(Decimal(str(a)) - Decimal(str(b)))
        if delta > tolerance:
            out.append(f"{f}: cpp={a} atlas={b} (off by {delta})")
    return out


def _missing_to_none(v: Any) -> Any:
    """NaN is a missing value, not a number.

    Any read that lands in pandas turns SQL NULL into float NaN, and NaN is neither
    None nor equal to itself — so an unguarded comparison would call a genuinely
    absent figure "present but unequal", or worse, quietly agree with another NaN.
    CPP leaves figures NULL on purpose (IND11 has no 6-month return at three months
    old), and this is the boundary where that has to survive the trip.
    """
    return None if isinstance(v, float) and v != v else v


def _show(v: Any) -> str:
    return "NULL" if v is None else str(v)
