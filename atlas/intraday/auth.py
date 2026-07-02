"""KiteConnect OAuth helper: token exchange, encrypted storage, retrieval."""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone

import psycopg2
import structlog

log = structlog.get_logger()

# IST offset: UTC+5:30
_IST_OFFSET = timezone(timedelta(hours=5, minutes=30))


def _strip_dialect(conn_str: str) -> str:
    """Strip SQLAlchemy dialect prefix for raw psycopg2 connections.

    Handles postgresql+psycopg2://... → postgresql://...
    Per wiki bug-pattern: SQLAlchemy Dialect Prefix in psycopg2/psql.
    """
    if conn_str.startswith("postgresql+psycopg2://"):
        return conn_str.replace("postgresql+psycopg2://", "postgresql://", 1)
    return conn_str


def exchange_request_token(request_token: str) -> dict[str, str]:
    """Exchange a KiteConnect OAuth request_token for an access_token.

    Args:
        request_token: The short-lived request token from the OAuth callback.

    Returns:
        Dict with keys: ``access_token``, ``login_time``, ``user_id``.

    Raises:
        ValueError: If KITE_API_KEY or KITE_API_SECRET are not set.
        RuntimeError: Wrapping any kiteconnect exceptions.
    """
    api_key = os.environ.get("KITE_API_KEY")
    api_secret = os.environ.get("KITE_API_SECRET")
    if not api_key:
        raise ValueError("KITE_API_KEY environment variable not set")
    if not api_secret:
        raise ValueError("KITE_API_SECRET environment variable not set")

    try:
        from kiteconnect import KiteConnect  # type: ignore[import-untyped]

        kite = KiteConnect(api_key=api_key)
        session_data: dict = kite.generate_session(request_token, api_secret=api_secret)
    except Exception as exc:
        raise RuntimeError(f"KiteConnect session generation failed: {exc}") from exc

    return {
        "access_token": session_data["access_token"],
        "login_time": str(session_data.get("login_time", "")),
        "user_id": str(session_data.get("user_id", "")),
    }


def store_access_token(access_token: str, *, conn_str: str) -> None:
    """Store a KiteConnect access token encrypted in atlas_kite_session.

    Closes any existing active sessions first, then inserts a new active row
    with the token encrypted via pgp_sym_encrypt.

    Args:
        access_token: Plaintext KiteConnect access token.
        conn_str: DSN for the atlas database.

    Raises:
        KeyError: If KITE_TOKEN_ENCRYPTION_KEY environment variable not set.
    """
    enc_key = os.environ["KITE_TOKEN_ENCRYPTION_KEY"]

    # Compute expires_at = 23:59:59 IST today (tokens expire at midnight IST)
    now_ist = datetime.now(tz=_IST_OFFSET)
    expires_ist = datetime.combine(now_ist.date(), time(23, 59, 59), tzinfo=_IST_OFFSET)

    dsn = _strip_dialect(conn_str)
    conn = psycopg2.connect(dsn)  # type: ignore[attr-defined]
    try:
        with conn:
            with conn.cursor() as cur:
                # Close all existing active sessions
                cur.execute(
                    """
                    UPDATE atlas_foundation.atlas_kite_session
                    SET session_type = 'closed', updated_at = NOW()
                    WHERE session_type = 'active'
                    """
                )
                closed_count = cur.rowcount
                if closed_count:
                    log.info("kite_sessions_closed", count=closed_count)

                # Insert new active session with encrypted token
                cur.execute(
                    """
                    INSERT INTO atlas_foundation.atlas_kite_session
                        (access_token_enc, session_type, expires_at)
                    VALUES
                        (pgp_sym_encrypt(%s, %s), 'active', %s)
                    """,
                    (access_token, enc_key, expires_ist),
                )
        log.info("kite_session_stored", expires_at=expires_ist.isoformat())
    finally:
        conn.close()


def get_valid_access_token(*, conn_str: str) -> str:
    """Retrieve and decrypt the active KiteConnect access token.

    Args:
        conn_str: DSN for the atlas database.

    Returns:
        Plaintext access_token string.

    Raises:
        KeyError: If KITE_TOKEN_ENCRYPTION_KEY environment variable not set.
        RuntimeError: If no active, non-expired session exists.
    """
    enc_key = os.environ["KITE_TOKEN_ENCRYPTION_KEY"]

    dsn = _strip_dialect(conn_str)
    conn = psycopg2.connect(dsn)  # type: ignore[attr-defined]
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pgp_sym_decrypt(access_token_enc, %s)
                FROM atlas_foundation.atlas_kite_session
                WHERE session_type = 'active'
                  AND expires_at > NOW()
                ORDER BY login_time DESC
                LIMIT 1
                """,
                (enc_key,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise RuntimeError("No valid Kite session found. Visit /api/kite/login to authenticate.")

    return str(row[0])
