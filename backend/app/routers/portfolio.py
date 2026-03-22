"""포트폴리오 API"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.portfolio import Holding, StopLossEvent
from app.schemas.portfolio import HoldingCreate, HoldingOut, StopCheckResult, StopCheckResponse
from app.services.monitor import check_stop_loss

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


@router.get("/holdings", response_model=list[HoldingOut])
async def list_holdings(db: AsyncSession = Depends(get_db)):
    stmt = select(Holding).where(Holding.is_active == True).order_by(Holding.entry_date)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/holdings", response_model=HoldingOut, status_code=201)
async def add_holding(data: HoldingCreate, db: AsyncSession = Depends(get_db)):
    # 중복 체크
    stmt = select(Holding).where(
        and_(Holding.ticker == data.ticker, Holding.is_active == True)
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(409, f"{data.ticker} 이미 보유 중")

    holding = Holding(
        ticker=data.ticker,
        entry_price=data.entry_price,
        peak_price=data.entry_price,
    )
    db.add(holding)
    await db.commit()
    await db.refresh(holding)
    return holding


@router.delete("/holdings/{ticker}", status_code=204)
async def remove_holding(ticker: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Holding).where(
        and_(Holding.ticker == ticker, Holding.is_active == True)
    )
    result = await db.execute(stmt)
    holding = result.scalar_one_or_none()
    if not holding:
        raise HTTPException(404, f"{ticker} 보유 종목 없음")

    holding.is_active = False
    await db.commit()


@router.post("/check-stops", response_model=StopCheckResponse)
async def check_stops(db: AsyncSession = Depends(get_db)):
    stmt = select(Holding).where(Holding.is_active == True)
    result = await db.execute(stmt)
    holdings = result.scalars().all()

    results = []
    for h in holdings:
        stop_result = check_stop_loss(h.ticker, h.entry_price, h.peak_price)
        results.append(StopCheckResult(**stop_result))

        # 이벤트 기록
        if stop_result["event_type"]:
            cur = stop_result["current_price"]
            if cur > h.peak_price:
                h.peak_price = cur

            db.add(StopLossEvent(
                holding_id=h.id,
                ticker=h.ticker,
                event_type=stop_result["event_type"],
                current_price=stop_result["current_price"],
                stop_price=stop_result["stop_price"],
                margin_pct=stop_result["margin_pct"],
            ))

    await db.commit()
    return StopCheckResponse(checked_at=datetime.utcnow(), results=results)
