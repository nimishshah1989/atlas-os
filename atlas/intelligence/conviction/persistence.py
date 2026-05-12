"""UPSERT helpers for conviction-score and tier-membership tables."""

from __future__ import annotations

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()


_UPSERT_CONVICTION_SQL = text("""
    INSERT INTO atlas.atlas_stock_conviction_daily
        (instrument_id, date, tier, conviction_score,
         confidence_label, backing_ic, contributing_signals,
         weight_set_version)
    VALUES
        (:instrument_id, :date, :tier, :conviction_score,
         :confidence_label, :backing_ic,
         CAST(:contributing_signals AS jsonb),
         :weight_set_version)
    ON CONFLICT (instrument_id, date) DO UPDATE SET
        tier = EXCLUDED.tier,
        conviction_score = EXCLUDED.conviction_score,
        confidence_label = EXCLUDED.confidence_label,
        backing_ic = EXCLUDED.backing_ic,
        contributing_signals = EXCLUDED.contributing_signals,
        weight_set_version = EXCLUDED.weight_set_version,
        computed_at = NOW(),
        updated_at = NOW()
""")


_UPSERT_TIER_SQL = text("""
    INSERT INTO atlas.atlas_tier_membership_daily
        (instrument_id, date, tier, adv_rank, adv_20d)
    VALUES
        (:instrument_id, :date, :tier, :adv_rank, :adv_20d)
    ON CONFLICT (instrument_id, date) DO UPDATE SET
        tier = EXCLUDED.tier,
        adv_rank = EXCLUDED.adv_rank,
        adv_20d = EXCLUDED.adv_20d
""")


def persist_conviction_batch(engine: Engine, df: pd.DataFrame) -> int:
    """UPSERT a batch of conviction rows. Returns row count."""
    if df.empty:
        return 0
    records = df.to_dict("records")
    with engine.begin() as conn:
        conn.execute(_UPSERT_CONVICTION_SQL, records)
    log.info("conviction_batch_persisted", n=len(records))
    return len(records)


def persist_tier_membership_batch(engine: Engine, df: pd.DataFrame) -> int:
    """UPSERT a batch of tier-membership rows. Returns row count."""
    if df.empty:
        return 0
    records = df.to_dict("records")
    with engine.begin() as conn:
        conn.execute(_UPSERT_TIER_SQL, records)
    log.info("tier_membership_batch_persisted", n=len(records))
    return len(records)
