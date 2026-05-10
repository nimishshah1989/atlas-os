#!/usr/bin/env python3
"""Send failure email from Atlas nightly cron.

Usage: notify_failure.py <step_name> <log_file>

Required env vars (add to .env):
  SMTP_USER — Gmail address for sending (e.g. alerts@yourcompany.com)
  SMTP_PASS — Gmail App Password (Settings → Security → App passwords)
  NOTIFY_EMAIL — recipient (defaults to nimish.shah1989@gmail.com)

If SMTP_USER / SMTP_PASS are not set, logs to stderr and exits 0
so the cron run still completes normally.
"""

from __future__ import annotations

import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def main() -> None:
    step = sys.argv[1] if len(sys.argv) > 1 else "unknown step"
    log_file = sys.argv[2] if len(sys.argv) > 2 else None

    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    notify_to = os.environ.get("NOTIFY_EMAIL", "nimish.shah1989@gmail.com")

    if not smtp_user or not smtp_pass:
        print(
            f"[notify_failure] SMTP_USER/SMTP_PASS not configured — "
            f"skipping email for failed step: {step}",
            file=sys.stderr,
        )
        return

    # Grab last 50 lines of log for context
    log_tail = ""
    if log_file and Path(log_file).exists():
        lines = Path(log_file).read_text(errors="replace").splitlines()
        log_tail = "\n".join(lines[-50:])

    subject = f"[Atlas] Nightly pipeline FAILED at {step} — {datetime.now():%Y-%m-%d}"
    body = f"""Atlas nightly pipeline failed at step: {step}
Time: {datetime.now():%Y-%m-%d %H:%M:%S IST}
Host: {os.uname().nodename}

--- Last 50 lines of log ---
{log_tail}
"""

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = notify_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [notify_to], msg.as_string())
        print(f"[notify_failure] Email sent to {notify_to}")
    except Exception as e:
        print(f"[notify_failure] Failed to send email: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
