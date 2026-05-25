"""Tests for ``scripts/rebuild_v3_cache.py``.

Validates the schema + behavior of the v3 cache builder without hitting
a real Postgres. We monkeypatch the engine seam so a synthetic OHLCV
result-set is streamed through the chunked-fetch path, then check the
output pickle matches the contract documented in
:mod:`atlas.discovery.engine` (4 columns: ``date``, ``iid``, ``close``,
``volume``; correct dtypes).
"""

from __future__ import annotations

import importlib
import json
import pickle
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Stub engine — emulates SQLAlchemy's stream_results + fetchmany API
# ---------------------------------------------------------------------------


class _StubResult:
    """Minimal SQLAlchemy ``Result``-like object for fetchmany chunking."""

    def __init__(self, rows: list[tuple[Any, ...]], keys: list[str]) -> None:
        self._rows = rows
        self._keys = keys
        self._idx = 0

    def keys(self) -> list[str]:
        return list(self._keys)

    def fetchmany(self, n: int) -> list[tuple[Any, ...]]:
        chunk = self._rows[self._idx : self._idx + n]
        self._idx += n
        return chunk

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows[self._idx :]


class _StubConn:
    """Connection stub returning canned results per SQL token."""

    def __init__(self, ohlcv_rows: list[tuple[Any, ...]], nifty_rows: list[tuple[Any, ...]]):
        self._ohlcv_rows = ohlcv_rows
        self._nifty_rows = nifty_rows

    def execution_options(self, **_kwargs: Any) -> _StubConn:
        return self

    def execute(self, sql: Any, _params: dict[str, Any] | None = None) -> _StubResult:
        text = str(sql)
        if "de_index_prices" in text:
            return _StubResult(self._nifty_rows, ["date", "close"])
        return _StubResult(self._ohlcv_rows, ["date", "iid", "close", "volume"])

    def close(self) -> None:
        return None

    def __enter__(self) -> _StubConn:
        return self

    def __exit__(self, *_a: Any) -> None:
        return None


class _StubEngine:
    """SQLAlchemy ``Engine`` stub good enough for rebuild_v3_cache."""

    def __init__(
        self,
        ohlcv_rows: list[tuple[Any, ...]],
        nifty_rows: list[tuple[Any, ...]],
    ) -> None:
        self._ohlcv_rows = ohlcv_rows
        self._nifty_rows = nifty_rows

    def connect(self) -> _StubConn:
        return _StubConn(self._ohlcv_rows, self._nifty_rows)


# ---------------------------------------------------------------------------
# Module loader — script lives outside the package, load via importlib
# ---------------------------------------------------------------------------


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    if "rebuild_v3_cache" in sys.modules:
        return importlib.reload(sys.modules["rebuild_v3_cache"])
    return importlib.import_module("rebuild_v3_cache")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_db_rows() -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    """Build a small OHLCV + Nifty result-set spanning 2015..2026.

    Includes:
    * 8 currently-trading iids (last trade = 2026-05-22)
    * 2 historically-delisted iids (last trade = 2019-12-31)

    This is exactly the shape :func:`atlas.discovery.engine._load_cache_files`
    expects to receive on disk, after the rebuild script writes it.
    """
    alive_iids = [f"iid_alive_{k:02d}" for k in range(8)]
    delisted_iids = [f"iid_dead_{k:02d}" for k in range(2)]
    rows: list[tuple[Any, ...]] = []
    # 2015-01-01 → 2026-05-22 alive iids
    start = date(2015, 1, 1)
    alive_end = date(2026, 5, 22)
    dead_end = date(2019, 12, 31)
    cur = start
    while cur <= alive_end:
        for iid in alive_iids:
            rows.append((cur, iid, 100.0 + (cur.toordinal() % 50), 100_000))
        if cur <= dead_end:
            for iid in delisted_iids:
                rows.append((cur, iid, 50.0, 50_000))
        cur += timedelta(days=1)
    # Nifty 500 series
    nifty_rows: list[tuple[Any, ...]] = []
    cur = start
    while cur <= alive_end:
        nifty_rows.append((cur, 10000.0 + (cur.toordinal() % 200)))
        cur += timedelta(days=1)
    return rows, nifty_rows


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_rebuild_v3_cache_emits_correct_shape(
    tmp_path: Path,
    synthetic_db_rows: tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]],
) -> None:
    """v3 cache pickle has the (date, iid, close, volume) columns + dtypes
    that :func:`atlas.discovery.engine._load_cache_files` consumes.
    """
    mod = _load_module()
    ohlcv_rows, nifty_rows = synthetic_db_rows
    engine = _StubEngine(ohlcv_rows, nifty_rows)

    output = tmp_path / "v3.pkl"
    stats = mod.rebuild_v3_cache(
        output=output,
        since=date(2015, 1, 1),
        nifty500_output=tmp_path / "nifty.pkl",
        blacklist_output=tmp_path / "blacklist.json",
        inherit_blacklist=None,
        engine=engine,
    )
    assert output.exists()
    # pickles in this test are produced by rebuild_v3_cache itself in tmp_path
    # — never user input. The S301 advisory does not apply.
    df = pd.read_pickle(output)  # noqa: S301
    assert list(df.columns) == ["date", "iid", "close", "volume"]
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert pd.api.types.is_object_dtype(df["iid"])
    assert pd.api.types.is_float_dtype(df["close"])
    assert pd.api.types.is_integer_dtype(df["volume"])
    # Both alive AND delisted iids present (the load-bearing invariant).
    assert stats.unique_instruments == 10
    # Nifty pickle is a Series indexed by date.
    nifty = pd.read_pickle(tmp_path / "nifty.pkl")  # noqa: S301
    assert isinstance(nifty, pd.Series)
    assert isinstance(nifty.index, pd.DatetimeIndex)
    # Blacklist defaults to empty list.
    with (tmp_path / "blacklist.json").open() as fh:
        bl = json.load(fh)
    assert bl == []


def test_rebuild_v3_cache_includes_delisted_instruments(
    tmp_path: Path,
    synthetic_db_rows: tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]],
) -> None:
    """v3 must retain historically-delisted names — this is the WHOLE
    reason for the rebuild. Smoke test: at least one iid has its last
    trade before 2020.
    """
    mod = _load_module()
    ohlcv_rows, nifty_rows = synthetic_db_rows
    engine = _StubEngine(ohlcv_rows, nifty_rows)
    output = tmp_path / "v3.pkl"
    stats = mod.rebuild_v3_cache(
        output=output,
        since=date(2015, 1, 1),
        nifty500_output=tmp_path / "nifty.pkl",
        blacklist_output=tmp_path / "blacklist.json",
        inherit_blacklist=None,
        engine=engine,
    )
    # pickle produced by rebuild_v3_cache in tmp_path; not user input.
    df = pd.read_pickle(output)  # noqa: S301
    last_by_iid = df.groupby("iid")["date"].max()
    delisted = last_by_iid[last_by_iid < pd.Timestamp("2020-01-01")]
    assert len(delisted) >= 1, "v3 cache must include historically-delisted iids; got none"
    # The stats helper agrees.
    assert stats.delisted_iids_in_data >= 1


def test_rebuild_v3_cache_covers_methodology_lock_windows(
    tmp_path: Path,
    synthetic_db_rows: tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]],
) -> None:
    """Date range must start at or before 2015-01-01 to give the
    walk-forward windows the burn-in they need (CONTEXT.md §"Universe (M1)").
    """
    mod = _load_module()
    ohlcv_rows, nifty_rows = synthetic_db_rows
    engine = _StubEngine(ohlcv_rows, nifty_rows)
    output = tmp_path / "v3.pkl"
    stats = mod.rebuild_v3_cache(
        output=output,
        since=date(2015, 1, 1),
        nifty500_output=tmp_path / "nifty.pkl",
        blacklist_output=tmp_path / "blacklist.json",
        inherit_blacklist=None,
        engine=engine,
    )
    assert stats.date_min is not None
    assert stats.date_min <= pd.Timestamp("2015-01-02")
    assert stats.date_max is not None
    assert stats.date_max >= pd.Timestamp("2026-05-01")


def test_rebuild_v3_cache_inherits_blacklist_when_provided(
    tmp_path: Path,
    synthetic_db_rows: tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]],
) -> None:
    """`--inherit-blacklist` copies the source list into the output JSON."""
    mod = _load_module()
    ohlcv_rows, nifty_rows = synthetic_db_rows
    engine = _StubEngine(ohlcv_rows, nifty_rows)
    src_blacklist = tmp_path / "src_blacklist.json"
    src_blacklist.write_text(json.dumps([{"iid": "iid_dead_00", "symbol": "DEAD0"}]))
    stats = mod.rebuild_v3_cache(
        output=tmp_path / "v3.pkl",
        since=date(2015, 1, 1),
        nifty500_output=tmp_path / "nifty.pkl",
        blacklist_output=tmp_path / "blacklist.json",
        inherit_blacklist=src_blacklist,
        engine=engine,
    )
    assert stats.unique_instruments == 10
    with (tmp_path / "blacklist.json").open() as fh:
        bl = json.load(fh)
    assert bl == [{"iid": "iid_dead_00", "symbol": "DEAD0"}]


def test_rebuild_v3_cache_raises_when_db_returns_empty(tmp_path: Path) -> None:
    """Defensive: an empty OHLCV result is a config error, not a silent zero-cache."""
    mod = _load_module()
    engine = _StubEngine(ohlcv_rows=[], nifty_rows=[])
    with pytest.raises(RuntimeError, match="zero rows"):
        mod.rebuild_v3_cache(
            output=tmp_path / "v3.pkl",
            since=date(2015, 1, 1),
            nifty500_output=tmp_path / "nifty.pkl",
            blacklist_output=tmp_path / "blacklist.json",
            inherit_blacklist=None,
            engine=engine,
        )


def test_rebuild_v3_cache_pickle_roundtrips_through_pickle_load(
    tmp_path: Path,
    synthetic_db_rows: tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]],
) -> None:
    """Exact ``pickle.load`` path that the engine's ``_load_cache_files``
    uses must succeed against the produced pickle.
    """
    mod = _load_module()
    ohlcv_rows, nifty_rows = synthetic_db_rows
    engine = _StubEngine(ohlcv_rows, nifty_rows)
    output = tmp_path / "v3.pkl"
    mod.rebuild_v3_cache(
        output=output,
        since=date(2015, 1, 1),
        nifty500_output=tmp_path / "nifty.pkl",
        blacklist_output=tmp_path / "blacklist.json",
        inherit_blacklist=None,
        engine=engine,
    )
    with output.open("rb") as fh:
        df = pickle.load(fh)  # noqa: S301
    assert isinstance(df, pd.DataFrame)
    assert {"date", "iid", "close", "volume"}.issubset(df.columns)
