"""``ingest_filings_8k``'s pure half, on the real submissions payloads.

No network and no database: ``filing_rows`` is a pure function of a payload, and the payloads are
the verbatim downloads under ``tests/fixtures/global/submissions/``.

The three things that would be wrong in a way nothing downstream could see:

* a dual-class issuer's filing reaching only one of its listings (Alphabet's GOOGL and GOOG share
  one CIK and one 8-K, and the table's two-part key exists for exactly that);
* the watermark being applied on the wrong side of the boundary, so every run either re-writes
  the whole history or skips the day it should have written; and
* the columns the writer names drifting from the columns the table has — an ``UndefinedColumn``
  at one in the morning, after the SEC requests have already been spent.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from atlas.global_market.scoring.stock_catalyst import CATALYST_KEYS
from tests.unit.global_market.script_loader import load_global_script

ingest = load_global_script("ingest_filings_8k")
seed_thresholds = load_global_script("seed_thresholds")

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "global" / "submissions"
DDL = REPO / "scripts" / "global_market" / "ddl" / "04_fundamentals_events.sql"

A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"


@cache
def payload(symbol: str) -> dict[str, Any]:
    return json.loads(gzip.decompress((FIXTURES / f"submissions_{symbol}.json.gz").read_bytes()))


# ── the dual-class fan-out ──────────────────────────────────────────────────


def test_one_filing_reaches_every_listing_that_shares_the_cik() -> None:
    """Alphabet files one 8-K and it belongs to both GOOGL and GOOG. Fetching by CIK is what
    halves the requests; fanning the rows out is what stops one listing losing the news."""
    rows, _ = ingest.filing_rows(payload("AAPL"), "0000320193", [A, B], None)
    accessions = {r["accession_no"] for r in rows}
    assert len(rows) == 2 * len(accessions)
    for accession in accessions:
        both = {r["instrument_id"] for r in rows if r["accession_no"] == accession}
        assert both == {A, B}
    # And every row carries the CIK it was fetched under, so the watermark can be read back.
    assert {r["cik"] for r in rows} == {"0000320193"}


def test_only_8ks_are_taken_from_a_payload_full_of_other_forms() -> None:
    """JPMorgan's feed is 25,985 filings and 26 of them are 8-Ks. A form filter that let a 424B
    through would put a prospectus into the catalyst lens with no items at all."""
    rows, _ = ingest.filing_rows(payload("JPM"), "0000019617", [A], None)
    assert len(rows) == 26
    assert ingest.FORMS == {"8-K", "8-K/A"}


# ── the watermark ───────────────────────────────────────────────────────────


def test_the_watermark_is_exclusive_so_a_run_neither_repeats_nor_skips() -> None:
    """``since`` is the newest filing already stored. Filings ON that date are already written;
    filings after it are not. Off by one in either direction is a silent bug: inclusive re-writes
    the whole history every night, and a strict `>=` would drop the day it should have kept."""
    everything, _ = ingest.filing_rows(payload("VZ"), "0000732712", [A], None)
    dates = sorted({r["filed"] for r in everything})
    cut = dates[len(dates) // 2]
    after, _ = ingest.filing_rows(payload("VZ"), "0000732712", [A], cut)
    assert all(r["filed"] > cut for r in after)
    assert len(after) == sum(1 for r in everything if r["filed"] > cut)
    # A watermark at the newest filing leaves nothing to do — the normal state of a quiet day.
    assert ingest.filing_rows(payload("VZ"), "0000732712", [A], max(dates))[0] == []


def test_the_feed_window_is_reported_whatever_the_watermark_kept() -> None:
    """The horizon is a property of the PAYLOAD, not of the rows this run wrote: a filer already
    at its watermark writes nothing and its feed may still be too shallow to score over."""
    _rows, covers = ingest.filing_rows(payload("JPM"), "0000019617", [A], dt.date(2099, 1, 1))
    assert covers is not None
    assert (covers[1] - covers[0]).days <= 366  # JPMorgan's whole 8-K horizon is one year
    apple_rows, apple_covers = ingest.filing_rows(payload("AAPL"), "0000320193", [A], None)
    assert apple_rows and apple_covers is not None
    assert apple_covers[0].year == 2015


# ── the row shape ───────────────────────────────────────────────────────────


def test_a_row_carries_the_item_codes_as_a_list_for_the_text_array_column() -> None:
    rows, _ = ingest.filing_rows(payload("AAPL"), "0000320193", [A], None)
    results = next(r for r in rows if r["accession_no"] == "0000320193-26-000018")
    assert results["items"] == ["2.02", "9.01"]
    assert isinstance(results["items"], list)  # psycopg2 adapts a list to a Postgres text[]
    assert results["filed"] == dt.date(2026, 7, 30)
    assert results["source"] == ingest.SOURCE_LABEL


def test_every_column_the_writer_names_exists_in_the_ddl() -> None:
    """A rename in the DDL without one here is an UndefinedColumn on the box at 01:00 UTC,
    after the SEC requests have already been spent."""
    body = DDL.read_text()
    start = body.index("CREATE TABLE IF NOT EXISTS atlas_global.filings_8k (")
    create = body[start : body.index("\n);", start)]
    names = {
        line.strip().split()[0]
        for line in create.splitlines()[1:]
        if line.startswith("    ") and not line.strip().startswith("CONSTRAINT")
    }
    assert set(ingest.COLUMNS) <= names, f"not in the DDL: {sorted(set(ingest.COLUMNS) - names)}"
    assert set(ingest.CONFLICT_COLUMNS) <= set(ingest.COLUMNS)
    # The two-part key is the dual-class fan-out's whole reason for working.
    assert ingest.CONFLICT_COLUMNS == ["accession_no", "instrument_id"]


def test_the_rows_fill_exactly_the_columns_the_writer_will_send() -> None:
    rows, _ = ingest.filing_rows(payload("VZ"), "0000732712", [A], None)
    assert rows and set(rows[0]) == set(ingest.COLUMNS)


# ── the contract with the thresholds table ──────────────────────────────────


def test_the_seed_table_carries_every_key_the_catalyst_lens_reads() -> None:
    """The lens has no defaults, so a key the seeder forgot is a KeyError on the first company
    that files that item — in prod, at night, after the fetches are spent."""
    seeded = {str(r["threshold_key"]) for r in seed_thresholds.SEEDS}
    assert set(CATALYST_KEYS) <= seeded, f"unseeded: {sorted(set(CATALYST_KEYS) - seeded)}"


def test_the_ingest_reads_the_lens_own_window_rather_than_naming_one() -> None:
    """The horizon check compares the feed against ``catalyst_recency_t3`` — the same row the
    scorer decays over. Two definitions of "how far back this lens looks" would eventually
    disagree, and the ingest would then pass a filer the scorer cannot score."""
    assert ingest.LOOKBACK_KEY == "catalyst_recency_t3"
    assert ingest.LOOKBACK_KEY in CATALYST_KEYS


def test_the_flags_are_the_ones_the_orchestrator_calls() -> None:
    options = {o for action in ingest.parser()._actions for o in action.option_strings}
    assert {"--symbols", "--limit", "--full", "--dry-run", "--report"} <= options
