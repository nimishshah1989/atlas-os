"""``_gdb`` takes ``ATLAS_DB_URL`` from the environment only.

India's ``_db.db_url`` falls back to ``frontend/.env.local`` (the India board's prod URL);
the global tree must never reach it — a laptop dry run of the orchestrators would otherwise
write prod (runbook §6). Every helper that can open a connection is behind the same check.
Pure: no DB, no network; ``_db``'s caches are cleared around each test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.global_market.script_loader import load_global_script

gdb = load_global_script("_gdb")

pytestmark = pytest.mark.unit

LOCAL = "postgresql://postgres:postgres@localhost:5432/atlas_scratch"


@pytest.fixture(autouse=True)
def _fresh_url_cache():
    gdb._db.db_url.cache_clear()
    yield
    gdb._db.db_url.cache_clear()


def test_unset_raises_before_any_file_or_connection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ATLAS_DB_URL", raising=False)
    decoy = tmp_path / ".env.local"  # India's fallback file, primed with a URL: must stay unread
    decoy.write_text(f"ATLAS_DB_URL={LOCAL}\n")
    monkeypatch.setattr(gdb._db, "_ENV_FILE", decoy)
    for reach in (
        gdb.db_url,
        gdb.psycopg2_url,
        gdb.engine,
        lambda: gdb.scalar("select 1"),
        lambda: gdb.read_df("select 1"),
        lambda: gdb.exec_sql("select 1"),
        lambda: gdb.exec_script("select 1;"),
        lambda: gdb.upsert_df("t", None, ["k"]),
    ):
        with pytest.raises(RuntimeError, match="ATLAS_DB_URL is not set"):
            reach()
    assert gdb._db.db_url.cache_info().currsize == 0  # _db.db_url was never consulted


def test_set_is_returned_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_DB_URL", LOCAL)
    assert gdb.db_url() == LOCAL.replace("postgresql://", "postgresql+psycopg2://", 1)
    assert gdb.psycopg2_url() == LOCAL
