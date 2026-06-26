#!/usr/bin/env python3
"""Headless daily Kite login via TOTP → store encrypted access token.

Zerodha access tokens expire at midnight IST, so this runs every morning (cron)
BEFORE the data pull. No browser: it drives Kite's login + twofa endpoints with
`requests`, generates the 6-digit code from the stored TOTP secret (pyotp),
captures the OAuth `request_token`, exchanges it for an access_token, and stores
it encrypted in atlas.atlas_kite_session (reusing atlas.intraday.auth).

Credentials come from .env (chmod 600, gitignored):
  KITE_API_KEY, KITE_API_SECRET, KITE_TOKEN_ENCRYPTION_KEY,
  KITE_USER_ID, KITE_PASSWORD, KITE_TOTP_SECRET

Run:  .venv/bin/python scripts/kite_autologin.py
Exit 0 on success (token stored + verified), non-zero otherwise.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import pyotp
import requests

_REPO = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    env = _REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$", line)
        if m and m.group(1) not in os.environ:
            os.environ[m.group(1)] = m.group(2).strip().strip('"').strip("'")


def _need(key: str) -> str:
    v = os.environ.get(key, "").strip()
    if not v:
        sys.exit(f"missing {key} in environment/.env")
    return v


def _find_request_token(resp: requests.Response) -> str | None:
    """request_token rides in a redirect Location across the login chain."""
    candidates = [resp.url]
    for h in resp.history:
        candidates.append(h.url)
        loc = h.headers.get("Location", "")
        if loc:
            candidates.append(loc)
    for u in candidates:
        q = parse_qs(urlparse(u).query)
        if "request_token" in q:
            return q["request_token"][0]
        m = re.search(r"request_token=([A-Za-z0-9]+)", u or "")
        if m:
            return m.group(1)
    return None


def auto_login() -> str:
    """Full TOTP login → returns a fresh access_token (also stored encrypted)."""
    _load_env()
    sys.path.insert(0, str(_REPO / "scripts" / "foundation"))
    import _db
    from atlas.intraday.auth import exchange_request_token, store_access_token

    api_key = _need("KITE_API_KEY")
    user_id = _need("KITE_USER_ID")
    password = _need("KITE_PASSWORD")
    totp_secret = _need("KITE_TOTP_SECRET")

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"

    # 1. password login → request_id
    r = s.post("https://kite.zerodha.com/api/login",
               data={"user_id": user_id, "password": password}, timeout=15)
    j = r.json()
    if j.get("status") != "success":
        sys.exit(f"login failed: {j.get('message', r.text[:160])}")
    request_id = j["data"]["request_id"]
    # Zerodha labels the authenticator-app TOTP code "app_code"; use whatever the
    # login step says this account expects rather than hardcoding.
    twofa_type = j["data"].get("twofa_type", "app_code")

    # 2. twofa with the time-based code
    code = pyotp.TOTP(totp_secret).now()
    r2 = s.post("https://kite.zerodha.com/api/twofa",
                data={"user_id": user_id, "request_id": request_id,
                      "twofa_value": code, "twofa_type": twofa_type}, timeout=15)
    j2 = r2.json()
    if j2.get("status") != "success":
        sys.exit(f"twofa failed: {j2.get('message', r2.text[:160])}")

    # 3. OAuth connect → capture request_token from the redirect chain
    try:
        resp = s.get(f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3",
                     allow_redirects=True, timeout=15)
        request_token = _find_request_token(resp)
    except requests.exceptions.RequestException as e:
        # redirect_url host may be unreachable; the token is still in the failed URL
        request_token = None
        m = re.search(r"request_token=([A-Za-z0-9]+)", str(getattr(e, "request", "")) + str(e))
        if m:
            request_token = m.group(1)
    if not request_token:
        sys.exit("could not capture request_token (check the app's redirect URL)")

    # 4. exchange + store encrypted
    session_data = exchange_request_token(request_token)
    access_token = session_data["access_token"]
    store_access_token(access_token, conn_str=_db.db_url())
    return access_token


def main() -> None:
    token = auto_login()
    # verify the token actually works
    from kiteconnect import KiteConnect
    kite = KiteConnect(api_key=os.environ["KITE_API_KEY"])
    kite.set_access_token(token)
    profile = kite.profile()
    print(f"OK — Kite session live for {profile.get('user_id')} "
          f"({profile.get('user_name', '')}). Token stored encrypted.")


if __name__ == "__main__":
    main()
