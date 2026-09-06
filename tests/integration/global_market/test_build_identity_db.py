# ruff: noqa: S608 -- every interpolated value is a symbol or uuid the test itself put in the table.
"""build_identity.py end to end on a REAL Postgres, from the dated 2026-09-04 snapshot.

Opt-in: set ``ATLAS_IDENTITY_TEST_DB_URL`` to a database that carries the atlas_global DDL
(CI's migrations job; a scratch database on the laptop — the DDL is (re)applied, it is
idempotent). The module TRUNCATES the tables build_identity.py writes — instrument_master,
symbol_alias, ingest_state, provider_calls, and through the foreign keys whatever hangs off
instrument_master — before the first test and after the last, so the database is left as the
DDL made it: never point it at prod. Every expected number is the real 2026-09-04 directory
as ``tests/unit/global_market/test_identity_frame.py`` measures it; the scenarios edit a COPY
of the snapshot with the registrant's other real spelling / the ticker's other real CIK.
Unset, the module skips — never a vacuous pass.

    ATLAS_IDENTITY_TEST_DB_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/scratch \\
        uv run --extra dev pytest tests/integration/global_market/test_build_identity_db.py \\
        -m integration
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SNAPSHOT = _REPO / "tests" / "fixtures" / "global" / "symbology"
_SCRIPTS = _REPO / "scripts" / "global_market"
_WRITTEN = ("symbol_alias", "instrument_master", "ingest_state", "provider_calls")

pytestmark = pytest.mark.integration

DB_URL = os.environ.get("ATLAS_IDENTITY_TEST_DB_URL", "")
if not DB_URL:
    pytest.skip(
        "ATLAS_IDENTITY_TEST_DB_URL (a throwaway database) is not set", allow_module_level=True
    )
if not all((_SNAPSHOT / f).is_file() for f in ("nasdaqlisted.txt", "company_tickers_mf.json")):
    pytest.skip(f"{_SNAPSHOT} lacks the snapshot files", allow_module_level=True)

ENV = {**os.environ, "ATLAS_DB_URL": DB_URL}


def _run(*args: str, expect: int = 0) -> str:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPTS / "build_identity.py"), *args],
        capture_output=True,
        text=True,
        env=ENV,
        cwd=_REPO,
        check=False,
    )
    assert proc.returncode == expect, proc.stdout + proc.stderr
    return proc.stdout + proc.stderr  # a refused parse reports on stderr


def _sql(query: str) -> list[tuple]:
    import psycopg2

    conn = psycopg2.connect(DB_URL.replace("postgresql+psycopg2://", "postgresql://", 1))
    try:
        with conn, conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall() if cur.description else []  # DDL returns no rows
    finally:
        conn.close()


def _truncate() -> None:
    _sql("truncate " + ", ".join(f"atlas_global.{t}" for t in _WRITTEN) + " cascade")


@pytest.fixture(scope="module", autouse=True)
def clean_tables() -> Iterator[None]:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPTS / "apply_ddl.py")],  # idempotent: IF NOT EXISTS throughout
        capture_output=True,
        text=True,
        env=ENV,
        cwd=_REPO,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    _truncate()
    yield
    _truncate()


@pytest.fixture(scope="module")
def snap(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A COPY of the snapshot the scenarios edit; every test restores what it changed."""
    d = tmp_path_factory.mktemp("snap")
    for f in _SNAPSHOT.iterdir():
        if f.is_file():
            (d / f.name).write_bytes(f.read_bytes())
    return d


def _plan_line(out: str) -> str:
    return next(line.strip() for line in out.splitlines() if line.strip().startswith("plan:"))


def _counts() -> tuple[int, int]:
    ((total, active),) = _sql(
        "select count(*), sum(is_active::int) from atlas_global.instrument_master"
    )
    return int(total), int(active)


def _row(symbol: str) -> list[tuple]:
    return _sql(
        "select instrument_id::text, asset_class, cik, series_id, is_active, delisted_at::text, "
        f"symbol from atlas_global.instrument_master where symbol = '{symbol}' order by is_active"
    )


def _respell(snap: Path, file: str, old: str, new: str) -> None:
    """One registrant's other real spelling in a Nasdaq file (the whole row's three
    spelling columns) or in company_tickers.json (the ticker)."""
    path = snap / file
    if file.endswith(".json"):
        ct = json.loads(path.read_text())
        (entry,) = [v for v in ct.values() if v["ticker"] == old]
        entry["ticker"] = new
        path.write_text(json.dumps(ct))
        return
    lines = path.read_text().splitlines()
    hit = [i for i, ln in enumerate(lines) if ln.startswith(old + "|")]
    assert len(hit) == 1, (file, old)
    lines[hit[0]] = "|".join(new if f == old else f for f in lines[hit[0]].split("|"))
    path.write_text("\n".join(lines) + "\n")


def _restore(snap: Path, *files: str) -> None:
    for f in files:
        (snap / f).write_bytes((_SNAPSHOT / f).read_bytes())


@pytest.fixture(autouse=True)
def pristine_snapshot(snap: Path) -> Iterator[None]:
    """Whatever a scenario edited is put back after it — a failure never leaks into the next."""
    yield
    _restore(snap, *(f.name for f in _SNAPSHOT.iterdir() if f.is_file()))


# ── the build, twice ──


def test_first_build_then_rerun_is_idempotent(snap: Path, tmp_path: Path) -> None:
    out = _run(
        "--from-snapshot",
        str(snap),
        "--run-date",
        "2026-09-04",
        "--report",
        str(tmp_path / "r1.csv"),
    )
    assert _plan_line(out).startswith(
        "plan: insert 13,154, rename 0, reactivate 0, update 0, unchanged 0"
    )
    assert "WARNING: company_tickers_exchange.json absent" in out  # optional, not committed
    assert _counts() == (13154, 13154)
    ((etfs, stocks, no_exchange),) = _sql(
        "select sum((asset_class='etf')::int), sum((asset_class='stock')::int), "
        "sum((exchange is null)::int) from atlas_global.instrument_master where is_active"
    )
    assert (etfs, stocks, no_exchange) == (5655, 7499, 0)
    ((stock_cik,),) = _sql(
        "select sum((cik is not null)::int) from atlas_global.instrument_master "
        "where asset_class = 'stock' and is_active"
    )
    assert stock_cik == 7467  # 99.6 percent
    ((etf_cik, etf_series),) = _sql(
        "select sum((cik is not null)::int), sum((series_id is not null)::int) "
        "from atlas_global.instrument_master where asset_class = 'etf' and is_active"
    )
    assert (etf_cik, etf_series) == (4666, 4486)  # 82.5 / 79.3 percent
    aliases = dict(_sql("select source, count(*) from atlas_global.symbol_alias group by source"))
    assert aliases == {
        "cqs": 7571,
        "nasdaq_symbol": 13154,
        "sec": 12133,
        "stooq": 13153,  # NMCO.V (rights when-issued) has no Stooq spelling
        "tiingo": 13078,
    }
    ((state,),) = _sql(
        "select value from atlas_global.ingest_state where source = 'identity' and key = 'last_run'"
    )
    assert state["counts"]["insert"] == 13154 and state["run_date"] == "2026-09-04"
    assert state["provenance"] == "fixture"
    assert state["files"]["nasdaqlisted.txt"]["fetched_at"] is None  # no manifest: unknown
    assert (
        state["coverage"]["sec_conflicts"] == 4 and state["coverage"]["name_disagreements"] == 117
    )
    report = (tmp_path / "r1.csv").read_text().splitlines()
    assert report[0] == (
        "symbol,asset_class,exchange,cik,series_id,key_kind,action,aliases,note,"
        "sec_conflict,name_agrees"
    )
    assert len(report) == 13155

    again = _run(
        "--from-snapshot",
        str(snap),
        "--run-date",
        "2026-09-11",
        "--report",
        str(tmp_path / "r2.csv"),
    )
    assert _plan_line(again) == (
        "plan: insert 0, rename 0, reactivate 0, update 0, unchanged 13,154, deactivate 0; "
        "aliases: insert 0, close 0"
    )
    ((n_alias,),) = _sql("select count(*) from atlas_global.symbol_alias")
    assert n_alias == 7571 + 13154 + 12133 + 13153 + 13078


# ── renames: ANTM → ELV (Elevance Health, CIK 0001156039; fja05680: ANTM until 2022-06-28) ──


def test_a_registrant_that_changes_ticker_keeps_its_uuid_and_closes_its_old_spellings(
    snap: Path, tmp_path: Path
) -> None:
    ((elv_id, *_rest),) = _row("ELV")
    _respell(snap, "otherlisted.txt", "ELV", "ANTM")
    _respell(snap, "company_tickers.json", "ELV", "ANTM")
    out = _run(
        "--from-snapshot",
        str(snap),
        "--run-date",
        "2026-09-11",
        "--report",
        str(tmp_path / "a.csv"),
    )
    assert "rename 1" in _plan_line(out) and "deactivate 0" in _plan_line(out)
    assert _row("ANTM") == [(elv_id, "stock", "0001156039", None, True, None, "ANTM")]
    assert _row("ELV") == []
    assert _counts() == (13154, 13154)
    closed = _sql(
        "select source, source_symbol, valid_to::text from atlas_global.symbol_alias "
        f"where instrument_id = '{elv_id}' and valid_to is not null order by source"
    )
    assert closed == [
        ("cqs", "ELV", "2026-09-11"),
        ("nasdaq_symbol", "ELV", "2026-09-11"),
        ("sec", "ELV", "2026-09-11"),
        ("stooq", "ELV.US", "2026-09-11"),
        ("tiingo", "ELV", "2026-09-11"),
    ]
    _restore(snap, "otherlisted.txt", "company_tickers.json")
    back = _run(
        "--from-snapshot",
        str(snap),
        "--run-date",
        "2026-09-18",
        "--report",
        str(tmp_path / "b.csv"),
    )
    assert "rename 1" in _plan_line(back)
    assert _row("ELV") == [(elv_id, "stock", "0001156039", None, True, None, "ELV")]
    open_now = _sql(
        "select source, source_symbol, valid_from::text from atlas_global.symbol_alias "
        f"where instrument_id = '{elv_id}' and valid_to is null order by source"
    )
    assert open_now == [
        ("cqs", "ELV", "2026-09-18"),
        ("nasdaq_symbol", "ELV", "2026-09-18"),
        ("sec", "ELV", "2026-09-18"),
        ("stooq", "ELV.US", "2026-09-18"),
        ("tiingo", "ELV", "2026-09-18"),
    ]


# ── recycle within one weekly gap: ISRL's other real CIK (the SPAC in company_tickers.json) ──


def test_a_cik_change_between_runs_recycles_the_ticker_and_its_return_reactivates(
    snap: Path, tmp_path: Path
) -> None:
    ((etf_id, _c, etf_cik, *_r),) = _row("ISRL")
    assert etf_cik == "0002081107"
    mf = json.loads((snap / "company_tickers_mf.json").read_text())
    mf["data"] = [row for row in mf["data"] if row[3] != "ISRL"]  # the fund class gone
    (snap / "company_tickers_mf.json").write_text(json.dumps(mf))
    out = _run(
        "--from-snapshot",
        str(snap),
        "--run-date",
        "2026-09-11",
        "--report",
        str(tmp_path / "a.csv"),
    )
    assert "insert 1" in _plan_line(out) and "deactivate 1" in _plan_line(out)
    rows = _row("ISRL")
    assert [(r[2], r[4], r[5]) for r in rows] == [
        ("0002081107", False, "2026-09-11"),
        ("0001915328", True, None),
    ]
    spac_id = rows[1][0]
    moved = _sql(
        "select instrument_id::text, valid_from::text, valid_to::text "
        "from atlas_global.symbol_alias "
        "where source = 'stooq' and source_symbol = 'ISRL.US' order by valid_from"
    )
    assert moved == [(etf_id, "2026-09-04", "2026-09-11"), (spac_id, "2026-09-11", None)]
    _restore(snap, "company_tickers_mf.json")
    back = _run(
        "--from-snapshot",
        str(snap),
        "--run-date",
        "2026-09-18",
        "--report",
        str(tmp_path / "b.csv"),
    )
    assert "reactivate 1" in _plan_line(back) and "deactivate 1" in _plan_line(back)
    rows = _row("ISRL")
    assert [(r[0], r[4], r[5]) for r in rows] == [
        (spac_id, False, "2026-09-18"),
        (etf_id, True, None),
    ]
    assert _counts() == (13155, 13154)


# ── ETF-flag flip on the same registrant: IA (stock-flagged; a fund class shares the ticker) ──


def test_an_etf_flag_flip_updates_the_row_in_place(snap: Path, tmp_path: Path) -> None:
    ((ia_id, _c, ia_cik, *_r),) = _row("IA")
    assert ia_cik == "0000836690"
    path = snap / "nasdaqlisted.txt"
    text = path.read_text()
    line = next(ln for ln in text.splitlines() if ln.startswith("IA|"))
    flipped = line.rsplit("|", 2)
    assert flipped[1] == "N"  # the ETF column
    path.write_text(text.replace(line, "|".join([flipped[0], "Y", flipped[2]])))
    out = _run(
        "--from-snapshot",
        str(snap),
        "--run-date",
        "2026-09-11",
        "--report",
        str(tmp_path / "a.csv"),
    )
    assert "update 1" in _plan_line(out) and "insert 0" in _plan_line(out)
    assert _row("IA") == [(ia_id, "etf", "0000836690", None, True, None, "IA")]
    _restore(snap, "nasdaqlisted.txt")
    _run(
        "--from-snapshot",
        str(snap),
        "--run-date",
        "2026-09-18",
        "--report",
        str(tmp_path / "b.csv"),
    )
    assert _row("IA") == [(ia_id, "stock", "0000836690", None, True, None, "IA")]


# ── the circuit breaker: a truncated directory writes nothing ──


def test_a_truncated_directory_is_refused_and_nothing_is_written(
    snap: Path, tmp_path: Path
) -> None:
    before = _counts()
    ((stamp,),) = _sql("select max(updated_at) from atlas_global.instrument_master")
    path = snap / "nasdaqlisted.txt"
    lines = path.read_text().splitlines(keepends=True)
    # (a) cut short: no "File Creation Time" trailer — the parser refuses the file.
    path.write_text("".join(lines[:1500]))
    out = _run("--from-snapshot", str(snap), "--run-date", "2026-09-11", expect=1)
    assert "truncated download?" in out
    # (b) 300 real rows missing but the trailer intact — the planner refuses: exit 2.
    path.write_text("".join(lines[:1] + lines[301:]))
    out = _run("--from-snapshot", str(snap), "--run-date", "2026-09-11", expect=2)
    assert "REFUSED: refusing to deactivate 300 of 13,154 active rows (cap 200" in out
    assert _counts() == before
    ((after,),) = _sql("select max(updated_at) from atlas_global.instrument_master")
    assert after == stamp  # not a single row touched
    _restore(snap, "nasdaqlisted.txt")


# ── a listing that flickers out of one weekly file: BZZ (no SEC row, no Tiingo row) ──


def test_a_flickered_no_cik_row_is_reactivated_under_its_first_key(
    snap: Path, tmp_path: Path
) -> None:
    ((bzz_id, _c, cik, _s, _a, _d, _sym),) = _row("BZZ")
    assert cik is None
    path = snap / "otherlisted.txt"
    text = path.read_text()
    line = next(ln for ln in text.splitlines(keepends=True) if ln.startswith("BZZ|"))
    path.write_text(text.replace(line, ""))
    out = _run(
        "--from-snapshot",
        str(snap),
        "--run-date",
        "2026-09-11",
        "--report",
        str(tmp_path / "a.csv"),
    )
    assert "deactivate 1" in _plan_line(out)
    _restore(snap, "otherlisted.txt")
    back = _run(
        "--from-snapshot",
        str(snap),
        "--run-date",
        "2026-09-18",
        "--report",
        str(tmp_path / "b.csv"),
    )
    assert "reactivate 1" in _plan_line(back) and "insert 0" in _plan_line(back)
    ((iid, _c, _k, _s, active, delisted, _sym),) = _row("BZZ")
    assert (iid, active, delisted) == (bzz_id, True, None)  # the 2026-09-04 key, not a 09-18 one


# ── manual rows are never auto-deactivated ──


def test_a_manual_row_absent_from_the_directory_stays_active(snap: Path, tmp_path: Path) -> None:
    _sql(
        "insert into atlas_global.instrument_master (instrument_id, asset_class, symbol, name, "
        "exchange, is_active, source) values (gen_random_uuid(), 'stock', 'ANTM', "
        "'Anthem, Inc. (FM-entered)', 'NYSE', true, 'manual')"
    )
    out = _run(
        "--from-snapshot",
        str(snap),
        "--run-date",
        "2026-09-25",
        "--report",
        str(tmp_path / "a.csv"),
    )
    assert "deactivate 0" in _plan_line(out)
    assert [(r[4], r[5]) for r in _row("ANTM")] == [(True, None)]
    assert any("manual row absent" in ln for ln in (tmp_path / "a.csv").read_text().splitlines())
    _sql("delete from atlas_global.instrument_master where symbol = 'ANTM' and source = 'manual'")
