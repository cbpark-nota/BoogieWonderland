"""시장 상태 + 시스템 API"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.market import RebalanceSchedule, DeviceToken, NotificationLog
from app.models.stock import ScreeningRun
from app.schemas.market import (
    MarketStatusResponse, RebalanceDateOut,
    NotificationRegister, NotificationLogOut, SystemStatusOut,
)
from app.services.screener import check_market

router = APIRouter(prefix="/api/v1", tags=["market"])


@router.get("/market/status", response_model=MarketStatusResponse)
async def market_status(db: AsyncSession = Depends(get_db)):
    mkt = check_market()
    if not mkt:
        return MarketStatusResponse(
            spy_price=0, is_golden_cross=False, ma50=0, ma200=0, gap_pct=0
        )

    # 다음 리밸런싱일
    stmt = (select(RebalanceSchedule)
            .where(RebalanceSchedule.scheduled_date >= date.today())
            .where(RebalanceSchedule.status == "PENDING")
            .order_by(RebalanceSchedule.scheduled_date)
            .limit(1))
    result = await db.execute(stmt)
    next_rebal = result.scalar_one_or_none()

    return MarketStatusResponse(
        spy_price=mkt["price"], is_golden_cross=mkt["is_golden"],
        ma50=mkt["ma50"], ma200=mkt["ma200"], gap_pct=mkt["gap_pct"],
        next_rebalance=next_rebal.scheduled_date if next_rebal else None,
    )


@router.get("/market/rebalance-schedule", response_model=list[RebalanceDateOut])
async def rebalance_schedule(db: AsyncSession = Depends(get_db)):
    stmt = (select(RebalanceSchedule)
            .where(RebalanceSchedule.scheduled_date >= date.today() - timedelta(days=90))
            .order_by(RebalanceSchedule.scheduled_date))
    result = await db.execute(stmt)
    return [RebalanceDateOut(scheduled_date=r.scheduled_date, status=r.status)
            for r in result.scalars().all()]


@router.post("/notifications/register", status_code=201)
async def register_token(data: NotificationRegister, db: AsyncSession = Depends(get_db)):
    stmt = select(DeviceToken).where(DeviceToken.token == data.token)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        return {"status": "already_registered"}

    db.add(DeviceToken(token=data.token, platform=data.platform))
    await db.commit()
    return {"status": "registered"}


@router.delete("/notifications/register/{token}", status_code=204)
async def unregister_token(token: str, db: AsyncSession = Depends(get_db)):
    stmt = select(DeviceToken).where(DeviceToken.token == token)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.commit()


@router.get("/notifications/history", response_model=list[NotificationLogOut])
async def notification_history(limit: int = 20, db: AsyncSession = Depends(get_db)):
    stmt = select(NotificationLog).order_by(desc(NotificationLog.sent_at)).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/system/refresh")
async def manual_refresh():
    """수동 데이터 갱신 (스크리닝과 동일 효과)."""
    from app.services.screener import run_screening
    data = run_screening()
    return {"status": "ok", "total_screened": data["total_screened"],
            "total_passed": data["total_passed"]}


@router.get("/system/status", response_model=SystemStatusOut)
async def system_status(db: AsyncSession = Depends(get_db)):
    stmt = select(ScreeningRun).order_by(desc(ScreeningRun.run_at)).limit(1)
    result = await db.execute(stmt)
    last_run = result.scalar_one_or_none()

    return SystemStatusOut(
        scheduler_running=True,
        last_screening=last_run.run_at if last_run else None,
    )
