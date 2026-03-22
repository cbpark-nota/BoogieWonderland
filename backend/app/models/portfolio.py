from datetime import date, datetime

from sqlalchemy import Float, Integer, String, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(ForeignKey("stocks.ticker"))
    entry_price: Mapped[float] = mapped_column(Float)
    entry_date: Mapped[date] = mapped_column(Date, default=date.today)
    peak_price: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class StopLossEvent(Base):
    __tablename__ = "stop_loss_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    holding_id: Mapped[int] = mapped_column(ForeignKey("holdings.id"))
    ticker: Mapped[str] = mapped_column(String(20))
    event_type: Mapped[str] = mapped_column(String(10))  # BREACH, WARNING
    current_price: Mapped[float] = mapped_column(Float)
    stop_price: Mapped[float] = mapped_column(Float)
    margin_pct: Mapped[float] = mapped_column(Float)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
