from datetime import date, datetime
from pydantic import BaseModel


class MarketStatusResponse(BaseModel):
    spy_price: float
    is_golden_cross: bool
    ma50: float
    ma200: float
    gap_pct: float
    next_rebalance: date | None = None


class RebalanceDateOut(BaseModel):
    scheduled_date: date
    status: str


class NotificationRegister(BaseModel):
    token: str
    platform: str | None = None


class NotificationLogOut(BaseModel):
    id: int
    type: str
    title: str
    body: str
    sent_at: datetime
    success_count: int
    fail_count: int


class SystemStatusOut(BaseModel):
    scheduler_running: bool
    last_screening: datetime | None = None
    last_stop_check: datetime | None = None
    data_freshness: str | None = None
