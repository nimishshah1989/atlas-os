"""``_redact`` must never publish a password — including for input it cannot parse.

This file exists because the same bug shipped three times in ``scripts/ops/diagnose_board.py``,
each time in a different disguise, in the one tool whose whole discipline is not printing
credentials: the process command line was printed verbatim (argv carries them), a non-numeric
port aborted the run mid-report, and a URL with no authority section put the entire credential
in ``urlsplit(...).path``.

The common cause is that redaction was written for WELL-FORMED input while its actual input is
arbitrary strings read out of other processes' environments. So the property asserted here is
not "these cases render nicely" but "no input renders the secret", and the malformed cases are
the point rather than an afterthought.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ops" / "diagnose_board.py"


def _load() -> ModuleType:
    """Import the script by path — it lives in scripts/ops/, which is not a package.

    Safe at import time: the module's only top-level imports are stdlib. psycopg2 is
    imported inside main(), deliberately, so this test never needs a database driver.
    """
    spec = importlib.util.spec_from_file_location("diagnose_board", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


CANARY = "pAssw0rdCANARY"

# Every shape this has been handed or plausibly could be: correct, the SQLAlchemy dialect
# spelling the repo's root .env actually uses, a missing "//", a non-numeric port, and junk.
URLS = [
    f"postgresql://boarduser:{CANARY}@db.example.com:5432/postgres?sslmode=require",
    f"postgresql+psycopg2://boarduser:{CANARY}@db.example.com:5432/postgres",
    f"postgresql:boarduser:{CANARY}@db.example.com:5432/postgres",  # no authority section
    f"postgresql://boarduser:{CANARY}@db.example.com:NOTAPORT/postgres",
    f"garbage-{CANARY}",
    "",
]


@pytest.fixture(scope="module")
def mod() -> ModuleType:
    return _load()


@pytest.mark.parametrize("url", URLS)
def test_redact_never_emits_the_password(mod, url: str) -> None:
    assert CANARY not in mod._redact(url), f"password leaked for {url!r}"


@pytest.mark.parametrize("url", URLS)
def test_redact_never_raises(mod, url: str) -> None:
    """A raise here aborts the whole diagnostic — and it did, on a non-numeric port."""
    assert isinstance(mod._redact(url), str)


def test_redact_still_identifies_a_well_formed_url(mod) -> None:
    """Failing closed must not mean failing blank: the identity is the useful part."""
    out = mod._redact(f"postgresql://boarduser:{CANARY}@db.example.com:5432/postgres")
    assert out == "boarduser@db.example.com:5432/postgres"


@pytest.mark.parametrize("url", URLS)
def test_differing_parts_never_raises(mod, url: str) -> None:
    assert isinstance(mod._differing_parts(url, URLS[0]), list)
