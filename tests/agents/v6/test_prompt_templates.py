"""Tests for ``atlas.agents.v6.prompt_templates``.

Coverage:
* Skeleton dict carries the whitelisted keys only.
* Decimal / UUID values are coerced safely (no leakage of object reprs).
* render_prompt embeds the constraint phrases the LLM must honour.
* Recent corp actions list is normalized into the expected shape.
* Skeleton with no recent corp actions yields an empty list (not None).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from atlas.agents.v6.prompt_templates import (
    BRIEF_PROMPT_TEMPLATE,
    SKELETON_KEYS,
    build_skeleton,
    render_prompt,
)


def _signal_call_fixture() -> dict:
    return {
        "signal_call_id": UUID("00000000-0000-4000-8000-000000000001"),
        "action": "POSITIVE",
        "confidence_unconditional": Decimal("0.7520"),
        "regime_state_at_call": "RISK_ON",
        "stable_features": ["rs_z", "trend_slope"],
        "predicted_excess": Decimal("0.299"),
        "tenure": "TWELVE_MONTH",
        "cap_tier_at_trigger": "MID",
    }


def _instrument_fixture() -> dict:
    return {"symbol": "INFY", "company_name": "Infosys Ltd"}


def _cell_fixture() -> dict:
    return {"rule_type": "Pullback"}


# ---------------------------------------------------------------------------
# Skeleton shape
# ---------------------------------------------------------------------------


def test_skeleton_has_only_whitelisted_keys() -> None:
    skeleton = build_skeleton(
        signal_call=_signal_call_fixture(),
        instrument=_instrument_fixture(),
        cell=_cell_fixture(),
    )
    extras = set(skeleton) - SKELETON_KEYS
    assert not extras, f"unexpected skeleton keys: {extras}"


def test_skeleton_includes_core_methodology_fields() -> None:
    skeleton = build_skeleton(
        signal_call=_signal_call_fixture(),
        instrument=_instrument_fixture(),
        cell=_cell_fixture(),
    )
    for required in (
        "ticker",
        "action",
        "confidence_unconditional",
        "regime_state",
        "stable_features",
        "cell_name",
        "predicted_excess",
    ):
        assert required in skeleton, f"missing required key {required}"


def test_skeleton_cell_name_format() -> None:
    skeleton = build_skeleton(
        signal_call=_signal_call_fixture(),
        instrument=_instrument_fixture(),
        cell=_cell_fixture(),
    )
    assert skeleton["cell_name"] == "MID Pullback @ TWELVE_MONTH"


def test_skeleton_uuid_stringified() -> None:
    skeleton = build_skeleton(
        signal_call=_signal_call_fixture(),
        instrument=_instrument_fixture(),
        cell=_cell_fixture(),
    )
    assert isinstance(skeleton["signal_call_id"], str)
    assert skeleton["signal_call_id"].startswith("00000000-")


def test_skeleton_decimal_coerced_to_float() -> None:
    skeleton = build_skeleton(
        signal_call=_signal_call_fixture(),
        instrument=_instrument_fixture(),
        cell=_cell_fixture(),
    )
    assert isinstance(skeleton["confidence_unconditional"], float)
    assert pytest.approx(skeleton["confidence_unconditional"], rel=1e-6) == 0.7520


def test_skeleton_missing_predicted_excess_yields_none() -> None:
    sc = _signal_call_fixture()
    sc["predicted_excess"] = None
    skeleton = build_skeleton(
        signal_call=sc,
        instrument=_instrument_fixture(),
        cell=_cell_fixture(),
    )
    assert skeleton["predicted_excess"] is None


def test_skeleton_stable_features_default_empty_list() -> None:
    sc = _signal_call_fixture()
    sc["stable_features"] = None
    skeleton = build_skeleton(
        signal_call=sc,
        instrument=_instrument_fixture(),
        cell=_cell_fixture(),
    )
    assert skeleton["stable_features"] == []


# ---------------------------------------------------------------------------
# Corp actions
# ---------------------------------------------------------------------------


def test_skeleton_recent_corp_actions_empty_when_none() -> None:
    skeleton = build_skeleton(
        signal_call=_signal_call_fixture(),
        instrument=_instrument_fixture(),
        cell=_cell_fixture(),
        recent_corp_actions=None,
    )
    assert skeleton["recent_corp_actions"] == []


def test_skeleton_summarises_recent_corp_actions() -> None:
    skeleton = build_skeleton(
        signal_call=_signal_call_fixture(),
        instrument=_instrument_fixture(),
        cell=_cell_fixture(),
        recent_corp_actions=[
            {
                "event_type": "merger",
                "effective_date": date(2026, 4, 1),
                "description": "Sample merger description.",
                # extra fields must be stripped:
                "internal_status": "draft",
            }
        ],
    )
    assert len(skeleton["recent_corp_actions"]) == 1
    ca = skeleton["recent_corp_actions"][0]
    assert ca == {
        "event_type": "merger",
        "effective_date": "2026-04-01",
        "description": "Sample merger description.",
    }
    assert "internal_status" not in ca


def test_skeleton_truncates_long_corp_action_description() -> None:
    long_desc = "A" * 500
    skeleton = build_skeleton(
        signal_call=_signal_call_fixture(),
        instrument=_instrument_fixture(),
        cell=_cell_fixture(),
        recent_corp_actions=[
            {
                "event_type": "merger",
                "effective_date": date(2026, 4, 1),
                "description": long_desc,
            }
        ],
    )
    desc = skeleton["recent_corp_actions"][0]["description"]
    assert len(desc) <= 180
    assert desc.endswith("…")


# ---------------------------------------------------------------------------
# render_prompt
# ---------------------------------------------------------------------------


def test_render_prompt_embeds_constraint_phrases() -> None:
    skeleton = build_skeleton(
        signal_call=_signal_call_fixture(),
        instrument=_instrument_fixture(),
        cell=_cell_fixture(),
    )
    prompt = render_prompt(skeleton)
    # Constraint phrases the LLM must see — assert each is present.
    assert "SEBI" in prompt
    assert "Do NOT" in prompt  # one of the hard constraints
    assert "skeleton" in prompt.lower()
    assert "research language" in prompt.lower()


def test_render_prompt_contains_skeleton_json() -> None:
    skeleton = build_skeleton(
        signal_call=_signal_call_fixture(),
        instrument=_instrument_fixture(),
        cell=_cell_fixture(),
    )
    prompt = render_prompt(skeleton)
    # The serialized JSON must appear verbatim; round-trip a key.
    assert '"ticker"' in prompt
    assert "INFY" in prompt


def test_render_prompt_json_is_parseable() -> None:
    """The embedded JSON must be valid (no Decimal/UUID leakage)."""
    skeleton = build_skeleton(
        signal_call=_signal_call_fixture(),
        instrument=_instrument_fixture(),
        cell=_cell_fixture(),
    )
    prompt = render_prompt(skeleton)
    # Pull the JSON block by stripping everything before the first '{'.
    start = prompt.index("{")
    end = prompt.rindex("}")
    json.loads(prompt[start : end + 1])  # raises on invalid JSON


def test_prompt_template_has_word_count_constraint() -> None:
    """The prompt must instruct the LLM to bound brief length."""
    assert "40" in BRIEF_PROMPT_TEMPLATE
    assert "80" in BRIEF_PROMPT_TEMPLATE
