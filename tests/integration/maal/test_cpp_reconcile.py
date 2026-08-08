"""The MaaL books must MIRROR clients.jslwealth.in, never recompute it.

A 4,975.1% return sat on a client page because Atlas derived a number
(``nav / initial_capital − 1``) from a placeholder corpus of Rs 1,00,000 that
``maal_ddl.sql`` itself documents as fake. Nothing objected. These tests are the
thing that objects.

Every assertion runs against REAL rows (rule #0): the synced mirror of
``cpp_risk_metrics`` and ``cpp_nav_series`` in ``atlas_foundation``, and the real
``portfolio_master`` registrations of BJ53 / BJ53IND / JR100PASS. Nothing here is
invented — where a test needs a "wrong" value to prove a comparison bites, it uses
a DIFFERENT real book's row rather than a fabricated one.

The half this file CANNOT reach is the live CPP database: ``MAAL_SOURCE_DB_URL``
exists only on the box. ``scripts/ops/maal_cpp_reconcile.py`` closes that half every
night from inside atlas_daily; what is proven here is that the mirror is served
verbatim and that no derived path can reach a client page.

Read-only against the live DB.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas.maal.cpp_metrics import COPIED_FIELDS, annualised_allowed, mismatches

pytestmark = pytest.mark.integration

BOOKS = ("leaders", "passive", "ind11")


def _rows(sql: str, params: dict | None = None) -> list[dict]:
    """Read straight through SQLAlchemy, NOT read_df.

    pandas coerces postgres numeric to float64 and SQL NULL to NaN, which would make
    these tests argue with an artefact of the reader instead of the data. The nightly
    gate reads the same way, so what is asserted here is what it will compare.
    """
    import _db  # pyright: ignore[reportMissingImports]
    from sqlalchemy import text

    with _db.engine().connect() as conn:
        return [dict(m) for m in conn.execute(text(sql), params or {}).mappings()]


@pytest.fixture(scope="module")
def stored() -> dict[str, dict]:
    """The latest synced CPP metrics row per book — the verbatim mirror."""
    rows = _rows("""
        SELECT DISTINCT ON (maal_code) *
        FROM atlas_foundation.maal_cpp_metrics
        ORDER BY maal_code, computed_date DESC
    """)
    return {r["maal_code"]: r for r in rows}


@pytest.fixture(scope="module")
def served() -> dict[str, dict]:
    """What the board actually renders — the read view, age rule already applied."""
    return {r["maal_code"]: r for r in _rows("SELECT * FROM atlas_foundation.maal_book_metrics")}


# ── The mirror exists and is complete ────────────────────────────────────────


def test_every_cpp_book_has_a_synced_metrics_row(stored: dict[str, dict]) -> None:
    assert set(stored) == set(BOOKS), (
        f"missing CPP metrics for {sorted(set(BOOKS) - set(stored))} — the board would "
        f"render a return with no source behind it"
    )


def test_the_view_serves_the_stored_figures_verbatim(
    stored: dict[str, dict], served: dict[str, dict]
) -> None:
    """Copying is the whole design: the served value IS the stored value, untouched.

    ``cagr`` and ``xirr`` are the deliberate exception — the age rule may withhold
    them — and are asserted separately below.
    """
    withheld = {"cagr", "xirr"}
    for code in BOOKS:
        for field in COPIED_FIELDS:
            if field in withheld:
                continue
            assert served[code][field] == stored[code][field], (
                f"{code}.{field}: the view transformed a CPP figure "
                f"({stored[code][field]} -> {served[code][field]})"
            )


# ── The annualisation rule (FM): XIRR/CAGR only past one year ────────────────


def test_a_book_under_a_year_old_serves_no_annualised_figure(
    stored: dict[str, dict], served: dict[str, dict]
) -> None:
    """IND11 is ~3 months old and CPP reports XIRR −94.51% — an artefact, not a return."""
    young = [c for c in BOOKS if not annualised_allowed(stored[c]["age_days"])]
    assert young, "no book under a year old — this rule needs a real young book to bite on"
    for code in young:
        assert stored[code]["xirr"] is not None, (
            f"{code}: CPP has no XIRR to withhold, so this proves nothing"
        )
        assert served[code]["xirr"] is None, (
            f"{code} is {stored[code]['age_days']} days old and served an XIRR of "
            f"{served[code]['xirr']}% — an annualisation artefact reached a client page"
        )
        assert served[code]["cagr"] is None, f"{code} served a CAGR at {stored[code]['age_days']}d"


def test_a_book_under_a_year_old_still_serves_its_period_returns(
    stored: dict[str, dict], served: dict[str, dict]
) -> None:
    """Withholding the artefact must not leave the card blank — 1m/3m/6m stand in."""
    for code in (c for c in BOOKS if not annualised_allowed(stored[c]["age_days"])):
        periods = [served[code][f] for f in ("return_1m", "return_3m", "return_6m")]
        assert any(p is not None for p in periods), (
            f"{code}: annualised figures withheld and no period return offered instead"
        )
        assert served[code]["absolute_return"] is not None


def test_a_book_past_a_year_serves_its_annualised_figures(
    stored: dict[str, dict], served: dict[str, dict]
) -> None:
    mature = [c for c in BOOKS if annualised_allowed(stored[c]["age_days"])]
    assert mature, "no book past a year old — this rule needs a real mature book"
    for code in mature:
        assert served[code]["xirr"] == stored[code]["xirr"]
        assert served[code]["cagr"] == stored[code]["cagr"]


def test_the_age_rule_turns_over_at_exactly_one_year() -> None:
    assert annualised_allowed(364) is False
    assert annualised_allowed(365) is True
    assert annualised_allowed(None) is False


# ── No derived return can reach a CPP book ───────────────────────────────────


def test_cpp_books_take_their_since_inception_from_cpp_not_from_initial_capital(
    served: dict[str, dict],
) -> None:
    """The exact expression /portfolios renders, run against the real registrations.

    ``initial_capital`` is a CHECK-satisfying placeholder for these three books. If
    the served number ever equals the placeholder-derived one again, that is the
    4,975% bug back.
    """
    rows = _rows("""
        SELECT m.params->>'maal_code' AS maal_code,
               m.initial_capital,
               ln.nav,
               CASE WHEN m.params->>'source' = 'cpp' THEN cm.absolute_return
                    ELSE (ln.nav / nullif(m.initial_capital, 0) - 1) * 100
               END AS since_inception_pct
        FROM atlas_foundation.portfolio_master m
        LEFT JOIN atlas_foundation.maal_book_metrics cm ON cm.maal_code = m.params->>'maal_code'
        LEFT JOIN LATERAL (
          SELECT nav FROM atlas_foundation.portfolio_nav_daily n
          WHERE n.portfolio_id = m.portfolio_id AND n.run_type = 'live'
          ORDER BY date DESC LIMIT 1
        ) ln ON true
        WHERE m.params->>'source' = 'cpp'
    """)
    assert len(rows) == 3, f"expected the 3 registered CPP books, found {len(rows)}"
    for r in rows:
        code = r["maal_code"]
        assert r["since_inception_pct"] == served[code]["absolute_return"], (
            f"{code}: /portfolios would render {r['since_inception_pct']}%, CPP says "
            f"{served[code]['absolute_return']}%"
        )
        derived = (Decimal(str(r["nav"])) / Decimal(str(r["initial_capital"])) - 1) * 100
        assert abs(Decimal(str(r["since_inception_pct"])) - derived) > 1, (
            f"{code}: the served return still tracks nav/initial_capital ({derived:.1f}%)"
        )


# ── The NAV history is whole ─────────────────────────────────────────────────


def test_the_nav_mirror_carries_the_whole_history_not_just_the_last_point() -> None:
    """Charts showed 4 points across 6 years because the sync kept only nav[0]."""
    rows = _rows("""
        SELECT maal_code, count(*) AS points, min(nav_date) AS first, max(nav_date) AS last
        FROM atlas_foundation.maal_cpp_nav GROUP BY maal_code
    """)
    by_code = {r["maal_code"]: r for r in rows}
    assert set(by_code) == set(BOOKS), f"NAV mirror missing books: {set(BOOKS) - set(by_code)}"

    inception = {
        r["maal_code"]: r["inception"]
        for r in _rows("""
            SELECT params->>'maal_code' AS maal_code, inception_date AS inception
            FROM atlas_foundation.portfolio_master WHERE params->>'source' = 'cpp'
        """)
    }
    for code, r in by_code.items():
        span_days = (r["last"] - r["first"]).days
        assert r["points"] > span_days * 0.6, (
            f"{code}: {r['points']} NAV points across {span_days} days — the history is holed"
        )
        assert r["first"] <= inception[code], (
            f"{code}: NAV history starts {r['first']}, after inception {inception[code]}"
        )


def test_a_days_snapshot_holds_exactly_one_view_of_each_book() -> None:
    """A snapshot is a complete look, not an accumulation of leftovers.

    Found 2026-08-08 by the reconciliation gate, on real rows. The sync runs twice a
    day and upserts on (as_of, maal_code, isin), so a name CPP dropped between the two
    runs kept its morning row alive under the evening's as_of: ind11 carried ETERNAL at
    source_as_of 2026-08-06 alongside seven positions at 2026-08-07. The desk reads that
    book to place sells — a stale name in it is an order for stock that is already gone.

    Two source_as_of values under one as_of is the signature.
    """
    rows = _rows("""
        SELECT as_of, maal_code, count(DISTINCT source_as_of) AS views
        FROM atlas_foundation.maal_holding_snapshot
        GROUP BY as_of, maal_code HAVING count(DISTINCT source_as_of) > 1
        ORDER BY as_of DESC
    """)
    assert rows == [], "snapshot mixes CPP dates within a single look: " + ", ".join(
        f"{r['maal_code']}@{r['as_of']} has {r['views']} source dates" for r in rows
    )


def test_the_newest_snapshot_is_priced_entirely_by_cpp() -> None:
    """Atlas's NSE close cannot reproduce the client's statement, only disagree with it."""
    rows = _rows("""
        SELECT s.maal_code, count(*) AS unpriced
        FROM atlas_foundation.maal_holding_snapshot s
        JOIN (SELECT maal_code AS c, max(as_of) AS a
              FROM atlas_foundation.maal_holding_snapshot GROUP BY maal_code) l
          ON l.c = s.maal_code AND l.a = s.as_of
        WHERE s.cpp_value IS NULL
        GROUP BY s.maal_code
    """)
    assert rows == [], f"positions valued by Atlas rather than CPP: {rows}"


# ── The comparison itself bites ──────────────────────────────────────────────


def test_a_row_reconciles_against_itself(stored: dict[str, dict]) -> None:
    for code in BOOKS:
        assert mismatches(stored[code], stored[code]) == []


def test_two_different_real_books_do_not_reconcile(stored: dict[str, dict]) -> None:
    """Leaders is +227%, Passive +100%. A comparison that passes here is asleep."""
    found = mismatches(stored["leaders"], stored["passive"])
    assert "absolute_return" in " ".join(found)
    assert len(found) >= 5, f"only {len(found)} field(s) differ between two unrelated books"


def test_a_null_on_one_side_only_is_a_mismatch(stored: dict[str, dict]) -> None:
    """IND11 is 3 months old, so its return_6m is genuinely NULL where Leaders' is not.

    Treating that as "equal enough" is how a missing figure becomes a silent zero.
    """
    assert stored["ind11"]["return_6m"] is None
    assert stored["leaders"]["return_6m"] is not None
    assert any("return_6m" in m for m in mismatches(stored["ind11"], stored["leaders"]))


def test_a_difference_inside_display_rounding_is_not_a_mismatch(stored: dict[str, dict]) -> None:
    """The board shows 2dp; CPP stores 4dp. Only a real divergence may fail the gate."""
    nudged = dict(stored["leaders"])
    nudged["absolute_return"] = Decimal(str(stored["leaders"]["absolute_return"])) + Decimal(
        "0.0001"
    )
    assert mismatches(stored["leaders"], nudged) == []
