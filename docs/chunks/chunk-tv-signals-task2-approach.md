# Chunk: TV Signals Task 2 — Pydantic v2 Models

## Scope
Pure model layer — no DB, no API routes, no data engineering.
Data scale: N/A (Pydantic model definitions only).

## Approach
- Two `BaseModel` subclasses: `TVSignalPayload` (inbound webhook) and `SignalReportResponse` (outbound).
- `TVSignalPayload.close` uses `Decimal` with a `field_validator(mode="before")` that explicitly rejects `float` — matching the Decimal-Not-Float wiki pattern.
- `TVSignalPayload.chart` uses a `field_validator` to enforce the enum (two allowed values). A `Literal` type could work, but the explicit validator gives a clearer error message.
- `SignalReportResponse.conviction_score` is `Optional[Decimal]` — nullable by design (new signals have no score yet).
- All optional fields default to `None` explicitly.

## Wiki patterns checked
- `Decimal Not Float` — `close` validator rejects `float` input at the Pydantic boundary.
- `Idempotent Upsert` — not applicable here (no DB in this chunk).

## Existing code reused
- `atlas/api/openbb/schemas.py` — reference for `from __future__ import annotations`, `field_validator` placement, `@classmethod` decorator pattern.

## Edge cases
- TV sends `close` as a formatted string (e.g. `"1820.50"`). Pydantic coerces via `str -> Decimal(str(v))`.
- Float passed as `close` is actively rejected (not silently coerced) to prevent precision loss.
- `chart` values are constrained to exactly two strings; any other value raises `ValueError`.
- All `SignalReportResponse` optional fields (`conviction_score`, `narrative`, etc.) default `None` — NULL in DB is valid state.

## Expected runtime
Not applicable — pure model validation, no I/O.

## Files touched
- `atlas/signals/__init__.py` (new)
- `atlas/signals/models.py` (new)
- `tests/unit/signals/__init__.py` (new)
- `tests/unit/signals/test_models.py` (new)
