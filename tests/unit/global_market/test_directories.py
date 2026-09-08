"""providers/directories.py without the network: snapshot round-trip on the real fixture
bytes (provenance without a manifest), the pacing and the retry on a fake clock, the
fair-access guard and the HTTP error path (a stub session — the only fabricated thing here
is an HTTP status, never a record)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from atlas.global_market.providers import directories as dirs

pytestmark = pytest.mark.unit

IDENTITY = "Test Person test@example.com"


def test_the_required_and_optional_files_are_derived_from_the_file_table() -> None:
    assert dirs.REQUIRED == (
        "nasdaqlisted.txt",
        "otherlisted.txt",
        "company_tickers.json",
        "company_tickers_mf.json",
    )
    assert dirs.OPTIONAL == {"company_tickers_exchange.json", "supported_tickers.zip"}
    assert dirs.endpoint("company_tickers.json") == "files/company_tickers.json"
    assert dirs.endpoint("supported_tickers.zip") == "docs/tiingo/daily/supported_tickers.zip"


# ── snapshots ──


def test_the_fixture_directory_is_a_readable_snapshot_without_a_manifest(
    symbology_dir: Path,
) -> None:
    snap = dirs.read_snapshot(symbology_dir)
    assert set(dirs.REQUIRED) <= set(snap.files)
    assert dirs.TIINGO_SUPPORTED_TICKERS in snap.files
    assert dirs.SEC_COMPANY_TICKERS_EXCHANGE not in snap.files  # optional, not committed
    # Hashes are recomputed from the bytes and match SOURCE.md.
    assert snap.sha256s[dirs.NASDAQ_LISTED].startswith("13d854464760097a")
    assert snap.sha256s[dirs.SEC_COMPANY_TICKERS_MF].startswith("5e1d35e69f868300")
    # No manifest: the fetch times are unknown, and say so — never a file's mtime.
    assert snap.provenance == dirs.PROVENANCE_FIXTURE
    assert set(snap.fetched_at.values()) == {None}
    assert snap.text(dirs.NASDAQ_LISTED).startswith("Symbol|Security Name|")
    csv_text = snap.tiingo_csv()
    assert csv_text is not None and csv_text.startswith("ticker,exchange,assetType")


def test_write_then_read_round_trips_bytes_and_manifest(
    symbology_dir: Path, tmp_path: Path
) -> None:
    snap = dirs.read_snapshot(symbology_dir)
    manifest = dirs.write_snapshot(tmp_path / "snap", snap)
    assert manifest.name == dirs.MANIFEST
    meta = json.loads(manifest.read_text())
    assert meta[dirs.NASDAQ_LISTED]["sha256"] == snap.sha256s[dirs.NASDAQ_LISTED]
    assert meta[dirs.NASDAQ_LISTED]["url"] == dirs.FILES[dirs.NASDAQ_LISTED][1]
    assert meta[dirs.NASDAQ_LISTED]["fetched_at"] is None  # unknown stays unknown
    back = dirs.read_snapshot(tmp_path / "snap")
    assert back.files == snap.files
    assert back.sha256s == snap.sha256s
    assert back.fetched_at == snap.fetched_at
    assert back.provenance == dirs.PROVENANCE_SNAPSHOT  # a manifest was there


def test_a_snapshot_missing_a_required_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / dirs.NASDAQ_LISTED).write_bytes(b"Symbol|\n")
    with pytest.raises(FileNotFoundError, match="lacks"):
        dirs.read_snapshot(tmp_path)


def test_prune_keeps_the_newest_dated_snapshots_and_nothing_else(tmp_path: Path) -> None:
    for name in ("2026-08-14", "2026-08-21", "2026-08-28", "2026-09-04", "notes", "latest"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "x").write_text("x")
    removed = dirs.prune_snapshots(tmp_path, keep=2)
    assert [p.name for p in removed] == ["2026-08-14", "2026-08-21"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "2026-08-28",
        "2026-09-04",
        "latest",
        "notes",
    ]
    assert dirs.prune_snapshots(tmp_path, keep=8) == []


# ── the provider on a stub session ──


class _Response:
    def __init__(self, status: int, content: bytes = b"") -> None:
        self.status_code = status
        self.content = content


class _Session:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str], timeout: int) -> _Response:
        self.requests.append((url, headers))
        return self.responses.pop(0)


class _Clock:
    """A monotonic clock the test advances by hand; ``sleep`` advances it and is recorded."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _provider(responses: list[_Response], clock: _Clock | None = None) -> dirs.DirectoryProvider:
    clock = clock or _Clock()
    return dirs.DirectoryProvider(
        _Session(responses),  # type: ignore[arg-type]
        clock=clock,
        sleep=clock.sleep,
    )


def test_sec_fetches_refuse_to_run_without_a_contact_identity(monkeypatch) -> None:
    class NeverCalled:
        def get(self, *_a, **_k):  # pragma: no cover - the guard fires first
            raise AssertionError("no request may be sent without an identity")

    p = dirs.DirectoryProvider(NeverCalled())  # type: ignore[arg-type]
    monkeypatch.delenv("EDGAR_IDENTITY", raising=False)
    with pytest.raises(RuntimeError, match="EDGAR_IDENTITY"):
        p.fetch_all()
    monkeypatch.setenv("EDGAR_IDENTITY", "Firstname Lastname")  # a name is not a contact
    with pytest.raises(RuntimeError, match="contact address"):
        p.fetch_all()
    assert sum(p.calls.values()) == 0  # nothing spent


def test_a_429_is_retried_once_after_the_backoff_then_raises(monkeypatch) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", IDENTITY)
    clock = _Clock()
    p = _provider([_Response(429), _Response(429)], clock)
    with pytest.raises(RuntimeError, match="HTTP 429"):
        p.fetch(dirs.SEC_COMPANY_TICKERS)
    assert p.calls == Counter({"files/company_tickers.json": 2})  # both attempts spent budget
    assert dirs.RETRY_BACKOFF_S in clock.slept
    (url, headers) = p._session.requests[0]  # type: ignore[attr-defined]
    assert url == dirs.FILES[dirs.SEC_COMPANY_TICKERS][1]
    assert headers["User-Agent"] == IDENTITY  # the fair-access contact


def test_a_503_then_a_200_returns_the_body(symbology_dir: Path, monkeypatch) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", IDENTITY)
    body = (symbology_dir / dirs.SEC_COMPANY_TICKERS_MF).read_bytes()
    p = _provider([_Response(503), _Response(200, body)])
    assert p.fetch(dirs.SEC_COMPANY_TICKERS_MF) == body
    assert p.calls == Counter({"files/company_tickers_mf.json": 2})


def test_a_404_and_an_empty_200_fail_without_a_retry(monkeypatch) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", IDENTITY)
    p = _provider([_Response(404)])
    with pytest.raises(RuntimeError, match="HTTP 404"):
        p.fetch(dirs.SEC_COMPANY_TICKERS)
    p = _provider([_Response(200, b"")])
    with pytest.raises(RuntimeError, match="empty response"):
        p.fetch(dirs.NASDAQ_LISTED)
    assert p.calls == Counter({"dynamic/SymDir/nasdaqlisted.txt": 1})


def test_sec_requests_are_paced_and_the_others_are_not(symbology_dir: Path, monkeypatch) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", IDENTITY)
    body = (symbology_dir / dirs.SEC_COMPANY_TICKERS).read_bytes()
    clock = _Clock()
    p = _provider([_Response(200, body)] * 3, clock)
    p.fetch(dirs.SEC_COMPANY_TICKERS)  # first SEC call: no wait
    p.fetch(dirs.SEC_COMPANY_TICKERS_MF)  # same instant: waits the whole interval
    assert clock.slept == [pytest.approx(dirs.SEC_MIN_INTERVAL_S)]
    clock.now += dirs.SEC_MIN_INTERVAL_S / 2
    p.fetch(dirs.SEC_COMPANY_TICKERS_MF)  # half the interval elapsed: waits the other half
    assert clock.slept[-1] == pytest.approx(dirs.SEC_MIN_INTERVAL_S / 2)
    nasdaq = _provider([_Response(200, body)], clock)
    nasdaq.fetch(dirs.NASDAQ_LISTED)
    assert clock.slept[-1] == pytest.approx(dirs.SEC_MIN_INTERVAL_S / 2)  # nothing new


def test_nasdaq_fetch_uses_the_plain_user_agent(symbology_dir: Path) -> None:
    body = (symbology_dir / dirs.NASDAQ_LISTED).read_bytes()
    p = _provider([_Response(200, body)])  # no identity needed
    assert p.fetch(dirs.NASDAQ_LISTED) == body
    (_url, headers) = p._session.requests[0]  # type: ignore[attr-defined]
    assert headers["User-Agent"] == dirs.USER_AGENT
    assert "github.com/nimishshah1989/atlas-os" in dirs.USER_AGENT
    assert p.calls == Counter({"dynamic/SymDir/nasdaqlisted.txt": 1})


def test_fetch_all_returns_every_file_with_a_fetch_time(symbology_dir: Path, monkeypatch) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", IDENTITY)
    real = dirs.read_snapshot(symbology_dir)
    responses = [
        _Response(200, real.files.get(name) or b'{"fields": [], "data": []}') for name in dirs.FILES
    ]
    p = _provider(responses)
    snap = p.fetch_all()
    assert list(snap.files) == list(dirs.FILES)
    assert snap.provenance == dirs.PROVENANCE_FETCHED
    assert all(snap.fetched_at[n] for n in dirs.FILES)
    assert snap.files[dirs.NASDAQ_LISTED] == real.files[dirs.NASDAQ_LISTED]
    assert sum(p.calls.values()) == len(dirs.FILES)
