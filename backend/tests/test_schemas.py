"""Pydantic 스키마 직렬화/검증 테스트"""
from datetime import date

import pytest

from app.schemas.screening import ScreeningResultOut
from app.schemas.portfolio import HoldingCreate, StopCheckResult
from app.schemas.market import MarketStatusResponse


def test_screening_result_out_serialization():
    """ScreeningResultOut이 올바르게 직렬화되는지 확인."""
    obj = ScreeningResultOut(
        rank=1,
        ticker="AAPL",
        market="US",
        sector="Technology",
        score=0.85,
        weight_pct=15.0,
        price=180.5,
        adx=32.0,
        rsi=62.0,
        ret_3m=0.12,
        stop_price=165.0,
        stop_dist_pct=-8.6,
        atr=3.5,
    )
    data = obj.model_dump()
    assert data["rank"] == 1
    assert data["ticker"] == "AAPL"
    assert data["adx"] == 32.0
    assert data["atr"] == 3.5


def test_screening_result_out_optional_none():
    """ScreeningResultOut의 선택 필드가 None이어도 직렬화되는지 확인."""
    obj = ScreeningResultOut(
        rank=2,
        ticker="TSLA",
        market="US",
        sector="Consumer Disc",
        score=0.5,
        weight_pct=10.0,
        price=250.0,
    )
    data = obj.model_dump()
    assert data["adx"] is None
    assert data["rsi"] is None
    assert data["stop_price"] is None


def test_holding_create_validation():
    """HoldingCreate가 필수 필드로 올바르게 생성되는지 확인."""
    h = HoldingCreate(ticker="NVDA", entry_price=450.0)
    assert h.ticker == "NVDA"
    assert h.entry_price == 450.0


def test_holding_create_missing_field():
    """HoldingCreate에 필수 필드가 누락되면 ValidationError가 발생해야 한다."""
    with pytest.raises(Exception):
        HoldingCreate(ticker="NVDA")  # entry_price 누락


def test_stop_check_result_serialization():
    """StopCheckResult가 올바르게 직렬화되는지 확인."""
    obj = StopCheckResult(
        ticker="AAPL",
        current_price=175.0,
        stop_price=165.0,
        margin_pct=5.71,
        event_type="WARNING",
    )
    data = obj.model_dump()
    assert data["event_type"] == "WARNING"
    assert data["margin_pct"] == pytest.approx(5.71)


def test_stop_check_result_ok():
    """StopCheckResult의 event_type이 None(OK)일 때 직렬화."""
    obj = StopCheckResult(
        ticker="MSFT",
        current_price=400.0,
        stop_price=380.0,
        margin_pct=5.0,
    )
    data = obj.model_dump()
    assert data["event_type"] is None


def test_market_status_response_serialization():
    """MarketStatusResponse가 올바르게 직렬화되는지 확인."""
    obj = MarketStatusResponse(
        spy_price=510.0,
        is_golden_cross=True,
        ma50=505.0,
        ma200=490.0,
        gap_pct=3.06,
        next_rebalance=date(2026, 4, 1),
    )
    data = obj.model_dump()
    assert data["spy_price"] == 510.0
    assert data["is_golden_cross"] is True
    assert data["next_rebalance"] == date(2026, 4, 1)


def test_market_status_response_no_rebalance():
    """MarketStatusResponse의 next_rebalance가 None이어도 직렬화되는지 확인."""
    obj = MarketStatusResponse(
        spy_price=500.0,
        is_golden_cross=False,
        ma50=495.0,
        ma200=500.0,
        gap_pct=-1.0,
    )
    data = obj.model_dump()
    assert data["next_rebalance"] is None
