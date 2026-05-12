"""Phase C Route Crawler — Playwright-based frontend accuracy validator.

Crawls Atlas frontend routes, extracts ``data-validator-id`` DOM values,
and diffs them against SQL source-of-truth. Persists mismatches as
``frontend_diff`` or ``frontend_extract_error`` findings.

Public API:
    run_crawl(engine, base_url, password) -> list[Finding]
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from atlas.agents.validator.models import Finding


def run_crawl(
    engine: Engine,
    *,
    base_url: str | None = None,
    password: str | None = None,
) -> list[Finding]:
    """Lazy-load crawl.run_crawl to defer playwright import until call time."""
    from atlas.agents.validator.route_crawler.crawl import run_crawl as _run_crawl

    return _run_crawl(engine, base_url=base_url, password=password)


__all__ = ["run_crawl"]
