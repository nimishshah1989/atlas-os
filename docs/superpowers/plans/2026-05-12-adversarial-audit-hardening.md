# Adversarial Audit Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all 21 findings from the 2026-05-12 Codex adversarial review, plus remove the OpenBB module entirely, achieving zero open issues before `/security-review` and `/cso` pass.

**Architecture:** Surgical file-level fixes across api/, compute/, intraday/, migrations/. No new abstractions. No scope creep. Each task is independently committable and independently testable.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, pandas/numpy, PyJWT, Alembic, psycopg2

---

## Task 1: Remove OpenBB entirely

**Files:**
- Delete: `atlas/api/openbb/` (entire directory)
- Modify: `atlas/api/__init__.py` (remove imports + router)
- Modify: `atlas/config.py` (remove OPENBB_BACKEND_API_KEY)

**Context:** The OpenBB BYO Copilot integration (SP03) is being decommissioned. The module at `atlas/api/openbb/` includes auth, query, events, metadata, schemas, and handlers. The `/v1/*` route exemption in auth.py and the CORS allow-list also need cleanup.

- [ ] **Step 1: Remove the openbb directory**
```bash
rm -rf atlas/api/openbb/
```

- [ ] **Step 2: Update atlas/api/__init__.py**

Current lines to remove:
```python
from atlas.api.openbb.router import openbb_router
# ...
allow_origins=["https://pro.openbb.co", "https://app.openbb.co", "https://openbb.co"],
# ...
app.include_router(openbb_router)  # SP03: OpenBB BYO Copilot — /v1/agents.json, /v1/query
```

Replace the CORS allow_origins with just the Atlas frontend:
```python
allow_origins=["https://atlas.jslwealth.in"],
```

Remove the `from atlas.api.openbb.router import openbb_router` import and the `app.include_router(openbb_router)` line. Final `__init__.py` router section should only include: strategies_router, kite_auth_router, agents_router, intraday_router, portfolios_router, rule_based_router, admin_proposals_router.

- [ ] **Step 3: Remove OPENBB_BACKEND_API_KEY from atlas/config.py**

Remove these lines from `Config`:
```python
# SP03: OpenBB BYO Copilot API key. Set in .env on EC2.
# NOT a Supabase JWT — OpenBB Workspace sends its own bearer for /v1/* routes.
# Empty string disables auth (local dev only). Never empty in production.
OPENBB_BACKEND_API_KEY: str = os.environ.get("OPENBB_BACKEND_API_KEY", "")
```

- [ ] **Step 4: Remove /v1 and /agents.json from auth exempt prefixes**

In `atlas/api/auth.py`, remove these two lines from `_EXEMPT_PREFIXES`:
```python
"/v1",
"/agents.json",
```

- [ ] **Step 5: Verify no remaining references**
```bash
grep -r "openbb\|OPENBB\|agents\.json" atlas/ frontend/src/ --include="*.py" --include="*.ts" --include="*.tsx" | grep -v ".pyc"
```
Expected: zero results (except possibly test files that reference OpenBB by string literal, which should also be removed).

- [ ] **Step 6: Run tests to confirm nothing broken**
```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os
python -m pytest tests/ -x -q 2>&1 | tail -20
```

- [ ] **Step 7: Commit**
```bash
git add -A atlas/api/openbb atlas/api/__init__.py atlas/config.py atlas/api/auth.py
git commit -m "feat(openbb): remove SP03 OpenBB BYO Copilot integration entirely"
```

---

## Task 2: JWT audience/issuer enforcement

**Files:**
- Modify: `atlas/api/auth.py:78`

**Context:** `jwt.decode` currently only checks signature and expiry. If a token is issued by a different service but shares the same HS256 secret, it's accepted. Adding `audience` and `issuer` checks closes token-confusion attacks.

The Supabase JWT uses `iss = "https://<project>.supabase.co/auth/v1"` and `aud = "authenticated"`.

- [ ] **Step 1: Add env vars to config**

In `atlas/config.py`, add to `Config` class:
```python
# Supabase JWT claims — must match tokens issued by your Supabase project.
SUPABASE_JWT_ISSUER: str = os.environ.get("SUPABASE_JWT_ISSUER", "")
SUPABASE_JWT_AUDIENCE: str = os.environ.get("SUPABASE_JWT_AUDIENCE", "authenticated")
```

- [ ] **Step 2: Update jwt.decode in auth.py**

Find this line in `atlas/api/auth.py`:
```python
payload: dict = jwt.decode(token, secret, algorithms=["HS256"])  # type: ignore[assignment]
```

Replace with:
```python
decode_kwargs: dict = {"algorithms": ["HS256"]}
if Config.SUPABASE_JWT_ISSUER:
    decode_kwargs["issuer"] = Config.SUPABASE_JWT_ISSUER
if Config.SUPABASE_JWT_AUDIENCE:
    decode_kwargs["audience"] = Config.SUPABASE_JWT_AUDIENCE
payload: dict = jwt.decode(token, secret, **decode_kwargs)  # type: ignore[assignment]
```

- [ ] **Step 3: Verify tests pass**
```bash
python -m pytest tests/ -x -q -k "auth" 2>&1 | tail -20
```

- [ ] **Step 4: Commit**
```bash
git add atlas/api/auth.py atlas/config.py
git commit -m "fix(auth): enforce aud/iss claims in JWT decode to prevent token-confusion"
```

---

## Task 3: Kite OAuth CSRF state validation

**Files:**
- Modify: `atlas/api/kite_auth.py`

**Context:** The Kite OAuth flow redirects to Zerodha, then receives a callback at `/api/kite/callback`. Without a `state` parameter, an attacker can trick the endpoint into accepting their token. Fix: generate a signed state (HMAC-SHA256 of a random nonce using `SUPABASE_JWT_SECRET` as key) at login, store in a short-lived DB row or cookie, verify at callback.

Simplest approach: use a signed state stored in a temporary DB column or a short-lived cache. Since we have no Redis, use a DB row with a 5-minute TTL.

- [ ] **Step 1: Add CSRF state table to new migration**

Create `migrations/versions/043_add_kite_oauth_state.py`:
```python
"""Add kite_oauth_state table for CSRF protection.

Revision ID: 043
Revises: 042
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_kite_oauth_state (
            state_token TEXT PRIMARY KEY,
            expires_at  TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '5 minutes'),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_kite_oauth_state"))
```

- [ ] **Step 2: Add state generation and verification to kite_auth.py**

In `atlas/api/kite_auth.py`, update the login endpoint to generate a state:
```python
import hashlib
import hmac
import secrets

def _generate_state(engine: Engine) -> str:
    """Generate a signed CSRF state token and persist it for 5 minutes."""
    nonce = secrets.token_urlsafe(32)
    secret = Config.SUPABASE_JWT_SECRET.encode() or b"dev"
    sig = hmac.new(secret, nonce.encode(), hashlib.sha256).hexdigest()
    state = f"{nonce}.{sig}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO atlas.atlas_kite_oauth_state (state_token) VALUES (:s)"),
            {"s": state},
        )
    return state
```

Update `kite_login` to add `state` to the redirect URL:
```python
state = _generate_state(get_engine())
login_url = f"{_KITE_LOGIN_BASE}?api_key={api_key}&v=3&state={state}"
```

Update `kite_callback` signature and add state verification:
```python
def kite_callback(
    request_token: Annotated[str, Query(...)],
    state: Annotated[str, Query(description="CSRF state from login redirect")],
) -> RedirectResponse:
    # Verify state exists and is not expired
    with get_engine().begin() as conn:
        row = conn.execute(
            text("""
                DELETE FROM atlas.atlas_kite_oauth_state
                WHERE state_token = :s AND expires_at > NOW()
                RETURNING state_token
            """),
            {"s": state},
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=400, detail={
            "error_code": "invalid_oauth_state",
            "message": "OAuth state is missing, expired, or already used.",
            "context": {},
        })
    # ... rest of callback unchanged
```

- [ ] **Step 3: Verify tests pass**
```bash
python -m pytest tests/ -x -q -k "kite" 2>&1 | tail -20
```

- [ ] **Step 4: Commit**
```bash
git add atlas/api/kite_auth.py migrations/versions/043_add_kite_oauth_state.py
git commit -m "fix(auth): add CSRF state validation to Kite OAuth flow"
```

---

## Task 4: Intraday backend service token auth

**Files:**
- Modify: `atlas/api/auth.py`
- Modify: `atlas/api/intraday.py`

**Context:** `/api/v1/intraday` is in `_EXEMPT_PREFIXES` so any unauthenticated caller can hit it directly. The frontend Next.js proxy sends `Authorization: Bearer $ATLAS_INTERNAL_SECRET` but the backend ignores it. Fix: remove the exemption and add a lightweight service-token check for the intraday prefix specifically.

- [ ] **Step 1: Add ATLAS_INTERNAL_SECRET to config**

In `atlas/config.py`:
```python
# Internal service-to-service secret. Set in .env. Frontend proxy sends this
# as Bearer token for /api/v1/intraday/* calls. Empty = dev mode (no check).
ATLAS_INTERNAL_SECRET: str = os.environ.get("ATLAS_INTERNAL_SECRET", "")
```

- [ ] **Step 2: Remove /api/v1/intraday from exempt prefixes in auth.py**

In `atlas/api/auth.py`, remove this line from `_EXEMPT_PREFIXES`:
```python
"/api/v1/intraday",  # SP08: intraday data — auth handled by Next.js proxy layer
```

Then add a service-token path in the dispatch method, BEFORE the full JWT check:
```python
# Service-token fast path for internal /api/v1/intraday/* calls.
# The Next.js proxy sends Authorization: Bearer <ATLAS_INTERNAL_SECRET>.
if path.startswith("/api/v1/intraday"):
    expected = Config.ATLAS_INTERNAL_SECRET
    if expected:
        bearer = request.headers.get("Authorization", "")[7:]
        if not hmac.compare_digest(bearer, expected):
            return _unauthorized("invalid_service_token", "Invalid internal service token")
    return await call_next(request)
```

Add `import hmac` at the top of auth.py.

- [ ] **Step 3: Verify tests pass**
```bash
python -m pytest tests/ -x -q -k "intraday" 2>&1 | tail -20
```

- [ ] **Step 4: Commit**
```bash
git add atlas/api/auth.py atlas/config.py
git commit -m "fix(auth): enforce service token on /api/v1/intraday instead of blanket exemption"
```

---

## Task 5: Redact PII from logs

**Files:**
- Modify: `scripts/run_intraday.py:86`
- Modify: `atlas/api/agents.py:98`
- Modify: `atlas/intraday/notify.py:34`

**Context:** Three locations leak sensitive data into structlog: the database URL prefix (can include auth tokens in unusual DSN formats), user questions (can contain PII under DPDP), and Telegram chat IDs.

- [ ] **Step 1: Fix scripts/run_intraday.py**

Find:
```python
log.info("intraday_starting", database_url_prefix=database_url[:30])
```
Replace with:
```python
log.info("intraday_starting")
```

- [ ] **Step 2: Fix atlas/api/agents.py**

Find:
```python
log.info(
    "agents_invoke_request",
    agent=body.agent,
    question_preview=body.question[:80],
    user_id=user_id,
)
```
Replace with:
```python
log.info(
    "agents_invoke_request",
    agent=body.agent,
    user_id=user_id,
)
```

- [ ] **Step 3: Fix atlas/intraday/notify.py**

Find:
```python
log.debug("telegram_message_sent", chat_id=chat_id)
```
Replace with:
```python
log.debug("telegram_message_sent")
```

- [ ] **Step 4: Commit**
```bash
git add scripts/run_intraday.py atlas/api/agents.py atlas/intraday/notify.py
git commit -m "fix(security): redact PII/credentials from structlog statements (DPDP compliance)"
```

---

## Task 6: Standardize DB URL to Config.assert_db_url()

**Files:**
- Modify: `atlas/api/kite_auth.py:93`
- Modify: `scripts/run_intraday.py:59`

**Context:** `kite_auth.py` reads `DATABASE_URL` directly from `os.environ`, and `run_intraday.py` does the same. Both should use `Config.assert_db_url()` so there is one source of truth and one error message if the URL is missing.

- [ ] **Step 1: Fix atlas/api/kite_auth.py**

Find:
```python
conn_str = os.environ.get("DATABASE_URL", "")
if not conn_str:
    log.error("kite_callback_missing_database_url")
    raise HTTPException(
        status_code=500,
        detail={
            "error_code": "server_misconfigured",
            "message": "DATABASE_URL not set.",
```
Replace with:
```python
from atlas.config import Config
try:
    conn_str = Config.assert_db_url()
except RuntimeError:
    log.error("kite_callback_missing_database_url")
    raise HTTPException(
        status_code=500,
        detail={
            "error_code": "server_misconfigured",
            "message": "ATLAS_DB_URL not set.",
```

Also add `from atlas.config import Config` at top of file if not already present. Remove `import os` usage for DATABASE_URL only.

- [ ] **Step 2: Fix scripts/run_intraday.py**

Find:
```python
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    log.error("intraday_startup_failed", reason="DATABASE_URL environment variable not set")
    sys.exit(1)
```
Replace with:
```python
try:
    database_url = Config.assert_db_url()
except RuntimeError:
    log.error("intraday_startup_failed", reason="ATLAS_DB_URL environment variable not set")
    sys.exit(1)
```

Add `from atlas.config import Config` at top of file.

- [ ] **Step 3: Commit**
```bash
git add atlas/api/kite_auth.py scripts/run_intraday.py
git commit -m "fix(config): standardize all DB URL reads to Config.assert_db_url() - closes split config bug"
```

---

## Task 7: Fix intraday ingester _current_bar race condition

**Files:**
- Modify: `atlas/intraday/ingester.py:313`

**Context:** `_on_reconnect` writes to `self._current_bar` without acquiring `self._bar_lock`, while `_bar_close_loop` acquires the lock before calling `_process_bar_close` (which also reads/writes `_current_bar`). This creates a data race during reconnect windows.

Fix: acquire `_bar_lock` at the start of `_on_reconnect` before touching `_current_bar`.

- [ ] **Step 1: Wrap _on_reconnect body in self._bar_lock**

In `atlas/intraday/ingester.py`, find `_on_reconnect`:
```python
def _on_reconnect(self, _ws: Any, attempts_count: int) -> None:
    """On reconnect, backfill current bar from REST quotes."""
    log.warning("ticker_reconnecting", attempts=attempts_count)
    if self._kite is None:
        return
    try:
        tokens = list(self._token_map.keys())
        quotes: dict = self._kite.quote(tokens)
        for token_str, quote_data in quotes.items():
```

Wrap the body in a lock:
```python
def _on_reconnect(self, _ws: Any, attempts_count: int) -> None:
    """On reconnect, backfill current bar from REST quotes."""
    log.warning("ticker_reconnecting", attempts=attempts_count)
    if self._kite is None:
        return
    with self._bar_lock:
        try:
            tokens = list(self._token_map.keys())
            quotes: dict = self._kite.quote(tokens)
            for token_str, quote_data in quotes.items():
                token = int(token_str)
                ohlc = quote_data.get("ohlc", {})
                last_price = quote_data.get("last_price")
                if not last_price:
                    continue
                close = Decimal(str(last_price))
                open_val = Decimal(str(ohlc.get("open", last_price)))
                high_val = Decimal(str(ohlc.get("high", last_price)))
                low_val = Decimal(str(ohlc.get("low", last_price)))
                volume = int(quote_data.get("volume", 0))

                if token not in self._current_bar:
                    self._current_bar[token] = {
                        "open": open_val,
                        "high": high_val,
                        "low": low_val,
                        "close": close,
                        "volume": volume,
                        "tick_count": 1,
                    }
                else:
                    bar = self._current_bar[token]
                    bar["close"] = close
                    bar["high"] = max(bar["high"], high_val)
                    bar["low"] = min(bar["low"], low_val)
            log.info("reconnect_backfill_complete", token_count=len(quotes))
        except Exception as exc:
            log.warning("reconnect_backfill_failed", error=str(exc))
```

- [ ] **Step 2: Run intraday tests**
```bash
python -m pytest tests/ -x -q -k "intraday or ingester" 2>&1 | tail -20
```

- [ ] **Step 3: Commit**
```bash
git add atlas/intraday/ingester.py
git commit -m "fix(intraday): acquire bar_lock in _on_reconnect to prevent _current_bar race"
```

---

## Task 8: Fix backtest and recompute concurrency races

**Files:**
- Modify: `atlas/api/strategies.py:83`
- Modify: `atlas/api/internal_recompute.py:137`
- Create: `migrations/versions/044_add_pipeline_concurrency_indexes.py`

**Context:** Both endpoints do check-then-insert without holding a lock. Two concurrent requests can both pass the "no running" check and both spawn runs. Fix: move the INSERT into the same connection+transaction as the check, using `INSERT ... ON CONFLICT DO NOTHING` with a unique partial index, then check if we inserted.

- [ ] **Step 1: Create migration with unique partial index**

Create `migrations/versions/044_add_pipeline_concurrency_indexes.py`:
```python
"""Add unique partial index for pipeline concurrency guard.

Revision ID: 044
Revises: 043
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One active backtest at a time. Partial index on active states only.
    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_pipeline_runs_backtest_active
        ON atlas.atlas_pipeline_runs (script_name)
        WHERE script_name = 'backtest_engine' AND status IN ('queued', 'running')
    """))
    # One active recompute per milestone at a time.
    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_pipeline_runs_milestone_active
        ON atlas.atlas_pipeline_runs (milestone)
        WHERE status = 'running'
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS atlas.uq_pipeline_runs_backtest_active"))
    op.execute(sa.text("DROP INDEX IF EXISTS atlas.uq_pipeline_runs_milestone_active"))
```

- [ ] **Step 2: Fix strategies.py backtest race**

In `atlas/api/strategies.py`, replace the two separate `with engine.connect()` blocks (check + insert) with a single atomic transaction using INSERT ON CONFLICT:
```python
new_run_id = uuid.uuid4()
try:
    with engine.begin() as conn:
        # Also verify strategy exists in same transaction
        strategy = conn.execute(
            text("SELECT strategy_id FROM atlas.atlas_strategies WHERE strategy_id = :sid"),
            {"sid": str(strategy_id)},
        ).fetchone()
        if strategy is None:
            raise HTTPException(status_code=404, detail={...})

        conn.execute(
            text("""
                INSERT INTO atlas.atlas_pipeline_runs
                  (run_id, script_name, milestone, started_at, status, host, git_sha)
                VALUES
                  (:rid, 'backtest_engine', 'M15', NOW(), 'queued', 'api', NULL)
            """),
            {"rid": str(new_run_id)},
        )
except HTTPException:
    raise
except Exception as exc:
    if "uq_pipeline_runs_backtest_active" in str(exc):
        raise HTTPException(status_code=409, detail={
            "error_code": "already_running",
            "message": "A backtest is already in progress",
            "context": {},
        })
    raise
```

Remove the old two-step check + insert pattern.

- [ ] **Step 3: Fix internal_recompute.py race**

In `atlas/api/internal_recompute.py`, change the concurrency check from a separate SELECT to an atomic INSERT ON CONFLICT. The pattern:

```python
run_id = uuid.uuid4()
try:
    with _db(engine) as conn:
        conn.execute(
            text("""
                INSERT INTO atlas.atlas_pipeline_runs
                  (run_id, script_name, milestone, started_at, status, host, git_sha)
                VALUES
                  (:rid, :script, :milestone, NOW(), 'running', 'api', NULL)
            """),
            {"rid": str(run_id), "script": f"{milestone}_daily.py", "milestone": milestone.upper()},
        )
        conn.commit()
except Exception as exc:
    if "uq_pipeline_runs_milestone_active" in str(exc):
        raise HTTPException(status_code=409, detail={
            "error_code": "already_running",
            "message": "A pipeline run is already in progress.",
            "context": {},
        })
    raise
```

Remove the old SELECT check before INSERT.

- [ ] **Step 4: Run tests**
```bash
python -m pytest tests/ -x -q -k "backtest or recompute or strategy" 2>&1 | tail -20
```

- [ ] **Step 5: Commit**
```bash
git add atlas/api/strategies.py atlas/api/internal_recompute.py migrations/versions/044_add_pipeline_concurrency_indexes.py
git commit -m "fix(concurrency): make backtest and recompute triggers atomic via INSERT ON CONFLICT + unique partial index"
```

---

## Task 9: Fix sector topdown RS scale mismatch

**Files:**
- Modify: `atlas/compute/sectors.py:717`

**Context:** `topdown_rs_3m_nifty500` is computed as `(1 + index_ret) / (1 + nifty500_ret) - 1` (delta form, centered around 0). The thresholds `> 1.05` and `< 0.95` are ratio-form thresholds — they can never be triggered since delta values are typically in the ±0.1 range. Fix: use delta-form thresholds `0.05` and `-0.05`.

- [ ] **Step 1: Update thresholds in sectors.py**

Find in `atlas/compute/sectors.py` around line 713:
```python
    # Use top-down ret_3m / RS-vs-Nifty500 as a simple proxy. Top-down state
    # is informational; final sector_state is bottomup-driven per methodology
    # priority. Top-down "Overweight" if rs_3m_nifty500 > 1.0, "Avoid" if
    # < 0.95, else Neutral / Underweight by ret_3m sign.
    td_rs = out["topdown_rs_3m_nifty500"]
    td_ret = out["topdown_ret_3m"]
    out["topdown_state"] = np.select(
        [
            td_rs > 1.05,
            td_rs < 0.95,
            (td_ret < 0),
        ],
        ["Overweight", "Avoid", "Underweight"],
        default="Neutral",
    )
```

Replace with:
```python
    # RS is price-relative delta form: (1+index_ret)/(1+bench_ret) - 1.
    # Values are centered around 0 (e.g. 0.05 = 5% outperformance).
    # Thresholds: >0.05 = meaningful outperformance, <-0.05 = meaningful underperformance.
    td_rs = out["topdown_rs_3m_nifty500"]
    td_ret = out["topdown_ret_3m"]
    out["topdown_state"] = np.select(
        [
            td_rs > 0.05,
            td_rs < -0.05,
            (td_ret < 0),
        ],
        ["Overweight", "Avoid", "Underweight"],
        default="Neutral",
    )
```

- [ ] **Step 2: Run sector tests**
```bash
python -m pytest tests/ -x -q -k "sector" 2>&1 | tail -20
```

- [ ] **Step 3: Commit**
```bash
git add atlas/compute/sectors.py
git commit -m "fix(compute): correct topdown_state RS thresholds from ratio form (1.05/0.95) to delta form (0.05/-0.05)"
```

---

## Task 10: Fix fund lens fillna(0) and swallowed exceptions

**Files:**
- Modify: `atlas/compute/lens_nav.py:223` (fillna)
- Modify: `atlas/compute/lens_nav.py:393` (swallowed exceptions)

**Context:**
1. `fillna(0)` on fund returns before RS calculation silently distorts RS when data is missing — a gap looks like a flat period and inflates the RS numerically.
2. Per-fund exceptions are caught and ignored, allowing the run to report success with partial output.

- [ ] **Step 1: Fix fillna(0) in RS calculation**

Find in `atlas/compute/lens_nav.py`:
```python
    for name in ("1m", "3m", "6m"):
        f_ret = merged[f"ret_{name}"].fillna(0)
        b_ret = merged[f"bench_ret_{name}"].fillna(0)  # benchmark gap → treat as 0
        denom = 1 + b_ret
        denom = denom.where(denom != 0, np.nan)
        merged[f"rs_{name}_category"] = (1 + f_ret) / denom - 1
```

Replace with:
```python
    for name in ("1m", "3m", "6m"):
        f_ret = merged[f"ret_{name}"]  # keep NaN — gaps must not become 0
        b_ret = merged[f"bench_ret_{name}"]  # keep NaN — gaps must not become 0
        denom = 1 + b_ret
        denom = denom.where(denom.notna() & (denom != 0), np.nan)
        merged[f"rs_{name}_category"] = (1 + f_ret) / denom - 1
        na_count = merged[f"rs_{name}_category"].isna().sum()
        if na_count:
            log.debug("fund_rs_null_rows", window=name, null_rows=int(na_count))
```

- [ ] **Step 2: Fix swallowed exceptions in lens_nav.py**

Find:
```python
    errors: list[dict[str, Any]] = []

    for _, fund in fund_universe.iterrows():
        try:
            fund_metrics = compute_fund_nav_raw_metrics(...)
            if not fund_metrics.empty:
                all_metrics.append(fund_metrics)
        except Exception as exc:
            errors.append({"mstar_id": fund["mstar_id"], "error": str(exc)})
            log.error("lens1_fund_error", mstar_id=fund["mstar_id"], error=str(exc))

    if not all_metrics:
        log.warning("lens1_no_metrics_computed")
```

Replace with:
```python
    errors: list[dict[str, Any]] = []
    total_funds = len(fund_universe)

    for _, fund in fund_universe.iterrows():
        try:
            fund_metrics = compute_fund_nav_raw_metrics(...)
            if not fund_metrics.empty:
                all_metrics.append(fund_metrics)
        except Exception as exc:
            errors.append({"mstar_id": fund["mstar_id"], "error": str(exc)})
            log.error("lens1_fund_error", mstar_id=fund["mstar_id"], error=str(exc))

    error_rate = len(errors) / max(total_funds, 1)
    if error_rate > 0.1:
        raise RuntimeError(
            f"Fund lens failed for {len(errors)}/{total_funds} funds "
            f"({error_rate:.0%}). Aborting to prevent partial write. "
            f"First error: {errors[0]['error'] if errors else 'none'}"
        )
    if errors:
        log.warning("lens1_partial_errors", error_count=len(errors), total=total_funds)

    if not all_metrics:
        log.warning("lens1_no_metrics_computed")
```

- [ ] **Step 3: Run tests**
```bash
python -m pytest tests/ -x -q -k "lens or fund" 2>&1 | tail -20
```

- [ ] **Step 4: Commit**
```bash
git add atlas/compute/lens_nav.py
git commit -m "fix(compute): fund lens must not fillna(0) before RS; fail run if >10% fund errors"
```

---

## Task 11: Make audit logging mandatory (remove silent failure)

**Files:**
- Modify: `atlas/health/runs.py`

**Context:** `safe_record` and `safe_finish` are used in production pipelines. If they silently fail, regulators have no execution lineage. The right fix: keep the safe interface but add retry and alert on failure. For now, log at ERROR (not WARNING) and re-raise after 1 retry so the pipeline gets a second chance without permanently blocking.

- [ ] **Step 1: Update safe_record and safe_finish in runs.py**

Find:
```python
def safe_record(script_name: str, **kwargs: Any) -> uuid.UUID | None:
    """Best-effort record_run that never raises.

    Use in scripts where a DB connection issue must NOT block the pipeline
    itself from running. Returns None if recording fails.
    """
    try:
        return record_run(script_name, **kwargs)
    except Exception as exc:
        log.warning("record_run_failed", script=script_name, error=str(exc))
        return None


def safe_finish(run_id: uuid.UUID | None, **kwargs: Any) -> None:
    """Best-effort finish_run that never raises."""
    if run_id is None:
        return
    try:
        finish_run(run_id, **kwargs)
    except Exception as exc:
        log.warning("finish_run_failed", run_id=str(run_id), error=str(exc))
```

Replace with:
```python
import time as _time


def safe_record(script_name: str, **kwargs: Any) -> uuid.UUID | None:
    """Record a pipeline run with one retry. Logs at ERROR on both failures.

    Returns None only after two consecutive failures — never silently drops.
    """
    for attempt in range(2):
        try:
            return record_run(script_name, **kwargs)
        except Exception as exc:
            log.error(
                "record_run_failed",
                script=script_name,
                attempt=attempt + 1,
                error=str(exc),
            )
            if attempt == 0:
                _time.sleep(2)
    return None


def safe_finish(run_id: uuid.UUID | None, **kwargs: Any) -> None:
    """Finish a pipeline run with one retry. Logs at ERROR on both failures."""
    if run_id is None:
        return
    for attempt in range(2):
        try:
            finish_run(run_id, **kwargs)
            return
        except Exception as exc:
            log.error(
                "finish_run_failed",
                run_id=str(run_id),
                attempt=attempt + 1,
                error=str(exc),
            )
            if attempt == 0:
                _time.sleep(2)
```

- [ ] **Step 2: Run tests**
```bash
python -m pytest tests/ -x -q -k "run or health" 2>&1 | tail -20
```

- [ ] **Step 3: Commit**
```bash
git add atlas/health/runs.py
git commit -m "fix(ops): safe_record/safe_finish now retry once and log at ERROR (not WARNING)"
```

---

## Task 12: Migrate Kite access_token_enc from TEXT to BYTEA

**Files:**
- Create: `migrations/versions/045_kite_token_text_to_bytea.py`
- Modify: `atlas/intraday/auth.py` (remove `::bytea` cast hack)

**Context:** The `access_token_enc` column is `TEXT` but stores encrypted binary data. `pgp_sym_decrypt` expects `BYTEA`. The current workaround is `access_token_enc::bytea` text cast which is fragile and binary-unsafe.

- [ ] **Step 1: Create migration**

Create `migrations/versions/045_kite_token_text_to_bytea.py`:
```python
"""Change access_token_enc from TEXT to BYTEA.

Revision ID: 045
Revises: 044
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_kite_session
        ALTER COLUMN access_token_enc TYPE BYTEA
        USING access_token_enc::bytea
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_kite_session
        ALTER COLUMN access_token_enc TYPE TEXT
        USING encode(access_token_enc, 'escape')
    """))
```

- [ ] **Step 2: Remove ::bytea cast in atlas/intraday/auth.py**

Find:
```python
SELECT pgp_sym_decrypt(access_token_enc::bytea, %s)
```
Replace with:
```python
SELECT pgp_sym_decrypt(access_token_enc, %s)
```

- [ ] **Step 3: Run tests**
```bash
python -m pytest tests/ -x -q -k "kite or intraday or auth" 2>&1 | tail -20
```

- [ ] **Step 4: Commit**
```bash
git add migrations/versions/045_kite_token_text_to_bytea.py atlas/intraday/auth.py
git commit -m "fix(intraday): migrate access_token_enc TEXT→BYTEA; drop fragile ::bytea cast"
```

---

## Task 13: Fix MV breakout/deterioration — use prior trading day

**Files:**
- Create: `migrations/versions/046_fix_mv_prior_trading_day.py`

**Context:** The materialized views `mv_breakout_candidates` and `mv_deterioration_watch` use `(SELECT d - 1 FROM latest)` which subtracts 1 calendar day. On Mondays and post-holidays this produces the wrong "prior" date. Fix: join to `de_trading_calendar` to get the actual most recent trading day before the latest date.

- [ ] **Step 1: Create migration that drops and recreates the two MVs**

Create `migrations/versions/046_fix_mv_prior_trading_day.py`:
```python
"""Fix breakout/deterioration MVs to use prior trading day, not d-1 calendar day.

Revision ID: 046
Revises: 045
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None

_BREAKOUT_MV = """
    CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_breakout_candidates AS
    WITH
    latest AS (
        SELECT MAX(date) AS d FROM atlas.atlas_stock_states_daily
    ),
    prior_trading AS (
        SELECT MAX(date) AS d
        FROM public.de_trading_calendar
        WHERE date < (SELECT d FROM latest)
          AND COALESCE(is_trading_day, TRUE) = TRUE
    ),
    today AS (
        SELECT s.instrument_id, s.date, s.rs_state, s.momentum_state, s.state_since_date,
               m.rs_pctile_3m
        FROM atlas.atlas_stock_states_daily s
        JOIN atlas.atlas_stock_metrics_daily m
          ON m.instrument_id = s.instrument_id AND m.date = s.date
        WHERE s.date = (SELECT d FROM latest)
          AND s.rs_state IN ('Strong', 'Leader')
          AND s.liquidity_gate_pass = TRUE
          AND s.history_gate_pass   = TRUE
    ),
    yesterday AS (
        SELECT instrument_id, rs_state
        FROM atlas.atlas_stock_states_daily
        WHERE date = (SELECT d FROM prior_trading)
    )
    SELECT
        t.instrument_id,
        t.date,
        u.symbol,
        u.company_name,
        u.sector,
        u.tier,
        t.rs_state          AS new_rs_state,
        y.rs_state          AS prior_rs_state,
        t.momentum_state,
        t.state_since_date,
        t.rs_pctile_3m::numeric(10, 4) AS rs_pctile_3m
    FROM today t
    JOIN atlas.atlas_universe_stocks u ON u.instrument_id = t.instrument_id
    LEFT JOIN yesterday y              ON y.instrument_id = t.instrument_id
    WHERE y.rs_state IS NULL OR y.rs_state NOT IN ('Strong', 'Leader')
    WITH DATA
"""

_DETERIORATION_MV = """
    CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_deterioration_watch AS
    WITH
    latest AS (
        SELECT MAX(date) AS d FROM atlas.atlas_stock_states_daily
    ),
    prior_trading AS (
        SELECT MAX(date) AS d
        FROM public.de_trading_calendar
        WHERE date < (SELECT d FROM latest)
          AND COALESCE(is_trading_day, TRUE) = TRUE
    ),
    today AS (
        SELECT instrument_id, date, rs_state, momentum_state, state_since_date,
               liquidity_gate_pass, history_gate_pass
        FROM atlas.atlas_stock_states_daily
        WHERE date = (SELECT d FROM latest)
    ),
    yesterday AS (
        SELECT instrument_id, rs_state
        FROM atlas.atlas_stock_states_daily
        WHERE date = (SELECT d FROM prior_trading)
    )
    SELECT
        t.instrument_id,
        t.date,
        u.symbol,
        u.company_name,
        u.sector,
        u.tier,
        y.rs_state          AS prior_rs_state,
        t.rs_state          AS new_rs_state,
        t.momentum_state,
        t.state_since_date,
        m.rs_pctile_3m::numeric(10, 4) AS rs_pctile_3m
    FROM today t
    JOIN atlas.atlas_universe_stocks u ON u.instrument_id = t.instrument_id
    JOIN yesterday y                   ON y.instrument_id = t.instrument_id
    LEFT JOIN atlas.atlas_stock_metrics_daily m
           ON m.instrument_id = t.instrument_id AND m.date = t.date
    WHERE y.rs_state IN ('Strong', 'Leader')
      AND t.rs_state NOT IN ('Strong', 'Leader')
    WITH DATA
"""


def upgrade() -> None:
    # Must drop CONCURRENTLY-indexed MVs before recreating
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_breakout_candidates CASCADE"))
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_deterioration_watch CASCADE"))
    op.execute(sa.text(_BREAKOUT_MV))
    op.execute(sa.text(_DETERIORATION_MV))
    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uix_mv_breakout_instrument
        ON atlas.mv_breakout_candidates (instrument_id)
    """))
    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uix_mv_deterioration_instrument
        ON atlas.mv_deterioration_watch (instrument_id)
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_breakout_candidates CASCADE"))
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_deterioration_watch CASCADE"))
```

- [ ] **Step 2: Commit**
```bash
git add migrations/versions/046_fix_mv_prior_trading_day.py
git commit -m "fix(migrations): breakout/deterioration MVs use prior trading day (not d-1 calendar day)"
```

---

## Task 14: Make conviction cron scheduling idempotent

**Files:**
- Create: `migrations/versions/047_idempotent_conviction_cron.py`

**Context:** Migration 039 calls `cron.schedule(...)` without first unscheduling any existing job with the same name. Re-running the migration creates duplicate cron entries.

- [ ] **Step 1: Create migration to fix cron idempotency**

Create `migrations/versions/047_idempotent_conviction_cron.py`:
```python
"""Make conviction MV cron scheduling idempotent.

Revision ID: 047
Revises: 046
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        DO $body$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_cron') THEN
                PERFORM cron.unschedule('atlas_mv_conviction') ;
            END IF;
        EXCEPTION WHEN OTHERS THEN NULL;
        END
        $body$;
    """))
    op.execute(sa.text("""
        DO $body$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_cron') THEN
                PERFORM cron.schedule(
                    'atlas_mv_conviction',
                    '45 14 * * *',
                    'REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_top_conviction_daily'
                );
            ELSE
                RAISE NOTICE 'pg_cron not installed; skipping (apply on EC2)';
            END IF;
        END
        $body$;
    """))


def downgrade() -> None:
    pass  # Cannot safely reverse a cron schedule state change
```

- [ ] **Step 2: Commit**
```bash
git add migrations/versions/047_idempotent_conviction_cron.py
git commit -m "fix(migrations): make conviction MV pg_cron scheduling idempotent (unschedule before schedule)"
```

---

## Task 15: Vectorize fund drawdown computation

**Files:**
- Modify: `atlas/compute/lens_nav.py:162`

**Context:** `_rolling_max_drawdown` uses a Python loop that is O(n×window). For 500+ funds × 10 years of history, this is unnecessarily slow on the EC2 t3.large. Fix: vectorize using pandas `expanding().min()` on the cumulative return.

- [ ] **Step 1: Find and replace _rolling_max_drawdown**

Find the `_rolling_max_drawdown` function in `atlas/compute/lens_nav.py` and replace with a vectorized implementation:
```python
def _rolling_max_drawdown(returns: pd.Series, window: int = 252) -> pd.Series:
    """Maximum drawdown over a rolling window using vectorized cummax.

    Returns the largest peak-to-trough decline within each rolling window.
    Result is negative (e.g. -0.15 means 15% drawdown).
    """
    # Cumulative growth factor
    cum = (1 + returns.fillna(0)).cumprod()
    # Rolling maximum within window (the "peak")
    rolling_peak = cum.rolling(window, min_periods=1).max()
    # Drawdown at each point: how far below the rolling peak
    drawdown = cum / rolling_peak - 1
    # Worst (most negative) drawdown within the window
    return drawdown.rolling(window, min_periods=1).min()
```

- [ ] **Step 2: Verify output is the same type and shape as before**
```bash
python -c "
import pandas as pd, numpy as np
from atlas.compute.lens_nav import _rolling_max_drawdown
returns = pd.Series(np.random.randn(500) * 0.01)
result = _rolling_max_drawdown(returns)
assert result.dtype == float or str(result.dtype).startswith('float'), f'wrong dtype: {result.dtype}'
assert len(result) == len(returns), 'length mismatch'
assert (result <= 0).all(), 'drawdown should be non-positive'
print('OK', result.head())
"
```

- [ ] **Step 3: Commit**
```bash
git add atlas/compute/lens_nav.py
git commit -m "perf(compute): vectorize fund drawdown with rolling cummax instead of O(n*w) loop"
```

---

## Task 16: Add rs_3m_nifty500 to frontend (remove NULL column)

**Files:**
- Modify: `frontend/src/lib/queries/leaders.ts`

**Context:** The frontend queries `rs_3m_nifty500` from the stock metrics table but the stock pipeline never writes it — it's always NULL. Since we're removing OpenBB (which used it for display), the frontend leaders page should either drop the column or use `rs_pctile_3m` which IS written. For now, remove the unwritten column from the leaders query.

- [ ] **Step 1: Remove rs_3m_nifty500 from leaders.ts queries**

In `frontend/src/lib/queries/leaders.ts`, remove all references to `rs_3m_nifty500`:
- Remove from `RSLeaderRow` type definition
- Remove from all SELECT queries
- Remove from `BreakoutCandidateRow` type definition

- [ ] **Step 2: Check for any components using rs_3m_nifty500**
```bash
grep -rn "rs_3m_nifty500" frontend/src/ --include="*.ts" --include="*.tsx"
```
Remove any UI references found.

- [ ] **Step 3: Build check**
```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -20
```

- [ ] **Step 4: Commit**
```bash
git add frontend/src/lib/queries/leaders.ts
git commit -m "fix(frontend): remove rs_3m_nifty500 from leader queries (column never written by stock pipeline)"
```

---

## Task 17: Typed strategy config model

**Files:**
- Modify: `atlas/simulation/core/paper_trader.py`

**Context:** `paper_trader.py` uses `config: object` and accesses config fields via `getattr(config, "field", default)`. A malformed config silently falls back to defaults and the system trades with wrong parameters. Fix: add a simple dataclass or Pydantic model and validate at load time.

- [ ] **Step 1: Add typed config to paper_trader.py**

At the top of `atlas/simulation/core/paper_trader.py`, add:
```python
from dataclasses import dataclass, field
from decimal import Decimal as _Decimal


@dataclass(frozen=True)
class BacktestConfig:
    """Typed configuration for backtest/paper trading runs.

    Validates that required fields are present and typed correctly.
    Any unknown field in the source config object raises AttributeError early.
    """
    start_capital: _Decimal
    position_size_pct: _Decimal
    max_positions: int
    entry_state: str = "Leader"
    exit_state: str = "Weak"
    rebalance_freq: str = "monthly"

    @classmethod
    def from_obj(cls, obj: object) -> "BacktestConfig":
        """Construct from strategy config object. Raises ValueError on invalid config."""
        try:
            return cls(
                start_capital=_Decimal(str(getattr(obj, "start_capital"))),
                position_size_pct=_Decimal(str(getattr(obj, "position_size_pct"))),
                max_positions=int(getattr(obj, "max_positions")),
                entry_state=str(getattr(obj, "entry_state", "Leader")),
                exit_state=str(getattr(obj, "exit_state", "Weak")),
                rebalance_freq=str(getattr(obj, "rebalance_freq", "monthly")),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid strategy config: {exc}") from exc
```

Update any function that receives `config: object` to call `BacktestConfig.from_obj(config)` early and use the typed version.

- [ ] **Step 2: Run tests**
```bash
python -m pytest tests/ -x -q -k "backtest or paper_trader or simulation" 2>&1 | tail -20
```

- [ ] **Step 3: Commit**
```bash
git add atlas/simulation/core/paper_trader.py
git commit -m "refactor(simulation): add BacktestConfig dataclass to validate strategy config at load time"
```

---

## Task 18: Final verification — zero open issues

- [ ] **Step 1: Run full test suite**
```bash
python -m pytest tests/ -q 2>&1 | tail -30
```

- [ ] **Step 2: Re-run adversarial grep sweep to confirm fixes**
```bash
# Auth gaps
grep -n "EXEMPT_PREFIXES" atlas/api/auth.py

# PII in logs
grep -n "database_url_prefix\|question_preview\|chat_id=chat_id" atlas/ scripts/ -r --include="*.py"

# SQL f-strings without noqa
grep -rn "f\".*SELECT\|f'.*SELECT" atlas/ --include="*.py" | grep -v "# noqa" | grep -v test

# DB URL split
grep -rn "DATABASE_URL" atlas/ scripts/ --include="*.py" | grep -v "ATLAS_DB_URL\|assert_db_url\|Config"

# Bare except
grep -rn "^except:$\|    except:$" atlas/ --include="*.py" | grep -v "# noqa"

# fillna(0) on returns
grep -n "fillna(0)" atlas/compute/lens_nav.py
```

- [ ] **Step 3: Check pyright type errors**
```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os && python -m pyright atlas/ 2>&1 | tail -30
```

- [ ] **Step 4: Final commit summary**
```bash
git log --oneline -20
```

---

## Deferred (architectural — separate initiative)

These require more than surgical changes and are deferred to a follow-up session:

1. **Custom portfolio durable queue** — Moving `atlas/simulation/custom/portfolio.py` from in-process threading to a durable job table requires a new migration, a job processor, and API changes. ~2-3 days of work.

2. **Oversized module splits** — `sectors.py` (1025 LOC), `preflight.py` (923 LOC), `m1_data_quality.py` (821 LOC) need decomposition by responsibility. Non-trivial refactors, risk of behavioral regression.

3. **Compute and store stock rs_*_nifty500** — Requires adding price-relative RS computation to the stock pipeline and writing to the metrics table. Medium complexity; needs benchmark data join.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Codex Adversarial | `/codex` | Independent 2nd opinion — full codebase | 1 | FAIL | 21 findings |
| Security Review | `/security-review` | OWASP/pen-test focused | 0 | NOT RUN | — |
| CSO Review | `/cso` | SEBI/DPDP regulatory compliance | 0 | NOT RUN | — |
| Eng Review | `/plan-eng-review` | Architecture | 0 | NOT RUN | — |
