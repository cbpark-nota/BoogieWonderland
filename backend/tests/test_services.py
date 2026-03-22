"""서비스 레이어 단위 테스트"""
import numpy as np
import pandas as pd
import pytest

from app.services.screener import (
    calc_indicators, screen_stock, count_hh_hl_swing,
    calc_position_weights, minmax, calc_atr_stop,
)


def _make_ohlcv(n=250, base_price=100.0, uptrend=True):
    """테스트용 OHLCV 데이터프레임 생성."""
    dates = pd.bdate_range("2024-01-01", periods=n)
    np.random.seed(42)

    prices = [base_price]
    for _ in range(n - 1):
        change = np.random.normal(0.002 if uptrend else -0.001, 0.01)
        prices.append(prices[-1] * (1 + change))

    close = pd.Series(prices, index=dates, name="Close")
    high = close * (1 + np.random.uniform(0.001, 0.02, n))
    low = close * (1 - np.random.uniform(0.001, 0.02, n))
    open_ = close * (1 + np.random.uniform(-0.005, 0.005, n))
    volume = pd.Series(np.random.randint(1_000_000, 5_000_000, n), index=dates)

    return pd.DataFrame({
        "Open": open_, "High": high, "Low": low,
        "Close": close, "Volume": volume,
    })


def test_calc_indicators_columns():
    """지표 계산 후 필수 컬럼이 생성되는지 확인."""
    df = _make_ohlcv(250)
    result = calc_indicators(df)
    required = ["MA20", "MA50", "MA200", "RSI", "ADX", "VolMA20", "VolMA60", "High52w", "ATR"]
    for col in required:
        assert col in result.columns, f"{col} 컬럼 누락"


def test_position_weights_sum_to_one():
    """포지션 비중 합이 1.0인지 확인."""
    scores = pd.Series([0.8, 0.6, 0.4, 0.2, 0.1], index=["A", "B", "C", "D", "E"])
    weights = calc_position_weights(scores, max_w=0.3)
    assert abs(weights.sum() - 1.0) < 1e-6, f"비중 합 {weights.sum()} != 1.0"
    assert (weights <= 0.3 + 1e-6).all(), f"상한 초과: {weights.max()}"


def test_position_weights_zero_scores():
    """점수가 모두 0일 때 동일비중 반환."""
    scores = pd.Series([0.0, 0.0, 0.0], index=["A", "B", "C"])
    weights = calc_position_weights(scores)
    assert abs(weights.sum() - 1.0) < 1e-6
    assert all(abs(w - 1/3) < 1e-6 for w in weights)


def test_minmax_normalization():
    """minmax 정규화 범위 확인."""
    s = pd.Series([10, 20, 30, 40, 50])
    result = minmax(s)
    assert abs(result.min()) < 1e-6
    assert abs(result.max() - 1.0) < 1e-6


def test_count_hh_hl_swing_basic():
    """HH-HL 카운트 기본 동작."""
    # 상승 추세 데이터
    df = _make_ohlcv(60, uptrend=True)
    count = count_hh_hl_swing(df, n=3)
    assert isinstance(count, (int, np.integer))
    assert count >= 0
