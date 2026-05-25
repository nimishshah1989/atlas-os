"""Constant sets for the v6 query audit.

Autonomous resolutions (from plan patch header 2026-05-26):
  - atlas_universe_snapshot   → RENAMED to atlas_universe_stocks; flag if found
  - atlas_sector_breadth_daily → DERIVED from atlas_scorecard_daily.features JSONB; flag if FROM found
  - atlas_fund_holdings_history → REPLACED by atlas_fund_scorecard.top_holdings JSONB; flag if FROM found
  - atlas_ledger_public       → RENAMED to atlas_ledger; flag if _public suffix found
"""

from __future__ import annotations

import re

# Tables that are VIEWs applied directly to Supabase (not in Alembic migrations).
# Source: docs/superpowers/plans/2026-05-18-atlas-signal-consolidation.md
KNOWN_VIEWS: frozenset[str] = frozenset(
    {
        "atlas_stock_signal_unified",
        "atlas_sector_signal_unified",
        "atlas_fund_signal_unified",
        "atlas_etf_signal_unified",
    }
)

# Tables in the JIP `public` schema — not tracked in Atlas Alembic migrations.
KNOWN_JIP_PUBLIC_TABLES: frozenset[str] = frozenset(
    {
        "de_index_prices",
        "de_index_constituents",
        "de_index_master",
        "de_mf_master",
        "de_mf_nav_daily",
        "de_mf_technical_daily",
        "instruments",
        "stock_ohlcv",
    }
)

# Deprecated table names that should have been replaced — flag these explicitly.
DEPRECATED_NAMES: dict[str, str] = {
    "atlas_universe_snapshot": (
        "REPLACED by atlas_universe_stocks (migration 002). "
        "Remove any atlas_universe_snapshot references in v6 queries."
    ),
    "atlas_sector_breadth_daily": (
        "DOES NOT EXIST. Derive sector breadth on-the-fly from "
        "atlas_scorecard_daily.features JSONB (ema_distance_20/50/200 present per migration 080)."
    ),
    "atlas_fund_holdings_history": (
        "DOES NOT EXIST. Use atlas_fund_scorecard.top_holdings JSONB "
        "(per autonomous resolution 2026-05-26)."
    ),
    "atlas_ledger_public": (
        "RENAMED to atlas_ledger (migration 083). "
        "Remove _public suffix from all v6 query references."
    ),
}

# Regex patterns that indicate a JSONB unpack rather than a real table reference.
# These are NOT table dependencies and should not be flagged.
JSONB_UNPACK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"jsonb_to_recordset\(", re.IGNORECASE),
    re.compile(r"jsonb_array_elements\(", re.IGNORECASE),
    re.compile(r"jsonb_each\(", re.IGNORECASE),
)
