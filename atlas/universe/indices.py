"""Atlas index universe builder.

Per methodology Section 9 + M1 spec: a curated 75-index list drawn from
NSE's broader catalog (135 indices in JIP). Five role categories totalling
exactly 75 codes.

Note (2026-05-06 reality check): JIP's index_code naming differs from
NSE's marketing names — e.g. ``NIFTY SMLCAP 250`` not ``NIFTY SMALLCAP 250``,
``NIFTY OIL AND GAS`` not ``NIFTY OIL & GAS``. The list below uses the
exact JIP codes verified against ``public.de_index_master``.

INDIA VIX is read by M3's regime classifier from ``atlas_index_metrics_daily``
but is NOT part of the curated 75 (VIX isn't an investable index — it's a
volatility input).
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.config import Config
from atlas.db import get_engine

log = structlog.get_logger()


_BROAD = (
    "NIFTY 50",
    "NIFTY 100",
    "NIFTY 200",
    "NIFTY 500",
    "NIFTY NEXT 50",
    "NIFTY MIDCAP 50",
    "NIFTY MIDCAP 100",
    "NIFTY MIDCAP 150",
    "NIFTY SMLCAP 50",
    "NIFTY SMLCAP 100",
    "NIFTY SMLCAP 250",
    "NIFTY MICROCAP250",
    "NIFTY TOTAL MKT",
    "NIFTY LARGEMID250",
    "NIFTY MIDSML 400",
)  # 15

_SECTORAL = (
    "NIFTY BANK",
    "NIFTY IT",
    "NIFTY FMCG",
    "NIFTY AUTO",
    "NIFTY PHARMA",
    "NIFTY METAL",
    "NIFTY ENERGY",
    "NIFTY REALTY",
    "NIFTY MEDIA",
    "NIFTY PSU BANK",
    "NIFTY PVT BANK",
    "NIFTY HEALTHCARE",
)  # 12

_INDUSTRY = (
    "NIFTY FIN SERVICE",
    "NIFTY FINSEREXBNK",
    "NIFTY OIL AND GAS",
    "NIFTY CONSR DURBL",
    "NIFTY CAPITAL MKT",
    "NIFTY MIDSML HLTH",
    "NIFTY MS FIN SERV",
    "NIFTY MS IT TELCM",
    "NIFTY MS IND CONS",
    "NIFTY HOUSING",
    "NIFTY MOBILITY",
    "NIFTY IND TOURISM",
    "NIFTY IND DEFENCE",
    "NIFTY EV",
    "NIFTY INFRALOG",
)  # 15

_FACTOR = (
    "NIFTY ALPHA 50",
    "NIFTY ALPHALOWVOL",
    "NIFTY100 QUALTY30",
    "NIFTY200 QUALTY30",
    "NIFTY200 VALUE 30",
    "NIFTY500 VALUE 50",
    "NIFTY500MOMENTM50",
    "NIFTY200MOMENTM30",
    "NIFTY100 LOWVOL30",
    "NIFTY LOW VOL 50",
    "NIFTY500 LOWVOL50",
    "NIFTY HIGHBETA 50",
    "NIFTY DIV OPPS 50",
    "NIFTY GROWSECT 15",
    "NIFTY100 EQL WGT",
    "NIFTY100 ALPHA 30",
    "NIFTY200 ALPHA 30",
    "NIFTY AQLV 30",
)  # 18

_THEMATIC = (
    "NIFTY CPSE",
    "NIFTY PSE",
    "NIFTY MNC",
    "NIFTY INFRA",
    "NIFTY INDIA MFG",
    "NIFTY SERV SECTOR",
    "NIFTY COMMODITIES",
    "NIFTY IND DIGITAL",
    "NIFTY CONSUMPTION",
    "NIFTY NEW CONSUMP",
    "NIFTY NONCYC CONS",
    "NIFTY INTERNET",
    "NIFTY MULTI INFRA",
    "NIFTY MULTI MFG",
    "NIFTY RAILWAYSPSU",
)  # 15


# Sector-index → atlas_sector_master.sector_name. Only sectoral indices have
# linked_sector populated. Industry/factor/thematic don't link 1:1 to a sector.
# Sector-index → atlas_sector_master.sector_name (verified against JIP).
# PSU Bank / Pvt Bank both map to parent "Banking" sector since JIP doesn't
# sub-classify them.
_SECTORAL_LINK_MAP: dict[str, str] = {
    "NIFTY BANK": "Banking",
    "NIFTY IT": "IT",
    "NIFTY FMCG": "FMCG",
    "NIFTY AUTO": "Automobile",
    "NIFTY PHARMA": "Pharma",
    "NIFTY METAL": "Metal",
    "NIFTY ENERGY": "Energy",
    "NIFTY REALTY": "Realty",
    "NIFTY MEDIA": "Media",
    "NIFTY HEALTHCARE": "Healthcare",
    "NIFTY PSU BANK": "Banking",
    "NIFTY PVT BANK": "Banking",
}


def _curated_list() -> list[tuple[str, str, str | None]]:
    """Return the 75-index list as (index_code, role, linked_sector)."""
    items: list[tuple[str, str, str | None]] = []
    for code in _BROAD:
        items.append((code, "broad", None))
    for code in _SECTORAL:
        items.append((code, "sectoral", _SECTORAL_LINK_MAP.get(code)))
    for code in _INDUSTRY:
        items.append((code, "industry", None))
    for code in _FACTOR:
        items.append((code, "factor", None))
    for code in _THEMATIC:
        items.append((code, "thematic", None))
    return items


def build_index_universe(engine: Engine | None = None) -> list[dict[str, object]]:
    """Return 75 index universe rows joined with ``de_index_master`` metadata.

    Raises ``AssertionError`` if any curated code is missing from
    ``de_index_master`` — that's a hard stop, not a silent skip.

    NOTE: ``de_index_master`` does NOT have ``inception_date`` (verified
    2026-05-06). Inception date stays NULL in atlas_universe_indices for v0.
    """
    eng = engine or get_engine()
    curated = _curated_list()

    if len(curated) != 75:
        raise AssertionError(
            f"Curated index list size = {len(curated)}, expected 75. "
            "Update _BROAD / _SECTORAL / _INDUSTRY / _FACTOR / _THEMATIC tuples."
        )

    with eng.connect() as conn:
        master_rows = conn.execute(
            text("SELECT index_code, index_name FROM public.de_index_master")
        ).all()
    master = {r[0]: r[1] for r in master_rows}

    missing = [code for code, _, _ in curated if code not in master]
    if missing:
        raise RuntimeError(
            f"Curated index codes not found in de_index_master: {missing}. "
            "Update curated list or check JIP Data Core ingest."
        )

    rows: list[dict[str, object]] = []
    role_counts: dict[str, int] = {}
    for code, role, linked_sector in curated:
        rows.append(
            {
                "index_code": code,
                "index_name": master[code],
                "role": role,
                "linked_sector": linked_sector,
                "inception_date": None,
            }
        )
        role_counts[role] = role_counts.get(role, 0) + 1

    log.info("index_universe_built", total=len(rows), roles=role_counts)
    return rows


def populate_universe_indices(engine: Engine | None = None) -> int:
    eng = engine or get_engine()
    rows = build_index_universe(eng)

    insert_sql = text("""
        INSERT INTO atlas.atlas_universe_indices
            (index_code, index_name, role, linked_sector, inception_date,
             effective_from, effective_to)
        VALUES
            (:index_code, :index_name, :role, :linked_sector, :inception_date,
             :effective_from, NULL)
        ON CONFLICT (index_code, effective_from) DO UPDATE SET
            index_name = EXCLUDED.index_name,
            role = EXCLUDED.role,
            linked_sector = EXCLUDED.linked_sector,
            updated_at = NOW()
    """)

    with eng.begin() as conn:
        for r in rows:
            conn.execute(insert_sql, {**r, "effective_from": Config.UNIVERSE_LOCK_DATE})

    log.info("universe_indices_populated", count=len(rows))
    return len(rows)
