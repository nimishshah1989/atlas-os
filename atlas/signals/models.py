from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator


class TVSignalPayload(BaseModel):
    tier: int
    code: str
    chart: str  # 'vs_nifty' | 'vs_sector'
    ticker: str
    exchange: str
    close: Decimal  # TV sends as string — Pydantic coerces
    volume: int
    time: str  # ISO string from TV {{timenow}}
    secret: str | None = None

    @field_validator("close", mode="before")
    @classmethod
    def parse_close(cls, v: object) -> Decimal:
        if isinstance(v, float):
            raise ValueError("close must be a string or Decimal, not float")
        return Decimal(str(v))

    @field_validator("chart")
    @classmethod
    def validate_chart(cls, v: str) -> str:
        if v not in ("vs_nifty", "vs_sector"):
            raise ValueError(f"chart must be 'vs_nifty' or 'vs_sector', got {v!r}")
        return v


class SignalReportResponse(BaseModel):
    id: str
    ticker: str
    condition_label: str
    condition_tier: int
    confirmation_level: str
    triggered_at: datetime
    verdict: str
    company_name: str | None = None
    sector: str | None = None
    conviction_score: Decimal | None = None
    cts_state: str | None = None
    rs_rank: int | None = None
    rs_rank_total: int | None = None
    rs_percentile: Decimal | None = None
    narrative: str | None = None
    chart_daily_url: str | None = None
    chart_weekly_url: str | None = None
    screenshot_daily: str | None = None
    screenshot_weekly: str | None = None
