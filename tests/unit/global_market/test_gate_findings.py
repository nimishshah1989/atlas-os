"""Which of gate A's findings withhold the board's publish, and which only say so.

WHY THIS FILE EXISTS. Gate A carries two kinds of finding and they read identically in the
log: one is a claim about the run that just happened ("tonight's session is missing a third of
its rows"), the other about a ten-year archive ("eleven of 1,751 instruments have a bad print
somewhere since 2016"). The first must stop a publish. The second must not — those instruments'
numbers are already in Postgres, the board reads Postgres directly, and publish is one
``revalidateTag('eod')``, so withholding it hides nothing and freezes everyone ELSE's numbers.
Gate A blocked on both from 2026-09-03 and the board went a week without advancing.

THE LINE IS A DATE, NOT A KIND OF CHECK, and getting that wrong cost a second night. The first
split moved two checks wholesale and left the impossible-move check blocking because a >100 %
session move "cannot be a price" — true, and irrelevant to the question. That check scans the
same archive, so it alone then held the publish for 5,474 healthy funds over twelve instruments
whose newest bad print was months old. The same test now runs twice: on the anchor session it
ASSERTS, and everywhere earlier it REPORTS. Both branches are pinned below.

Nothing in the pipeline can catch a regression here: re-blocking the archive scan is a
one-word edit, the gate still runs, the log still looks right, and the only symptom is a board
that quietly stops moving — which is exactly how long it took to notice the first time. So the
split is pinned in source, by the text of each check, with no DB and no network.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts" / "global_market"
_GATE_A = _SCRIPTS / "gate_a.py"

# A distinctive literal from each finding's name, and the method it must be raised through.
# `check` FAILS the gate and withholds publish; `report` prints just as loudly and does not.
BLOCKING = [
    "every scored instrument has bars",  # nothing to render at all
    "has an anchor bar at or before the EOD",  # no anchor session means no calendar
    "the newest session carries",  # tonight's completeness against last night's
    "INTO the anchor session",  # a >100% move on the bar THIS run ingested
    "daily returns vs FRED",  # the anchor against an independent publisher
]
REPORTING = [
    "log jump on close_adj",  # the ten-year archive scan (both branches)
    "no close_tr/close ratio falls further",  # re-basing seams, per instrument, in history
    "anywhere earlier in the archive",  # the SAME >100% test, on sessions already past
]


def _finding_names() -> dict[str, str]:
    """``{the check's literal text: the Gate method it goes through}`` for every call in gate A.

    The names are f-strings, so only their constant parts survive; that is enough to identify a
    finding and it is what a reader sees in the log either way.
    """
    tree = ast.parse(_GATE_A.read_text())
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        target = node.func.value
        if not isinstance(target, ast.Name) or target.id != "g":
            continue
        if node.func.attr not in {"check", "report"} or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found[first.value] = node.func.attr
        elif isinstance(first, ast.JoinedStr):
            literal = "".join(
                part.value
                for part in first.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            found[literal] = node.func.attr
    return found


def _method_for(fragment: str, names: dict[str, str]) -> set[str]:
    return {method for name, method in names.items() if fragment in name}


def test_gate_a_raises_a_finding_through_one_of_two_methods_and_no_other() -> None:
    names = _finding_names()
    assert names, f"no g.check/g.report call found in {_GATE_A.name} — was `g` renamed?"
    assert set(names.values()) <= {"check", "report"}


@pytest.mark.parametrize("fragment", BLOCKING)
def test_a_finding_about_tonight_withholds_the_publish(fragment: str) -> None:
    methods = _method_for(fragment, _finding_names())
    assert methods, f"no gate A finding mentions {fragment!r} any more — was it renamed?"
    assert methods == {"check"}, (
        f"{fragment!r} is raised through g.{methods} — a finding about the run that just "
        "happened must FAIL the gate, or the board publishes on top of it"
    )


@pytest.mark.parametrize("fragment", REPORTING)
def test_a_finding_about_the_archive_does_not_withhold_the_publish(fragment: str) -> None:
    methods = _method_for(fragment, _finding_names())
    assert methods, f"no gate A finding mentions {fragment!r} any more — was it renamed?"
    assert methods == {"report"}, (
        f"{fragment!r} is raised through g.{methods} — a per-instrument defect in a ten-year "
        "archive must not withhold the whole board's publish. It hides nothing (the board "
        "reads Postgres directly) and it freezes every other instrument's numbers. Quarantine "
        "the instrument via universe_snapshot.exclusion_reason instead."
    )


def test_report_counts_a_finding_without_failing_the_gate() -> None:
    from tests.unit.global_market.script_loader import load_global_script

    gate = load_global_script("validate_global").Gate()
    assert gate.fails == 0 and gate.reported == 0

    assert gate.report("an archive finding", False, "eleven instruments") is False
    assert (gate.fails, gate.reported) == (0, 1), "a reported finding must not fail the gate"

    assert gate.report("an archive finding that holds", True) is True
    assert (gate.fails, gate.reported) == (0, 1), "a passing report counts as nothing"

    assert gate.check("a finding about tonight", False, "a third of the rows are missing") is False
    assert (gate.fails, gate.reported) == (1, 1), "a failed check must fail the gate"
