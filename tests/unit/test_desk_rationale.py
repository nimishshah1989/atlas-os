"""Unit tests for ``portfolio_run.desk_rationale``.

Anchored on a REAL desk order (rule #0): the NEULANDLAB buy thesis the Atlas Desk
PM wrote in atlas_foundation.desk_journal.applied. Every desk fill used to land on
portfolio_trades with a hardcoded reason of "manual" and no thesis at all — the row
said nothing about WHY an agent bought. `reason` is a CHECK-constrained kind, so the
agent's words go in the `rationale` column and this builds that text.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "foundation"))
from portfolio_run import desk_rationale

pytestmark = pytest.mark.unit

# Real PM thesis, desk_journal.applied (Atlas Desk — Conviction, NEULANDLAB buy).
REAL_THESIS = (
    "Composite 96.8 with +30.96 5‑day delta, rs_3m_n500 0.416 and price above "
    "both 50‑day and 200‑day EMAs signal strong short‑term momentum in a "
    "Risk‑On regime"
)


def stamp(thesis: str | None, conviction: object = None) -> str:
    """desk_rationale, asserted non-None — every case below supplies a thesis, so a
    None here is the failure itself rather than something to type-guard at each site."""
    out = desk_rationale(thesis, conviction)
    assert out is not None
    return out


def test_carries_thesis_and_conviction() -> None:
    out = stamp(REAL_THESIS, 4)
    assert out.startswith("c4: ")
    assert "Composite 96.8" in out


def test_conviction_renders_as_an_int_not_a_float() -> None:
    # pandas reads the journal's 1-5 int as float; "c4.0" is noise on every row.
    assert stamp(REAL_THESIS, 4.0).startswith("c4: ")


def test_conviction_omitted_when_the_pm_returns_none() -> None:
    # Every real desk order so far has conviction null — the stamp must not print "cNone".
    out = stamp(REAL_THESIS)
    assert out.startswith("Composite 96.8")
    assert "None" not in out


def test_conviction_omitted_when_pandas_yields_nan() -> None:
    # The journal backfill reads through pandas, where a missing conviction is float nan,
    # which is not None and not "" — this slipped past a naive emptiness check.
    assert "nan" not in stamp(REAL_THESIS, float("nan"))


def test_truncates_so_one_thesis_cannot_dominate_the_row() -> None:
    out = stamp(REAL_THESIS * 5, 3)
    assert len(out) <= 500 + len("c3: ")
    assert out.endswith("...")


def test_returns_none_without_a_thesis() -> None:
    # A booking must never be dropped just because the agent returned no thesis.
    assert desk_rationale(None) is None
    assert desk_rationale("") is None


def test_collapses_whitespace_so_the_row_stays_one_line() -> None:
    assert desk_rationale("multi\n  line\tthesis", 2) == "c2: multi line thesis"
