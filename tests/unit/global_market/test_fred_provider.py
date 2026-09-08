"""``providers/fred.py`` — the CSV parser on a REAL committed export, and both live doors.

``unit``: ``tests/fixtures/global/macro/DTB3.csv`` is a verbatim copy of FRED's own keyless
export (provenance and sha256 in its ``SOURCE.md``), so the parser is exercised on real
prints — 2,783 rows, 115 of them a day the bond market did not publish, a real negative yield
from the March-2020 bill panic, and a real bond holiday on a stock-market session.

``live``: the keyless endpoint itself, which is the whole point of this chunk — it must
answer with no key at all, honour ``cosd``/``coed``, and 404 (not silently empty) on a series
that does not exist. Those tests fetch, so they are ``live``, never ``unit``, and under
``ATLAS_LIVE_FIXTURES=required`` (``make test-live``) an unreachable FRED is a FAILURE.

The JSON API tests run only with ``FRED_API_KEY`` set (this sandbox has none — they skip and
say so) and assert that the two transports return the SAME observations, which is the claim
the keyless path rests on.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
import requests

from atlas.global_market.providers.fred import (
    CSV_ENDPOINT,
    FRED_CSV_BASE,
    JSON_ENDPOINT,
    fred_series,
    parse_fred_csv,
)
from tests.unit.global_market.live_files import FIXTURES

DTB3_CSV = FIXTURES / "macro" / "DTB3.csv"
FRED_KEY = os.environ.get("FRED_API_KEY", "").strip()

# Facts of the committed export, read off the file itself (SOURCE.md records the same).
REF_RAW_ROWS, REF_VALUES, REF_BLANKS = 2783, 2668, 115
REF_FIRST, REF_LAST = date(2016, 1, 4), date(2026, 9, 2)


@pytest.fixture(scope="module")
def dtb3_text() -> str:
    return DTB3_CSV.read_text()


@pytest.fixture(scope="module")
def dtb3(dtb3_text: str) -> pd.DataFrame:
    return parse_fred_csv(dtb3_text, "DTB3")


# ── the parser, on the committed real export (unit) ──


@pytest.mark.unit
def test_the_export_parses_to_the_documented_observation_count(
    dtb3_text: str, dtb3: pd.DataFrame
) -> None:
    assert len(dtb3_text.strip().splitlines()) - 1 == REF_RAW_ROWS
    assert len(dtb3) == REF_VALUES
    assert REF_RAW_ROWS - len(dtb3) == REF_BLANKS


@pytest.mark.unit
def test_the_contract_holds_date_decimal_ascending(dtb3: pd.DataFrame) -> None:
    assert list(dtb3.columns) == ["date", "value"]
    assert all(isinstance(d, date) for d in dtb3["date"])
    assert all(isinstance(v, Decimal) for v in dtb3["value"])
    assert list(dtb3["date"]) == sorted(dtb3["date"])
    assert dtb3["date"].iloc[0] == REF_FIRST and dtb3["date"].iloc[-1] == REF_LAST


@pytest.mark.unit
def test_an_empty_value_is_dropped_not_zero_filled(dtb3: pd.DataFrame) -> None:
    """Columbus Day 2025: the bond market did not publish, the stock market traded. The
    export writes ``2025-10-13,`` — an EMPTY field, not the JSON API's ``"."`` — and a
    dropped row is the only honest reading (rule #0). A zero-fill would print a 0.00% bill."""
    on = dict(zip(dtb3["date"], dtb3["value"], strict=True))
    assert date(2025, 10, 13) not in on
    assert on[date(2025, 10, 10)] == Decimal("3.86")
    assert on[date(2025, 10, 14)] == Decimal("3.85")
    assert Decimal(0) not in set(dtb3["value"])


@pytest.mark.unit
def test_a_real_negative_print_survives_as_a_decimal(dtb3: pd.DataFrame) -> None:
    """2020-03-25/26: the bill yield went negative. A parser that treated ``-0.05`` as a
    missing marker, or rounded it through a float, would erase a real market event."""
    on = dict(zip(dtb3["date"], dtb3["value"], strict=True))
    assert on[date(2020, 3, 26)] == Decimal("-0.05")
    assert min(dtb3["value"]) == Decimal("-0.05")


@pytest.mark.unit
def test_a_body_that_is_not_this_series_export_raises(dtb3_text: str) -> None:
    """An HTML error page served as HTTP 200, or the wrong series, must never read as
    "no observations". The header names the series, so it is the integrity check."""
    with pytest.raises(ValueError, match="DGS10"):
        parse_fred_csv(dtb3_text, "DGS10")  # the real export, asked for as another series
    with pytest.raises(ValueError, match="SP500"):
        parse_fred_csv("<!DOCTYPE html>\n<html lang='en'>\n", "SP500")


@pytest.mark.unit
def test_the_two_endpoint_labels_are_distinct(dtb3: pd.DataFrame) -> None:
    """provider_calls records the spend under the door actually used; one label for both
    would let the ledger claim a JSON call that was never made."""
    assert JSON_ENDPOINT != CSV_ENDPOINT
    assert not dtb3.empty  # the fixture is real, not an empty stand-in


# ── the keyless endpoint itself (live) ──


def _fetch(**params: str) -> requests.Response:
    try:
        return requests.get(FRED_CSV_BASE, params=params, timeout=60)
    except requests.RequestException as e:  # pragma: no cover - network shape, not logic
        if os.environ.get("ATLAS_LIVE_FIXTURES", "").strip().lower() == "required":
            pytest.fail(f"{FRED_CSV_BASE} unreachable with ATLAS_LIVE_FIXTURES=required: {e}")
        pytest.skip(reason=f"{FRED_CSV_BASE} unreachable: {e}")


@pytest.mark.live
def test_the_keyless_export_answers_with_no_key_at_all() -> None:
    r = _fetch(id="SP500")
    assert r.status_code == 200
    df = parse_fred_csv(r.text, "SP500")
    print(f"live keyless SP500: {len(df)} obs {df['date'].iloc[0]} → {df['date'].iloc[-1]}")
    assert len(df) >= 2400  # FRED publishes SP500 as a rolling 10-year window
    assert all(isinstance(v, Decimal) and v > 0 for v in df["value"])
    assert list(df["date"]) == sorted(df["date"])


@pytest.mark.live
def test_cosd_and_coed_bound_the_window_inclusively() -> None:
    """The claim the provider's window rests on, checked against the endpoint rather than
    assumed: both bounds are inclusive and applied server-side."""
    lo, hi = date(2026, 8, 3), date(2026, 8, 14)
    df = parse_fred_csv(_fetch(id="SP500", cosd=lo.isoformat(), coed=hi.isoformat()).text, "SP500")
    print(f"live window {lo} → {hi}: {len(df)} obs {df['date'].iloc[0]} → {df['date'].iloc[-1]}")
    assert df["date"].iloc[0] == lo and df["date"].iloc[-1] == hi
    assert all(lo <= d <= hi for d in df["date"])


@pytest.mark.live
def test_a_series_that_does_not_exist_is_an_http_error_not_an_empty_frame() -> None:
    r = _fetch(id="NOT_A_FRED_SERIES")
    print(f"live bogus series → HTTP {r.status_code}")
    assert r.status_code >= 400
    with pytest.raises(requests.HTTPError):
        fred_series("NOT_A_FRED_SERIES", date(2026, 1, 1), None)


@pytest.mark.live
def test_fred_series_keyless_honours_start_and_end() -> None:
    lo, hi = date(2026, 6, 15), date(2026, 6, 25)
    df = fred_series("DGS10", lo, None, end=hi)
    on = dict(zip(df["date"], df["value"], strict=True))
    print(f"live keyless DGS10 {lo} → {hi}: {len(df)} obs")
    assert all(lo <= d <= hi for d in df["date"])
    assert date(2026, 6, 19) not in on  # Juneteenth: the export writes an empty value
    assert all(isinstance(v, Decimal) for v in df["value"])


# ── the two transports must agree (only with a key) ──

needs_key = pytest.mark.skipif(not FRED_KEY, reason="FRED_API_KEY not set — JSON API skipped")


@needs_key
@pytest.mark.live
def test_the_keyed_and_keyless_transports_return_the_same_observations() -> None:
    lo, hi = date(2026, 1, 2), date(2026, 6, 30)
    keyed = fred_series("SP500", lo, FRED_KEY, end=hi)
    keyless = fred_series("SP500", lo, None, end=hi)
    print(f"keyed {len(keyed)} obs vs keyless {len(keyless)} obs over {lo} → {hi}")
    assert list(keyed["date"]) == list(keyless["date"])
    assert list(keyed["value"]) == list(keyless["value"])
