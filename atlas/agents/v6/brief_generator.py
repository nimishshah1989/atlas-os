"""Main LLM brief generator for v6.

Pipeline (per CEO plan §E2 + CONTEXT.md "Brief cache invalidation"):

1. **Cache lookup.**  Read ``atlas_brief_cache`` for the active brief
   (``invalidated_at IS NULL AND valid_until > NOW()``) keyed by
   ``(instrument_id, date, action, cell_id)``.  Cache hit → return
   stored brief unchanged.
2. **Cache miss.**  Open an ACL-enforced read-only session
   (:func:`atlas.agents.v6.readonly_session.open_readonly_session`) and
   fetch the signal_call row + its cell_definition + its instrument +
   recent corp actions.
3. **Skeleton construction.**  Build the constrained JSON skeleton via
   :func:`atlas.agents.v6.prompt_templates.build_skeleton`.
4. **Groq call.**  Invoke the injected :class:`GroqClient` with the
   rendered prompt (timeout 10s).  Real production wiring uses the
   ``groq`` SDK; tests inject a mock.
5. **SEBI guard.**  Run :func:`atlas.agents.v6.sebi_guard.check_brief`
   on the output.  Any forbidden phrase → deterministic fallback.
6. **Fallback on failure.**  Groq failure, timeout, or guard trip →
   :func:`_deterministic_fallback` returns a template-assembled brief.
   Always safe to serve; never raises.
7. **Cache write.**  Insert into ``atlas_brief_cache`` with
   ``valid_until = NOW() + 24h``.  Cache writes happen inside their own
   short transaction (the agent ACL session is read-only and cannot
   write).
8. **Return** :class:`BriefGenerationResult`.

Concurrency cap
===============
:data:`MAX_CONCURRENT_GROQ_CALLS` = 4 per eng review §4 Finding 4.C.
This generator is synchronous; the cap is enforced at the orchestrator
layer (the inference cron that calls this in a loop).  Module-level
constant gives the orchestrator a stable reference.

Cache invalidation
==================
:func:`invalidate_briefs_on_corp_action` is the corp-action ingest cron
post-step hook per CONTEXT.md.  Allowlisted corp-action types invalidate
briefs for ACTIVE signal_calls only (``exit_date IS NULL``).

PII / logging
=============
Never log brief text content — the brief references live tickers + may
embed company-specific context that we treat as sensitive.  We log the
``signal_call_id`` + ``cache_hit`` / ``fallback_used`` flags only.
"""

# allow-large: brief generator pulls together the cache lookup, ACL
# session, skeleton construction, Groq invocation, SEBI guard, fallback,
# cache write, and invalidation hook — one cohesive E2 surface per the
# CEO plan §E2.  Splitting would force shared mutable state across
# modules with no clean public seam (every helper threads the same
# engine + signal_call_id + result dataclass).

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from atlas.agents.v6.prompt_templates import build_skeleton, render_prompt
from atlas.agents.v6.readonly_session import (
    open_readonly_session,
    verify_query_allowlist,
)
from atlas.agents.v6.sebi_guard import SEBIGuardTripped, check_brief

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Concurrency cap enforced at the orchestrator layer per eng review §4
#: Finding 4.C.  The brief generator itself is synchronous; the inference
#: cron caps concurrent Groq calls to this value.
MAX_CONCURRENT_GROQ_CALLS: int = 4

#: Brief cache TTL — 24h per CONTEXT.md.  Fallback briefs are cached with
#: a shorter TTL (1h) so retries happen sooner per the same section.
_CACHE_TTL_HOURS: int = 24
_FALLBACK_CACHE_TTL_HOURS: int = 1

#: Groq call timeout in seconds.  The brief generator is on the daily
#: cron critical path; long timeouts cascade.
_GROQ_TIMEOUT_S: float = 10.0

#: Max-tokens cap for the Groq call.  Briefs are 40-80 words ≈ 120 tokens.
_GROQ_MAX_TOKENS: int = 200

#: Corp-action types that invalidate cached briefs per CONTEXT.md.
#: Stock-split / bonus / regular-dividend are intentionally EXCLUDED —
#: the adjusted-price pipeline absorbs them; the cell sees no semantic
#: change.
_INVALIDATING_CORP_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "merger",
        "demerger",
        "scheme_of_arrangement",
        "rights_issue",
        "spin_off",
        "special_dividend",
        "delisting",
        "suspension",
        "name_change",
        "isin_change",
    }
)


# ---------------------------------------------------------------------------
# Protocols + return contract
# ---------------------------------------------------------------------------


@runtime_checkable
class GroqClient(Protocol):
    """Minimal interface the brief generator needs from a Groq client.

    Production wiring uses the ``groq`` SDK; tests inject a mock.  The
    real client constructor is lazy-imported inside
    :func:`_make_default_groq_client` so unit tests do not need
    ``GROQ_API_KEY`` in the environment.
    """

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = _GROQ_MAX_TOKENS,
        timeout_s: float = _GROQ_TIMEOUT_S,
    ) -> str:  # pragma: no cover - protocol
        ...


@dataclass(frozen=True)
class BriefGenerationResult:
    """Outcome of one :func:`generate_brief` call.

    Attributes
    ----------
    signal_call_id:
        The signal_call this brief is keyed to.
    brief_text:
        The brief that should be surfaced (cache hit, LLM output, or
        deterministic fallback — caller does not need to discriminate).
    cache_hit:
        True if the brief came from ``atlas_brief_cache`` unchanged.
    fallback_used:
        True if the deterministic fallback served (Groq failure /
        timeout / SEBI guard trip).
    sebi_guard_tripped:
        True if Groq output was blocked by the SEBI guard.  Implies
        ``fallback_used``.
    generation_ms:
        End-to-end wall time for this call in milliseconds.
    cache_written:
        True if a new row was inserted into ``atlas_brief_cache``.
        False on cache hits.
    """

    signal_call_id: UUID
    brief_text: str
    cache_hit: bool
    fallback_used: bool
    sebi_guard_tripped: bool
    generation_ms: int
    cache_written: bool = False


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def generate_brief(
    signal_call_id: UUID,
    db_engine: Engine,
    *,
    groq_client: GroqClient | None = None,
    write_to_cache: bool = True,
    now: datetime | None = None,
) -> BriefGenerationResult:
    """Generate (or fetch cached) a brief for ``signal_call_id``.

    See module docstring for the full pipeline.

    Parameters
    ----------
    signal_call_id:
        UUID of the ``atlas_signal_calls`` row.
    db_engine:
        Process-wide engine (typically :func:`atlas.db.get_engine`).
    groq_client:
        Injected GroqClient.  ``None`` lazy-constructs the default via
        :func:`_make_default_groq_client`.  Tests always inject a mock.
    write_to_cache:
        If False, skip the cache write at the end.  Used by callers
        running in dry-run / shadow mode.
    now:
        Override for the "current time" anchor.  Tests inject this to
        get deterministic ``valid_until`` values; production passes
        ``None``.

    Returns
    -------
    BriefGenerationResult
    """
    t_start = time.perf_counter()
    current_time = now if now is not None else datetime.now(tz=UTC)

    # --- 1. Cache lookup --------------------------------------------------
    cached = _lookup_cache(db_engine, signal_call_id, current_time)
    if cached is not None:
        log.info(
            "brief_cache_hit",
            signal_call_id=str(signal_call_id),
        )
        return BriefGenerationResult(
            signal_call_id=signal_call_id,
            brief_text=cached,
            cache_hit=True,
            fallback_used=False,
            sebi_guard_tripped=False,
            generation_ms=int((time.perf_counter() - t_start) * 1000),
            cache_written=False,
        )

    # --- 2. Cache miss → ACL session + skeleton ---------------------------
    with open_readonly_session(db_engine) as conn:
        ctx = _fetch_brief_context(conn, signal_call_id)
    if ctx is None:
        # Signal call row not found.  Return a minimal fallback that the
        # caller can still serve (never raise from this entrypoint).
        fallback = _missing_signal_fallback(signal_call_id)
        log.warning(
            "brief_signal_call_not_found",
            signal_call_id=str(signal_call_id),
        )
        return BriefGenerationResult(
            signal_call_id=signal_call_id,
            brief_text=fallback,
            cache_hit=False,
            fallback_used=True,
            sebi_guard_tripped=False,
            generation_ms=int((time.perf_counter() - t_start) * 1000),
            cache_written=False,
        )

    skeleton = build_skeleton(
        signal_call=ctx["signal_call"],
        instrument=ctx["instrument"],
        cell=ctx["cell"],
        recent_corp_actions=ctx["recent_corp_actions"],
    )
    prompt = render_prompt(skeleton)

    # --- 3. Groq call + SEBI guard ---------------------------------------
    fallback_used = False
    sebi_guard_tripped = False
    brief_text: str
    client = groq_client if groq_client is not None else _make_default_groq_client()
    try:
        raw = client.complete(
            prompt,
            max_tokens=_GROQ_MAX_TOKENS,
            timeout_s=_GROQ_TIMEOUT_S,
        )
        brief_text = (raw or "").strip()
        if not brief_text:
            raise RuntimeError("Groq returned empty brief")
        check_brief(brief_text)
    except SEBIGuardTripped as exc:
        # SEBI guard trip → log the phrase (already on the exception;
        # safe — it's from the static allowlist, not the brief content)
        # and fall back.
        log.warning(
            "brief_sebi_guard_tripped",
            signal_call_id=str(signal_call_id),
            phrase=exc.phrase,
        )
        sebi_guard_tripped = True
        fallback_used = True
        brief_text = _deterministic_fallback(
            signal_call=ctx["signal_call"],
            instrument=ctx["instrument"],
            cell=ctx["cell"],
        )
    except Exception as exc:
        log.warning(
            "brief_groq_failed",
            signal_call_id=str(signal_call_id),
            err_type=type(exc).__name__,
            err=str(exc)[:200],
        )
        fallback_used = True
        brief_text = _deterministic_fallback(
            signal_call=ctx["signal_call"],
            instrument=ctx["instrument"],
            cell=ctx["cell"],
        )

    # --- 4. Cache write ---------------------------------------------------
    cache_written = False
    if write_to_cache:
        ttl_hours = _FALLBACK_CACHE_TTL_HOURS if fallback_used else _CACHE_TTL_HOURS
        try:
            _write_cache(
                engine=db_engine,
                ctx=ctx,
                brief_text=brief_text,
                generated_at=current_time,
                valid_until=current_time + timedelta(hours=ttl_hours),
            )
            cache_written = True
        except Exception as exc:
            # Cache write failure is non-fatal — the caller still gets
            # the brief.  Log + continue.
            log.warning(
                "brief_cache_write_failed",
                signal_call_id=str(signal_call_id),
                err=str(exc)[:200],
            )

    return BriefGenerationResult(
        signal_call_id=signal_call_id,
        brief_text=brief_text,
        cache_hit=False,
        fallback_used=fallback_used,
        sebi_guard_tripped=sebi_guard_tripped,
        generation_ms=int((time.perf_counter() - t_start) * 1000),
        cache_written=cache_written,
    )


# ---------------------------------------------------------------------------
# Cache invalidation hook
# ---------------------------------------------------------------------------


def invalidate_briefs_on_corp_action(
    db_engine: Engine,
    corp_action: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> int:
    """Invalidate cached briefs after a corp-action ingest.

    Called by the de_corporate_actions ingest cron post-step per
    CONTEXT.md "Brief cache invalidation".  Only briefs for ACTIVE
    signal_calls (``exit_date IS NULL``) are invalidated.

    Parameters
    ----------
    db_engine:
        Process-wide engine.
    corp_action:
        The corp-action row.  Required keys: ``event_type``,
        ``instrument_id``.  Optional: ``id`` (FK target for
        ``invalidated_by_corp_action_id``).
    now:
        Override for the invalidated_at timestamp (tests).

    Returns
    -------
    int
        Number of brief rows newly invalidated.  Returns 0 when the
        event_type is not in the invalidating allowlist.
    """
    event_type = (corp_action.get("event_type") or "").strip()
    if not event_type or event_type not in _INVALIDATING_CORP_ACTION_TYPES:
        log.info(
            "corp_action_no_invalidate",
            event_type=event_type or "(missing)",
        )
        return 0
    instrument_id = corp_action.get("instrument_id")
    if instrument_id is None:
        raise ValueError("corp_action.instrument_id is required")
    invalidated_at = now if now is not None else datetime.now(tz=UTC)
    corp_action_id = corp_action.get("id")

    sql = text(
        """
        UPDATE atlas.atlas_brief_cache AS bc
        SET invalidated_at = :invalidated_at,
            invalidated_by_corp_action_id = :corp_action_id
        FROM atlas.atlas_signal_calls AS sc
        WHERE bc.signal_call_id = sc.signal_call_id
          AND sc.exit_date IS NULL
          AND bc.invalidated_at IS NULL
          AND bc.instrument_id = :instrument_id
        """
    )
    with db_engine.begin() as conn:
        result = conn.execute(
            sql,
            {
                "invalidated_at": invalidated_at,
                "corp_action_id": corp_action_id,
                "instrument_id": instrument_id,
            },
        )
        n_rows = result.rowcount or 0
    log.info(
        "corp_action_invalidated_briefs",
        event_type=event_type,
        instrument_id=str(instrument_id),
        n_invalidated=n_rows,
    )
    return n_rows


# ---------------------------------------------------------------------------
# Internal helpers — cache I/O
# ---------------------------------------------------------------------------


_CACHE_LOOKUP_SQL = """
SELECT brief_text
FROM atlas.atlas_brief_cache
WHERE signal_call_id = :signal_call_id
  AND invalidated_at IS NULL
  AND valid_until > :now
ORDER BY generated_at DESC
LIMIT 1
"""


def _lookup_cache(
    engine: Engine,
    signal_call_id: UUID,
    now: datetime,
) -> str | None:
    """Return the cached brief text, or ``None`` on miss.

    The lookup is read-only and runs OUTSIDE the agent ACL session
    because the agent role is intentionally NOT granted on
    ``atlas_brief_cache`` (agents do not read their own outputs per
    CONTEXT.md).  Cache is a service-layer concern.
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(_CACHE_LOOKUP_SQL),
                {"signal_call_id": signal_call_id, "now": now},
            ).first()
    except Exception as exc:
        log.warning(
            "brief_cache_lookup_failed",
            signal_call_id=str(signal_call_id),
            err=str(exc)[:200],
        )
        return None
    if row is None:
        return None
    return row[0]


_CACHE_INSERT_SQL = """
INSERT INTO atlas.atlas_brief_cache (
    instrument_id, date, action, cell_id, signal_call_id,
    brief_text, generated_at, valid_until
)
VALUES (
    :instrument_id, :date, :action, :cell_id, :signal_call_id,
    :brief_text, :generated_at, :valid_until
)
ON CONFLICT (instrument_id, date, action, cell_id) DO UPDATE
SET brief_text = EXCLUDED.brief_text,
    signal_call_id = EXCLUDED.signal_call_id,
    generated_at = EXCLUDED.generated_at,
    valid_until = EXCLUDED.valid_until,
    invalidated_at = NULL,
    invalidated_by_corp_action_id = NULL
"""


def _write_cache(
    *,
    engine: Engine,
    ctx: dict[str, Any],
    brief_text: str,
    generated_at: datetime,
    valid_until: datetime,
) -> None:
    """Insert or refresh the cache row for this (iid, date, action, cell)."""
    sc = ctx["signal_call"]
    params = {
        "instrument_id": sc["instrument_id"],
        "date": sc["date"],
        "action": sc["action"],
        "cell_id": sc["cell_id"],
        "signal_call_id": sc["signal_call_id"],
        "brief_text": brief_text,
        "generated_at": generated_at,
        "valid_until": valid_until,
    }
    with engine.begin() as conn:
        conn.execute(text(_CACHE_INSERT_SQL), params)


# ---------------------------------------------------------------------------
# Internal helpers — agent ACL data fetch
# ---------------------------------------------------------------------------


# All SQL strings issued via the agent ACL session pass through
# verify_query_allowlist before execution.  Anything off-allowlist
# raises ACLViolation defense-in-depth.

_SIGNAL_CALL_FETCH_SQL = """
SELECT
    sc.signal_call_id,
    sc.instrument_id,
    sc.date,
    sc.cell_id,
    sc.cap_tier_at_trigger,
    sc.tenure,
    sc.action,
    sc.confidence_unconditional,
    sc.regime_state_at_call,
    sc.stable_features,
    sc.predicted_excess
FROM atlas_signal_calls AS sc
WHERE sc.signal_call_id = :signal_call_id
LIMIT 1
"""

_CELL_FETCH_SQL = """
SELECT
    cd.cell_id,
    cd.cap_tier,
    cd.action,
    cd.tenure,
    cd.rule_dsl,
    cd.confidence_unconditional,
    cd.stable_features
FROM atlas_cell_definitions AS cd
WHERE cd.cell_id = :cell_id
LIMIT 1
"""

# Recent corp actions (within the lookback window) for the instrument.
# Used to colour the brief — does NOT trigger invalidation (that's the
# corp-action ingest cron's job).
_RECENT_CORP_ACTIONS_SQL = """
SELECT
    event_type,
    effective_date,
    description
FROM de_corporate_actions
WHERE instrument_id = :instrument_id
  AND effective_date >= :since
ORDER BY effective_date DESC
LIMIT 5
"""

# Lookback window for recent corp-action context in the brief.  Keep
# bounded so the prompt skeleton stays small.
_CORP_ACTION_LOOKBACK_DAYS: int = 90


def _fetch_brief_context(
    conn: Connection,
    signal_call_id: UUID,
) -> dict[str, Any] | None:
    """Fetch the signal_call + cell + instrument + recent corp actions.

    Returns ``None`` if the signal_call row is not found.  Every SQL
    string is run through :func:`verify_query_allowlist` first.
    """
    # 1. signal_call row
    verify_query_allowlist(_SIGNAL_CALL_FETCH_SQL)
    sc_row = (
        conn.execute(
            text(_SIGNAL_CALL_FETCH_SQL),
            {"signal_call_id": signal_call_id},
        )
        .mappings()
        .first()
    )
    if sc_row is None:
        return None
    signal_call = dict(sc_row)

    # 2. cell_definition row
    verify_query_allowlist(_CELL_FETCH_SQL)
    cell_row = (
        conn.execute(
            text(_CELL_FETCH_SQL),
            {"cell_id": signal_call["cell_id"]},
        )
        .mappings()
        .first()
    )
    cell = dict(cell_row) if cell_row else {}

    # 3. instrument metadata.  In production this joins to a separate
    # de_instruments table; for this issue (#47) the agent ACL does not
    # grant on de_instruments, so we use a graceful default sourced from
    # what the signal_call carries.  The full instrument lookup wires in
    # with issue #29 (full factuality guard).
    instrument = {
        "instrument_id": signal_call["instrument_id"],
        "symbol": _instrument_fallback_symbol(signal_call["instrument_id"]),
        "company_name": None,
    }

    # 4. recent corp actions (allowlisted table — de_corporate_actions)
    since = signal_call["date"] - timedelta(days=_CORP_ACTION_LOOKBACK_DAYS)
    verify_query_allowlist(_RECENT_CORP_ACTIONS_SQL)
    ca_rows = (
        conn.execute(
            text(_RECENT_CORP_ACTIONS_SQL),
            {"instrument_id": signal_call["instrument_id"], "since": since},
        )
        .mappings()
        .all()
    )
    recent_corp_actions = [dict(r) for r in ca_rows]

    return {
        "signal_call": signal_call,
        "cell": cell,
        "instrument": instrument,
        "recent_corp_actions": recent_corp_actions,
    }


def _instrument_fallback_symbol(instrument_id: Any) -> str:
    """Short symbolic name when no de_instruments join is available.

    Issue #29 wires the canonical de_instruments lookup; until then the
    brief skeleton needs a placeholder so the LLM has SOMETHING to
    reference.  We surface the truncated UUID — never random or invented
    data.
    """
    s = str(instrument_id)
    return f"INSTR-{s[:8]}"


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------


def _deterministic_fallback(
    *,
    signal_call: Mapping[str, Any],
    instrument: Mapping[str, Any],
    cell: Mapping[str, Any],
) -> str:
    """Template-assembled brief from skeleton fields.  Never raises.

    Always SEBI-safe (no recommendation language, no price forecasts).
    Used when Groq fails / times out / trips the SEBI guard.

    Output shape:
        "<cap_tier> <rule_type> @ <tenure> registered for <symbol>
        (<action> state). Cell exhibits <conf>% confidence in the
        <regime> regime. Position basis: <feature1, feature2>."
    """
    cap_tier = signal_call.get("cap_tier_at_trigger") or signal_call.get("cap_tier") or "—"
    tenure = signal_call.get("tenure") or "—"
    action = signal_call.get("action") or "—"
    regime = signal_call.get("regime_state_at_call") or "—"
    symbol = instrument.get("symbol") or "—"
    rule_type = cell.get("rule_type") or cell.get("name") or "rule"

    conf_raw = signal_call.get("confidence_unconditional")
    if conf_raw is None:
        conf_pct = "—"
    else:
        try:
            conf_pct = f"{float(conf_raw) * 100:.1f}%"
        except (TypeError, ValueError):
            conf_pct = "—"

    features = signal_call.get("stable_features") or []
    if isinstance(features, list) and features:
        # Truncate to the first 3 features so the fallback is bounded.
        feature_str = ", ".join(str(f) for f in features[:3])
    else:
        feature_str = "no stable features recorded"

    return (
        f"{cap_tier} {rule_type} @ {tenure} registered for {symbol} "
        f"({action} state). Cell exhibits {conf_pct} confidence in the "
        f"{regime} regime. Position basis: {feature_str}."
    )


def _missing_signal_fallback(signal_call_id: UUID) -> str:
    """Returned when the signal_call row cannot be located.

    Never references the missing UUID directly — the brief is
    user-facing.  This is the safest possible default.
    """
    return (
        "Brief temporarily unavailable for this signal. Please refresh "
        "shortly. Methodology context: this signal reflects a cell "
        "trigger from the Atlas daily inference run."
    )


# ---------------------------------------------------------------------------
# Default Groq client constructor (lazy)
# ---------------------------------------------------------------------------


def _make_default_groq_client() -> GroqClient:  # pragma: no cover - lazy real client
    """Construct a real Groq-backed client.

    Lazy-import keeps unit tests free of any ``GROQ_API_KEY``
    dependency.  Production wiring uses the ``groq`` SDK; on import
    failure we surface a clear runtime error.
    """
    return _RealGroqClient()


class _RealGroqClient:  # pragma: no cover - real client not exercised in unit tests
    """Thin adapter mapping the :class:`GroqClient` protocol to the SDK.

    The full SP07 specialists' tool-calling loop is intentionally NOT
    inherited here — issue #47 is the simple brief-only path.  Real
    Groq tool-calling for v6 specialists lifts in a later issue.
    """

    _MODEL = "llama-3.3-70b-versatile"

    def __init__(self) -> None:
        import os

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai SDK not installed. Run: pip install 'openai>=1.50'") from exc
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set. Get one at console.groq.com.")
        self._client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = _GROQ_MAX_TOKENS,
        timeout_s: float = _GROQ_TIMEOUT_S,
    ) -> str:
        resp = self._client.chat.completions.create(
            model=self._MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout_s,
        )
        return (resp.choices[0].message.content or "").strip()
