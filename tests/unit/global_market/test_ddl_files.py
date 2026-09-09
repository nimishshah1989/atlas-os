"""The DDL files' own rules, checked in ``make gate`` rather than ten minutes later in CI.

``apply_ddl.check_no_percent`` refuses a bare ``percent`` sign anywhere in a DDL file —
comments included — because psycopg2 reads one as a parameter marker whenever a parameter
object is passed, which SQLAlchemy's ``exec_driver_sql`` (the migration's path) always does,
and fails with an opaque ``TypeError``. Both apply paths therefore accept exactly the same
files.

Until this test existed the ONLY thing enforcing that rule was the "Migrations apply on a
fresh DB" CI job, which needs a Postgres service and takes minutes; a per-cent sign written
into a comment cost a full red-CI round trip. It is a pure string check over seven files, so
it belongs in the seven-second gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.global_market.script_loader import load_global_script

apply_ddl = load_global_script("apply_ddl")

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]

DDL_FILES = sorted(apply_ddl.DDL_DIR.glob(apply_ddl.DDL_GLOB))


def test_the_ddl_directory_is_not_empty() -> None:
    """A glob that matches nothing would make every test below pass vacuously."""
    assert len(DDL_FILES) >= 7
    assert [f.name for f in DDL_FILES] == sorted(f.name for f in DDL_FILES)


@pytest.mark.parametrize("path", DDL_FILES, ids=lambda p: p.name)
def test_no_ddl_file_carries_a_per_cent_sign(path) -> None:
    apply_ddl.check_no_percent(path.read_text(), path.name)


def test_the_check_still_refuses_one_in_a_comment() -> None:
    """The case that actually happened: a measured figure written into a comment."""
    with pytest.raises(SystemExit, match="not allowed in DDL files"):
        apply_ddl.check_no_percent("-- the fund sums to 101.26% of net assets\n", "02_etf.sql")


def test_the_migration_enforces_the_same_rule_over_the_same_files() -> None:
    """There are TWO copies of this rule — ``apply_ddl.check_no_percent`` and an inline test
    in ``0002_atlas_global.upgrade`` — because prod applies the files directly and CI applies
    them through alembic. Testing one only covers the other while they agree, so this asserts
    the migration still reads the same directory with the same glob and refuses on the same
    character. If the migration's test is ever rewritten, this goes red rather than leaving
    the gate covering half the paths."""
    migration = (REPO / "migrations" / "versions" / "0002_atlas_global.py").read_text()
    assert 'if "%" in sql:' in migration
    assert "'%' is not allowed in DDL files; write 'percent'" in migration
    assert f'_DDL_GLOB = "{apply_ddl.DDL_GLOB}"' in migration
