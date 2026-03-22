from datetime import date, datetime
from pydantic import BaseModel


class HoldingCreate(BaseModel):
    ticker: str
    entry_price: float


class HoldingOut(BaseModel):
    id: int
    ticker: str
    entry_price: float
    entry_date: date
    peak_price: float
    is_active: bool


class StopCheckResult(BaseModel):
    ticker: str
    current_price: float
    stop_price: float
    margin_pct: float
    event_type: str | None = None  # BREACH, WARNING, None=OK


class StopCheckResponse(BaseModel):
    checked_at: datetime
    results: list[StopCheckResult]
