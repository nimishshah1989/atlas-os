"""``exclusion_reason`` — the ONE reason each excluded row is out — over REAL run rows.

Every line of :data:`RUN_CSV` is a line of the ``--report`` CSV that
``scripts/global_market/build_universe_snapshot.py --eod 2026-09-03`` wrote against the scratch
clone of the FM's archive (13,155 active instruments, floor $1,000,000, the 2026-09-06 rules),
copied verbatim with its header. Nothing here is typed in and no frame is invented (rule #0);
re-running the script prints these ten lines again.

They cover all seven values the column can hold plus the in-universe NULL, and two of them —
ALA and VALG, both geared ETFs — carry an ADV$ status instead of ``leveraged``, which is the
ordering the ladder exists to express: no signal is no signal, whatever the instrument is.

The three ADV$ statuses are not re-derived here: ``status()`` needs
``liquidity_min_observations_60d``, an ``atlas_thresholds`` row, and a unit test has no
database to read it from (rule #1 — never a literal). They arrive as the real run recorded
them; ``tests/integration/global_market/test_universe_snapshot_db.py`` proves the ladder
itself, and the write path, against the archive.
"""

from __future__ import annotations

import csv
import io
import re

import pandas as pd
import pytest

from tests.unit.global_market.script_loader import SCRIPTS_DIR, load_global_script

bus = load_global_script("build_universe_snapshot")

pytestmark = pytest.mark.unit

DDL = SCRIPTS_DIR / "ddl" / "05_scores.sql"

RUN_CSV = """\
asset_class,symbol,instrument_id,status,n_obs,last_date,adv_usd_median_60d,in_sp500,leverage_rule,in_universe
etf,ALA,53d136ba-fb33-5d63-85cd-0af49b9bdfb5,too_few_observations,39,2026-09-03,,False,explicit_multiple,False
etf,BOND,246981e8-ac1d-5f70-99c1-b65bdad15ae1,no_bars,0,,,False,no_leverage_pattern,False
etf,ILCB,20825faf-e866-5e83-b665-85d4094eaf70,ok,60,2026-09-03,998362.3508,False,no_leverage_pattern,False
etf,SH,3aaa80f8-c09b-5556-b4e9-a1e6c70df45e,inverse,60,2026-09-03,229633977.685,False,proshares_short,False
etf,SPY,089e61e3-f730-56d8-bca2-5ed6d01d9658,ok,60,2026-09-03,33705334350.09,False,no_leverage_pattern,True
etf,TQQQ,b3e32b5b-58da-515a-a126-1495dd7a3473,leveraged,60,2026-09-03,4452417125.6,False,proshares_ultra,False
etf,VALG,3b88762f-0873-526b-934b-41f0a690168b,stale,40,2026-08-27,,False,explicit_multiple,False
stock,AA,dd72e1e0-2995-5e4c-a701-538b579389be,not_sp500,60,2026-09-03,269910230.005,False,no_leverage_pattern,False
stock,AAPL,0117bc1c-0752-5b5e-b374-50a246a128f6,ok,60,2026-09-03,14114234323.095,True,no_leverage_pattern,True
stock,CRAC,0f0e5b89-f005-57fb-8909-769d29f39f8a,stale,43,2026-08-26,,False,no_leverage_pattern,False
"""

# What the journal must say about each of those rows, and why — the instrument's real state on
# 2026-09-03, read from the run above and from instrument_master's names.
EXPECTED: dict[str, str | None] = {
    "SPY": None,  # State Street SPDR S&P 500 ETF Trust — in the universe, so no reason at all
    "AAPL": None,  # Apple, an S&P 500 member $14bn a day — in
    "BOND": "no_bars",  # PIMCO Active Bond ETF: not one bar in the 60-session window
    "ALA": "too_few_observations",  # Corgi ALAB 2x Daily ETF, 39 traded sessions — one short
    "VALG": "stale",  # Leverage Shares 2X Long VALE: 40 sessions, last one 27 Aug
    "CRAC": "stale",  # Crown Reserve Acquisition Corp. I, last bar 26 Aug
    "AA": "not_sp500",  # Alcoa: $270m a day and out — the FM scores current members only
    "TQQQ": "leveraged",  # ProShares UltraPro QQQ
    "SH": "inverse",  # ProShares Short S&P500 — inverse WITHOUT gearing
    "ILCB": "below_floor",  # iShares Morningstar Large-Cap: clears every rule, $1,638 short
}


@pytest.fixture
def frame() -> pd.DataFrame:
    """The report rows as the script holds them at the write site — ``status`` from
    ``universe_status``, ``in_universe`` a boolean — with the column under test derived."""
    rows = pd.DataFrame(list(csv.DictReader(io.StringIO(RUN_CSV))))
    rows["in_universe"] = rows["in_universe"] == "True"
    return rows.assign(
        exclusion_reason=lambda f: bus.exclusion_reasons(f["status"], f["in_universe"])
    )


def test_every_row_gets_the_one_reason_its_real_state_earns(frame: pd.DataFrame) -> None:
    got = dict(zip(frame["symbol"], frame["exclusion_reason"], strict=True))
    assert {k: (v if pd.notna(v) else None) for k, v in got.items()} == EXPECTED
    # The sample IS the whole column: all seven, and nothing outside them.
    assert set(EXPECTED.values()) - {None} == set(bus.EXCLUSION_REASONS)


def test_a_row_in_the_universe_carries_no_reason_and_every_other_row_carries_one(
    frame: pd.DataFrame,
) -> None:
    inside = pd.Series(frame["in_universe"])
    reason = pd.Series(frame["exclusion_reason"])
    assert list(frame.loc[inside, "symbol"]) == ["SPY", "AAPL"]
    assert bool(reason.loc[inside].isna().all()) and bool(reason.loc[~inside].notna().all())
    assert int(reason.notna().sum()) == int((~inside).sum())  # exactly one each, never two


def test_the_adv_ladder_bites_before_the_leverage_rules(frame: pd.DataFrame) -> None:
    """ALA and VALG ARE geared — ``leverage_flags`` fired ``explicit_multiple`` on both — and
    are still out on the ADV$ ladder: a fund with no usable median has no signal to gear."""
    geared = frame.set_index("symbol").loc[["ALA", "VALG"]]
    assert set(geared["leverage_rule"]) == {"explicit_multiple"}
    assert list(geared["exclusion_reason"]) == ["too_few_observations", "stale"]


def test_below_floor_is_the_row_that_cleared_every_structural_rule(frame: pd.DataFrame) -> None:
    """``universe_status`` deliberately calls ILCB ``ok``: it has an ADV$, it is an ETF that is
    neither geared nor inverse. Only the floor — the FM's, and moveable — leaves it out, and
    that is the one reason the write site derives rather than that function."""
    ilcb = frame.set_index("symbol").loc["ILCB"]
    assert ilcb["status"] == bus.STATUS_OK and not ilcb["in_universe"]
    assert ilcb["exclusion_reason"] == bus.STATUS_BELOW_FLOOR
    assert float(ilcb["adv_usd_median_60d"]) < 1_000_000  # the floor this run read from the table


def test_the_seven_reasons_are_exactly_what_the_ddl_check_allows() -> None:
    """The tuple in the script and the CHECK in ddl/05_scores.sql are one list; drift between
    them is a run that dies on a constraint violation at 01:00 UTC."""
    body = DDL.read_text().split("chk_universe_snapshot_exclusion_reason", 1)[1].split("))", 1)[0]
    assert tuple(re.findall(r"'(\w+)'", body)) == bus.EXCLUSION_REASONS


def test_assert_partition_accepts_the_real_frame(frame: pd.DataFrame) -> None:
    bus.assert_partition(frame)  # raises if it does not


@pytest.mark.parametrize(
    ("symbol", "reason", "complaint"),
    [
        ("AA", None, "out with no reason"),  # the bare "excluded" this column exists to end
        ("SPY", "below_floor", "in the universe with one"),
        ("AA", "delisted", "outside"),  # a reason the DDL's CHECK would refuse anyway
    ],
    ids=["unexplained", "explained-but-in", "unknown-reason"],
)
def test_assert_partition_refuses_a_frame_that_does_not_partition(
    frame: pd.DataFrame, symbol: str, reason: str | None, complaint: str
) -> None:
    broken = frame.set_index("symbol")
    broken.loc[symbol, "exclusion_reason"] = reason
    with pytest.raises(RuntimeError, match="does not partition") as e:
        bus.assert_partition(broken.reset_index())
    assert complaint in str(e.value) and "nothing written" in str(e.value)
