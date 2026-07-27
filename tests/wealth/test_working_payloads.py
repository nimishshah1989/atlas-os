"""Generic contract sweep over every exhibit's `working` object across the
whole book (Q1-Q7, B1-B5, client_index annotation, Client 360). Complements
test_capability_data.py's per-exhibit assertions with one cross-cutting pass:
every `working` dict has the 7 required keys, every assumption states a bias,
honesty is one of the four allowed values (or None only for a true
empty-state), and a handful of representative sample_rows are re-queryable
against the live DB (not fabricated). Rule #0: one real fetch_book() call
against the live connection, no fixtures.
"""

import re
import sys

import pytest

sys.path.insert(0, "scripts/wealth")

from capability_app.data import fetch_book
from engine_common import connect

HONESTY_VALUES = {"exact", "estimate", "upper bound", "floor"}
WORKING_KEYS = {"inputs", "rule", "assumptions", "steps", "sample_rows", "sample_of", "honesty"}

SAMPLE_CLIENT = 1


def _is_working_shaped(obj) -> bool:
    return isinstance(obj, dict) and WORKING_KEYS <= obj.keys()


def _find_exhibits(obj, path="book") -> list[tuple[str, dict]]:
    """Recursively collect every dict that carries a `working` key shaped like
    a working object — i.e. an exhibit dict, tagged with a dotted path. The
    exhibit itself (not just its nested `working`) is what carries the
    top-level `verdict`/`message` strings actually rendered to a user."""
    found = []
    if isinstance(obj, dict):
        if _is_working_shaped(obj.get("working")):
            found.append((path, obj))
        for k, v in obj.items():
            found.extend(_find_exhibits(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):  # a few list entries is enough, this isn't exhaustive
            found.extend(_find_exhibits(v, f"{path}[{i}]"))
    return found


def _find_workings(obj, path="book") -> list[tuple[str, dict]]:
    """Thin wrapper over _find_exhibits: same paths (plus `.working`), but
    returns just the nested `working` object — what most shape/content
    assertions actually want."""
    return [(f"{p}.working", exhibit["working"]) for p, exhibit in _find_exhibits(obj, path)]


@pytest.fixture(scope="module")
def book():
    conn = connect()
    try:
        return fetch_book(conn)
    finally:
        conn.close()


def test_every_working_object_in_the_book_has_the_required_shape(book):
    workings = _find_workings(book)
    # sanity: this must actually find the known exhibits, not silently match zero
    paths = {p for p, _w in workings}
    for key in ("book.q1.working", "book.q4.working", "book.b5.working"):
        assert key in paths, f"expected to find {key}"
    assert len(workings) >= 12 + 7  # Q1-Q7 + B1-B5 (12) + one client's 7 sections, at minimum

    for path, working in workings:
        assert working.keys() == WORKING_KEYS, f"{path}: unexpected/missing keys"
        assert isinstance(working["rule"], str), f"{path}: rule must be a string"
        for a in working["assumptions"]:
            assert a.get("bias"), f"{path}: every assumption must state its bias direction"
            assert a.get("text"), f"{path}: every assumption must state its text"
        assert isinstance(working["sample_rows"], list)
        assert len(working["sample_rows"]) <= 20, f"{path}: sample_rows must be capped at 20"
        assert isinstance(working["sample_of"], int) and working["sample_of"] >= 0
        honesty = working["honesty"]
        if honesty is None:
            # None is only legitimate for a true empty-state: no rows, no sample
            assert working["sample_of"] == 0, f"{path}: honesty=None but sample_of > 0"
        else:
            assert honesty in HONESTY_VALUES, f"{path}: {honesty!r} not an allowed honesty value"


def test_no_working_object_leaks_a_banned_word(book):
    """The banned-word gate (xirr/alpha/disposition/pgr/plr/counterfactual)
    applies to every rendered string shown to a user — a working object's
    rule text, assumption text/bias, and step/input labels, AND the exhibit's
    own top-level `verdict`/`message` strings that sit alongside `working` in
    every exhibit's return dict (these are equally rendered UI text; scanning
    only the nested working object would miss a regression there). pgr/plr
    are matched on word boundaries (bare substring matches common English
    words like "upgrade")."""
    banned_re = re.compile(r"xirr|alpha|disposition|\bpgr\b|\bplr\b|counterfactual", re.I)
    for path, exhibit in _find_exhibits(book):
        working = exhibit["working"]
        haystacks = [working["rule"]]
        haystacks += [a["text"] for a in working["assumptions"]]
        haystacks += [a["bias"] for a in working["assumptions"]]
        haystacks += [str(s.get("label", "")) for s in working["steps"]]
        haystacks += [str(i.get("label", "")) for i in working["inputs"]]
        haystacks += [str(exhibit.get("verdict", ""))]
        haystacks += [str(exhibit.get("message", ""))]
        text = " ".join(haystacks)
        m = banned_re.search(text)
        assert m is None, f"{path}: banned word {m.group() if m else ''!r} found in {text!r}"


def test_sample_rows_are_genuinely_requeryable(book):
    """Representative (not exhaustive) spot-checks that sample_rows point at
    real rows rather than fabricated ones, across three different tables."""
    conn = connect()
    try:
        cur = conn.cursor()

        # Q1 (Holdings): client_id + scheme_id pair must exist in wealth.holdings
        q1_sample = book["q1"]["working"]["sample_rows"]
        assert q1_sample
        row = q1_sample[0]
        cur.execute(
            "select 1 from wealth.holdings where client_id = %s and scheme_id = %s "
            "and market_value > 0",
            (row["client_id"], row["scheme_id"]),
        )
        assert cur.fetchone() is not None, "Q1 sample_row does not resolve to a real holding"

        # B4 (advice switches): client_id + switch_date must exist in wealth.advice_ledger
        b4_sample = book["b4"]["working"]["sample_rows"]
        assert b4_sample
        row = b4_sample[0]
        cur.execute(
            "select 1 from wealth.advice_ledger where client_id = %s and switch_date::text = %s",
            (row["client_id"], row["switch_date"]),
        )
        assert cur.fetchone() is not None, "B4 sample_row does not resolve to a real switch"

        # Client 360 timeline (client-scoped table): month must exist for that client
        timeline = book["client360"][SAMPLE_CLIENT]["timeline"]
        month_sample = timeline["working"]["sample_rows"]
        assert month_sample
        row = month_sample[0]
        cur.execute(
            "select 1 from wealth.client_curves where client_id = %s "
            "and to_char(month, 'YYYY-MM') = %s",
            (SAMPLE_CLIENT, row["month"]),
        )
        assert cur.fetchone() is not None, "client_360 timeline sample_row not in client_curves"
    finally:
        conn.close()
