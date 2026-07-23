"""Real-data tests for the narration number validator (Rule #0: no
fixtures -- every assertion runs against real wealth.audit_packs.payload
rows pulled from the live DB, never invented inputs). Does NOT call the
claude CLI (cost/time) -- that path is covered by the required smoke run,
per the task brief."""
import functools
import sys

sys.path.insert(0, "scripts/wealth")

from engine_common import connect
from narrate_audit_packs import BANNED_WORDS, SECTION_NAMES, template_only, validate


@functools.lru_cache(maxsize=1)
def _real_payload():
    """The highest-MV client with a sufficient `map` section -- real numbers
    across most sections to exercise the validator against."""
    conn = connect()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        """select payload from wealth.audit_packs
           where payload->'map'->>'insufficient' is null
           order by (payload->'map'->>'total_mv')::float desc limit 1"""
    )
    (payload,) = cur.fetchone()
    return payload


def _an_insufficient_section_payload(section):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "select payload from wealth.audit_packs "
        "where payload->%s->>'insufficient' = 'true' limit 1",
        (section,),
    )
    row = cur.fetchone()
    assert row, f"expected at least one client with an insufficient {section} section"
    return row[0]


def test_prose_quoting_a_real_payload_number_passes():
    payload = _real_payload()
    n_funds = payload["map"]["n_funds"]
    n_stocks = payload["map"]["n_stocks"]
    prose = f"You hold {n_funds} funds reaching into {n_stocks} stocks."
    assert validate(prose, payload) == []


def test_prose_with_invented_number_fails():
    payload = _real_payload()
    prose = "You could save about ₹99,999 a year by switching funds."
    violations = validate(prose, payload)
    assert any("unsupported number" in v and "99,999" in v for v in violations), violations


def test_each_banned_word_fails():
    payload = _real_payload()
    for word in BANNED_WORDS:
        prose = f"Your {word} this year looks reasonable."
        violations = validate(prose, payload)
        msg = f"{word!r} was not flagged: {violations}"
        assert any(word.lower() in v.lower() for v in violations), msg


def test_clean_prose_has_no_banned_words():
    payload = _real_payload()
    prose = "Your yearly growth is running ahead of a plain index fund."
    violations = validate(prose, payload)
    assert not any(v.startswith("banned word") for v in violations)


def test_lcr_scaled_form_of_a_real_number_passes():
    payload = _real_payload()
    total_mv = payload["map"]["total_mv"]
    lakhs = round(total_mv / 1e5, 2)
    prose = f"Your book is worth about ₹{lakhs}L right now."
    assert validate(prose, payload) == [], f"total_mv={total_mv} -> ₹{lakhs}L should validate"


def test_number_under_ten_is_never_checked():
    payload = _real_payload()
    prose = "About 7.5 of your holdings need a look (not a real payload number)."
    assert validate(prose, payload) == []


def test_template_only_self_validates_every_sufficient_section():
    payload = _real_payload()
    for section in SECTION_NAMES:
        if payload[section].get("insufficient"):
            continue
        text = template_only(section, payload)
        assert isinstance(text, str) and text.strip(), f"{section}: empty template"
        violations = validate(text, payload)
        assert violations == [], f"{section}: {violations} in {text!r}"


def test_template_only_self_validates_an_insufficient_section():
    payload = _an_insufficient_section_payload("benchmark")
    text = template_only("benchmark", payload)
    assert isinstance(text, str) and text.strip()
    assert validate(text, payload) == []


def test_template_only_covers_every_section_name():
    """Every SECTION_NAMES key must have a real template branch, not just
    the generic insufficient/fallback text -- guards against a silently
    unhandled section leaking the placeholder string into prod prose."""
    payload = _real_payload()
    for section in SECTION_NAMES:
        if payload[section].get("insufficient"):
            continue
        text = template_only(section, payload)
        assert text != "No narration available for this section.", section
