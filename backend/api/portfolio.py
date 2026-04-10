"""포트폴리오 CRUD API 라우터 (SQLite 기반)."""
import math
from datetime import UTC, datetime
from typing import Any

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db.models import Portfolio

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


# ─── Pydantic 스키마 ──────────────────────────────────────────────────────────

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
    created_at: str
    updated_at: str
    current_price: float | None = None

    model_config = {"from_attributes": True}


class PortfolioSummary(BaseModel):
    total_items: int
    total_invested: float
    total_current_value: float
    total_pnl: float
    total_pnl_pct: float


# ─── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _fetch_prices(tickers: list[str]) -> dict[str, float]:
    """yfinance로 현재가 일괄 조회. 실패 시 빈 dict."""
    if not tickers:
        return {}
    try:
        data = yf.download(tickers, period="1d", progress=False, auto_adjust=True)
        if data.empty:
            return {}
        close = data["Close"] if "Close" in data.columns else data
        result: dict[str, float] = {}
        if len(tickers) == 1:
            val = float(close.iloc[-1])
            if not math.isnan(val):
                result[tickers[0]] = val
        else:
            for ticker in tickers:
                if ticker in close.columns:
                    val = float(close[ticker].iloc[-1])
                    if not math.isnan(val):
                        result[ticker] = val
        return result
    except Exception:
        return {}


def _to_out(item: Portfolio, current_price: float | None = None) -> dict[str, Any]:
    return {
        "id": item.id,
        "ticker": item.ticker,
        "name": item.name,
        "entry_price": item.entry_price,
        "quantity": item.quantity,
        "entry_date": item.entry_date,
        "stop_loss": item.stop_loss,
        "market": item.market,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "current_price": current_price,
    }


# ─── 엔드포인트 ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[PortfolioOut])
def list_portfolio(db: Session = Depends(get_db)):
    """전체 포트폴리오 조회."""
    items = db.execute(select(Portfolio).order_by(Portfolio.id)).scalars().all()
    return items


@router.post("", response_model=PortfolioOut, status_code=201)
def create_portfolio(data: PortfolioCreate, db: Session = Depends(get_db)):
    """종목 추가."""
    item = Portfolio(**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/{item_id}", response_model=PortfolioOut)
def update_portfolio(item_id: int, data: PortfolioUpdate, db: Session = Depends(get_db)):
    """종목 수정."""
    item = db.get(Portfolio, item_id)
    if not item:
        raise HTTPException(404, f"id={item_id} 종목 없음")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.updated_at = datetime.now(UTC).isoformat(timespec="seconds")
    db.commit()
    db.refresh(item)
    return item


@router.delete("/ticker/{ticker}", status_code=204)
def delete_portfolio_by_ticker(ticker: str, db: Session = Depends(get_db)):
    """티커로 종목 삭제."""
    stmt = select(Portfolio).where(Portfolio.ticker == ticker)
    item = db.execute(stmt).scalar_one_or_none()
    if not item:
        raise HTTPException(404, f"ticker={ticker} 종목 없음")
    db.delete(item)
    db.commit()


@router.delete("/{item_id}", status_code=204)
def delete_portfolio(item_id: int, db: Session = Depends(get_db)):
    """종목 삭제."""
    item = db.get(Portfolio, item_id)
    if not item:
        raise HTTPException(404, f"id={item_id} 종목 없음")
    db.delete(item)
    db.commit()


@router.get("/summary", response_model=PortfolioSummary)
def portfolio_summary(db: Session = Depends(get_db)):
    """포트폴리오 요약 (총 투자금액, 현재 평가액 등)."""
    items = db.execute(select(Portfolio).order_by(Portfolio.id)).scalars().all()

    if not items:
        return PortfolioSummary(
            total_items=0, total_invested=0.0,
            total_current_value=0.0, total_pnl=0.0, total_pnl_pct=0.0,
        )

    tickers = list({i.ticker for i in items})
    prices = _fetch_prices(tickers)

    total_invested = sum(i.entry_price * i.quantity for i in items)
    total_current = sum(prices.get(i.ticker, i.entry_price) * i.quantity for i in items)
    pnl = total_current - total_invested
    pnl_pct = (pnl / total_invested * 100) if total_invested else 0.0

    return PortfolioSummary(
        total_items=len(items),
        total_invested=round(total_invested, 2),
        total_current_value=round(total_current, 2),
        total_pnl=round(pnl, 2),
        total_pnl_pct=round(pnl_pct, 4),
    )


@router.get("/refresh", response_model=list[PortfolioOut])
def refresh_portfolio(db: Session = Depends(get_db)):
    """yfinance로 현재가 조회 후 응답에 포함 (DB 미저장)."""
    items = db.execute(select(Portfolio).order_by(Portfolio.id)).scalars().all()
    tickers = list({i.ticker for i in items})
    prices = _fetch_prices(tickers)
    return [_to_out(i, prices.get(i.ticker)) for i in items]


@router.post("/check-stops")
def check_stops(db: Session = Depends(get_db)) -> dict:
    """스톱로스 체크: 현재가가 stop_loss 이하이면 STOP_HIT 이벤트 반환."""
    items = db.execute(select(Portfolio).order_by(Portfolio.id)).scalars().all()
    tickers = list({i.ticker for i in items})
    prices = _fetch_prices(tickers)
    results = []
    for item in items:
        cp = prices.get(item.ticker)
        if cp is None:
            continue
        stop = item.stop_loss if item.stop_loss else item.entry_price * 0.85
        margin = (cp - stop) / stop * 100
        results.append({
            "ticker": item.ticker,
            "current_price": round(cp, 4),
            "stop_price": round(stop, 4),
            "margin_pct": round(margin, 2),
            "event_type": "STOP_HIT" if cp <= stop else None,
        })
    return {"results": results}
