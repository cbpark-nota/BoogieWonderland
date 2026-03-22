from datetime import datetime
from pydantic import BaseModel


class MarketStatusOut(BaseModel):
    spy_price: float
    is_golden_cross: bool
    ma50: float
    ma200: float
    gap_pct: float


class ScreeningResultOut(BaseModel):
    rank: int
    ticker: str
    market: str
    sector: str
    score: float
    weight_pct: float
    price: float
    adx: float | None = None
    rsi: float | None = None
    ret_3m: float | None = None
    stop_price: float | None = None
    stop_dist_pct: float | None = None
    atr: float | None = None


class ScreeningRunOut(BaseModel):
    run_id: int
    run_date: datetime
    market_status: MarketStatusOut | None = None
    total_screened: int
    total_passed: int
    results: list[ScreeningResultOut]


class ScreeningRunSummary(BaseModel):
    run_id: int
    run_date: datetime
    total_passed: int
