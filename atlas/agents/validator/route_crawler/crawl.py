"""Playwright-based route crawler for Phase C validator.

``run_crawl(engine, base_url, password)`` visits each route defined in
``routes.yaml``, extracts all ``data-validator-id`` DOM elements, diffs
their values against SQL source-of-truth, and returns a list of
``Finding`` objects for findings with severity P0–P2.

Authentication uses direct cookie injection (``atlas_auth`` cookie).
No login page visit; no Supabase JWT; no browser credentials stored.

Per-route isolation: a single route failure produces one P2 ``crawl_error``
finding and the crawl continues to the next route.

Screenshots: element-scoped, base64-encoded in ``evidence["screenshot_b64"]``.
Captured for P0 and P1 only. Element is scrolled into view first.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import structlog
import yaml
from playwright.async_api import (  # type: ignore[import-untyped]
    BrowserContext,
    Page,
    async_playwright,
)
from sqlalchemy.engine import Engine

from atlas.agents.validator.models import Finding
from atlas.agents.validator.route_crawler.diff import DiffResult, compare
from atlas.agents.validator.route_crawler.extract import ExtractError, ParsedValue, parse_dom_value
from atlas.agents.validator.route_crawler.sql_lookup import lookup

log = structlog.get_logger()

_ROUTES_YAML = Path(__file__).parent / "routes.yaml"
_TIMEOUT_MS = 30_000  # 30 s per route load
_NETWORKIDLE_MS = 15_000


def _load_routes() -> list[dict[str, str]]:
    with _ROUTES_YAML.open() as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return data["routes"]


async def _setup_auth(context: BrowserContext, base_url: str, password: str) -> None:
    """Inject atlas_auth cookie — matches frontend/middleware.ts password check."""
    parsed = urlparse(base_url)
    domain = parsed.netloc.split(":")[0]  # strip port if present
    await context.add_cookies(
        [
            {
                "name": "atlas_auth",
                "value": password,
                "domain": domain,
                "path": "/",
                "httpOnly": False,
                "secure": base_url.startswith("https"),
            }
        ]
    )


async def _capture_screenshot(page: Page, element_locator_str: str) -> str | None:
    """Scroll element into view and capture element-scoped screenshot.

    Returns base64-encoded PNG or None if capture fails.
    """
    try:
        loc = page.locator(f'[data-validator-id="{element_locator_str}"]').first
        await loc.scroll_into_view_if_needed(timeout=5_000)
        png_bytes = await loc.screenshot(timeout=5_000)
        return base64.b64encode(png_bytes).decode("ascii")
    except Exception:
        return None


async def _crawl_route(
    page: Page,
    base_url: str,
    route_cfg: dict[str, str],
    engine: Engine,
) -> list[Finding]:
    """Crawl a single route and return findings for that route.

    Raises on unrecoverable errors; caller wraps in try/except.
    """
    path = route_cfg["path"]
    wait_selector = route_cfg.get("wait_selector", "[data-validator-id]")
    url = base_url.rstrip("/") + path

    log.info("crawl_route_start", path=path)
    await page.goto(url, timeout=_TIMEOUT_MS, wait_until="domcontentloaded")

    # Belt-and-suspenders: wait for data elements AND network idle
    try:
        await page.wait_for_selector(wait_selector, timeout=_TIMEOUT_MS)
    except Exception:
        log.warning("crawl_route_no_elements", path=path)
        return []

    try:
        await page.wait_for_load_state("networkidle", timeout=_NETWORKIDLE_MS)
    except Exception:
        # networkidle timeout is non-fatal — data may still be present
        log.debug("crawl_route_networkidle_timeout", path=path)

    elements = await page.query_selector_all("[data-validator-id]")
    log.info("crawl_route_elements", path=path, count=len(elements))

    findings: list[Finding] = []
    with engine.connect() as conn:
        for el in elements:
            vid = await el.get_attribute("data-validator-id")
            raw_text = (await el.inner_text()).strip()
            if not vid:
                continue

            # Parse the field_key for diff
            field_key = vid.split(":")[0] if ":" in vid else vid

            # 1. Extract frontend value.
            # Prefer data-validator-raw for scale-adjusted fields (e.g. rs_pctile_3m
            # displayed as integer 85 but stored as 0.85 — raw carries the stored scale).
            raw_attr = await el.get_attribute("data-validator-raw")
            parse_source = raw_attr.strip() if raw_attr else raw_text
            frontend_val: ParsedValue
            try:
                frontend_val = parse_dom_value(parse_source)
            except ExtractError as exc:
                findings.append(
                    Finding(
                        finding_class="frontend_extract_error",
                        severity="P2",
                        surface=field_key,
                        identifier=vid,
                        expected_value="parseable value",
                        actual_value=exc.raw,
                        evidence={"route": path, "raw_text": exc.raw},
                        remediation="Data not yet loaded; check page hydration timing.",
                    )
                )
                continue

            # 2. Fetch backend value
            try:
                backend_val = lookup(vid, conn)
            except (ValueError, Exception) as exc:
                log.warning("crawl_lookup_error", vid=vid, error=str(exc))
                continue  # Unknown field — skip silently

            # 3. Diff
            result: DiffResult = compare(field_key, frontend_val, backend_val)

            if result.severity == "P3":
                continue  # clean — not persisted

            # 4. Capture screenshot for P0/P1
            screenshot_b64: str | None = None
            if result.needs_screenshot:
                screenshot_b64 = await _capture_screenshot(page, vid)

            evidence: dict[str, Any] = {
                "route": path,
                "raw_text": raw_text,
            }
            if screenshot_b64:
                evidence["screenshot_b64"] = screenshot_b64

            findings.append(
                Finding(
                    finding_class="frontend_diff",
                    severity=result.severity,
                    surface=field_key,
                    identifier=vid,
                    expected_value=result.expected,
                    actual_value=result.actual,
                    evidence=evidence,
                    remediation=(
                        "Frontend value diverges from SQL source. "
                        "Check nightly compute pipeline and MV refresh ordering."
                    ),
                    delta_abs=result.delta_abs,
                    delta_pct=result.delta_pct,
                )
            )

    p0 = sum(1 for f in findings if f.severity == "P0")
    p1 = sum(1 for f in findings if f.severity == "P1")
    p2 = sum(1 for f in findings if f.severity == "P2")
    log.info("crawl_route_done", path=path, p0=p0, p1=p1, p2=p2)
    return findings


async def _run_crawl_async(
    engine: Engine,
    base_url: str,
    password: str,
) -> list[Finding]:
    routes = _load_routes()
    all_findings: list[Finding] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        await _setup_auth(context, base_url, password)

        for route_cfg in routes:
            path = route_cfg["path"]
            page = await context.new_page()
            try:
                route_findings = await _crawl_route(page, base_url, route_cfg, engine)
                all_findings.extend(route_findings)
            except Exception as exc:
                log.error("crawl_route_error", path=path, error=str(exc))
                all_findings.append(
                    Finding(
                        finding_class="frontend_diff",
                        severity="P2",
                        surface=f"route_crawler.{path.lstrip('/').replace('/', '_')}",
                        identifier=f"route={path}",
                        expected_value="successful page crawl",
                        actual_value=f"error: {exc}",
                        evidence={"route": path, "error": str(exc)},
                        remediation=(
                            "Route failed to load. Check that the frontend is up "
                            "and that auth cookie is valid."
                        ),
                    )
                )
            finally:
                await page.close()

        await context.close()
        await browser.close()

    return all_findings


def run_crawl(
    engine: Engine,
    *,
    base_url: str | None = None,
    password: str | None = None,
) -> list[Finding]:
    """Crawl all configured routes and return a list of findings.

    Args:
        engine: SQLAlchemy engine for backend SQL lookups.
        base_url: Atlas frontend base URL. Defaults to ``ATLAS_BASE_URL`` env var.
        password: ``atlas_auth`` cookie value. Defaults to ``ATLAS_PASSWORD`` env var.

    Returns:
        List of ``Finding`` objects with severity P0, P1, or P2.
        P3 (clean) comparisons are not returned.
    """
    import asyncio

    resolved_url = base_url or os.environ.get("ATLAS_BASE_URL", "")
    resolved_pw = password or os.environ.get("ATLAS_PASSWORD", "")

    if not resolved_url:
        raise ValueError("ATLAS_BASE_URL not set and base_url not provided.")
    if not resolved_pw:
        raise ValueError("ATLAS_PASSWORD not set and password not provided.")

    return asyncio.run(_run_crawl_async(engine, resolved_url, resolved_pw))
