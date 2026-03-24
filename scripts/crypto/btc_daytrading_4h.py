#!/usr/bin/env python3
"""
BTC 4시간봉 데이 트레이딩 알고리즘
=====================================
기존 일봉(btc_daytrading_v2.py) 전략을 4시간봉으로 전환 + 파라미터 재조정

목표: 주간 평균 +1% 수익 (연 ~68% CAGR)
수수료: 매수 0.05% + 매도 0.05% = RT 0.1%
데이터: Binance API (BTC/USDT 4h) — 2021-01-01 이후
       Fallback: yfinance 1h → 4h 리샘플링

4h 특성:
  - 1일 = 6 캔들 (24h / 4h)
  - 24/7 거래 → 연간 캔들 수 ≈ 2190 (365 × 6)
  - 일봉 대비 거래 기회 6배
  - ATR/변동성 척도는 4h 기준으로 재조정

전략 버전:
  V1: TTM Squeeze Momentum 기본 (4h 파라미터)
  V2: + 200MA 추세 필터 (4h 200봉 ≈ 33일)
  V3: + VWAP 이탈 회귀 (4h VWAP 120봉 롤링)
  V4: + RSI Pullback + 다중 시간프레임
  V5: 레짐 감지 + 자동 전환
  V6: 파라미터 완화 (더 많은 거래 기회)
  V7: + BB Break 신호
  V8: 롱온리 전략
  V9: + Squeeze 조기 진입 + EMA 크로스
  V10: 복합 최적화 (주간 +1% 목표)

실행:
  python scripts/crypto/btc_daytrading_4h.py
"""

import time
import warnings

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

# 4h 연간 캔들 수 (24/7 crypto: 365일 × 6봉/일)
BARS_PER_YEAR = 2190


# ══════════════════════════════════════════════════════════════════════
# 1. 데이터 수집
# ══════════════════════════════════════════════════════════════════════

def _fetch_binance_4h(start_ms: int, end_ms: int) -> list:
    """Binance 공개 API에서 BTCUSDT 4h 봉 페이지네이션 수집"""
    url = "https://api.binance.com/api/v3/klines"
    all_rows = []
    cur = start_ms
    while cur < end_ms:
        params = {
            "symbol": "BTCUSDT",
            "interval": "4h",
            "startTime": cur,
            "endTime": end_ms,
            "limit": 1000,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            rows = resp.json()
        except Exception as e:
            print(f"    Binance API 오류: {e}")
            break
        if not rows:
            break
        all_rows.extend(rows)
        cur = rows[-1][0] + 4 * 3600 * 1000  # 다음 구간 시작
        time.sleep(0.05)
    return all_rows


def get_btc_data_4h(start: str = "2021-01-01") -> pd.DataFrame:
    """
    BTC-USD/USDT 4시간봉 데이터 수집
    1순위: Binance 공개 API (BTC/USDT, 2021~현재 전체)
    2순위: yfinance 1h → 4h 리샘플링 (최근 730일)
    """
    print("BTC 4h 데이터 수집 중...")

    # ── Binance API ──────────────────────────────────────────
    try:
        start_ms = int(pd.Timestamp(start).timestamp() * 1000)
        end_ms   = int(pd.Timestamp.now().timestamp() * 1000)
        rows = _fetch_binance_4h(start_ms, end_ms)

        if len(rows) > 200:
            df = pd.DataFrame(rows, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_vol", "n_trades",
                "taker_base", "taker_quote", "ignore",
            ])
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            df = df.set_index("open_time")
            df = df[["open", "high", "low", "close", "volume"]].astype(float)
            df = df[~df.index.duplicated(keep="first")].sort_index()
            print(f"  [Binance] 기간: {df.index[0].date()} ~ {df.index[-1].date()}  ({len(df):,}봉, 4h)")
            return df
    except Exception as e:
        print(f"  Binance 실패: {e}  — yfinance 1h 데이터로 대체")

    # ── yfinance 1h → 4h 리샘플링 ────────────────────────────
    print("  yfinance 1h 수집 중...")
    raw = yf.download("BTC-USD", period="730d", interval="1h",
                      progress=False, auto_adjust=True)
    raw.columns = [c[0].lower() if isinstance(c, tuple) else c.lower()
                   for c in raw.columns]
    raw = raw[["open", "high", "low", "close", "volume"]].dropna()

    # 4h 리샘플링
    df = raw.resample("4h", closed="left", label="left").agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna()

    df = df.loc[start:] if start else df
    print(f"  [yfinance 1h→4h] 기간: {df.index[0].date()} ~ {df.index[-1].date()}  ({len(df):,}봉, 4h)")
    return df


# ══════════════════════════════════════════════════════════════════════
# 2. 기술 지표 계산 (4h 최적화)
# ══════════════════════════════════════════════════════════════════════

# ── 4h 주요 기간 상수 ─────────────────────────────────────────────────
# 일봉 기간 → 4h 봉 기간 (1일 = 6봉)
# MA20d  = 120봉  /  MA50d = 300봉  /  MA200d = 1200봉
# 그러나 200봉 ≈ 33일은 "4h 기준 중기 추세"로 충분히 의미 있음
# 여기서는 일봉과 동일한 200봉을 MA200(4h)로 사용 (≈ 33일)
# ATR14, RSI14, BB20: 단기 지표는 동일 봉 수 유지

BB_PERIOD      = 20    # BB: 20봉 ≈ 3.3일
KC_PERIOD      = 20    # KC: 20봉
ATR_PERIOD     = 14    # ATR: 14봉 ≈ 2.3일
RSI_PERIOD     = 14    # RSI: 14봉
VWAP_PERIOD    = 120   # VWAP: 120봉 = 20일 (의미 있는 롤링 VWAP)
VOL_PERIOD_S   = 120   # 단기 변동성: 120봉 = 20일
VOL_PERIOD_L   = 360   # 장기 변동성: 360봉 = 60일
RANGE_PERIOD   = 120   # 레인지(H/L): 120봉 = 20일
SLOPE_EMA      = 150   # 주간 slope용 EMA: 150봉 ≈ 25일
SLOPE_LOOKBACK = 30    # 주간 slope 변화율: 30봉 = 5일


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
    """4h 기술 지표 전체 계산"""
    df = df.copy()
    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]

    # ── 이동평균 ─────────────────────────────────────────────
    # 20/50/100/200봉 (4h 기준 ≈ 3.3/8.3/16.7/33.3일)
    for p in [20, 50, 100, 200]:
        df[f"ma{p}"] = close.rolling(p).mean()
    df["ema20"] = close.ewm(span=20, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()

    # ── ATR (14봉) ───────────────────────────────────────────
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    df["atr14"] = tr.ewm(span=ATR_PERIOD, adjust=False).mean()
    df["atr20"] = tr.rolling(BB_PERIOD).mean()

    # ── 볼린저 밴드 (20봉, ±2σ) ─────────────────────────────
    bb_mid = close.rolling(BB_PERIOD).mean()
    bb_std = close.rolling(BB_PERIOD).std(ddof=0)
    df["bb_mid"]   = bb_mid
    df["bb_upper"] = bb_mid + 2 * bb_std
    df["bb_lower"] = bb_mid - 2 * bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / bb_mid

    # ── 켈트너 채널 (20봉, ±2.0×ATR20) ──────────────────────
    kc_mid = df["ema20"]
    df["kc_upper"] = kc_mid + 2.0 * df["atr20"]
    df["kc_lower"] = kc_mid - 2.0 * df["atr20"]

    # ── TTM Squeeze ──────────────────────────────────────────
    df["sq_on"] = (df["bb_upper"] < df["kc_upper"]) & \
                  (df["bb_lower"] > df["kc_lower"])
    df["sq_release"] = (~df["sq_on"]) & df["sq_on"].shift(1).fillna(False)

    # 스퀴즈 모멘텀: 4h에서도 20봉 Donchian + BB 중간값 사용
    donchian_mid = (high.rolling(BB_PERIOD).max() + low.rolling(BB_PERIOD).min()) / 2
    mid_val = (donchian_mid + bb_mid) / 2
    raw_mom = close - mid_val
    df["sq_mom"]       = _linreg_end(raw_mom, 12)
    df["sq_mom_delta"] = df["sq_mom"] - df["sq_mom"].shift(1)

    # ── VWAP (120봉 롤링 = 20일) ─────────────────────────────
    tp      = (high + low + close) / 3
    vwap    = (tp * volume).rolling(VWAP_PERIOD).sum() / \
              volume.rolling(VWAP_PERIOD).sum()
    vwap_s  = (tp - vwap).rolling(VWAP_PERIOD).std(ddof=0)
    df["vwap20"]     = vwap
    df["vwap_upper2"] = vwap + 2 * vwap_s
    df["vwap_lower2"] = vwap - 2 * vwap_s
    df["vwap_dev"]   = (close - vwap) / vwap

    # ── ADX + DI ─────────────────────────────────────────────
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

    # ── RSI (14봉) ───────────────────────────────────────────
    delta  = close.diff()
    gain   = delta.clip(lower=0).ewm(span=RSI_PERIOD, adjust=False).mean()
    loss   = (-delta.clip(upper=0)).ewm(span=RSI_PERIOD, adjust=False).mean()
    df["rsi14"] = 100 - 100 / (1 + gain / (loss + 1e-9))

    # ── 레인지 포지션 (120봉 = 20일) ────────────────────────
    h120 = high.rolling(RANGE_PERIOD).max()
    l120 = low.rolling(RANGE_PERIOD).min()
    df["h120"] = h120
    df["l120"] = l120
    df["range_pos"] = (close - l120) / (h120 - l120 + 1e-9)

    # ── 변동성 레짐 (4h 기준) ────────────────────────────────
    # 4h 수익률 → 연환산 (24/7: 2190봉/년)
    ret_4h = close.pct_change()
    df["vol20"] = ret_4h.rolling(VOL_PERIOD_S).std() * np.sqrt(BARS_PER_YEAR)
    df["vol60"] = ret_4h.rolling(VOL_PERIOD_L).std() * np.sqrt(BARS_PER_YEAR)
    df["vol_ratio"] = df["vol20"] / (df["vol60"] + 1e-9)

    # ── 주간 추세 슬로프 (EMA150 기반 30봉 변화율 = 5일) ────
    ema_slope = close.ewm(span=SLOPE_EMA, adjust=False).mean()
    df["weekly_slope"] = ema_slope.pct_change(SLOPE_LOOKBACK)

    return df


# ══════════════════════════════════════════════════════════════════════
# 3. 백테스트 엔진
# ══════════════════════════════════════════════════════════════════════

def run_backtest(
    df: pd.DataFrame,
    strategy_func,
    fee_rate: float = 0.001,
) -> tuple[np.ndarray, pd.DataFrame]:
    """
    4h 백테스트 엔진

    Parameters
    ----------
    df            : 지표가 추가된 4h OHLCV 데이터프레임
    strategy_func : 포지션 배열을 반환하는 전략 함수
    fee_rate      : 왕복 수수료 (0.001 = 0.1%)

    Returns
    -------
    equity : 자산 곡선 (시작 = 1.0)
    trades : 거래 내역 데이터프레임
    """
    signals   = strategy_func(df.copy())
    pos       = signals["position"].values
    close     = df["close"].values
    dates     = df.index
    n         = len(close)
    equity    = np.ones(n, dtype=float)
    half_fee  = fee_rate / 2.0

    trade_log  = []
    entry_price = np.nan
    entry_pos   = 0
    entry_idx   = 0

    for i in range(1, n):
        prev_p = pos[i - 1]
        curr_p = pos[i]

        ret = close[i] / close[i - 1]
        if prev_p == 1:
            equity[i] = equity[i - 1] * ret
        elif prev_p == -1:
            equity[i] = equity[i - 1] * (2.0 - ret)
        else:
            equity[i] = equity[i - 1]

        if prev_p != curr_p:
            if prev_p != 0:
                equity[i] *= (1.0 - half_fee)
                if not np.isnan(entry_price):
                    if entry_pos == 1:
                        trade_ret = close[i] / entry_price - 1
                    else:
                        trade_ret = entry_price / close[i] - 1
                    trade_log.append(dict(
                        entry_date=dates[entry_idx],
                        exit_date=dates[i],
                        direction="long" if entry_pos == 1 else "short",
                        entry_price=entry_price,
                        exit_price=close[i],
                        gross_return=trade_ret,
                        hold_bars=i - entry_idx,          # 4h 봉 수
                        hold_days=(i - entry_idx) / 6.0,  # 일 환산
                    ))
            if curr_p != 0:
                equity[i] *= (1.0 - half_fee)
                entry_price = close[i]
                entry_pos   = curr_p
                entry_idx   = i
            else:
                entry_price = np.nan
                entry_pos   = 0

    trades_df = pd.DataFrame(trade_log)
    return equity, trades_df


# ══════════════════════════════════════════════════════════════════════
# 4. 성과 지표
# ══════════════════════════════════════════════════════════════════════

def calc_metrics(
    equity: np.ndarray,
    dates: pd.DatetimeIndex,
    trades_df: pd.DataFrame = None,
    risk_free: float = 0.05,
) -> dict:
    """CAGR / MDD / 샤프 / 주간 수익률 (4h 봉 기준)"""
    equity_s = pd.Series(equity, index=dates)
    bar_ret  = equity_s.pct_change().dropna()

    years     = (dates[-1] - dates[0]).days / 365.25
    total_ret = equity[-1] / equity[0] - 1
    cagr      = (equity[-1] / equity[0]) ** (1.0 / max(years, 0.01)) - 1

    peak = np.maximum.accumulate(equity)
    dd   = (equity - peak) / peak
    mdd  = dd.min()

    # 샤프: 4h 봉 기준 (연간 2190봉)
    bar_rf  = (1 + risk_free) ** (1.0 / BARS_PER_YEAR) - 1
    excess  = bar_ret - bar_rf
    sharpe  = (excess.mean() / excess.std() * np.sqrt(BARS_PER_YEAR)
               if excess.std() > 0 else 0.0)

    # 주간 수익률 (W-FRI 리샘플)
    weekly_eq  = equity_s.resample("W-FRI").last().ffill()
    weekly_ret = weekly_eq.pct_change().dropna()

    result = dict(
        total_ret=total_ret,
        cagr=cagr,
        mdd=mdd,
        sharpe=sharpe,
        weekly_avg=weekly_ret.mean(),
        weekly_1pct=(weekly_ret >= 0.01).mean(),
        weekly_returns=weekly_ret,
        years=years,
    )

    if trades_df is not None and len(trades_df) > 0:
        wins = trades_df[trades_df["gross_return"] > 0]
        loss = trades_df[trades_df["gross_return"] <= 0]
        result.update(dict(
            n_trades=len(trades_df),
            win_rate=len(wins) / len(trades_df),
            avg_win=wins["gross_return"].mean() if len(wins) > 0 else 0.0,
            avg_loss=loss["gross_return"].mean() if len(loss) > 0 else 0.0,
            avg_hold_bars=trades_df["hold_bars"].mean(),
            avg_hold_days=trades_df["hold_days"].mean(),
            trades_per_yr=len(trades_df) / max(years, 0.01),
        ))

    return result


def calc_period(equity: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    """2021+ 세부 시기별 CAGR/MDD"""
    s = pd.Series(equity, index=dates)
    periods = {
        "2021-2022 (불장→폭락)":      ("2021-01-01", "2022-12-31"),
        "2023-2024 (회복·신고가)":    ("2023-01-01", "2024-12-31"),
        "2025-현재 (Out-of-Sample)":  ("2025-01-01", None),
    }
    out = {}
    for name, (st, en) in periods.items():
        sub = s.loc[st:en] if en else s.loc[st:]
        if len(sub) < 10:
            continue
        yr = (sub.index[-1] - sub.index[0]).days / 365.25
        if yr < 0.05:
            continue
        cagr = (sub.iloc[-1] / sub.iloc[0]) ** (1.0 / yr) - 1
        pk   = np.maximum.accumulate(sub.values)
        mdd  = ((sub.values - pk) / pk).min()
        out[name] = dict(cagr=cagr, mdd=mdd)
    return out


# ══════════════════════════════════════════════════════════════════════
# 5. 공통 헬퍼: 청산 조건
# ══════════════════════════════════════════════════════════════════════

def _check_exit(
    curr_pos: int,
    close_i: float,
    entry_price: float,
    entry_atr: float,
    hold_bars: int,
    sl_mult: float,
    tp_mult: float,
    max_bars: int,   # 4h 봉 수
) -> bool:
    """포지션 청산 조건: 스톱/타겟/최대 보유봉 수"""
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


# ══════════════════════════════════════════════════════════════════════
# 6. 전략 구현 (V1 ~ V10)
#    * MH 파라미터: 모두 4h 봉 수 (일봉 × 6)
#    * START: 210봉 (웜업, MA200 확보에 충분)
# ══════════════════════════════════════════════════════════════════════

START = 210   # 웜업 구간 (봉 수)


# ─────────────────────────────────────────────────────────────────────
# V1: TTM Squeeze Momentum 기본 (4h 파라미터)
# ─────────────────────────────────────────────────────────────────────

def strategy_v1(df: pd.DataFrame) -> pd.DataFrame:
    """
    V1: TTM Squeeze Momentum 기본 (4h)
    ─────────────────────────────────────
    · BB < KC (Squeeze ON) 후 해제(Release) 시 진입
    · 모멘텀 양수 + 증가 → 롱 / 음수 + 감소 → 숏
    · SL=2.0×ATR, TP=3.5×ATR, 최대 60봉(10일)
    일봉 대비: MH 10일→60봉, SL 2.5→2.0 (4h ATR 작음)
    """
    n   = len(df)
    pos = np.zeros(n, dtype=int)
    cp  = 0; ep = 0.0; ei = 0; ea = 0.0
    SL, TP, MH = 2.0, 3.5, 60

    for i in range(START, n):
        c   = df["close"].iloc[i]
        atr = df["atr14"].iloc[i]
        if cp != 0:
            if _check_exit(cp, c, ep, ea, i - ei, SL, TP, MH):
                cp = 0
        if cp == 0:
            mom = df["sq_mom"].iloc[i]
            dm  = df["sq_mom_delta"].iloc[i]
            rel = df["sq_release"].iloc[i]
            if rel and not (np.isnan(mom) or np.isnan(dm)):
                if mom > 0 and dm > 0:
                    cp, ep, ei, ea = 1, c, i, atr
                elif mom < 0 and dm < 0:
                    cp, ep, ei, ea = -1, c, i, atr
        pos[i] = cp

    df["position"] = pos
    return df


# ─────────────────────────────────────────────────────────────────────
# V2: V1 + 200MA 추세 필터 (4h 200봉 ≈ 33일)
# ─────────────────────────────────────────────────────────────────────

def strategy_v2(df: pd.DataFrame) -> pd.DataFrame:
    """
    V2: TTM Squeeze + MA200(4h) 추세 필터
    ─────────────────────────────────────────
    · 가격 > MA200(33일) → 롱만 / 가격 < MA200 → 숏만
    · SL=2.0×ATR, TP=4.0×ATR, 최대 72봉(12일)
    일봉 대비: MH 12→72봉
    """
    n   = len(df)
    pos = np.zeros(n, dtype=int)
    cp  = 0; ep = 0.0; ei = 0; ea = 0.0
    SL, TP, MH = 2.0, 4.0, 72

    for i in range(START, n):
        c    = df["close"].iloc[i]
        atr  = df["atr14"].iloc[i]
        if cp != 0:
            if _check_exit(cp, c, ep, ea, i - ei, SL, TP, MH):
                cp = 0
        if cp == 0:
            mom   = df["sq_mom"].iloc[i]
            dm    = df["sq_mom_delta"].iloc[i]
            rel   = df["sq_release"].iloc[i]
            ma200 = df["ma200"].iloc[i]
            if rel and not (np.isnan(mom) or np.isnan(ma200)):
                bull = c > ma200
                bear = c < ma200
                if bull and mom > 0 and dm > 0:
                    cp, ep, ei, ea = 1, c, i, atr
                elif bear and mom < 0 and dm < 0:
                    cp, ep, ei, ea = -1, c, i, atr
        pos[i] = cp

    df["position"] = pos
    return df


# ─────────────────────────────────────────────────────────────────────
# V3: V2 + VWAP 이탈 회귀 (120봉 롤링 VWAP)
# ─────────────────────────────────────────────────────────────────────

def strategy_v3(df: pd.DataFrame) -> pd.DataFrame:
    """
    V3: TTM Squeeze + MA200 필터 + VWAP(120봉) 이탈 회귀
    ────────────────────────────────────────────────────────
    · VWAP 이탈 임계값: ±3.0% (4h에서는 이탈 폭이 더 작음)
    · VWAP 트레이드: SL=1.5, TP=2.0, 최대 30봉(5일)
    · Squeeze 트레이드: SL=2.0, TP=4.0, 최대 72봉
    일봉 대비: VWAP 임계값 4%→3%, MH 모두 ×6
    """
    n   = len(df)
    pos = np.zeros(n, dtype=int)
    cp  = 0; ep = 0.0; ei = 0; ea = 0.0; etype = ""

    PARAMS = {
        "sq":   dict(sl=2.0, tp=4.0, mh=72),
        "vwap": dict(sl=1.5, tp=2.0, mh=30),
    }

    for i in range(START, n):
        c   = df["close"].iloc[i]
        atr = df["atr14"].iloc[i]
        if cp != 0:
            p = PARAMS[etype]
            if _check_exit(cp, c, ep, ea, i - ei, p["sl"], p["tp"], p["mh"]):
                cp = 0; etype = ""
        if cp == 0:
            mom   = df["sq_mom"].iloc[i]
            dm    = df["sq_mom_delta"].iloc[i]
            rel   = df["sq_release"].iloc[i]
            ma200 = df["ma200"].iloc[i]
            vd    = df["vwap_dev"].iloc[i]
            if np.isnan(ma200):
                continue
            bull = c > ma200
            bear = c < ma200
            if rel and not np.isnan(mom):
                if bull and mom > 0 and dm > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr, "sq"
                elif bear and mom < 0 and dm < 0:
                    cp, ep, ei, ea, etype = -1, c, i, atr, "sq"
            if cp == 0 and not np.isnan(vd):
                if vd < -0.03 and bull:
                    cp, ep, ei, ea, etype = 1, c, i, atr, "vwap"
                elif vd > 0.03 and bear:
                    cp, ep, ei, ea, etype = -1, c, i, atr, "vwap"
        pos[i] = cp

    df["position"] = pos
    return df


# ─────────────────────────────────────────────────────────────────────
# V4: V3 + 다중 시간프레임 RSI Pullback
# ─────────────────────────────────────────────────────────────────────

def strategy_v4(df: pd.DataFrame) -> pd.DataFrame:
    """
    V4: TTM Squeeze + MA200 + VWAP + 다중 시간프레임 RSI Pullback
    ─────────────────────────────────────────────────────────────────
    · 4h RSI: 과매도<40, 과매수>60 (일봉 38/62에서 완화)
    · ADX > 20 필터 (4h ADX 유효)
    · MA50도 함께 확인 (4h 50봉 ≈ 8일 단기 추세)
    · Pullback: SL=1.8, TP=3.0, 최대 60봉(10일)
    일봉 대비: RSI 38/62→40/60, MH ×6
    """
    n   = len(df)
    pos = np.zeros(n, dtype=int)
    cp  = 0; ep = 0.0; ei = 0; ea = 0.0; etype = ""

    PARAMS = {
        "sq":       dict(sl=2.0, tp=4.5, mh=84),
        "vwap":     dict(sl=1.5, tp=2.0, mh=30),
        "pullback": dict(sl=1.8, tp=3.0, mh=60),
    }

    for i in range(START, n):
        c   = df["close"].iloc[i]
        atr = df["atr14"].iloc[i]
        if cp != 0:
            p = PARAMS[etype]
            if _check_exit(cp, c, ep, ea, i - ei, p["sl"], p["tp"], p["mh"]):
                cp = 0; etype = ""
        if cp == 0:
            mom    = df["sq_mom"].iloc[i]
            dm     = df["sq_mom_delta"].iloc[i]
            rel    = df["sq_release"].iloc[i]
            ma200  = df["ma200"].iloc[i]
            ma50   = df["ma50"].iloc[i]
            vd     = df["vwap_dev"].iloc[i]
            rsi    = df["rsi14"].iloc[i]
            adx    = df["adx"].iloc[i]
            wslope = df["weekly_slope"].iloc[i]
            if np.isnan(ma200) or np.isnan(rsi):
                continue
            bull  = c > ma200 and c > ma50
            bear  = c < ma200 and c < ma50
            w_up  = wslope >  0.01
            w_dn  = wslope < -0.01
            if rel and not np.isnan(mom):
                if bull and w_up and mom > 0 and dm > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr, "sq"
                elif bear and w_dn and mom < 0 and dm < 0:
                    cp, ep, ei, ea, etype = -1, c, i, atr, "sq"
            if cp == 0 and adx > 20:
                if bull and w_up and rsi < 40:
                    cp, ep, ei, ea, etype = 1, c, i, atr, "pullback"
                elif bear and w_dn and rsi > 60:
                    cp, ep, ei, ea, etype = -1, c, i, atr, "pullback"
            if cp == 0 and not np.isnan(vd):
                if vd < -0.03 and bull:
                    cp, ep, ei, ea, etype = 1, c, i, atr, "vwap"
                elif vd > 0.03 and bear:
                    cp, ep, ei, ea, etype = -1, c, i, atr, "vwap"
        pos[i] = cp

    df["position"] = pos
    return df


# ─────────────────────────────────────────────────────────────────────
# V5: 레짐 감지 + 전략 자동 전환 (4h 기준)
# ─────────────────────────────────────────────────────────────────────

def strategy_v5(df: pd.DataFrame) -> pd.DataFrame:
    """
    V5: 레짐 감지 + 자동 전환 (4h 최적화)
    ─────────────────────────────────────────
    레짐:
      Bull     : MA50>MA200 + 가격>MA50 + ADX>18
      Bear     : MA50<MA200 + 가격<MA50 + ADX>18
      Sideways : ADX<15

    파라미터 (4h):
      Bull    : SL=1.8, TP=4.5, MH=90봉(15일)
      Bear    : SL=1.5, TP=3.0, MH=60봉(10일)
      Sideways: SL=1.0, TP=1.8, MH=36봉(6일)
      Neutral : SL=1.8, TP=3.0, MH=48봉(8일)

    4h 조정: VWAP 이탈 임계 ±5%→±4%, vol_ratio<2.5
    """
    df     = df.copy()
    ma50   = df["ma50"].fillna(0)
    ma200  = df["ma200"].fillna(0)
    adx    = df["adx"].fillna(0)
    close  = df["close"]

    bull_m     = (ma50 > ma200) & (close > ma50) & (adx > 18)
    bear_m     = (ma50 < ma200) & (close < ma50) & (adx > 18)
    side_m     = adx < 15
    df["regime"] = "neutral"
    df.loc[side_m, "regime"] = "sideways"
    df.loc[bear_m, "regime"] = "bear"
    df.loc[bull_m, "regime"] = "bull"

    n   = len(df)
    pos = np.zeros(n, dtype=int)
    cp  = 0; ep = 0.0; ei = 0; ea = 0.0; etype = ""

    RPARAMS = {
        "bull":     dict(sl=1.8, tp=4.5, mh=90),
        "bear":     dict(sl=1.5, tp=3.0, mh=60),
        "sideways": dict(sl=1.0, tp=1.8, mh=36),
        "neutral":  dict(sl=1.8, tp=3.0, mh=48),
    }

    for i in range(START, n):
        c      = df["close"].iloc[i]
        atr_i  = df["atr14"].iloc[i]
        regime = df["regime"].iloc[i]
        p      = RPARAMS[regime]

        if cp != 0:
            if _check_exit(cp, c, ep, ea, i - ei, p["sl"], p["tp"], p["mh"]):
                cp = 0; etype = ""
        if cp == 0:
            mom    = df["sq_mom"].iloc[i]
            dm     = df["sq_mom_delta"].iloc[i]
            rel    = df["sq_release"].iloc[i]
            vd     = df["vwap_dev"].iloc[i]
            rsi    = df["rsi14"].iloc[i]
            adx_i  = df["adx"].iloc[i]
            wslope = df["weekly_slope"].iloc[i]
            rpos   = df["range_pos"].iloc[i]
            vol_r  = df["vol_ratio"].iloc[i]

            if vol_r > 2.5:
                pos[i] = cp; continue
            if np.isnan(rsi) or np.isnan(mom):
                pos[i] = cp; continue

            w_up = wslope >  0.005
            w_dn = wslope < -0.005

            if regime == "bull":
                if rel and mom > 0 and dm > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "sq"
                if cp == 0 and rsi < 38 and w_up and adx_i > 20:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "pullback"
                if cp == 0 and not np.isnan(vd) and vd < -0.04:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "vwap"
            elif regime == "bear":
                if rel and mom < 0 and dm < 0:
                    cp, ep, ei, ea, etype = -1, c, i, atr_i, "sq"
                if cp == 0 and rsi > 62 and w_dn and adx_i > 20:
                    cp, ep, ei, ea, etype = -1, c, i, atr_i, "pullback"
                if cp == 0 and not np.isnan(vd) and vd > 0.04:
                    cp, ep, ei, ea, etype = -1, c, i, atr_i, "vwap"
            elif regime == "sideways":
                if not np.isnan(rpos):
                    if rpos < 0.20 and rsi < 42:
                        cp, ep, ei, ea, etype = 1, c, i, atr_i, "range"
                    elif rpos > 0.80 and rsi > 58:
                        cp, ep, ei, ea, etype = -1, c, i, atr_i, "range"
        pos[i] = cp

    df["position"] = pos
    return df


# ─────────────────────────────────────────────────────────────────────
# V6: V5 기반 + 4h 맞춤 파라미터 완화 (거래 빈도 확대)
# ─────────────────────────────────────────────────────────────────────

def strategy_v6(df: pd.DataFrame) -> pd.DataFrame:
    """
    V6: 4h 시장 맞춤 파라미터 완화
    ─────────────────────────────────────────
    4h 완화 포인트:
      - ADX 임계값: 18→15 (4h ADX 분포 조정)
      - RSI Pullback: 38/62 → 43/57
      - VWAP 임계값: ±4% → ±2.5%
      - vol_ratio 필터: 2.5 → 3.0
      - Bull MH: 90→72봉(12일), Bear: 60→48봉
      - Sideways 레인지: 0.20/0.80→0.25/0.75
    """
    df     = df.copy()
    ma50   = df["ma50"].fillna(0)
    ma200  = df["ma200"].fillna(0)
    adx    = df["adx"].fillna(0)
    close  = df["close"]

    bull_m = (ma50 > ma200) & (close > ma50) & (adx > 15)
    bear_m = (ma50 < ma200) & (close < ma50) & (adx > 15)
    side_m = adx < 12
    df["regime"] = "neutral"
    df.loc[side_m, "regime"] = "sideways"
    df.loc[bear_m, "regime"] = "bear"
    df.loc[bull_m, "regime"] = "bull"

    n   = len(df)
    pos = np.zeros(n, dtype=int)
    cp  = 0; ep = 0.0; ei = 0; ea = 0.0; etype = ""

    RPARAMS = {
        "bull":     dict(sl=1.6, tp=4.0, mh=72),
        "bear":     dict(sl=1.4, tp=2.8, mh=48),
        "sideways": dict(sl=0.9, tp=1.5, mh=30),
        "neutral":  dict(sl=1.6, tp=2.8, mh=48),
    }

    for i in range(START, n):
        c      = df["close"].iloc[i]
        atr_i  = df["atr14"].iloc[i]
        regime = df["regime"].iloc[i]
        p      = RPARAMS[regime]

        if cp != 0:
            if _check_exit(cp, c, ep, ea, i - ei, p["sl"], p["tp"], p["mh"]):
                cp = 0; etype = ""
        if cp == 0:
            mom    = df["sq_mom"].iloc[i]
            dm     = df["sq_mom_delta"].iloc[i]
            rel    = df["sq_release"].iloc[i]
            vd     = df["vwap_dev"].iloc[i]
            rsi    = df["rsi14"].iloc[i]
            adx_i  = df["adx"].iloc[i]
            wslope = df["weekly_slope"].iloc[i]
            rpos   = df["range_pos"].iloc[i]
            vol_r  = df["vol_ratio"].iloc[i]

            if vol_r > 3.0:
                pos[i] = cp; continue
            if np.isnan(rsi) or np.isnan(mom):
                pos[i] = cp; continue

            w_up = wslope >  0.003
            w_dn = wslope < -0.003

            if regime == "bull":
                if rel and mom > 0 and dm > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "sq"
                if cp == 0 and rsi < 43 and w_up and adx_i > 15:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "pullback"
                if cp == 0 and not np.isnan(vd) and vd < -0.025:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "vwap"
            elif regime == "bear":
                if rel and mom < 0 and dm < 0:
                    cp, ep, ei, ea, etype = -1, c, i, atr_i, "sq"
                if cp == 0 and rsi > 57 and w_dn and adx_i > 15:
                    cp, ep, ei, ea, etype = -1, c, i, atr_i, "pullback"
                if cp == 0 and not np.isnan(vd) and vd > 0.025:
                    cp, ep, ei, ea, etype = -1, c, i, atr_i, "vwap"
            elif regime == "sideways":
                if not np.isnan(rpos):
                    if rpos < 0.25 and rsi < 45:
                        cp, ep, ei, ea, etype = 1, c, i, atr_i, "range"
                    elif rpos > 0.75 and rsi > 55:
                        cp, ep, ei, ea, etype = -1, c, i, atr_i, "range"
        pos[i] = cp

    df["position"] = pos
    return df


# ─────────────────────────────────────────────────────────────────────
# V7: V6 + BB Break 신호 추가
# ─────────────────────────────────────────────────────────────────────

def strategy_v7(df: pd.DataFrame) -> pd.DataFrame:
    """
    V7: V6 + 볼린저 밴드 상·하단 돌파 신호
    ─────────────────────────────────────────
    BB Break:
      - 상단 돌파: prev_c ≤ bb_upper AND c > bb_upper
                  AND bull regime AND sq_mom > 0 → 롱
      - 하단 돌파: prev_c ≥ bb_lower AND c < bb_lower
                  AND bear regime AND sq_mom < 0 → 숏
      - BB Break 파라미터: SL=1.3, TP=2.2, MH=42봉(7일)
    4h에서 BB Break는 강한 단기 모멘텀 포착에 유효
    """
    df     = df.copy()
    ma50   = df["ma50"].fillna(0)
    ma200  = df["ma200"].fillna(0)
    adx    = df["adx"].fillna(0)
    close  = df["close"]

    bull_m = (ma50 > ma200) & (close > ma50) & (adx > 15)
    bear_m = (ma50 < ma200) & (close < ma50) & (adx > 15)
    side_m = adx < 12
    df["regime"] = "neutral"
    df.loc[side_m, "regime"] = "sideways"
    df.loc[bear_m, "regime"] = "bear"
    df.loc[bull_m, "regime"] = "bull"

    n   = len(df)
    pos = np.zeros(n, dtype=int)
    cp  = 0; ep = 0.0; ei = 0; ea = 0.0; etype = ""

    RPARAMS = {
        "bull":     dict(sl=1.6, tp=4.0, mh=72),
        "bear":     dict(sl=1.4, tp=2.8, mh=48),
        "sideways": dict(sl=0.9, tp=1.5, mh=30),
        "neutral":  dict(sl=1.6, tp=2.8, mh=48),
        "bb":       dict(sl=1.3, tp=2.2, mh=42),
    }

    for i in range(START, n):
        c      = df["close"].iloc[i]
        atr_i  = df["atr14"].iloc[i]
        regime = df["regime"].iloc[i]
        pkey   = "bb" if etype == "bb" else regime
        p      = RPARAMS.get(pkey, RPARAMS["bull"])

        if cp != 0:
            if _check_exit(cp, c, ep, ea, i - ei, p["sl"], p["tp"], p["mh"]):
                cp = 0; etype = ""
        if cp == 0:
            mom    = df["sq_mom"].iloc[i]
            dm     = df["sq_mom_delta"].iloc[i]
            rel    = df["sq_release"].iloc[i]
            vd     = df["vwap_dev"].iloc[i]
            rsi    = df["rsi14"].iloc[i]
            adx_i  = df["adx"].iloc[i]
            wslope = df["weekly_slope"].iloc[i]
            rpos   = df["range_pos"].iloc[i]
            vol_r  = df["vol_ratio"].iloc[i]
            bb_up  = df["bb_upper"].iloc[i]
            bb_lo  = df["bb_lower"].iloc[i]
            prev_c = df["close"].iloc[i - 1]

            if vol_r > 3.0:
                pos[i] = cp; continue
            if np.isnan(rsi) or np.isnan(mom):
                pos[i] = cp; continue

            w_up = wslope >  0.003
            w_dn = wslope < -0.003

            if regime == "bull":
                if rel and mom > 0 and dm > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "sq"
                if cp == 0 and rsi < 43 and w_up and adx_i > 15:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "pullback"
                if cp == 0 and not np.isnan(vd) and vd < -0.025:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "vwap"
                if cp == 0 and prev_c <= bb_up and c > bb_up and mom > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "bb"
            elif regime == "bear":
                if rel and mom < 0 and dm < 0:
                    cp, ep, ei, ea, etype = -1, c, i, atr_i, "sq"
                if cp == 0 and rsi > 57 and w_dn and adx_i > 15:
                    cp, ep, ei, ea, etype = -1, c, i, atr_i, "pullback"
                if cp == 0 and not np.isnan(vd) and vd > 0.025:
                    cp, ep, ei, ea, etype = -1, c, i, atr_i, "vwap"
                if cp == 0 and prev_c >= bb_lo and c < bb_lo and mom < 0:
                    cp, ep, ei, ea, etype = -1, c, i, atr_i, "bb"
            elif regime == "sideways":
                if not np.isnan(rpos):
                    if rpos < 0.25 and rsi < 45:
                        cp, ep, ei, ea, etype = 1, c, i, atr_i, "range"
                    elif rpos > 0.75 and rsi > 55:
                        cp, ep, ei, ea, etype = -1, c, i, atr_i, "range"
        pos[i] = cp

    df["position"] = pos
    return df


# ─────────────────────────────────────────────────────────────────────
# V8: V7 기반 롱온리 (BTC 강세 바이어스)
# ─────────────────────────────────────────────────────────────────────

def strategy_v8(df: pd.DataFrame) -> pd.DataFrame:
    """
    V8: V7 기반 롱온리 전략 (4h)
    ─────────────────────────────
    · Bear 레짐 → 현금 보유 (숏 완전 제거)
    · 롱 SL 확대: 1.6→1.8, TP=5.0, MH=84봉(14일)
    · RSI Pullback 완화: 43→46
    · VWAP 임계값 완화: -2.5%→-2.0%
    · Sideways 롱 MH=36봉(6일)
    4h에서 롱온리는 BTC 장기 상승 바이어스 + 숏 변동성 리스크 제거
    """
    df    = df.copy()
    ma50  = df["ma50"].fillna(0)
    ma200 = df["ma200"].fillna(0)
    adx   = df["adx"].fillna(0)
    close = df["close"]

    bull_m = (ma50 > ma200) & (close > ma50) & (adx > 15)
    side_m = adx < 12
    df["regime"] = "neutral"
    df.loc[side_m, "regime"] = "sideways"
    df.loc[bull_m, "regime"] = "bull"

    n   = len(df)
    pos = np.zeros(n, dtype=int)
    cp  = 0; ep = 0.0; ei = 0; ea = 0.0; etype = ""

    PARAMS = {
        "bull":     dict(sl=1.8, tp=5.0, mh=84),
        "sideways": dict(sl=0.9, tp=1.5, mh=36),
        "neutral":  dict(sl=1.4, tp=2.8, mh=48),
        "bb":       dict(sl=1.3, tp=2.2, mh=42),
    }

    for i in range(START, n):
        c      = df["close"].iloc[i]
        atr_i  = df["atr14"].iloc[i]
        regime = df["regime"].iloc[i]
        pkey   = "bb" if etype == "bb" else regime
        p      = PARAMS.get(pkey, PARAMS["bull"])

        if cp != 0:
            if _check_exit(cp, c, ep, ea, i - ei, p["sl"], p["tp"], p["mh"]):
                cp = 0; etype = ""
        if cp == 0:
            mom    = df["sq_mom"].iloc[i]
            dm     = df["sq_mom_delta"].iloc[i]
            rel    = df["sq_release"].iloc[i]
            vd     = df["vwap_dev"].iloc[i]
            rsi    = df["rsi14"].iloc[i]
            adx_i  = df["adx"].iloc[i]
            wslope = df["weekly_slope"].iloc[i]
            rpos   = df["range_pos"].iloc[i]
            vol_r  = df["vol_ratio"].iloc[i]
            bb_up  = df["bb_upper"].iloc[i]
            prev_c = df["close"].iloc[i - 1]

            if vol_r > 3.0:
                pos[i] = cp; continue
            if np.isnan(rsi) or np.isnan(mom):
                pos[i] = cp; continue

            w_up = wslope > 0.002

            if regime == "bull":
                if rel and mom > 0 and dm > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "sq"
                if cp == 0 and rsi < 46 and w_up and adx_i > 15:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "pullback"
                if cp == 0 and not np.isnan(vd) and vd < -0.02:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "vwap"
                if cp == 0 and prev_c <= bb_up and c > bb_up and mom > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "bb"
            elif regime == "sideways":
                if not np.isnan(rpos) and rpos < 0.25 and rsi < 48:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "range"
        pos[i] = cp

    df["position"] = pos
    return df


# ─────────────────────────────────────────────────────────────────────
# V9: V8 + Squeeze 조기 진입 + EMA 골든크로스
# ─────────────────────────────────────────────────────────────────────

def strategy_v9(df: pd.DataFrame) -> pd.DataFrame:
    """
    V9: V8 + Squeeze 중 조기 진입 + EMA 크로스 (4h)
    ─────────────────────────────────────────────────
    추가 신호:
      ① Squeeze ON + sq_mom > 0.45×60봉std + dm>0 + RSI<68 → 롱
         (4h에서는 좀 더 엄격: 일봉 0.5→0.45)
      ② EMA20>EMA50 골든크로스 + ADX>15 → 롱
         EMA 크로스: SL=1.6, TP=3.8, MH=60봉(10일)
    기대 효과: 4h 거래 빈도 일봉 대비 3~4배
    """
    df    = df.copy()
    ma50  = df["ma50"].fillna(0)
    ma200 = df["ma200"].fillna(0)
    adx   = df["adx"].fillna(0)
    close = df["close"]

    ema20 = df["ema20"]
    ema50 = df["ema50"]
    ema_cross_up = (ema20 > ema50) & (ema20.shift(1) <= ema50.shift(1))

    bull_m = (ma50 > ma200) & (close > ma50) & (adx > 15)
    side_m = adx < 12
    df["regime"] = "neutral"
    df.loc[side_m, "regime"] = "sideways"
    df.loc[bull_m, "regime"] = "bull"

    n   = len(df)
    pos = np.zeros(n, dtype=int)
    cp  = 0; ep = 0.0; ei = 0; ea = 0.0; etype = ""

    PARAMS = {
        "bull":     dict(sl=1.8, tp=5.0, mh=84),
        "sideways": dict(sl=0.9, tp=1.5, mh=36),
        "neutral":  dict(sl=1.4, tp=2.8, mh=48),
        "bb":       dict(sl=1.3, tp=2.2, mh=42),
        "ema":      dict(sl=1.6, tp=3.8, mh=60),
        "sqm":      dict(sl=1.4, tp=3.2, mh=60),
    }

    mom_series = df["sq_mom"].fillna(0)

    for i in range(START, n):
        c      = df["close"].iloc[i]
        atr_i  = df["atr14"].iloc[i]
        regime = df["regime"].iloc[i]
        pkey   = etype if etype in PARAMS else regime
        p      = PARAMS.get(pkey, PARAMS["bull"])

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
            vol_r  = df["vol_ratio"].iloc[i]
            bb_up  = df["bb_upper"].iloc[i]
            prev_c = df["close"].iloc[i - 1]
            ema_x  = ema_cross_up.iloc[i]
            mom_std = mom_series.iloc[max(0, i - 60):i].std()

            if vol_r > 3.0:
                pos[i] = cp; continue
            if np.isnan(rsi) or np.isnan(mom):
                pos[i] = cp; continue

            w_up = wslope > 0.002

            if regime == "bull":
                if rel and mom > 0 and dm > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "sq"
                if cp == 0 and sq_on and mom > 0.45 * mom_std and dm > 0 and rsi < 68:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "sqm"
                if cp == 0 and ema_x and adx_i > 15:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "ema"
                if cp == 0 and rsi < 46 and w_up and adx_i > 15:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "pullback"
                if cp == 0 and not np.isnan(vd) and vd < -0.02:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "vwap"
                if cp == 0 and prev_c <= bb_up and c > bb_up and mom > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "bb"
            elif regime == "sideways":
                if not np.isnan(rpos) and rpos < 0.25 and rsi < 48:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "range"
        pos[i] = cp

    df["position"] = pos
    return df


# ─────────────────────────────────────────────────────────────────────
# V10: 복합 최적화 (주간 +1% 목표 달성)
# ─────────────────────────────────────────────────────────────────────

def strategy_v10(df: pd.DataFrame) -> pd.DataFrame:
    """
    V10: 4h 최종 복합 최적화 (주간 +1% 목표)
    ─────────────────────────────────────────────
    V9 기반 추가 최적화:
      - ADX 임계값 완화: 15→13
      - Squeeze 조기 진입 임계값 완화: 0.45→0.38×std
      - RSI Pullback 완화: 46→49
      - VWAP 완화: -2.0%→-1.6%
      - Sideways 범위 확대: range_pos < 0.30
      - Neutral 레짐에서도 EMA 크로스 포착
      - 적응형 SL: 저변동 구간 타이트, 고변동 구간 여유
      - 극단 변동성 필터 완화: 2.5→3.5 (4h는 변동성 큼)
    """
    df    = df.copy()
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
    cp  = 0; ep = 0.0; ei = 0; ea = 0.0; etype = ""

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

        # 적응형 SL: 저변동 타이트, 고변동 여유
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
        pos[i] = cp

    df["position"] = pos
    return df


# ══════════════════════════════════════════════════════════════════════
# 7. 결과 출력 및 메인
# ══════════════════════════════════════════════════════════════════════

SEP  = "=" * 82
LINE = "-" * 82


def pf(val: float, dec: int = 1) -> str:
    return f"{val * 100:.{dec}f}%"


def print_strategy_table(results: dict, btc_m: dict) -> None:
    hdr = (f"{'전략':<40} {'CAGR':>7} {'MDD':>7} {'샤프':>6} "
           f"{'주간≥1%':>7} {'주간평균':>7} {'거래/년':>7}")
    print(hdr)
    print(LINE)
    for name, (_, trades, m) in results.items():
        n_yr = f"{m.get('trades_per_yr', 0):.0f}"
        print(
            f"{name:<40} {pf(m['cagr']):>7} {pf(m['mdd']):>7} "
            f"{m['sharpe']:>6.2f} {pf(m['weekly_1pct']):>7} "
            f"{pf(m['weekly_avg']):>7} {n_yr:>7}"
        )
    print(LINE)
    print(
        f"{'BTC Buy & Hold':<40} {pf(btc_m['cagr']):>7} {pf(btc_m['mdd']):>7} "
        f"{btc_m['sharpe']:>6.2f} {pf(btc_m['weekly_1pct']):>7} "
        f"{pf(btc_m['weekly_avg']):>7} {'N/A':>7}"
    )


def print_period_analysis(label: str, pm: dict) -> None:
    print(f"\n  {label}")
    for name, d in pm.items():
        print(f"    {name:<30}: CAGR {pf(d['cagr']):>8},  MDD {pf(d['mdd']):>8}")


def print_weekly_detail(m: dict) -> None:
    wr  = m["weekly_returns"]
    print(f"  주간 +1% 이상 달성 비율 : {pf(m['weekly_1pct'])}")
    print(f"  주간 평균 수익률       : {pf(m['weekly_avg'])}")
    print(f"  주간 수익률 분포       : "
          f"P25={pf(wr.quantile(0.25))}  P50={pf(wr.median())}  P75={pf(wr.quantile(0.75))}")
    print(f"  음(-)수익 주 비율      : {pf((wr < 0).mean())}")


def print_trade_detail(name: str, trades_df: pd.DataFrame, m: dict) -> None:
    if len(trades_df) == 0:
        return
    print(f"\n  [{name}] 거래 통계:")
    print(f"    총 거래 수      : {m['n_trades']:.0f}  ({m['trades_per_yr']:.1f}회/년)")
    print(f"    승률            : {pf(m['win_rate'])}")
    print(f"    평균 수익 (승)  : {pf(m['avg_win'])}")
    print(f"    평균 손실 (패)  : {pf(m['avg_loss'])}")
    print(f"    평균 보유 기간  : {m['avg_hold_days']:.1f}일 ({m['avg_hold_bars']:.0f}봉)")
    for d in ["long", "short"]:
        sub = trades_df[trades_df["direction"] == d]
        if len(sub) > 0:
            wr  = (sub["gross_return"] > 0).mean()
            avg = sub["gross_return"].mean()
            print(f"    {d:5s}          : {len(sub):3d}회, 승률={pf(wr)}, 평균={pf(avg, 2)}")


def main() -> None:
    print(SEP)
    print("  BTC 4시간봉 데이 트레이딩  ─  V1~V10 백테스트")
    print(f"  기간: 2021-01-01 ~ 현재 | 수수료: RT 0.1% | 1일 = 6봉 (4h)")
    print(f"  목표: 주간 평균 +1% (연 CAGR ~68%)")
    print(f"  데이터: Binance BTC/USDT 4h (Fallback: yfinance 1h → 4h 리샘플)")
    print(SEP)

    df = get_btc_data_4h("2021-01-01")
    df = add_indicators(df)
    print(f"\n  지표 계산 완료: {len(df):,}봉, {len(df)/6:.0f}일 분량\n")

    FEE = 0.001  # RT 0.1%

    STRATEGIES = [
        ("V1: Squeeze Momentum 기본 (4h)",             strategy_v1),
        ("V2: + MA200(33일) 추세 필터",                strategy_v2),
        ("V3: + VWAP(20일) 이탈 회귀",                 strategy_v3),
        ("V4: + RSI Pullback + 다중 시간프레임",        strategy_v4),
        ("V5: 레짐 감지 + 자동 전환",                  strategy_v5),
        ("V6: 파라미터 완화 (거래 빈도 확대)",         strategy_v6),
        ("V7: + BB Break 신호",                        strategy_v7),
        ("V8: 롱온리 전략",                            strategy_v8),
        ("V9: + Squeeze 조기진입 + EMA 크로스",        strategy_v9),
        ("V10: 복합 최적화 (주간 +1% 목표)",           strategy_v10),
    ]

    # ── Buy & Hold ────────────────────────────────────────
    bh_equity = df["close"].values / df["close"].values[0]
    btc_m = calc_metrics(bh_equity, df.index)

    # ── 전략 실행 ──────────────────────────────────────────
    print("[V1~V5] 레거시 기본 전략 실행 중...\n")
    results = {}
    for name, func in STRATEGIES[:5]:
        print(f"  {name} ...", end=" ", flush=True)
        try:
            eq, tr = run_backtest(df, func, fee_rate=FEE)
            m = calc_metrics(eq, df.index, tr)
            results[name] = (eq, tr, m)
            n_yr = m.get("trades_per_yr", 0)
            print(f"CAGR={pf(m['cagr'])}  MDD={pf(m['mdd'])}  "
                  f"샤프={m['sharpe']:.2f}  거래={n_yr:.1f}회/년")
        except Exception as exc:
            print(f"오류: {exc}")
            import traceback; traceback.print_exc()

    print(f"\n[V6~V10] 최적화 전략 실행 중...\n")
    new_results = {}
    for name, func in STRATEGIES[5:]:
        print(f"  {name} ...", end=" ", flush=True)
        try:
            eq, tr = run_backtest(df, func, fee_rate=FEE)
            m = calc_metrics(eq, df.index, tr)
            new_results[name] = (eq, tr, m)
            n_yr = m.get("trades_per_yr", 0)
            print(f"CAGR={pf(m['cagr'])}  MDD={pf(m['mdd'])}  "
                  f"샤프={m['sharpe']:.2f}  거래={n_yr:.1f}회/년")
        except Exception as exc:
            print(f"오류: {exc}")
            import traceback; traceback.print_exc()

    all_results = {**results, **new_results}

    # ── V1~V5 요약 ────────────────────────────────────────
    print(f"\n{SEP}")
    print("  [V1~V5] 성과 요약")
    print(SEP)
    print_strategy_table(results, btc_m)

    # ── V6~V10 요약 ───────────────────────────────────────
    print(f"\n{SEP}")
    print("  [V6~V10] 최적화 전략 성과 요약")
    print(SEP)
    print_strategy_table(new_results, btc_m)

    # ── 전체 비교 테이블 ──────────────────────────────────
    print(f"\n{SEP}")
    print("  [전체 V1~V10] 통합 성과 비교")
    print(SEP)
    print_strategy_table(all_results, btc_m)

    # ── 시기별 분석 ───────────────────────────────────────
    print(f"\n{SEP}")
    print("  시기별 성과 분석 (2021~2022 불장/폭락, 2023~2024 회복, 2025+ OOS)")
    print(SEP)
    btc_pm = calc_period(bh_equity, df.index)
    print_period_analysis("BTC Buy & Hold:", btc_pm)
    for name, (eq, _, _) in all_results.items():
        pm = calc_period(eq, df.index)
        if pm:
            print_period_analysis(name, pm)

    # ── V10 상세 분석 ─────────────────────────────────────
    best_key = "V10: 복합 최적화 (주간 +1% 목표)"
    if best_key in new_results:
        eq10, tr10, m10 = new_results[best_key]
        print(f"\n{SEP}")
        print(f"  주간 +1% 목표 달성 분석 ({best_key})")
        print(SEP)
        print_weekly_detail(m10)
        print_trade_detail(best_key, tr10, m10)

    # ── 주간 수익률 분포 비교 ─────────────────────────────
    print(f"\n{SEP}")
    print("  V6~V10 주간 수익률 분포 비교")
    print(SEP)
    hdr2 = f"  {'전략':<42} {'평균':>7} {'중앙값':>7} {'P25':>7} {'P75':>7} {'≥+1%':>7}"
    print(hdr2)
    print(LINE)
    for name, (_, _, m) in new_results.items():
        wr = m["weekly_returns"]
        print(
            f"  {name:<42} "
            f"{pf(m['weekly_avg']):>7} "
            f"{pf(wr.median()):>7} "
            f"{pf(wr.quantile(0.25)):>7} "
            f"{pf(wr.quantile(0.75)):>7} "
            f"{pf(m['weekly_1pct']):>7}"
        )
    print(LINE)
    bwr_s = pd.Series(bh_equity, index=df.index)
    bwr_w = bwr_s.resample("W-FRI").last().ffill().pct_change().dropna()
    print(
        f"  {'BTC Buy & Hold':<42} "
        f"{pf(bwr_w.mean()):>7} "
        f"{pf(bwr_w.median()):>7} "
        f"{pf(bwr_w.quantile(0.25)):>7} "
        f"{pf(bwr_w.quantile(0.75)):>7} "
        f"{pf((bwr_w >= 0.01).mean()):>7}"
    )

    # ── 주간 +1% 목표 달성 여부 요약 ──────────────────────
    print(f"\n{SEP}")
    print("  주간 +1% 목표 달성 여부 요약")
    print(SEP)
    TARGET = 0.01
    for name, (_, _, m) in all_results.items():
        met  = m["weekly_1pct"] >= 0.30
        flag = "✓ 달성" if met else "✗ 미달"
        print(f"  {flag}  {name:<42}  "
              f"주간≥+1% {pf(m['weekly_1pct'])}  "
              f"주간평균 {pf(m['weekly_avg'])}  "
              f"CAGR {pf(m['cagr'])}")
    print(LINE)
    bh_met = (bwr_w.mean() >= TARGET)
    print(f"  {'✓' if bh_met else '✗'}      "
          f"{'BTC Buy & Hold':<42}  "
          f"주간≥+1% {pf((bwr_w >= 0.01).mean())}  "
          f"주간평균 {pf(bwr_w.mean())}  "
          f"CAGR {pf(btc_m['cagr'])}")
    print(f"\n  * 주간≥+1% 달성 기준: 전체 주 중 30% 이상")

    print(f"\n{SEP}")
    print("  백테스트 완료")
    print(SEP)


if __name__ == "__main__":
    main()
