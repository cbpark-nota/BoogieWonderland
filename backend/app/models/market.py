from datetime import date, datetime

from sqlalchemy import Integer, String, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RebalanceSchedule(Base):
    __tablename__ = "rebalance_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scheduled_date: Mapped[date] = mapped_column(Date, unique=True)
    status: Mapped[str] = mapped_column(String(10), default="PENDING")  # PENDING, DONE, SKIPPED
    run_id: Mapped[int | None] = mapped_column(ForeignKey("screening_runs.id"), nullable=True)


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String, unique=True)
    platform: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(20))  # REBALANCE, STOP_BREACH, STOP_WARNING
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(String)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
