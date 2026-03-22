"""포트폴리오 모니터링 서비스 — 스톱로스 체크"""
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
import pandas_ta as ta

ATR_PERIOD = 14
ATR_MULT = 2.5


def get_current_price(ticker: str) -> float | None:
    try:
        df = yf.download(ticker, period="5d", auto_adjust=True, progress=False)
        if df.empty:
            return None
        close = df["Close"].squeeze()
        return float(close.iloc[-1])
    except Exception:
        return None


def calc_atr_stop_for_ticker(ticker: str) -> dict | None:
    """종목의 현재 ATR 스톱 정보를 계산."""
    try:
        df = yf.download(ticker, period="3mo", auto_adjust=True, progress=False)
        if df.empty or len(df) < 20:
            return None

        close = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
        high = df["High"].squeeze() if isinstance(df["High"], pd.DataFrame) else df["High"]
        low = df["Low"].squeeze() if isinstance(df["Low"], pd.DataFrame) else df["Low"]

        atr = ta.atr(high, low, close, length=ATR_PERIOD)
        if atr is None or atr.dropna().empty:
            return None

        atr_val = float(atr.dropna().iloc[-1])
        peak_20 = float(high.tail(20).max())
        cur_price = float(close.iloc[-1])
        stop_price = round(peak_20 - atr_val * ATR_MULT, 2)
        margin_pct = (cur_price - stop_price) / cur_price * 100

        return {
            "current_price": cur_price,
            "stop_price": stop_price,
            "margin_pct": margin_pct,
            "atr": atr_val,
            "peak_20": peak_20,
        }
    except Exception:
        return None


def check_stop_loss(ticker: str, entry_price: float, peak_price: float) -> dict:
    """단일 종목 스톱로스 체크. 결과 dict 반환."""
    info = calc_atr_stop_for_ticker(ticker)
    if info is None:
        return {
            "ticker": ticker,
            "current_price": 0,
            "stop_price": 0,
            "margin_pct": 0,
            "event_type": None,
        }

    cur_price = info["current_price"]
    stop_price = info["stop_price"]
    margin_pct = info["margin_pct"]

    event_type = None
    if cur_price <= stop_price:
        event_type = "BREACH"
    elif margin_pct < 5.0:
        event_type = "WARNING"

    return {
        "ticker": ticker,
        "current_price": cur_price,
        "stop_price": stop_price,
        "margin_pct": margin_pct,
        "event_type": event_type,
    }
