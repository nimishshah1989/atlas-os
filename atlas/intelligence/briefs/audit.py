"""SP05: persist DailyBrief + context snapshot to atlas.atlas_daily_briefs.

UPSERT keyed on as_of_date - re-running the CLI for the same date overwrites
the prior row. The context_snapshot column carries the full structured input
that produced the brief (SEBI audit-trail requirement).
"""

from __future__ import annotations

import json

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.intelligence.briefs.context import DailyMarketContext
from atlas.intelligence.briefs.generator import DailyBrief

log = structlog.get_logger()

_UPSERT_SQL = """
    INSERT INTO atlas.atlas_daily_briefs (
        as_of_date, regime_state, regime_delta, narrative, key_themes,
        regime_summary, top_sector_mentions, context_snapshot,
        model, prompt_version, input_tokens, output_tokens
    ) VALUES (
        :as_of_date, :regime_state, :regime_delta, :narrative,
        CAST(:key_themes AS JSONB),
        :regime_summary,
        CAST(:top_sector_mentions AS JSONB),
        CAST(:context_snapshot AS JSONB),
        :model, :prompt_version, :input_tokens, :output_tokens
    )
    ON CONFLICT (as_of_date)
    DO UPDATE SET
        regime_state          = EXCLUDED.regime_state,
        regime_delta          = EXCLUDED.regime_delta,
        narrative             = EXCLUDED.narrative,
        key_themes            = EXCLUDED.key_themes,
        regime_summary        = EXCLUDED.regime_summary,
        top_sector_mentions   = EXCLUDED.top_sector_mentions,
        context_snapshot      = EXCLUDED.context_snapshot,
        model                 = EXCLUDED.model,
        prompt_version        = EXCLUDED.prompt_version,
        input_tokens          = EXCLUDED.input_tokens,
        output_tokens         = EXCLUDED.output_tokens,
        generated_at          = NOW(),
        updated_at            = NOW()
"""


def persist_brief(
    engine: Engine,
    *,
    context: DailyMarketContext,
    brief: DailyBrief,
) -> None:
    """UPSERT one daily-brief row keyed on context.as_of."""
    params = {
        "as_of_date": context.as_of,
        "regime_state": context.regime,
        "regime_delta": context.regime_delta,
        "narrative": brief.narrative,
        "key_themes": json.dumps(brief.key_themes),
        "regime_summary": brief.regime_summary,
        "top_sector_mentions": json.dumps(brief.top_sector_mentions),
        "context_snapshot": json.dumps(context.to_dict()),
        "model": brief.model,
        "prompt_version": brief.prompt_version,
        "input_tokens": brief.input_tokens,
        "output_tokens": brief.output_tokens,
    }
    with engine.begin() as conn:
        conn.execute(text(_UPSERT_SQL), params)
    log.info(
        "daily_brief_persisted",
        as_of=context.as_of.isoformat(),
        regime=context.regime,
        model=brief.model,
    )
