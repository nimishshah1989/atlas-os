"""The params-ahead-of-code guard for apply_crossover_v2 (post-incident, 2026-07-31).

What happened: the switch-on script was built to protect schema-before-params, and it
did. Nobody checked CODE-before-params. The params went live while `main` was still the
docs-only spec commit, so the database began asking a box whose ``EmaCross`` accepted
neither keyword for ``EmaCross(exit=..., entry_confirm=...)``.

That is a TypeError on all four stock crossover books at the next nightly mark. And
because ``portfolio_mark`` is a step rather than a gate — and the Telegram failure alert
had just been removed — ``atlas_daily`` would have carried on and said nothing.

The box tracks ``main``, so "does main carry the code these params need" is the check
that would have caught it, and it needs no SSH.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parents[2] / "scripts" / "ops"
if str(OPS) not in sys.path:
    sys.path.insert(0, str(OPS))

import apply_crossover_v2 as A  # noqa: E402  # pyright: ignore[reportMissingImports]

pytestmark = pytest.mark.unit


def test_code_missing_a_required_keyword_is_refused() -> None:
    old = "def __init__(self, fast, slow, intraday=False, same_day_fill=None):"
    missing = A.missing_support(old)
    assert "entry_confirm" in missing
    assert "exit" in missing


def test_code_carrying_both_keywords_passes() -> None:
    new = (
        "def __init__(self, fast, slow, intraday=False, same_day_fill=None,"
        ' exit="death_cross", entry_confirm="intraday"):'
    )
    assert A.missing_support(new) == []


def test_the_live_repo_supports_what_this_script_applies() -> None:
    # Self-check: the RULES this script writes must be constructible by the code sitting
    # beside it, or the script is shipping params its own repo cannot honour.
    src = (
        Path(__file__).resolve().parents[2] / "atlas" / "portfolio" / "strategies" / "ema_cross.py"
    ).read_text()
    assert A.missing_support(src) == []
