"""스크리너 서비스 엣지 케이스 테스트"""
import numpy as np
import pandas as pd
import pytest

from app.services.screener import (
    calc_atr_stop,
    calc_indicators,
    rank_stocks,
    screen_stock,
)
from tests.test_services import _make_ohlcv


def _make_screened_df(n=250, **overrides):
    """calc_indicators를 적용한 DataFrame을 만들고, 마지막 행 지표를 덮어쓴다."""
    df = calc_indicators(_make_ohlcv(n, uptrend=True))
    for col, val in overrides.items():
        df.iloc[-1, df.columns.get_loc(col)] = val
    return df


# ── screen_stock 엣지 케이스 ──────────────────────────────────────────


def test_screen_stock_insufficient_rows():
    """200행 미만 데이터는 False를 반환해야 한다."""
    df = calc_indicators(_make_ohlcv(150, uptrend=True))
    passed, metrics = screen_stock(df)
    assert passed is False
    assert metrics == {}


def test_screen_stock_low_adx():
    """ADX < 20일 때 False를 반환해야 한다 (v3.2: ADX_THRESH=20)."""
    df = _make_screened_df(ADX=15.0)
    passed, _ = screen_stock(df)
    assert passed is False


def test_screen_stock_ma_not_aligned():
    """MA 역배열(MA20 < MA50)일 때 False를 반환해야 한다."""
    df = _make_screened_df(ADX=30.0, MA20=90.0, MA50=100.0, MA200=80.0)
    passed, _ = screen_stock(df)
    assert passed is False


def test_screen_stock_rsi_out_of_range_low():
    """RSI < 50일 때 False를 반환해야 한다."""
    df = _make_screened_df(ADX=30.0, RSI=40.0)
    passed, _ = screen_stock(df)
    assert passed is False


def test_screen_stock_rsi_out_of_range_high():
    """RSI > 75일 때 False를 반환해야 한다."""
    df = _make_screened_df(ADX=30.0, RSI=80.0)
    passed, _ = screen_stock(df)
    assert passed is False


def test_screen_stock_volume_spike():
    """최근 20일 내 거래량이 60일 평균의 3배를 초과하면 False를 반환해야 한다."""
    df = calc_indicators(_make_ohlcv(250, uptrend=True))
    # ADX, MA 정배열, RSI를 통과하도록 설정
    df.iloc[-1, df.columns.get_loc("ADX")] = 30.0
    df.iloc[-1, df.columns.get_loc("MA20")] = 200.0
    df.iloc[-1, df.columns.get_loc("MA50")] = 150.0
    df.iloc[-1, df.columns.get_loc("MA200")] = 100.0
    df.iloc[-1, df.columns.get_loc("RSI")] = 60.0
    # 거래량 급등 유발: 최근 20일 중 하나를 VolMA60의 4배로 설정
    vol_ma60 = df.iloc[-1]["VolMA60"]
    if not pd.isna(vol_ma60) and vol_ma60 > 0:
        df.iloc[-5, df.columns.get_loc("Volume")] = int(vol_ma60 * 4.0)
    passed, _ = screen_stock(df)
    assert passed is False


# ── calc_atr_stop ─────────────────────────────────────────────────────


def test_calc_atr_stop_normal():
    """ATR 스톱가가 정상 계산되는지 확인."""
    df = calc_indicators(_make_ohlcv(250, uptrend=True))
    stop = calc_atr_stop(df)
    assert not np.isnan(stop)
    # stop = peak_20 - ATR * 2.5 이므로 양수여야 한다
    assert stop > 0


def test_calc_atr_stop_nan_atr():
    """ATR이 모두 NaN일 때 NaN을 반환해야 한다."""
    df = _make_ohlcv(250, uptrend=True)
    df["ATR"] = np.nan
    stop = calc_atr_stop(df)
    assert np.isnan(stop)


# ── rank_stocks ───────────────────────────────────────────────────────


def test_rank_stocks_empty_dict():
    """빈 passed dict를 넣으면 빈 DataFrame을 반환해야 한다."""
    result = rank_stocks({}, {}, {})
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0
