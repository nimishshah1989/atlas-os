"""write_health_snapshot's pure pieces on the weekly orchestrator's REAL runfile rows and the
Labor Day week calendar (``script_loader.LABOR_DAY_WEEK``).

The four runfile lines are the rows ``scripts/ops/atlas_global_weekly.sh`` wrote on its first
end-to-end run (2026-09-04, EOD 2026-09-03, a scratch clone of the identity database),
re-serialised in the orchestrator's own TSV format: real step names, real timings, the real
gate outcome (freshness_guard FAILED on ``macro_daily: EMPTY`` — no FRED key in the sandbox).
The stubbed counts and max() values are that clone's own answers, quoted where they are used.

Pure: no DB, no network. ``_gdb`` is imported for its path setup only.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tests.unit.global_market.script_loader import LABOR_DAY_WEEK, load_global_script

whs = load_global_script("write_health_snapshot")

pytestmark = pytest.mark.unit

NY = ZoneInfo("America/New_York")
NOW = dt.datetime(2026, 9, 4, 10, 44, 21, tzinfo=NY)

WEEKLY_RUNFILE = (
    "build_identity\t2026-09-04T14:43:51+00:00\t2026-09-04T14:44:01+00:00\tsuccess\n"
    "seed_benchmarks\t2026-09-04T14:44:01+00:00\t2026-09-04T14:44:02+00:00\tsuccess\n"
    "ingest_index_membership\t2026-09-04T14:44:02+00:00\t2026-09-04T14:44:20+00:00\tsuccess\n"
    "freshness_guard\t2026-09-04T14:44:20+00:00\t2026-09-04T14:44:21+00:00\tfailed\n"
)

# `select count(*), max(<col>)` on atlas_p1f_rev (a clone of that 2026-09-04 identity run),
# read 2026-09-04: instrument_master 13,429 rows / updated_at 2026-09-04 14:51:44+00;
# ohlcv_daily 5,414 rows / date 2026-09-03; macro_daily, technical_daily, universe_snapshot 0.
INSTRUMENT_MASTER_ROWS = 13_429
INSTRUMENT_MASTER_MAX = dt.datetime(2026, 9, 4, 14, 51, 44, tzinfo=dt.UTC)
OHLCV_ROWS = 5_414
OHLCV_MAX = dt.date(2026, 9, 3)


@pytest.fixture
def runfile(tmp_path: Path) -> Path:
    p = tmp_path / "atlas_global_weekly_runs.tsv"
    p.write_text(WEEKLY_RUNFILE)
    return p


# ── run rows ──


def test_the_weekly_runfile_becomes_one_run_row_per_step(runfile: Path) -> None:
    steps = whs.read_runfile(runfile)
    rows = whs.run_rows(steps, "weekly", "vm", "7f24769", NOW)
    assert [r["script_name"] for r in rows] == [
        "build_identity",
        "seed_benchmarks",
        "ingest_index_membership",
        "freshness_guard",
    ]
    assert [r["status"] for r in rows] == ["success", "success", "success", "failed"]
    assert {r["milestone"] for r in rows} == {"weekly"}
    assert rows[0]["started_at"] == "2026-09-04T14:43:51+00:00"
    assert rows[0]["ended_at"] == "2026-09-04T14:44:01+00:00"
    assert rows[0]["host"] == "vm" and rows[0]["git_sha"] == "7f24769"
    assert rows[0]["updated_at"] == NOW
    assert len({r["run_id"] for r in rows}) == 4
    # The idempotency key: the same runfile always mints the same ids, and each of
    # (milestone, step, started_at) changes them.
    again = whs.run_rows(whs.read_runfile(runfile), "weekly", "vm", "7f24769", NOW)
    assert [r["run_id"] for r in again] == [r["run_id"] for r in rows]
    first = rows[0]["run_id"]
    assert first == whs.run_id("weekly", "build_identity", "2026-09-04T14:43:51+00:00")
    assert first != whs.run_id("daily", "build_identity", "2026-09-04T14:43:51+00:00")
    assert first != whs.run_id("weekly", "build_identity", "2026-09-04T14:43:52+00:00")
    assert first != whs.run_id("weekly", "seed_benchmarks", "2026-09-04T14:43:51+00:00")


def test_only_gate_steps_become_validator_rows_sharing_the_gates_run_id(runfile: Path) -> None:
    steps = whs.read_runfile(runfile)
    runs = {r["script_name"]: r for r in whs.run_rows(steps, "weekly", "vm", None, NOW)}
    validators = whs.validator_rows(steps, "weekly", "vm", None, NOW)
    assert len(validators) == 1
    v = validators[0]
    assert v["validator"] == "freshness_guard"
    assert v["status"] == "FAIL" and v["failures"] == 1 and v["total_checks"] == 1
    assert v["ran_at"] == "2026-09-04T14:44:21+00:00"
    assert v["run_id"] == runs["freshness_guard"]["run_id"]


def test_validator_names_fit_the_sixteen_character_column() -> None:
    assert all(len(v) <= 16 for v in whs._GATE_VALIDATORS.values())


def test_a_malformed_runfile_line_is_skipped(tmp_path: Path) -> None:
    p = tmp_path / "runs.tsv"
    p.write_text(
        "\t2026-09-04T14:43:51+00:00\t2026-09-04T14:44:01+00:00\tsuccess\n"  # no name
        "seed_benchmarks\t2026-09-04T14:44:01+00:00\n"  # too few fields
        "freshness_guard\t2026-09-04T14:44:20+00:00\t\tfailed\n"  # no end: allowed
    )
    steps = whs.read_runfile(p)
    # Four columns in, five out: the reason column is "" when the line never carried one.
    assert steps == [("freshness_guard", "2026-09-04T14:44:20+00:00", "", "failed", "")]
    (row,) = whs.run_rows(steps, "daily", "vm", None, NOW)
    assert row["ended_at"] is None
    (v,) = whs.validator_rows(steps, "daily", "vm", None, NOW)
    assert v["ran_at"] == NOW  # no end stamp → the snapshot's own clock


# ── freshness rows ──


def test_lag_is_counted_in_spy_sessions_not_calendar_days() -> None:
    eod = dt.date(2026, 9, 8)
    mx = dt.date(2026, 9, 4)  # four calendar days, ONE session (09-08) behind
    fresh = whs.freshness_row("macro_daily", 2_690, mx, eod, LABOR_DAY_WEEK, (3, "critical"), NOW)
    assert fresh["value_today"] == 1
    assert fresh["is_anomaly"] is False and fresh["severity"] == "info"
    assert fresh["metric_name"] == "freshness_lag_sessions"
    assert fresh["data_date"] == eod and fresh["computed_at"] == NOW
    assert "2,690 rows; latest 2026-09-04; lag in sessions" in fresh["notes"]
    assert "tolerance 3 session(s), critical when exceeded" in fresh["notes"]

    stale = whs.freshness_row("macro_daily", 2_690, mx, eod, LABOR_DAY_WEEK, (0, "critical"), NOW)
    assert stale["value_today"] == 1
    assert stale["is_anomaly"] is True and stale["severity"] == "critical"

    board = whs.freshness_row("index_membership", 503, mx, eod, LABOR_DAY_WEEK, (0, "warn"), NOW)
    assert board["is_anomaly"] is True and board["severity"] == "warn"


def test_without_spy_bars_there_is_no_lag_and_the_note_says_so() -> None:
    guarded = whs.freshness_row(
        "instrument_master",
        INSTRUMENT_MASTER_ROWS,
        INSTRUMENT_MASTER_MAX,
        dt.date(2026, 9, 8),
        [],
        (8, "warn"),
        NOW,
    )
    assert guarded["value_today"] is None
    assert "13,429 rows; latest 2026-09-04; no SPY bar: no session calendar" in guarded["notes"]
    assert guarded["is_anomaly"] is True and guarded["severity"] == "warn"  # the guard FAILS too

    unguarded = whs.freshness_row(
        "ohlcv_daily", OHLCV_ROWS, OHLCV_MAX, dt.date(2026, 9, 8), [], None, NOW
    )
    assert unguarded["value_today"] is None
    assert unguarded["is_anomaly"] is False and unguarded["severity"] == "info"


def test_an_empty_guarded_table_is_flagged_and_an_unguarded_one_is_only_reported() -> None:
    eod = dt.date(2026, 9, 3)
    key = whs.freshness_row("macro_daily", 0, None, eod, LABOR_DAY_WEEK, (3, "critical"), NOW)
    assert key["value_today"] is None
    assert key["is_anomaly"] is True and key["severity"] == "critical"
    assert key["notes"].startswith("EMPTY;")

    unguarded = whs.freshness_row("technical_daily", 0, None, eod, LABOR_DAY_WEEK, None, NOW)
    assert unguarded["value_today"] is None
    assert unguarded["is_anomaly"] is False and unguarded["severity"] == "info"
    assert unguarded["notes"] == "EMPTY; not guarded by freshness_guard yet"

    fresh_unguarded = whs.freshness_row(
        "ohlcv_daily", OHLCV_ROWS, OHLCV_MAX, eod, LABOR_DAY_WEEK, None, NOW
    )
    assert fresh_unguarded["value_today"] == 0
    assert fresh_unguarded["is_anomaly"] is False
    assert fresh_unguarded["notes"].endswith("; not guarded by freshness_guard yet")


def test_every_tracked_table_the_guard_watches_is_tracked_here() -> None:
    tracked = {t for t, _c in whs.TRACKED}
    guarded = {t for t, _c, _l in whs.guard.KEY_TABLES + whs.guard.BOARD_TABLES}
    assert guarded <= tracked, f"guarded but not tracked: {sorted(guarded - tracked)}"


def _clone_scalar(asked: list[str]):
    """``_gdb.scalar`` answering as the 2026-09-04 clone does (the constants above)."""

    def scalar(sql: str, _params: dict | None = None):
        asked.append(sql)
        table = sql.split(f"{whs.M}.")[1].split()[0]
        if sql.startswith("select count"):
            return {"instrument_master": INSTRUMENT_MASTER_ROWS, "ohlcv_daily": OHLCV_ROWS}.get(
                table, 0
            )
        return {"instrument_master": INSTRUMENT_MASTER_MAX, "ohlcv_daily": OHLCV_MAX}.get(table)

    return scalar


def test_freshness_rows_query_each_tracked_table_once_on_the_guards_registries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live path: one count and one max per tracked table, the guard's own calendar, and
    the guard's registries as the ONE place a table's tolerance and tier are written."""
    asked: list[str] = []
    monkeypatch.setattr(whs._gdb, "scalar", _clone_scalar(asked))
    monkeypatch.setattr(whs.guard, "spy_sessions", lambda: LABOR_DAY_WEEK)
    rows = whs.freshness_rows(dt.date(2026, 9, 3), NOW)
    assert [r["table_name"] for r in rows] == [t for t, _c in whs.TRACKED]
    assert len(asked) == 2 * len(whs.TRACKED)
    by_table = {r["table_name"]: r for r in rows}
    assert by_table["instrument_master"]["value_today"] == 0  # 14:51 UTC = Fri 09-04 in New York
    assert by_table["ohlcv_daily"]["value_today"] == 0
    for table, _col, lag in whs.guard.KEY_TABLES:
        assert f"tolerance {lag} session(s), critical when exceeded" in by_table[table]["notes"]
    for table, _col, lag in whs.guard.BOARD_TABLES:
        assert f"tolerance {lag} session(s), warn when exceeded" in by_table[table]["notes"]
    assert by_table["macro_daily"]["is_anomaly"] is True  # EMPTY on a KEY table: critical
    assert by_table["macro_daily"]["severity"] == "critical"
    # technical_daily joined KEY_TABLES with P1-D, so an EMPTY one is now critical, not
    # ignorable: the board's returns, relative strength and risk all read from it.
    assert by_table["technical_daily"]["is_anomaly"] is True
    assert by_table["technical_daily"]["severity"] == "critical"


def test_a_table_that_cannot_be_read_is_skipped_not_fatal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing table or a statement timeout loses that row, never the snapshot (India)."""
    asked: list[str] = []
    clone = _clone_scalar(asked)

    def scalar(sql: str, _params: dict | None = None):
        if "universe_snapshot" in sql:
            raise RuntimeError('relation "atlas_global.universe_snapshot" does not exist')
        return clone(sql, _params)

    monkeypatch.setattr(whs._gdb, "scalar", scalar)
    monkeypatch.setattr(whs.guard, "spy_sessions", lambda: LABOR_DAY_WEEK)
    rows = whs.freshness_rows(dt.date(2026, 9, 3), NOW)
    assert [r["table_name"] for r in rows] == [
        t for t, _c in whs.TRACKED if t != "universe_snapshot"
    ]
    assert "skip universe_snapshot: relation" in capsys.readouterr().err


# ── the fifth column: why a step failed ──────────────────────────────────────


def test_failed_step_reason_reaches_error_message_and_green_row_has_none(tmp_path: Path) -> None:
    """Four-column lines (every runfile before 2026-09-09) still parse; a fifth column lands in
    error_message; success rows carry NULL, never "". The lines are TSV shapes, not data."""
    p = tmp_path / "runs.tsv"
    p.write_text(
        "ingest_prices\t2026-09-08T01:00:00+00:00\t2026-09-08T01:00:12+00:00\tfailed\t"
        "rc=1: alpaca: 403 forbidden — check ALPACA_API_KEY in the box .env\n"
        "ingest_macro\t2026-09-08T01:00:12+00:00\t2026-09-08T01:00:19+00:00\tsuccess\t\n"
        "compute_technicals\t2026-09-08T01:00:19+00:00\t2026-09-08T01:00:24+00:00\tfailed\n"
    )
    steps = whs.read_runfile(p)
    rows = {r["script_name"]: r for r in whs.run_rows(steps, "daily", "vm", None, NOW)}
    assert rows["ingest_prices"]["error_message"].startswith("rc=1: alpaca: 403")
    assert rows["ingest_macro"]["error_message"] is None
    assert rows["compute_technicals"]["error_message"] is None  # four columns: no reason recorded
    # gate rows unpack the wider tuple without complaint
    assert whs.validator_rows(whs.read_runfile(p), "daily", "vm", None, NOW) == []


def test_a_reason_never_carries_a_credential_onto_the_open_board() -> None:
    """The shapes a traceback takes — requests' HTTPError with the keyed URL, a connection
    string, an Authorization header, Alpaca's key headers — each lose the value and nothing
    else. Placeholder values, deliberately low-entropy: this asserts on text shape, not data."""
    fred = (
        "403 Client Error: Forbidden for url: https://api.stlouisfed.org/fred/series/"
        "observations?series_id=SP500&api_key=aaaaaaaaaaaaaaaa&file_type=json"
    )
    assert whs.redact(fred) == (
        "403 Client Error: Forbidden for url: https://api.stlouisfed.org/fred/series/"
        "observations?series_id=SP500&api_key=***&file_type=json"
    )
    dsn = "connection to postgresql://atlas_global_app.abc:pw@aws-1.pooler.supabase.com:6543/pg"
    assert whs.redact(dsn) == (
        "connection to postgresql://atlas_global_app.abc:***@aws-1.pooler.supabase.com:6543/pg"
    )
    hdr = (
        "{'Authorization': 'Bearer aaaaaaaaaaaa', 'APCA-API-KEY-ID': 'aaaa', "
        "'APCA-API-SECRET-KEY': 'bbbb'}"
    )
    out = whs.redact(hdr)
    assert "aaaaaaaaaaaa" not in out and "'aaaa'" not in out and "'bbbb'" not in out
    assert "APCA-API-KEY-ID" in out  # the NAME survives, so the reader knows which header
    plain = "rc=1: ingest_prices: SPY has no bar for 2026-09-08 (series_id=SP500 checked)"
    assert whs.redact(plain) == plain
