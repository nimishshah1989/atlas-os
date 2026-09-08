"""ingest_macro's pure pieces on REAL FRED observations, and the live API when a key exists.

The keyless part uses FRED's own CSV export of DTB3 (``tests/fixtures/global/macro/DTB3.csv``,
provenance in its ``SOURCE.md``): real prints, a real bond-market holiday (2025-10-13, Columbus
Day — the stock market was open) and a real last observation (2026-09-02). The session lists
are hand-listed weekdays — calendar facts, not market data. The API tests run only with
``FRED_API_KEY`` set (the sandbox has none — they skip, and say so); they assert on real
values and cross-check one print against the CSV export.
"""

from __future__ import annotations

import csv
import os
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from atlas.global_market.providers.fred import fred_series
from tests.unit.global_market.live_files import FIXTURES
from tests.unit.global_market.script_loader import load_global_script

im = load_global_script("ingest_macro")

DTB3_CSV = FIXTURES / "macro" / "DTB3.csv"
FRED_KEY = os.environ.get("FRED_API_KEY", "").strip()

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def dtb3() -> pd.DataFrame:
    """The export as ``fred_series`` would shape it: ``date, value`` (Decimal), blanks dropped."""
    rows = [
        (date.fromisoformat(r["observation_date"]), Decimal(r["DTB3"]))
        for r in csv.DictReader(DTB3_CSV.open())
        if r["DTB3"].strip()
    ]
    return pd.DataFrame.from_records(rows, columns=["date", "value"])


def test_the_export_holds_the_documented_observations(dtb3: pd.DataFrame) -> None:
    dates = set(dtb3["date"])
    assert len(dtb3) >= 2400 and dtb3["date"].iloc[0] == date(2016, 1, 4) == im.HISTORY_START
    assert dtb3["date"].iloc[-1] == date(2026, 9, 2)
    assert date(2025, 10, 10) in dates and date(2025, 10, 14) in dates
    assert date(2025, 10, 13) not in dates  # Columbus Day: no T-bill print, SPY traded


def test_ffill_carries_the_prior_print_onto_a_bond_holiday_session(dtb3: pd.DataFrame) -> None:
    sessions = [date(2025, 10, 9), date(2025, 10, 10), date(2025, 10, 13), date(2025, 10, 14)]
    out = im.ffill_onto(sessions, dtb3)
    assert list(out) == sessions
    assert out[date(2025, 10, 10)] == Decimal("3.86")
    assert out[date(2025, 10, 13)] == Decimal("3.86")  # carried from 10-10
    assert out[date(2025, 10, 14)] == Decimal("3.85")  # its own print
    assert im.ffill_onto(sessions, dtb3.iloc[::-1]) == out  # observation order does not matter


def test_no_value_before_the_first_or_after_the_last_observation(dtb3: pd.DataFrame) -> None:
    out = im.ffill_onto([date(2015, 12, 31), date(2016, 1, 4)], dtb3)
    assert out[date(2015, 12, 31)] is None and out[date(2016, 1, 4)] == Decimal("0.22")
    tail = im.ffill_onto([date(2026, 9, 2), date(2026, 9, 3)], dtb3)
    assert tail[date(2026, 9, 2)] == Decimal("3.78")
    assert tail[date(2026, 9, 3)] is None  # never yesterday's print stamped as today's


def test_wide_frame_over_sessions_and_over_raw_dates(dtb3: pd.DataFrame) -> None:
    sessions = [date(2025, 10, 10), date(2025, 10, 13), date(2026, 9, 3)]
    frame = im.wide_frame(sessions, {"dtb3": dtb3})
    assert list(frame.columns) == list(im.COLUMNS) == ["date", *im.SERIES]
    assert frame["date"].tolist() == sessions[:2]  # 2026-09-03 has no value at all → no row
    assert frame["dtb3"].tolist() == [Decimal("3.86"), Decimal("3.86")]
    assert frame["sp500"].isna().all()
    raw = im.wide_frame([], {"dtb3": dtb3})
    assert raw["date"].tolist() == dtb3["date"].tolist()  # no calendar: the raw dates, no fill
    assert raw["dtb3"].tolist() == dtb3["value"].tolist()


# ── the live API (only with a key; the sandbox has none) ──

needs_key = pytest.mark.skipif(
    not FRED_KEY, reason="FRED_API_KEY not set — live FRED tests skipped"
)


@needs_key
def test_sp500_has_at_least_2400_observations_since_2016() -> None:
    sp = fred_series(im.SERIES["sp500"], im.HISTORY_START, FRED_KEY)
    assert len(sp) >= 2400
    assert all(isinstance(v, Decimal) and v > 0 for v in sp["value"])


@needs_key
def test_dtb3_is_a_percent_rate_and_agrees_with_the_csv_export(dtb3: pd.DataFrame) -> None:
    api = fred_series(im.SERIES["dtb3"], im.HISTORY_START, FRED_KEY)
    assert all(Decimal(0) <= v <= Decimal(20) for v in api["value"])
    on = dict(zip(api["date"], api["value"], strict=True))
    assert on[date(2025, 10, 10)] == Decimal("3.86")
    assert date(2025, 10, 13) not in on


@needs_key
def test_the_five_series_build_a_wide_frame_over_their_raw_dates() -> None:
    series = {c: fred_series(sid, im.HISTORY_START, FRED_KEY) for c, sid in im.SERIES.items()}
    frame = im.wide_frame([], series)
    assert len(frame) >= 2400 and list(frame.columns) == list(im.COLUMNS)
