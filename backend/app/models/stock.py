from datetime import datetime

from sqlalchemy import Float, Integer, SmallInteger, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Stock(Base):
    __tablename__ = "stocks"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100))
    market: Mapped[str] = mapped_column(String(2))  # US, KR
    sector: Mapped[str] = mapped_column(String(30))


class ScreeningRun(Base):
    __tablename__ = "screening_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    market_spy_price: Mapped[float | None] = mapped_column(Float)
    market_is_golden: Mapped[bool | None] = mapped_column(Boolean)
    market_ma50: Mapped[float | None] = mapped_column(Float)
    market_ma200: Mapped[float | None] = mapped_column(Float)
    total_screened: Mapped[int | None] = mapped_column(Integer)
    total_passed: Mapped[int | None] = mapped_column(Integer)

    results: Mapped[list["ScreeningResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class ScreeningResult(Base):
    __tablename__ = "screening_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("screening_runs.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(SmallInteger)
    ticker: Mapped[str] = mapped_column(ForeignKey("stocks.ticker"))
    score: Mapped[float] = mapped_column(Float)
    weight_pct: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    adx: Mapped[float | None] = mapped_column(Float)
    rsi: Mapped[float | None] = mapped_column(Float)
    ret_3m: Mapped[float | None] = mapped_column(Float)
    sector_strength: Mapped[float | None] = mapped_column(Float)
    vol_stability: Mapped[float | None] = mapped_column(Float)
    stop_price: Mapped[float | None] = mapped_column(Float)
    stop_dist_pct: Mapped[float | None] = mapped_column(Float)
    atr: Mapped[float | None] = mapped_column(Float)

    run: Mapped["ScreeningRun"] = relationship(back_populates="results")
