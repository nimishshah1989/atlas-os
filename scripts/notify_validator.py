#!/usr/bin/env python3
"""Send Phase C validator digest email.

Queries the most recent ``frontend_diff`` run from atlas_validator_findings
and sends an email digest summarising P0/P1 findings with their routes and
identifiers.

Usage:
    python scripts/notify_validator.py [--run-id UUID]

Options:
    --run-id UUID   Notify about a specific run. Defaults to the most recent
                    frontend_diff run completed today.

Required env vars:
    SMTP_USER     — Gmail address for sending
    SMTP_PASS     — Gmail App Password
    NOTIFY_EMAIL  — Recipient email (default: nimish.shah1989@gmail.com)
    ATLAS_DB_URL  — PostgreSQL DSN
"""

from __future__ import annotations

import argparse
import os
import smtplib
import sys
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import text


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Atlas validator digest notifier")
    p.add_argument("--run-id", default="", help="Specific run UUID (default: latest)")
    return p.parse_args()


def _get_latest_run_id(conn: object) -> str | None:
    from sqlalchemy.engine import Connection

    assert isinstance(conn, Connection)
    row = conn.execute(
        text("""
            SELECT id FROM atlas.atlas_validator_runs
            WHERE scope = 'frontend_diff'
              AND status = 'success'
            ORDER BY completed_at DESC NULLS LAST
            LIMIT 1
        """)
    ).fetchone()
    return str(row[0]) if row else None


def _fetch_findings(conn: object, run_id: str) -> list[dict[str, str]]:
    from sqlalchemy.engine import Connection

    assert isinstance(conn, Connection)
    rows = conn.execute(
        text("""
            SELECT severity, surface, identifier, expected_value, actual_value, route
            FROM atlas.atlas_validator_findings
            WHERE run_id = :rid
              AND severity IN ('P0', 'P1')
            ORDER BY severity, surface
        """),
        {"rid": run_id},
    ).fetchall()
    return [
        {
            "severity": r[0],
            "surface": r[1],
            "identifier": r[2],
            "expected": r[3],
            "actual": r[4],
            "route": r[5] or "—",
        }
        for r in rows
    ]


def main() -> int:
    args = _parse_args()

    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    notify_to = os.environ.get("NOTIFY_EMAIL", "nimish.shah1989@gmail.com")

    if not smtp_user or not smtp_pass:
        print(
            "[notify_validator] SMTP_USER/SMTP_PASS not configured — skipping digest.",
            file=sys.stderr,
        )
        return 0

    from atlas.db import get_engine

    engine = get_engine()

    with engine.connect() as conn:
        run_id = args.run_id.strip() or _get_latest_run_id(conn)
        if not run_id:
            print("[notify_validator] No completed frontend_diff run found.", file=sys.stderr)
            return 0

        findings = _fetch_findings(conn, run_id)

    if not findings:
        print(f"[notify_validator] No P0/P1 findings for run {run_id} — skipping email.")
        return 0

    p0_count = sum(1 for f in findings if f["severity"] == "P0")
    p1_count = sum(1 for f in findings if f["severity"] == "P1")
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"Atlas Frontend Validator Digest — {now_str}",
        f"Run ID: {run_id}",
        f"P0 findings: {p0_count}  |  P1 findings: {p1_count}",
        "",
    ]

    if p0_count:
        lines.append(f"=== P0 DIFFS ({p0_count}) ===")
        for f in findings:
            if f["severity"] == "P0":
                lines.append(
                    f"  [{f['severity']}] {f['surface']}  route={f['route']}"
                    f"\n      id={f['identifier']}"
                    f"\n      expected={f['expected']}  actual={f['actual']}"
                )
        lines.append("")

    if p1_count:
        lines.append(f"=== P1 DIFFS ({p1_count}) ===")
        for f in findings:
            if f["severity"] == "P1":
                lines.append(
                    f"  [{f['severity']}] {f['surface']}  route={f['route']}"
                    f"\n      id={f['identifier']}"
                )
        lines.append("")

    body = "\n".join(lines)
    subject = f"[Atlas] Frontend Validator — {p0_count} P0, {p1_count} P1 — {now_str[:10]}"

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = notify_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [notify_to], msg.as_string())
        print(f"[notify_validator] Digest sent to {notify_to} ({p0_count}P0, {p1_count}P1)")
    except Exception as e:
        print(f"[notify_validator] Failed to send email: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
