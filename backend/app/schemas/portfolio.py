from datetime import date, datetime
from pydantic import BaseModel


# ─── Portfolio CRUD 스키마 ────────────────────────────────────────────────────

class PortfolioCreate(BaseModel):
    ticker: str
    name: str | None = None
    entry_price: float
    quantity: int
    entry_date: str | None = None
    stop_loss: float | None = None
    market: str = "US"


class PortfolioUpdate(BaseModel):
    name: str | None = None
    entry_price: float | None = None
    quantity: int | None = None
    entry_date: str | None = None
    stop_loss: float | None = None
    market: str | None = None


class PortfolioOut(BaseModel):
    id: int
    ticker: str
    name: str | None
    entry_price: float
    quantity: int
    entry_date: str | None
    stop_loss: float | None
    market: str
    created_at: datetime
    updated_at: datetime
    current_price: float | None = None

    model_config = {"from_attributes": True}


class PortfolioSummary(BaseModel):
    total_items: int
    total_invested: float       # 총 투자금액 (entry_price * quantity 합계)
    total_current_value: float  # 현재 평가액 (current_price * quantity 합계, 조회 실패 시 투자금액)
    total_pnl: float            # 손익 (평가액 - 투자금액)
    total_pnl_pct: float        # 손익률 (%)


# ─── Holding 스키마 (기존) ────────────────────────────────────────────────────

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
