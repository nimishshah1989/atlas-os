"""fja05680/sp500 — the committed ``start_end`` copy (MIT) and, ``live``, the pair (rule #0).

``tests/fixtures/global/index/sp500_ticker_start_end.csv`` is the file fetched 2026-09-04
(provenance in ``SOURCE.md``): the interval FACTS (AAPL's open spell, WBA's and SIVB's closed
ones, AAL's two spells) are asserted on it — ``unit``. The 5.5 MB components file, which
production never fetches, is the cross-check: it is downloaded live together with a second
copy of ``start_end`` (the two must come from the same revision) — ``live``.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from atlas.global_market.providers.sp500_history import (
    INTERVAL_COLUMNS,
    START_END_ENDPOINT,
    START_END_URL,
    known_through,
    parse_start_end,
)
from tests.unit.global_market.live_files import FIXTURES, fetch_or_skip

COMMITTED = FIXTURES / "index" / START_END_ENDPOINT
COMPONENTS_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv"
)
REF_KNOWN_THROUGH = date(2026, 6, 30)  # the live components file's last row on 2026-09-04

unit, live = pytest.mark.unit, pytest.mark.live


def parse_components(text: str) -> pd.DataFrame:
    """``DataFrame[date, tickers]`` of the components file — one row per change date, the
    FULL membership list as a sorted tuple; rows must ascend with no repeats. Test-only:
    production reads the ``start_end`` file alone."""
    rd = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = [h.strip() for h in next(rd, [])]
    if header != ["date", "tickers"]:
        raise ValueError(f"components: header {header} != ['date', 'tickers']")
    rows: list[tuple[date, tuple[str, ...]]] = []
    for n, r in enumerate(rd, start=2):
        if not r or not any(c.strip() for c in r):
            continue
        d = date.fromisoformat(r[0].strip())
        tickers = tuple(sorted({t.strip() for t in r[1].split(",") if t.strip()}))
        if not tickers or (rows and d <= rows[-1][0]):
            raise ValueError(f"components line {n}: {d} lists nothing or is out of order")
        rows.append((d, tickers))
    return pd.DataFrame.from_records(rows, columns=["date", "tickers"])


@pytest.fixture(scope="module")
def start_end() -> pd.DataFrame:
    return parse_start_end(COMMITTED.read_text())


@pytest.fixture(scope="module")
def live_start_end(live_cache: Path) -> pd.DataFrame:
    return parse_start_end(fetch_or_skip(START_END_URL, START_END_ENDPOINT, live_cache).read_text())


@pytest.fixture(scope="module")
def components(live_cache: Path) -> pd.DataFrame:
    path = fetch_or_skip(COMPONENTS_URL, "sp500_historical_components_and_changes.csv", live_cache)
    return parse_components(path.read_text())


def _spells(df: pd.DataFrame, ticker: str) -> list[tuple[date, date | None]]:
    rows = df.loc[df["ticker"] == ticker, ["start_date", "end_date"]]
    return [(s, e) for s, e in rows.itertuples(index=False)]


# ── the committed copy: shape and the interval facts ──


@unit
def test_start_end_shape(start_end: pd.DataFrame) -> None:
    assert list(start_end.columns) == list(INTERVAL_COLUMNS)
    assert len(start_end) == 1259
    assert int(start_end["end_date"].isna().sum()) == 503  # current members
    assert all(isinstance(d, date) for d in start_end["start_date"])


@unit
def test_known_through_is_the_last_change_date(start_end: pd.DataFrame) -> None:
    # CAG,1996-01-02,2026-06-30 — the last change the file knows is CAG's departure.
    assert known_through(start_end) == REF_KNOWN_THROUGH
    assert _spells(start_end, "CAG") == [(date(1996, 1, 2), REF_KNOWN_THROUGH)]


@unit
def test_aapl_has_been_a_member_since_before_2016_and_still_is(start_end: pd.DataFrame) -> None:
    (start, end), *rest = _spells(start_end, "AAPL")
    assert not rest
    assert start <= date(2016, 1, 4) and end is None  # row: AAPL,1996-01-02,


@unit
def test_known_departures_have_closed_intervals(start_end: pd.DataFrame) -> None:
    # rows: WBA,1996-01-02,2025-08-28  and  SIVB,2018-03-19,2023-03-15
    assert _spells(start_end, "WBA") == [(date(1996, 1, 2), date(2025, 8, 28))]
    assert _spells(start_end, "SIVB") == [(date(2018, 3, 19), date(2023, 3, 15))]


@unit
def test_a_ticker_that_left_and_returned_has_one_row_per_spell(start_end: pd.DataFrame) -> None:
    assert _spells(start_end, "AAL") == [
        (date(1996, 1, 2), date(1997, 1, 15)),
        (date(2015, 3, 23), date(2024, 9, 23)),
    ]
    multi = start_end.groupby("ticker").size()
    assert int((multi > 1).sum()) == 52


@unit
def test_class_shares_keep_the_dot_spelling(start_end: pd.DataFrame) -> None:
    current = set(start_end.loc[start_end["end_date"].isna(), "ticker"])
    assert {"BRK.B", "BF.B"} <= current


# ── the live pair: shape, semantics, and the cross-checks ──


@live
def test_components_shape_and_known_through_agrees_with_start_end(
    components: pd.DataFrame, live_start_end: pd.DataFrame
) -> None:
    """``known_through`` reads the last change date off start_end alone (the latest start or
    end date) — this is where the components file, which production never fetches, proves
    the two agree."""
    assert list(components.columns) == ["date", "tickers"]
    assert components["date"].is_monotonic_increasing and components["date"].is_unique
    last = components["date"].iloc[-1]
    print(f"live rows={len(components)} known through {last} (2026-06-30 on 2026-09-04)")
    assert len(components) >= 2718 and last >= REF_KNOWN_THROUGH
    assert known_through(live_start_end) == last
    assert 500 <= len(components["tickers"].iloc[-1]) <= 505
    first_2016 = components.loc[components["date"] >= date(2016, 1, 1)].iloc[0]
    assert first_2016["date"] == date(2016, 1, 4) and len(first_2016["tickers"]) == 504


@live
def test_start_is_inclusive_and_end_is_exclusive_on_the_real_rows(
    components: pd.DataFrame,
) -> None:
    """SIVB,2018-03-19,2023-03-15: listed on the row dated 2018-03-19 (absent on the row before),
    absent on the row dated 2023-03-15 (present on the row before). This is why
    index_membership.effective_to is the first date NOT a member."""
    by_date = dict(zip(components["date"], components["tickers"], strict=True))
    dates = list(components["date"])
    for d, present in ((date(2018, 3, 19), True), (date(2023, 3, 15), False)):
        assert d in by_date, f"{d} is not a change-date row"
        assert ("SIVB" in by_date[d]) is present
        previous = dates[dates.index(d) - 1]
        assert ("SIVB" in by_date[previous]) is not present


@live
def test_both_live_files_agree_on_the_current_members(
    live_start_end: pd.DataFrame, components: pd.DataFrame
) -> None:
    current = set(live_start_end.loc[live_start_end["end_date"].isna(), "ticker"])
    assert current == set(components["tickers"].iloc[-1])


@live
def test_settled_spells_of_the_committed_copy_keep_their_start_in_the_live_file(
    start_end: pd.DataFrame, live_start_end: pd.DataFrame
) -> None:
    """Every spell that started before the committed copy's known-through date is settled
    history: the live file must carry that ticker with the same start. A current member
    leaving upstream (its end_date filled in) does not trip this; an upstream CORRECTION of
    a start date does, as a named failure — then re-fetch the committed copy and re-run
    ``--history`` (the non-ssga rows are re-derived from the file), never edit it by hand."""
    known = known_through(start_end)
    settled = {(t, s) for t, s, _ in start_end.itertuples(index=False, name=None) if s < known}
    live_starts = {(t, s) for t, s, _ in live_start_end.itertuples(index=False, name=None)}
    changed = sorted(settled - live_starts)
    print(
        f"committed: {len(settled)} settled spells; live: {len(live_start_end)} spells, "
        f"known through {known_through(live_start_end)}; {len(changed)} start(s) changed upstream"
    )
    assert not changed, (
        f"spell starts changed upstream — re-fetch the committed copy: {changed[:5]}"
    )
