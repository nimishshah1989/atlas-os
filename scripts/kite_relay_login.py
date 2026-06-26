#!/usr/bin/env python3
"""One-time Kite login by relaying a single live 2FA code from the user.

Two steps so a human can hand over one fresh code in between:
  start          -> password login, save session + request_id to a state file
  finish <code>  -> submit the 6-digit code, capture request_token, store token

Avoids browser address-bar copying and avoids retry loops (one twofa attempt).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests

_REPO = Path(__file__).resolve().parents[1]
_STATE = Path(
    "/tmp/claude-1000/-home-ubuntu-atlas-os/e6126a13-7711-4b3d-a338-2dfda44b6a45/scratchpad/kite_relay_state.json"
)


def _load_env() -> None:
    env = _REPO / ".env"
    for line in env.read_text().splitlines():
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$", line)
        if m and m.group(1) not in os.environ:
            os.environ[m.group(1)] = m.group(2).strip().strip('"').strip("'")


def start() -> None:
    _load_env()
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    r = s.post(
        "https://kite.zerodha.com/api/login",
        data={"user_id": os.environ["KITE_USER_ID"], "password": os.environ["KITE_PASSWORD"]},
        timeout=15,
    )
    j = r.json()
    if j.get("status") != "success":
        sys.exit(f"login failed: {j.get('message', r.text[:160])}")
    st = {
        "request_id": j["data"]["request_id"],
        "twofa_type": j["data"].get("twofa_type", "app_code"),
        "cookies": requests.utils.dict_from_cookiejar(s.cookies),
        "user_id": os.environ["KITE_USER_ID"],
    }
    _STATE.write_text(json.dumps(st))
    print("primed OK — ready for one fresh 6-digit code.")


def finish(code: str) -> None:
    _load_env()
    sys.path.insert(0, str(_REPO / "scripts" / "foundation"))
    sys.path.insert(0, str(_REPO / "scripts"))
    import _db
    from kite_autologin import _find_request_token

    from atlas.intraday.auth import exchange_request_token, store_access_token

    st = json.loads(_STATE.read_text())
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    s.cookies = requests.utils.cookiejar_from_dict(st["cookies"])

    r2 = s.post(
        "https://kite.zerodha.com/api/twofa",
        data={
            "user_id": st["user_id"],
            "request_id": st["request_id"],
            "twofa_value": code.strip(),
            "twofa_type": st["twofa_type"],
        },
        timeout=15,
    )
    j2 = r2.json()
    if j2.get("status") != "success":
        sys.exit(f"twofa failed: {j2.get('message', r2.text[:160])}")

    api_key = os.environ["KITE_API_KEY"]
    resp = s.get(
        f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3",
        allow_redirects=True,
        timeout=15,
    )
    rt = _find_request_token(resp)
    if not rt:
        sys.exit("authenticated, but could not capture request_token")
    access_token = exchange_request_token(rt)["access_token"]
    store_access_token(access_token, conn_str=_db.db_url())

    from kiteconnect import KiteConnect

    k = KiteConnect(api_key=api_key)
    k.set_access_token(access_token)
    p = k.profile()
    print(
        f"OK — Kite session live for {p.get('user_id')} ({p.get('user_name', '')}). Token stored."
    )


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "finish":
        finish(sys.argv[2])
    else:
        start()
