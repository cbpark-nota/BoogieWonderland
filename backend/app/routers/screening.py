"""스크리닝 API"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.stock import ScreeningRun, ScreeningResult, Stock
from app.schemas.screening import ScreeningRunOut, ScreeningRunSummary, ScreeningResultOut, MarketStatusOut
from app.services.screener import run_screening, ALL_UNIVERSE

router = APIRouter(prefix="/api/v1/screening", tags=["screening"])


@router.post("/run", response_model=ScreeningRunOut)
async def trigger_screening(db: AsyncSession = Depends(get_db)):
    """스크리닝 실행 후 결과 저장."""
    data = run_screening()
    mkt = data["market"]

    run = ScreeningRun(
        run_at=datetime.utcnow(),
        market_spy_price=mkt["price"] if mkt else None,
        market_is_golden=mkt["is_golden"] if mkt else None,
        market_ma50=mkt["ma50"] if mkt else None,
        market_ma200=mkt["ma200"] if mkt else None,
        total_screened=data["total_screened"],
        total_passed=data["total_passed"],
    )
    db.add(run)
    await db.flush()

    for r in data["results"]:
        db.add(ScreeningResult(
            run_id=run.id, rank=r["rank"], ticker=r["ticker"],
            score=r["score"], weight_pct=r["weight_pct"], price=r["price"],
            adx=r["adx"], rsi=r["rsi"], ret_3m=r["ret_3m"],
            stop_price=r["stop_price"], stop_dist_pct=r["stop_dist_pct"],
            atr=r["atr"],
        ))
    await db.commit()

    return _build_run_response(run, data["results"], mkt)


@router.get("/latest", response_model=ScreeningRunOut)
async def get_latest(db: AsyncSession = Depends(get_db)):
    stmt = (select(ScreeningRun)
            .options(selectinload(ScreeningRun.results))
            .order_by(desc(ScreeningRun.run_at))
            .limit(1))
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "스크리닝 결과 없음")

    results_out = _results_from_model(run.results)
    mkt = _market_from_run(run)
    return _build_run_response(run, results_out, mkt)


@router.get("/history", response_model=list[ScreeningRunSummary])
async def get_history(limit: int = 20, db: AsyncSession = Depends(get_db)):
    stmt = select(ScreeningRun).order_by(desc(ScreeningRun.run_at)).limit(limit)
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return [ScreeningRunSummary(
        run_id=r.id, run_date=r.run_at, total_passed=r.total_passed or 0
    ) for r in runs]


@router.get("/{run_id}", response_model=ScreeningRunOut)
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (select(ScreeningRun)
            .options(selectinload(ScreeningRun.results))
            .where(ScreeningRun.id == run_id))
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "스크리닝 결과 없음")

    results_out = _results_from_model(run.results)
    mkt = _market_from_run(run)
    return _build_run_response(run, results_out, mkt)


def _market_from_run(run: ScreeningRun) -> dict | None:
    if run.market_spy_price is None:
        return None
    return {
        "price": run.market_spy_price, "is_golden": run.market_is_golden,
        "ma50": run.market_ma50, "ma200": run.market_ma200,
        "gap_pct": (run.market_ma50 - run.market_ma200) / run.market_ma200 * 100
        if run.market_ma200 else 0,
    }


def _results_from_model(results: list[ScreeningResult]) -> list[dict]:
    sorted_r = sorted(results, key=lambda r: r.rank)
    return [{
        "rank": r.rank, "ticker": r.ticker,
        "market": "KR" if r.ticker.endswith(".KS") else "US",
        "sector": ALL_UNIVERSE.get(r.ticker, "Unknown"),
        "score": r.score, "weight_pct": r.weight_pct, "price": r.price,
        "adx": r.adx, "rsi": r.rsi, "ret_3m": r.ret_3m,
        "stop_price": r.stop_price, "stop_dist_pct": r.stop_dist_pct,
        "atr": r.atr,
    } for r in sorted_r]


def _build_run_response(run, results, mkt) -> ScreeningRunOut:
    market_out = None
    if mkt:
        market_out = MarketStatusOut(
            spy_price=mkt["price"], is_golden_cross=mkt["is_golden"],
            ma50=mkt["ma50"], ma200=mkt["ma200"],
            gap_pct=mkt.get("gap_pct", 0),
        )
    results_out = [ScreeningResultOut(**r) if isinstance(r, dict) else r for r in results]
    return ScreeningRunOut(
        run_id=run.id, run_date=run.run_at, market_status=market_out,
        total_screened=run.total_screened or 0, total_passed=run.total_passed or 0,
        results=results_out,
    )
