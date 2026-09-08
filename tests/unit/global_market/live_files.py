"""The real source files for the global-market tests: committed copies under ``FIXTURES`` and
live, cached downloads of the ones that cannot be committed.

Rule #0 wants the parsers tested on REAL records; SSGA's disclosure forbids reproducing its
workbooks ("may not be reproduced, copied or transmitted … without SSGA's express written
consent") and the repository is public — so the SPY and Select Sector SPDR workbooks are
never committed: each test session fetches them from SSGA. fja05680/sp500 is MIT-licensed;
its 28 KB ``sp500_ticker_start_end.csv`` is committed, its 5.5 MB components file is fetched.

Files land in ``INDEX_FIXTURE_CACHE`` (an env var) or, unset, under pytest's base temp
directory, named ``<UTC date>-<file>`` so a persistent cache refreshes daily. Each download
prints its size, sha256 and fetch time (the test log, visible with ``-s``) and carries a
descriptive ``User-Agent``. A download that FAILS skips the tests that need it, naming the
URL and the error — unless ``ATLAS_LIVE_FIXTURES=required`` (CI's live step, ``make
test-live``), where it is a test FAILURE: the ``live``-marked tests must RUN there, never
quietly skip.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "global"
CACHE_ENV = "INDEX_FIXTURE_CACHE"
REQUIRED_ENV = "ATLAS_LIVE_FIXTURES"
TIMEOUT = 60
USER_AGENT = "atlas-os live-fixture test"


def cache_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    env = os.environ.get(CACHE_ENV, "").strip()
    d = Path(env) if env else tmp_path_factory.getbasetemp() / "index-fixture-cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch_or_skip(url: str, name: str, cache: Path) -> Path:
    """The file at ``url`` as ``cache/<UTC date>-<name>``, downloaded once per day; a failed
    download skips — or FAILS under ``ATLAS_LIVE_FIXTURES=required`` — naming the URL."""
    path = cache / f"{datetime.now(UTC):%Y-%m-%d}-{name}"
    if path.is_file() and path.stat().st_size > 0:
        print(f"[live-fixture] {name}: reusing {path} ({path.stat().st_size:,d} bytes)")
        return path
    fetched_at = datetime.now(UTC)
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        path.write_bytes(r.content)
    except (requests.RequestException, OSError) as e:
        if os.environ.get(REQUIRED_ENV, "").strip().lower() == "required":
            pytest.fail(f"{url} unreachable with {REQUIRED_ENV}=required: {e}")
        pytest.skip(reason=f"{url} unreachable: {e}")
    digest = hashlib.sha256(r.content).hexdigest()
    print(
        f"[live-fixture] {name}: {len(r.content):,d} bytes sha256={digest} "
        f"fetched {fetched_at:%Y-%m-%dT%H:%M:%SZ} from {url}"
    )
    return path
