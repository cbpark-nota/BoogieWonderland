#!/usr/bin/env python3
"""
BTC V10 실시간 매매 시그널 체커
================================
Binance API에서 BTC/USDT 4h 최근 500봉을 수집하고
V10 알고리즘(Squeeze Momentum + BB Break + EMA 크로스 + 적응형 SL)을
적용해 현재 매매 시그널을 출력한다.

실행:
    python scripts/crypto/btc_signal_v10.py
"""

import sys
import time
import warnings

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════════════
# 상수
# ══════════════════════════════════════════════════════════════════════
BARS_PER_YEAR = 2190   # 24/7 crypto: 365일 × 6봉/일
BB_PERIOD     = 20
KC_PERIOD     = 20
ATR_PERIOD    = 14
RSI_PERIOD    = 14
VWAP_PERIOD   = 120
VOL_PERIOD_S  = 120
VOL_PERIOD_L  = 360
RANGE_PERIOD  = 120
SLOPE_EMA     = 150
SLOPE_LOOKBACK= 30
START         = 210    # 웜업 구간 (봉 수)

SEP  = "=" * 62
LINE = "-" * 62


# ══════════════════════════════════════════════════════════════════════
# 1. 데이터 수집 (최근 N봉)
# ══════════════════════════════════════════════════════════════════════

def fetch_binance_recent(n_bars: int = 500) -> pd.DataFrame | None:
    """Binance 공개 API에서 BTC/USDT 4h 최근 n_bars봉 수집"""
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": "BTCUSDT",
        "interval": "4h",
        "limit": min(n_bars, 1000),
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        print(f"  [Binance] API 오류: {e}")
        return None

    if len(rows) < 50:
        return None

    df = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "n_trades",
        "taker_base", "taker_quote", "ignore",
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time")
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df


def fetch_yfinance_fallback() -> pd.DataFrame | None:
    """yfinance 1h → 4h 리샘플링 (Binance 실패 시 대체)"""
    try:
        raw = yf.download("BTC-USD", period="730d", interval="1h",
                          progress=False, auto_adjust=True)
        raw.columns = [c[0].lower() if isinstance(c, tuple) else c.lower()
                       for c in raw.columns]
        raw = raw[["open", "high", "low", "close", "volume"]].dropna()
        df = raw.resample("4h", closed="left", label="left").agg({
            "open":   "first",
            "high":   "max",
            "low":    "min",
            "close":  "last",
            "volume": "sum",
        }).dropna()
        return df
    except Exception as e:
        print(f"  [yfinance] 오류: {e}")
        return None


def get_data() -> pd.DataFrame:
    print("  BTC/USDT 4h 데이터 수집 중...", end="", flush=True)
    df = fetch_binance_recent(500)
    if df is not None and len(df) >= 300:
        print(f" 완료 ({len(df)}봉, Binance)")
        return df
    print(" Binance 실패 → yfinance 사용", flush=True)
    df = fetch_yfinance_fallback()
    if df is not None and len(df) >= 300:
        print(f"  완료 ({len(df)}봉, yfinance 1h→4h)")
        return df
    print("  데이터 수집 실패")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════
# 2. 지표 계산
# ══════════════════════════════════════════════════════════════════════

def _linreg_end(series: pd.Series, window: int) -> pd.Series:
    """TTM Squeeze 모멘텀용 선형 회귀 끝점 (벡터화)"""
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    x_dev = x - x_mean
    denom = float((x_dev ** 2).sum())

    def _last(y_arr: np.ndarray) -> float:
        y_mean = y_arr.mean()
        slope = np.dot(x_dev, y_arr - y_mean) / denom
        return slope * (window - 1) + (y_mean - slope * x_mean)

    return series.rolling(window).apply(_last, raw=True)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]

    for p in [20, 50, 100, 200]:
        df[f"ma{p}"] = close.rolling(p).mean()
    df["ema20"] = close.ewm(span=20, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()

    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    df["atr14"] = tr.ewm(span=ATR_PERIOD, adjust=False).mean()
    df["atr20"] = tr.rolling(BB_PERIOD).mean()

    bb_mid = close.rolling(BB_PERIOD).mean()
    bb_std = close.rolling(BB_PERIOD).std(ddof=0)
    df["bb_mid"]    = bb_mid
    df["bb_upper"]  = bb_mid + 2 * bb_std
    df["bb_lower"]  = bb_mid - 2 * bb_std
    df["bb_width"]  = (df["bb_upper"] - df["bb_lower"]) / bb_mid

    kc_mid = df["ema20"]
    df["kc_upper"] = kc_mid + 2.0 * df["atr20"]
    df["kc_lower"] = kc_mid - 2.0 * df["atr20"]

    df["sq_on"] = (df["bb_upper"] < df["kc_upper"]) & \
                  (df["bb_lower"] > df["kc_lower"])
    df["sq_release"] = (~df["sq_on"]) & df["sq_on"].shift(1).fillna(False)

    donchian_mid = (high.rolling(BB_PERIOD).max() + low.rolling(BB_PERIOD).min()) / 2
    mid_val = (donchian_mid + bb_mid) / 2
    raw_mom = close - mid_val
    df["sq_mom"]       = _linreg_end(raw_mom, 12)
    df["sq_mom_delta"] = df["sq_mom"] - df["sq_mom"].shift(1)

    tp   = (high + low + close) / 3
    vwap = (tp * volume).rolling(VWAP_PERIOD).sum() / \
           volume.rolling(VWAP_PERIOD).sum()
    vwap_s = (tp - vwap).rolling(VWAP_PERIOD).std(ddof=0)
    df["vwap20"]      = vwap
    df["vwap_upper2"] = vwap + 2 * vwap_s
    df["vwap_lower2"] = vwap - 2 * vwap_s
    df["vwap_dev"]    = (close - vwap) / vwap

    up_move  = high.diff()
    dn_move  = -low.diff()
    plus_dm  = up_move.where((up_move > dn_move) & (up_move > 0), 0.0)
    minus_dm = dn_move.where((dn_move > up_move) & (dn_move > 0), 0.0)
    atr14s   = tr.ewm(span=ATR_PERIOD, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(span=ATR_PERIOD, adjust=False).mean() / atr14s
    minus_di = 100 * minus_dm.ewm(span=ATR_PERIOD, adjust=False).mean() / atr14s
    dx       = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    df["adx"]      = dx.ewm(span=ATR_PERIOD, adjust=False).mean()
    df["plus_di"]  = plus_di
    df["minus_di"] = minus_di

    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(span=RSI_PERIOD, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(span=RSI_PERIOD, adjust=False).mean()
    df["rsi14"] = 100 - 100 / (1 + gain / (loss + 1e-9))

    h120 = high.rolling(RANGE_PERIOD).max()
    l120 = low.rolling(RANGE_PERIOD).min()
    df["h120"]      = h120
    df["l120"]      = l120
    df["range_pos"] = (close - l120) / (h120 - l120 + 1e-9)

    ret_4h = close.pct_change()
    df["vol20"]      = ret_4h.rolling(VOL_PERIOD_S).std() * np.sqrt(BARS_PER_YEAR)
    df["vol60"]      = ret_4h.rolling(VOL_PERIOD_L).std() * np.sqrt(BARS_PER_YEAR)
    df["vol_ratio"]  = df["vol20"] / (df["vol60"] + 1e-9)

    ema_slope = close.ewm(span=SLOPE_EMA, adjust=False).mean()
    df["weekly_slope"] = ema_slope.pct_change(SLOPE_LOOKBACK)

    return df


# ══════════════════════════════════════════════════════════════════════
# 3. V10 시그널 생성
# ══════════════════════════════════════════════════════════════════════

BASE_PARAMS = {
    "bull":     dict(sl=1.8, tp=5.0, mh=84),
    "sideways": dict(sl=0.9, tp=1.5, mh=36),
    "neutral":  dict(sl=1.4, tp=2.8, mh=48),
    "bb":       dict(sl=1.3, tp=2.2, mh=42),
    "ema":      dict(sl=1.6, tp=3.8, mh=60),
    "sqm":      dict(sl=1.4, tp=3.2, mh=60),
    "pullback": dict(sl=1.8, tp=4.5, mh=72),
    "vwap":     dict(sl=1.3, tp=2.8, mh=48),
    "range":    dict(sl=0.9, tp=1.6, mh=36),
}

ETYPE_LABEL = {
    "sq":       "Squeeze Release",
    "sqm":      "Squeeze 조기진입 (모멘텀)",
    "ema":      "EMA Golden Cross (20>50)",
    "pullback": "RSI Pullback 매수",
    "vwap":     "VWAP 이탈 회귀",
    "bb":       "BB Upper Break",
    "range":    "Range 하단 매수 (Sideways)",
    "":         "-",
}


def _check_exit(curr_pos, close_i, entry_price, entry_atr,
                hold_bars, sl_mult, tp_mult, max_bars):
    if curr_pos == 0:
        return False
    if hold_bars >= max_bars:
        return True
    if curr_pos == 1:
        return (close_i <= entry_price - sl_mult * entry_atr or
                close_i >= entry_price + tp_mult * entry_atr)
    else:
        return (close_i >= entry_price + sl_mult * entry_atr or
                close_i <= entry_price - tp_mult * entry_atr)


def run_v10_signals(df: pd.DataFrame) -> pd.DataFrame:
    """V10 포지션 + 시그널 이유를 컬럼으로 추가"""
    df = df.copy()
    ma50  = df["ma50"].fillna(0)
    ma200 = df["ma200"].fillna(0)
    adx   = df["adx"].fillna(0)
    close = df["close"]
    ema20 = df["ema20"]
    ema50 = df["ema50"]

    ema_cross_up = (ema20 > ema50) & (ema20.shift(1) <= ema50.shift(1))
    bull_m = (ma50 > ma200) & (close > ma50) & (adx > 13)
    side_m = adx < 13
    df["regime"] = "neutral"
    df.loc[side_m, "regime"] = "sideways"
    df.loc[bull_m, "regime"] = "bull"

    n   = len(df)
    pos = np.zeros(n, dtype=int)
    etypes = [""] * n
    entry_prices = np.zeros(n, dtype=float)
    entry_atrs   = np.zeros(n, dtype=float)
    entry_idxs   = np.zeros(n, dtype=int)

    cp = 0; ep = 0.0; ei = 0; ea = 0.0; etype = ""
    mom_series = df["sq_mom"].fillna(0)

    for i in range(START, n):
        c      = df["close"].iloc[i]
        atr_i  = df["atr14"].iloc[i]
        regime = df["regime"].iloc[i]
        vol_r  = df["vol_ratio"].iloc[i]
        if np.isnan(vol_r):
            vol_r = 1.0

        pkey = etype if etype in BASE_PARAMS else regime
        p = BASE_PARAMS.get(pkey, BASE_PARAMS["bull"]).copy()

        if vol_r < 0.8:
            p["sl"] = max(p["sl"] * 0.8, 0.8)
        elif vol_r > 2.0:
            p["sl"] = p["sl"] * 1.2

        if cp != 0:
            if _check_exit(cp, c, ep, ea, i - ei, p["sl"], p["tp"], p["mh"]):
                cp = 0; etype = ""

        if cp == 0:
            mom    = df["sq_mom"].iloc[i]
            dm     = df["sq_mom_delta"].iloc[i]
            rel    = df["sq_release"].iloc[i]
            sq_on  = df["sq_on"].iloc[i]
            vd     = df["vwap_dev"].iloc[i]
            rsi    = df["rsi14"].iloc[i]
            adx_i  = df["adx"].iloc[i]
            wslope = df["weekly_slope"].iloc[i]
            rpos   = df["range_pos"].iloc[i]
            bb_up  = df["bb_upper"].iloc[i]
            prev_c = df["close"].iloc[i - 1]
            ema_x  = ema_cross_up.iloc[i]
            mom_std = mom_series.iloc[max(0, i - 60):i].std()

            if vol_r > 3.5:
                pos[i] = cp; continue
            if np.isnan(rsi) or np.isnan(mom):
                pos[i] = cp; continue

            w_up = wslope > 0.001

            if regime == "bull":
                if rel and mom > 0 and dm > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "sq"
                if cp == 0 and sq_on and mom > 0.38 * mom_std and dm > 0 and rsi < 70:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "sqm"
                if cp == 0 and ema_x and adx_i > 13:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "ema"
                if cp == 0 and rsi < 49 and w_up and adx_i > 13:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "pullback"
                if cp == 0 and not np.isnan(vd) and vd < -0.016:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "vwap"
                if cp == 0 and prev_c <= bb_up and c > bb_up and mom > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "bb"
            elif regime == "sideways":
                if not np.isnan(rpos) and rpos < 0.30 and rsi < 50:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "range"
            elif regime == "neutral":
                if ema_x and adx_i > 13 and rsi < 60:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "ema"

        pos[i]          = cp
        etypes[i]       = etype if cp != 0 else ""
        entry_prices[i] = ep if cp != 0 else 0.0
        entry_atrs[i]   = ea if cp != 0 else 0.0
        entry_idxs[i]   = ei if cp != 0 else 0

    df["position"]    = pos
    df["entry_type"]  = etypes
    df["entry_price"] = entry_prices
    df["entry_atr"]   = entry_atrs
    df["entry_idx"]   = entry_idxs
    return df


# ══════════════════════════════════════════════════════════════════════
# 4. 현재 시그널 분석 및 출력
# ══════════════════════════════════════════════════════════════════════

def _pct(v: float) -> str:
    return f"{v * 100:+.2f}%"

def _bb_position(close, bb_lower, bb_upper, bb_mid) -> str:
    if close >= bb_upper:
        return f"상단 돌파 ({close:.0f} >= {bb_upper:.0f})"
    elif close <= bb_lower:
        return f"하단 이탈 ({close:.0f} <= {bb_lower:.0f})"
    pct = (close - bb_lower) / (bb_upper - bb_lower + 1e-9)
    return f"{pct * 100:.0f}% (mid={bb_mid:.0f})"


def print_signal(df: pd.DataFrame) -> None:
    last = df.iloc[-1]
    prev = df.iloc[-2]

    cur_price   = last["close"]
    cur_pos     = int(last["position"])
    etype       = last["entry_type"]
    entry_price = last["entry_price"]
    entry_atr   = last["entry_atr"]
    entry_idx   = int(last["entry_idx"])
    regime      = last["regime"]
    rsi         = last["rsi14"]
    adx         = last["adx"]
    plus_di     = last["plus_di"]
    minus_di    = last["minus_di"]
    bb_pos_str  = _bb_position(cur_price, last["bb_lower"], last["bb_upper"], last["bb_mid"])
    ema20       = last["ema20"]
    ema50       = last["ema50"]
    sq_on       = bool(last["sq_on"])
    sq_rel      = bool(last["sq_release"])
    sq_mom      = last["sq_mom"]
    sq_dm       = last["sq_mom_delta"]
    vwap_dev    = last["vwap_dev"]
    vol_ratio   = last["vol_ratio"]
    range_pos   = last["range_pos"]
    weekly_slope= last["weekly_slope"]
    ts          = df.index[-1]

    # ── 시그널 판단 ──────────────────────────────────────────
    # 직전 봉 → 현재 봉 포지션 변화로 BUY/SELL 감지
    prev_pos = int(prev["position"])
    if prev_pos == 0 and cur_pos == 1:
        signal = "BUY"
    elif prev_pos == 1 and cur_pos == 0:
        signal = "SELL"
    elif cur_pos == 1:
        signal = "HOLD (롱 유지)"
    else:
        signal = "HOLD (대기)"

    signal_color = {
        "BUY":         "\033[92m",   # 초록
        "SELL":        "\033[91m",   # 빨강
        "HOLD (롱 유지)": "\033[93m",# 노랑
        "HOLD (대기)": "\033[0m",    # 기본
    }.get(signal, "\033[0m")
    RESET = "\033[0m"

    ema_state = "골든크로스 (EMA20 > EMA50)" if ema20 > ema50 else "데드크로스 (EMA20 < EMA50)"
    ema_cross_now = (ema20 > ema50) and (prev["ema20"] <= prev["ema50"])
    regime_label = {"bull": "Bull (상승)", "sideways": "Sideways (횡보)", "neutral": "Neutral (중립)"}.get(regime, regime)

    # SL/TP 가격 계산 (포지션 진입 중일 때)
    sl_price = tp_price = hold_bars = pnl = None
    if cur_pos == 1 and entry_price > 0:
        pkey = etype if etype in BASE_PARAMS else regime
        p    = BASE_PARAMS.get(pkey, BASE_PARAMS["bull"]).copy()
        if vol_ratio < 0.8:
            p["sl"] = max(p["sl"] * 0.8, 0.8)
        elif vol_ratio > 2.0:
            p["sl"] = p["sl"] * 1.2
        sl_price   = entry_price - p["sl"]  * entry_atr
        tp_price   = entry_price + p["tp"]  * entry_atr
        hold_bars  = len(df) - 1 - entry_idx
        hold_days  = hold_bars * 4 / 24
        pnl        = (cur_price - entry_price) / entry_price

    print(SEP)
    print("  BTC V10 실시간 시그널 체커")
    print(SEP)
    print(f"  기준 시각  : {ts.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  현재 가격  : ${cur_price:,.2f}")
    print()

    print(f"  ┌─ 시그널 ──────────────────────────────────────────")
    print(f"  │  {signal_color}{signal}{RESET}")
    if etype:
        print(f"  │  이유: {ETYPE_LABEL.get(etype, etype)}")
    if ema_cross_now:
        print(f"  │  ※ 이번 봉에서 EMA 골든크로스 발생!")
    if sq_rel:
        print(f"  │  ※ 이번 봉에서 Squeeze Release 발생!")
    print(f"  └───────────────────────────────────────────────────")
    print()

    print(f"  ┌─ 주요 지표 ────────────────────────────────────────")
    print(f"  │  레짐     : {regime_label}")
    print(f"  │  RSI(14)  : {rsi:.1f}")
    print(f"  │  ADX(14)  : {adx:.1f}  (+DI={plus_di:.1f}, -DI={minus_di:.1f})")
    print(f"  │  BB 위치  : {bb_pos_str}")
    print(f"  │  EMA 상태 : {ema_state}  (EMA20={ema20:.0f}, EMA50={ema50:.0f})")
    print(f"  │  Squeeze  : {'ON (압축 중)' if sq_on else 'OFF'}  "
          f"│ 모멘텀={sq_mom:.2f}  Δ={sq_dm:.2f}")
    print(f"  │  VWAP 편차: {vwap_dev * 100:+.2f}%  (기준: -1.6% 이하 → 매수)")
    print(f"  │  Vol Ratio: {vol_ratio:.2f}  (1 기준, >3.5 → 진입 차단)")
    print(f"  │  주간 슬로프: {weekly_slope * 100:+.3f}%  (>+0.1% → 상승 추세)")
    print(f"  │  레인지 포지: {range_pos * 100:.1f}%  (<30% → Sideways 매수)")
    print(f"  └───────────────────────────────────────────────────")
    print()

    if cur_pos == 1 and sl_price is not None:
        print(f"  ┌─ 포지션 상태 (시뮬레이션) ─────────────────────────")
        print(f"  │  상태       : 롱 포지션 보유 중")
        print(f"  │  진입 유형  : {ETYPE_LABEL.get(etype, etype)}")
        print(f"  │  진입 가격  : ${entry_price:,.2f}")
        print(f"  │  현재 수익  : {_pct(pnl)}  (${cur_price - entry_price:+,.2f})")
        print(f"  │  스톱로스   : ${sl_price:,.2f}  ({_pct((sl_price - entry_price)/entry_price)})")
        print(f"  │  타겟       : ${tp_price:,.2f}  ({_pct((tp_price - entry_price)/entry_price)})")
        print(f"  │  보유 기간  : {hold_bars}봉 ({hold_days:.1f}일)")
        print(f"  └───────────────────────────────────────────────────")
    else:
        print(f"  ┌─ 포지션 상태 (시뮬레이션) ─────────────────────────")
        print(f"  │  상태       : 현금 (포지션 없음)")
        print(f"  └───────────────────────────────────────────────────")

    print()
    print(SEP)


# ══════════════════════════════════════════════════════════════════════
# 5. 메인
# ══════════════════════════════════════════════════════════════════════

def main() -> None:
    print(SEP)
    print("  BTC V10 Signal Checker  (4h | Binance BTC/USDT)")
    print(SEP)
    print()

    df = get_data()
    print("  지표 계산 중...", end="", flush=True)
    df = add_indicators(df)
    print(" 완료")
    print("  V10 시그널 계산 중...", end="", flush=True)
    df = run_v10_signals(df)
    print(" 완료\n")

    print_signal(df)


if __name__ == "__main__":
    main()
