"""US company fundamentals — PURE code over SEC EDGAR XBRL company facts.

Three modules, no I/O between them and none inside them:

* :mod:`.xbrl_map` — the us-gaap tag → concept mapping. A company reports revenue under any
  of several tags and changes which one it uses between filings, so every concept carries an
  ORDERED tuple and the tag actually chosen is returned alongside the value.
* :mod:`.facts` — a raw company-facts payload → the periods a filer reported, keyed by
  ``(form, filed, period_end)`` so a restatement is a new record and never an overwrite.
* :mod:`.ratios` — TTM assembly and the ratios of ``docs/global/plan.md`` §B. Every function
  returns ``Decimal | None``; ``None`` means an input was missing, never zero and never a
  default (rule #0).

The fetching, the SQL and the watermarks live in ``scripts/global_market/ingest_financials.py``
— the off-box boundary — which is the only thing in this chunk that touches the network or the
database.
"""

from .facts import PeriodRow, extract_rows, period_class, quarter_count, tag_summary
from .ratios import (
    buyback_yield,
    current_ratio,
    debt_to_equity,
    ebitda,
    fcf,
    fcf_margin,
    gross_margin,
    growth,
    implied_q4,
    interest_cover,
    mean_of,
    net_margin,
    operating_leverage,
    operating_margin,
    roce,
    roe,
    ttm,
)
from .xbrl_map import CONCEPTS, INSTANT_CONCEPTS, UNITS, pick

__all__ = [
    "CONCEPTS",
    "INSTANT_CONCEPTS",
    "UNITS",
    "PeriodRow",
    "buyback_yield",
    "current_ratio",
    "debt_to_equity",
    "ebitda",
    "extract_rows",
    "fcf",
    "fcf_margin",
    "gross_margin",
    "growth",
    "implied_q4",
    "interest_cover",
    "mean_of",
    "net_margin",
    "operating_leverage",
    "operating_margin",
    "period_class",
    "pick",
    "quarter_count",
    "roce",
    "roe",
    "tag_summary",
    "ttm",
]
