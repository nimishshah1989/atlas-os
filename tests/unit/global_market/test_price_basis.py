"""The price-basis mapping, and that it still agrees with the DDL that stores it.

Pure filesystem — no DB, no network, no TA-Lib. The values asserted here are not market data:
they are the vocabulary two producers share (``import_stooq.py`` writes the
``adjustment_source`` label, ``compute_technicals.py`` reads it back), and the real artefact
under test is ``scripts/global_market/ddl/01_prices.sql`` — a mapping that can emit a label
the CHECK constraint refuses would fail the whole nightly write, at 3am, on the box.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from atlas.global_market import price_basis as pb

pytestmark = pytest.mark.unit

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts" / "global_market"
_DDL = _SCRIPTS / "ddl" / "01_prices.sql"


def _check_constraint_values(constraint: str) -> set[str]:
    """The literals a named CHECK ... IN (...) in the DDL allows."""
    text = _DDL.read_text()
    match = re.search(rf"CONSTRAINT {constraint} CHECK \([a-z_]+ IN \(([^)]*)\)\)", text)
    assert match, f"{constraint} is not in {_DDL.name} — the column or its CHECK was renamed"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def test_every_basis_the_mapping_can_emit_is_one_the_ddl_accepts() -> None:
    allowed = _check_constraint_values("chk_technical_daily_price_basis")
    assert set(pb.PRICE_BASES) == allowed
    assert set(pb.BASIS_BY_ADJUSTMENT_SOURCE.values()) <= allowed
    assert set(pb.COLUMNS_BY_BASIS) == allowed


def test_the_stooq_total_return_label_reads_close_tr() -> None:
    assert pb.basis_of(pb.STOOQ_TOTAL_RETURN) == pb.TOTAL_RETURN
    assert pb.price_columns(pb.TOTAL_RETURN) == ("open", "high", "low", "close_tr")


def test_the_module_states_no_measurement_of_its_own() -> None:
    """The basis of a real feed is MEASURED by validate_global.py --check BASIS, once, from
    real rows. A second copy of that answer sitting here as a constant would go on reading
    `total_return` the day a feed changed — so the vocabulary lives here and the verdict does
    not. This test fails if anyone puts one back."""
    numbers = [
        name
        for name, value in vars(pb).items()
        if not name.startswith("_")
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ]
    assert not numbers, f"{numbers} — a measured quantity belongs in the BASIS gate, not here"
    importer = _SCRIPTS / "import_stooq.py"
    assert "measured_total_return" in importer.read_text(), (
        "import_stooq.py must ask the BASIS gate before it mints a basis label"
    )


def test_alpaca_labels_split_from_total_return() -> None:
    assert pb.basis_of(pb.ALPACA_SPLIT) == pb.SPLIT_ONLY
    assert pb.basis_of(pb.ALPACA_ALL) == pb.TOTAL_RETURN
    assert pb.price_columns(pb.SPLIT_ONLY) == ("open_adj", "high_adj", "low_adj", "close_adj")


def test_an_unlabelled_or_unknown_source_yields_no_basis() -> None:
    """The pre-measurement label and anything unrecognised must NOT resolve: those rows have
    no usable adjusted close, and a caller that guessed would score on a raw price."""
    assert pb.basis_of(None) is None
    assert pb.basis_of("") is None
    assert pb.basis_of(pb.STOOQ_UNKNOWN) is None
    assert pb.basis_of("stooq_detected_split") is None  # a label nothing writes (yet)


def test_price_columns_refuses_a_basis_that_is_not_one() -> None:
    with pytest.raises(ValueError, match="unknown price basis"):
        pb.price_columns("raw")


def test_the_ddl_still_declares_the_two_closes_the_mapping_reads() -> None:
    """A renamed column would make compute_technicals build SQL for a column that is gone."""
    text = _DDL.read_text()
    for basis in pb.PRICE_BASES:
        for column in pb.price_columns(basis):
            assert re.search(rf"^\s+{column}\s+numeric", text, re.MULTILINE), (
                f"ohlcv_daily has no {column} column"
            )
