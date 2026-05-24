"""Pydantic v2 schema for the ``atlas_cell_definitions.rule_dsl`` JSONB column.

The rule shape is **flat-AND**, not a nested expression tree (per CONTEXT.md
§"Cell rule"):

* ``eligibility: list[FeaturePredicate]`` — universe + per-cell filters.
  Additive over the M1 baseline; cells MAY tighten but not loosen.
* ``entry: list[FeaturePredicate]`` — cell-entry predicates, AND-joined.
* ``rule_type``, ``tier``, ``action``, ``tenure``, ``rule_version``,
  ``methodology_lock_ref`` — the cell's domain identity.

Each :class:`FeaturePredicate` is ``(feature, cmp, value)`` where:

* ``feature`` is validated against the :data:`atlas.features.FEATURES`
  allowlist — a typo becomes a Pydantic ``ValidationError`` at the moment
  the cell row is written, not at inference time. This is the load-bearing
  reason ``FEATURES`` is centralised in ``atlas.features`` per
  /grill-with-docs Q4.
* ``cmp`` is one of ``">", ">=", "<", "<=", "==", "in_range",
  "in_top_quantile"``.
* ``value`` is a ``Decimal`` for the scalar comparisons or a
  ``tuple[Decimal, Decimal]`` for ``in_range``. The ``in_top_quantile``
  comparison uses the optional ``value_quantile_n`` field (e.g. 5 → top
  quintile, 10 → top decile); ``value`` carries the quantile membership
  marker (typically ``Decimal("1")``) and is unused at evaluation time
  except as a presence sentinel.

OR semantics are NOT supported in-rule. If two predicate sets need
"a OR b", define two cells with the same ``(tier, action, tenure)``; the
methodology lock treats cells as atomic.

Validation on insert is wired separately (SQLAlchemy event listener — out
of scope here); the :func:`validate_rule_dsl` helper is the canonical
entry point for callers that want to validate a JSONB-shaped dict.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Import the FEATURES allowlist — the centralised v6 source of truth.
from atlas.features import FEATURES

# Comparison operators supported by FeaturePredicate.
CMP = Literal[">", ">=", "<", "<=", "==", "in_range", "in_top_quantile"]


class FeaturePredicate(BaseModel):
    """A single feature-level predicate in a cell rule.

    Args (Pydantic fields):
        feature: feature name. Validated against ``FEATURES`` allowlist.
        cmp: comparison operator. See :data:`CMP`.
        value: scalar (``Decimal``) for scalar comparisons; tuple
            ``(low, high)`` for ``cmp == "in_range"``; sentinel
            ``Decimal("1")`` for ``cmp == "in_top_quantile"`` (the
            quantile cutoff is carried by ``value_quantile_n``).
        value_quantile_n: required when ``cmp == "in_top_quantile"`` —
            the quantile count (e.g. 5 = top quintile, 10 = top decile).
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    feature: str
    cmp: CMP
    value: Decimal | tuple[Decimal, Decimal]
    value_quantile_n: int | None = None

    # -- Validators ----------------------------------------------------------

    @field_validator("feature")
    @classmethod
    def _feature_in_allowlist(cls, v: str) -> str:
        """Reject feature names not in :data:`atlas.features.FEATURES`.

        Per /grill-with-docs Q4: a typo at this layer must surface as a
        validation error, not as a silent NaN at inference time.
        """
        if v not in FEATURES:
            raise ValueError(
                f"feature {v!r} not in atlas.features.FEATURES allowlist "
                f"(known features: {len(FEATURES)} entries — see "
                "atlas/features/__init__.py)"
            )
        return v

    @model_validator(mode="after")
    def _check_value_shape(self) -> FeaturePredicate:
        """Cross-field shape check between ``cmp`` and ``value`` / ``value_quantile_n``.

        - ``in_range`` requires ``value`` to be a 2-tuple with ``low <= high``.
        - ``in_top_quantile`` requires ``value_quantile_n`` to be a positive
          int (>= 2 — top-1-of-1 makes no sense).
        - All scalar comparisons (``>``, ``>=``, ``<``, ``<=``, ``==``)
          require ``value`` to be a ``Decimal`` (not a tuple).
        """
        if self.cmp == "in_range":
            if not isinstance(self.value, tuple):
                raise ValueError("cmp='in_range' requires value to be a (low, high) tuple")
            if len(self.value) != 2:
                raise ValueError("cmp='in_range' tuple must have exactly 2 elements")
            low, high = self.value
            if low > high:
                raise ValueError(f"cmp='in_range' low must be <= high (got low={low}, high={high})")
        elif self.cmp == "in_top_quantile":
            if self.value_quantile_n is None or self.value_quantile_n < 2:
                raise ValueError(
                    "cmp='in_top_quantile' requires value_quantile_n >= 2 (e.g. 5 = top quintile)"
                )
        else:
            # Scalar comparisons — value must be a plain Decimal, not a tuple.
            if isinstance(self.value, tuple):
                raise ValueError(
                    f"cmp={self.cmp!r} requires value to be a Decimal scalar, not a tuple"
                )
        return self


class CellRule(BaseModel):
    """The Pydantic v2 schema mirroring ``atlas_cell_definitions.rule_dsl``.

    Pydantic ``Literal[...]`` enforces every enum at validation time:
    ``rule_type`` (the 9 v6 archetypes including ``"placeholder"`` for the
    seeded rows from migration 089), ``tier`` (``Small`` / ``Mid`` /
    ``Large`` per the ``atlas_cap_tier`` enum), ``action`` (``POSITIVE``
    / ``NEUTRAL`` / ``NEGATIVE`` per R1 collapse), and ``tenure``
    (``1m`` / ``3m`` / ``6m`` / ``12m`` per the ``atlas_tenure`` enum).

    Display labels (BUY/ACCUMULATE/HOLD/WATCH/AVOID/SELL) are resolved at
    the API layer based on the requesting user's portfolio ownership —
    they are NOT validated as separate ``action`` values here.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    rule_type: Literal[
        "pullback",
        "severely_broken",
        "emerging",
        "topping",
        "accumulate",
        "trim",
        "watch",
        "hold",
        "placeholder",
    ]
    eligibility: list[FeaturePredicate] = Field(default_factory=list)
    entry: list[FeaturePredicate] = Field(default_factory=list)
    tier: Literal["Small", "Mid", "Large"]
    action: Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]
    tenure: Literal["1m", "3m", "6m", "12m"]
    rule_version: int = 1
    methodology_lock_ref: str
    notes: str = ""


def validate_rule_dsl(rule_dsl_json: dict) -> CellRule:
    """Parse + validate a ``rule_dsl`` JSONB blob.

    Args:
        rule_dsl_json: the dict shape stored in
            ``atlas_cell_definitions.rule_dsl``.

    Returns:
        Validated :class:`CellRule`.

    Raises:
        pydantic.ValidationError: when the shape mismatches or a
            ``FeaturePredicate.feature`` is outside the allowlist.
    """
    return CellRule.model_validate(rule_dsl_json)


__all__ = [
    "CMP",
    "CellRule",
    "FeaturePredicate",
    "validate_rule_dsl",
]
