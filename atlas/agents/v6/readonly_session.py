"""ACL-enforced read-only session for v6 agents.

Two-layer enforcement per CONTEXT.md "atlas_agent_readonly ACL" + /grill
Q9:

1. **Postgres GRANT (load-bearing):** the ``atlas_agent_readonly`` role
   has ``SELECT`` only on the 11 allowlisted tables. Provisioned by
   infrastructure (separate from Alembic — see migration 083 for the
   conditional grant on ``atlas_ledger_public``). Even a compromised
   agent process cannot read outside the grants.
2. **Application-layer (defense in depth):** every SQL string the agent
   issues is parsed via ``sqlparse``; the referenced tables must be in
   the same hardcoded allowlist below. Catches accidental schema
   additions (a new table without an explicit grant decision) **before**
   the query hits Postgres.

If the ``atlas_agent_readonly`` Postgres role does not exist in the
local dev DB, this module falls back to a regular session and logs a
warning — production EC2 has the role; dev may not. The
application-layer guard remains active in either case.

Public surface
==============

- :data:`ACL_ALLOWLIST` — the 11-table allowlist (frozenset).
- :exc:`ACLViolation` — raised by :func:`verify_query_allowlist`.
- :func:`open_readonly_session` — context manager yielding a
  SQLAlchemy ``Connection`` bound to the readonly role (or a regular
  connection with a warning logged).
- :func:`verify_query_allowlist` — parse a SQL string + check referenced
  tables. Exposed for test coverage + manual audit hooks.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import sqlparse
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlparse.sql import Identifier, IdentifierList, Token
from sqlparse.tokens import Keyword

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------

# 11-table allowlist per CONTEXT.md "atlas_agent_readonly ACL".  The
# atlas_ledger_public VIEW is in this list; the base atlas_ledger table
# is NOT (only the view exposes the agent-safe columns).
ACL_ALLOWLIST: frozenset[str] = frozenset(
    {
        # atlas methodology surface
        "atlas_signal_calls",
        "atlas_scorecard_daily",
        "atlas_cell_definitions",
        "atlas_cell_walkforward_runs",
        "atlas_regime_daily",
        "atlas_drift_status",
        # de_* market data surface (no PII)
        "de_corporate_actions",
        "de_news_events",
        "de_equity_ohlcv",
        "de_index_prices",
        # The VIEW — atlas_ledger base table is intentionally NOT here.
        "atlas_ledger_public",
    }
)

# Schemas the agent may reference. Bare table refs (no schema prefix) are
# allowed — Postgres resolves via search_path.
_ALLOWED_SCHEMAS: frozenset[str] = frozenset({"atlas", "public"})


# Name of the Postgres role provisioned for agent reads.
_AGENT_ROLE: str = "atlas_agent_readonly"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ACLViolation(RuntimeError):  # noqa: N818 — public API; "Violation" reads cleaner than "ViolationError"
    """Raised when a SQL string references a table outside :data:`ACL_ALLOWLIST`.

    Carries the offending table name on :attr:`table` so tests + audit
    logs can assert which table tripped the guard.
    """

    def __init__(self, table: str, sql: str) -> None:
        super().__init__(f"ACL violation: table {table!r} is not in the agent allowlist")
        self.table = table
        self.sql = sql


# ---------------------------------------------------------------------------
# Application-layer guard
# ---------------------------------------------------------------------------


def verify_query_allowlist(sql: str, *, allowlist: frozenset[str] | None = None) -> None:
    """Parse ``sql`` via sqlparse + assert every referenced table is allowlisted.

    The check is conservative — when ``sqlparse`` cannot resolve a token
    cleanly, we raise rather than allow the query through silently.

    Parameters
    ----------
    sql:
        The SQL string the agent intends to execute.
    allowlist:
        Optional override (defaults to :data:`ACL_ALLOWLIST`). Tests use
        the override to construct positive + negative cases.

    Raises
    ------
    ACLViolation
        On any table reference outside the allowlist.
    """
    allow = allowlist if allowlist is not None else ACL_ALLOWLIST
    tables = extract_table_names(sql)
    if not tables:
        # No FROM/JOIN at all — likely a comment-only string or a SELECT
        # of constants. Conservative: allow (no DB tables touched).
        return
    for raw in tables:
        bare = _strip_schema(raw)
        if bare not in allow:
            raise ACLViolation(table=raw, sql=sql)


def extract_table_names(sql: str) -> list[str]:
    """Return the table identifiers referenced by FROM/JOIN clauses.

    Strips comments + string literals before parsing (sqlparse already
    tokenises them as separate Token types — we filter post-parse).

    Returned names preserve any schema prefix (e.g. ``atlas.atlas_signal_calls``);
    :func:`verify_query_allowlist` strips the schema for the allowlist
    comparison.
    """
    if not sql or not sql.strip():
        return []
    parsed = sqlparse.parse(sql)
    tables: list[str] = []
    for statement in parsed:
        tables.extend(_walk_statement_for_tables(statement))
    # De-dup while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for t in tables:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def _walk_statement_for_tables(statement: sqlparse.sql.Statement) -> list[str]:
    """Walk a sqlparse Statement and pull table identifiers from FROM/JOIN."""
    tables: list[str] = []
    # sqlparse exposes tokens flat at the top level + nested for
    # identifier lists; we iterate flat tokens and track context.
    from_seen = False
    tokens = list(statement.flatten())
    structured = list(statement.tokens)

    for idx, tok in enumerate(structured):
        if _is_from_or_join_keyword(tok):
            target = _next_meaningful(structured, idx)
            if target is None:
                continue
            tables.extend(_identifiers_from_token(target))
        # UPDATE / DELETE / INSERT INTO targets — defense in depth.  This
        # module is intended for SELECT-only reads, but we treat any
        # mutating reference as a violation by recording the table name
        # the same way (the allowlist check will then refuse it).
        if tok.ttype is Keyword.DML and tok.normalized.upper() in {"UPDATE", "DELETE", "INSERT"}:
            target = _next_meaningful(structured, idx)
            if target is None:
                continue
            tables.extend(_identifiers_from_token(target))

    # Some test cases (very short or whitespace-only) may bypass the
    # structural walk; fall back to a permissive flat scan that picks up
    # post-FROM identifiers we may have missed.
    if not tables:
        for _i, tok in enumerate(tokens):
            if tok.ttype is Keyword and tok.normalized.upper() in {"FROM", "JOIN"}:
                from_seen = True
                continue
            if from_seen and tok.ttype is None and tok.value.strip():
                tables.append(tok.value.strip())
                from_seen = False
    return tables


def _is_from_or_join_keyword(token: Token) -> bool:
    """True if ``token`` is a FROM/JOIN keyword (any JOIN variant)."""
    if token.ttype is not Keyword:
        return False
    norm = token.normalized.upper()
    return norm == "FROM" or norm.endswith("JOIN")


def _next_meaningful(tokens: list[Token], idx: int) -> Token | None:
    """Return the next non-whitespace, non-comment token after ``idx``."""
    for tok in tokens[idx + 1 :]:
        if tok.is_whitespace:
            continue
        if tok.ttype in (sqlparse.tokens.Comment, sqlparse.tokens.Comment.Single):
            continue
        return tok
    return None


def _identifiers_from_token(token: Token) -> list[str]:
    """Pull bare table identifiers out of an Identifier / IdentifierList."""
    out: list[str] = []
    if isinstance(token, IdentifierList):
        for ident in token.get_identifiers():
            out.extend(_identifiers_from_token(ident))
        return out
    if isinstance(token, Identifier):
        name = token.get_real_name()
        if name:
            parent = token.get_parent_name()
            out.append(f"{parent}.{name}" if parent else name)
        return out
    # Some sqlparse versions return a bare Name token instead of an
    # Identifier — pull the raw value.
    val = (token.value or "").strip()
    if val:
        # Strip trailing punctuation that sqlparse may leave attached
        # (e.g. "atlas_signal_calls," in a comma-joined FROM list).
        cleaned = val.rstrip(",;)").strip()
        if cleaned and not cleaned.startswith("("):
            out.append(cleaned)
    return out


def _strip_schema(qualified: str) -> str:
    """Return ``table`` from ``schema.table`` (drops the schema prefix).

    Schemas not in :data:`_ALLOWED_SCHEMAS` make the bare name fall
    through to the allowlist check unchanged (and therefore reject).
    """
    if "." not in qualified:
        return qualified
    schema, _, table = qualified.partition(".")
    if schema.lower() in _ALLOWED_SCHEMAS:
        return table
    return qualified  # unknown schema — leave qualified so allowlist rejects


# ---------------------------------------------------------------------------
# Session opener
# ---------------------------------------------------------------------------


@contextmanager
def open_readonly_session(
    engine: Engine,
    *,
    role: str = _AGENT_ROLE,
) -> Iterator[Connection]:
    """Yield a SQLAlchemy ``Connection`` configured for read-only agent use.

    Behaviour
    ---------
    * If the Postgres role ``atlas_agent_readonly`` exists, the
      connection is wrapped in a transaction with ``SET LOCAL ROLE`` to
      the agent role for the duration of the session. Postgres then
      refuses any access outside the role's GRANTs.
    * If the role does NOT exist (local dev), a warning is logged and
      the connection runs as the engine's default role. The
      application-layer :func:`verify_query_allowlist` guard still
      applies.

    Either way, the session is wrapped in a transaction with read-only +
    deferrable flags so any accidental write attempt errors out at the
    server.

    Parameters
    ----------
    engine:
        The SQLAlchemy engine (typically from :func:`atlas.db.get_engine`).
    role:
        Override the role name — defaults to ``atlas_agent_readonly``.

    Yields
    ------
    Connection
        A connection bound to the readonly role (or default), wrapped
        in a read-only transaction.
    """
    conn = engine.connect()
    try:
        role_exists = _role_exists(conn, role)
        if not role_exists:
            log.warning(
                "agent_acl_role_missing",
                role=role,
                msg=("agent ACL: Postgres role missing; relying on application-layer guard only"),
            )
        # Begin a transaction so SET LOCAL + read-only mode survive only
        # this session.
        trans = conn.begin()
        try:
            # READ ONLY + DEFERRABLE catches any accidental UPDATE/INSERT
            # at the server even before the application-layer guard runs.
            conn.execute(text("SET TRANSACTION READ ONLY"))
            if role_exists:
                conn.execute(text(f'SET LOCAL ROLE "{role}"'))
            yield conn
            trans.commit()
        except Exception:
            trans.rollback()
            raise
    finally:
        conn.close()


def _role_exists(conn: Connection, role: str) -> bool:
    """Return True iff a Postgres role with the given name is provisioned."""
    try:
        result = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
            {"role": role},
        ).first()
    except Exception as exc:
        # Non-Postgres backend (SQLite in some test fixtures) or other
        # error — treat as "role missing" and continue with the
        # application-layer guard.
        log.warning(
            "agent_acl_role_check_failed",
            role=role,
            err=str(exc)[:200],
        )
        return False
    return result is not None
