"""SQLAlchemy ORM 모델 — SQLite 기반 스크리닝 결과 저장."""
from datetime import UTC, datetime

from sqlalchemy import Integer, String, Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.database import Base


class Portfolio(Base):
    """포트폴리오 보유 종목."""

    __tablename__ = "portfolio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_date: Mapped[str | None] = mapped_column(String(10))          # YYYY-MM-DD
    stop_loss: Mapped[float | None] = mapped_column(Float)
    market: Mapped[str] = mapped_column(String(2), default="US")        # US | KR
    created_at: Mapped[str] = mapped_column(
        String(30), default=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    updated_at: Mapped[str] = mapped_column(
        String(30), default=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )


class ScreeningResult(Base):
    """개별 종목 스크리닝 결과."""

    __tablename__ = "screening_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False)          # YYYY-MM-DD
    strategy: Mapped[str] = mapped_column(String(20), nullable=False)      # aggressive | balanced | conservative | adaptive
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    rank: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float | None] = mapped_column(Float)
    market: Mapped[str] = mapped_column(String(5), default="US")           # US | KR
    data_json: Mapped[str | None] = mapped_column(Text)                    # 추가 지표 JSON
    created_at: Mapped[str] = mapped_column(
        String(30), default=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )


class ScreeningHistory(Base):
    """날짜별 전체 스크리닝 결과 스냅샷."""

    __tablename__ = "screening_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)  # YYYY-MM-DD
    data_json: Mapped[str] = mapped_column(Text, nullable=False)                # 전체 JSON
    created_at: Mapped[str] = mapped_column(
        String(30), default=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
