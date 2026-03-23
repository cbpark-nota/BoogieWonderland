#!/usr/bin/env python3
"""
BTC 데이 트레이딩 알고리즘 v2
=================================
완전히 새로운 접근: Squeeze Momentum + VWAP 회귀 + 다중 시간프레임 + 레짐 감지

목표: 주간 평균 +1% 수익 (연 ~68% CAGR)
수수료: 매수 0.05% + 매도 0.05% = RT 0.1%
데이터: yfinance BTC-USD 일봉 (2015~현재)

전략 버전:
  V1: TTM Squeeze Momentum (기본)
  V2: V1 + 추세 필터 (200MA)
  V3: V2 + VWAP 이탈 회귀 전략 병행
  V4: V3 + 다중 시간프레임 Pullback (RSI + 주간 모멘텀)
  V5: 레짐 감지 (Bull/Bear/Sideways) + 전략 자동 전환

실행:
  python scripts/crypto/btc_daytrading_v2.py
"""

import pandas as pd
import numpy as np
import yfinance as yf
import warnings

warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════════════
# 1. 데이터 수집
# ══════════════════════════════════════════════════════════════════════

def get_btc_data(start: str = "2015-01-01") -> pd.DataFrame:
    """BTC-USD 일봉 데이터 수집 (yfinance)"""
    print("BTC-USD 데이터 수집 중...")
    raw = yf.download("BTC-USD", start=start, progress=False, auto_adjust=True)
    df = raw.copy()
    df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    print(f"기간: {df.index[0].date()} ~ {df.index[-1].date()}  ({len(df):,}일)")
    return df


# ══════════════════════════════════════════════════════════════════════
# 2. 기술 지표 계산
# ══════════════════════════════════════════════════════════════════════

def _linreg_end(series: pd.Series, window: int) -> pd.Series:
    """
    각 구간의 선형 회귀 끝점 값 (벡터화)
    TTM Squeeze 모멘텀 계산에 사용
    """
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
    """모든 기술 지표 계산 후 반환"""
    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # ── 이동평균 ──────────────────────────────────────
    for p in [20, 50, 100, 200]:
        df[f"ma{p}"] = close.rolling(p).mean()
    df["ema20"] = close.ewm(span=20, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()

    # ── ATR ───────────────────────────────────────────
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    df["atr14"] = tr.ewm(span=14, adjust=False).mean()
    df["atr20"] = tr.rolling(20).mean()

    # ── 볼린저 밴드 (20일, ±2σ) ───────────────────────
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std(ddof=0)
    df["bb_mid"] = bb_mid
    df["bb_upper"] = bb_mid + 2 * bb_std
    df["bb_lower"] = bb_mid - 2 * bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / bb_mid

    # ── 켈트너 채널 (20일, ±2.0×ATR20) ───────────────
    # BTC는 변동성이 높아 2.0 배수 사용 (1.5는 스퀴즈가 너무 드물다)
    kc_mid = df["ema20"]
    df["kc_upper"] = kc_mid + 2.0 * df["atr20"]
    df["kc_lower"] = kc_mid - 2.0 * df["atr20"]

    # ── TTM Squeeze ────────────────────────────────────
    # BB가 KC 안에 완전히 들어오면 "스퀴즈 ON"
    df["sq_on"] = (df["bb_upper"] < df["kc_upper"]) & (df["bb_lower"] > df["kc_lower"])
    # 이전 바에서 ON → 현재 OFF: 스퀴즈 해제
    df["sq_release"] = (~df["sq_on"]) & df["sq_on"].shift(1).fillna(False)

    # 스퀴즈 모멘텀: close - 중간가격(donchian mid + bb_mid) 의 12일 선형회귀 끝점
    donchian_mid = (high.rolling(20).max() + low.rolling(20).min()) / 2
    mid_val = (donchian_mid + bb_mid) / 2
    raw_mom = close - mid_val
    df["sq_mom"] = _linreg_end(raw_mom, 12)          # 모멘텀 값
    df["sq_mom_delta"] = df["sq_mom"] - df["sq_mom"].shift(1)  # 모멘텀 방향

    # ── VWAP (Rolling 20일) ────────────────────────────
    tp = (high + low + close) / 3
    vwap = (tp * volume).rolling(20).sum() / volume.rolling(20).sum()
    vwap_std = (tp - vwap).rolling(20).std(ddof=0)
    df["vwap20"] = vwap
    df["vwap_upper2"] = vwap + 2 * vwap_std
    df["vwap_lower2"] = vwap - 2 * vwap_std
    df["vwap_dev"] = (close - vwap) / vwap   # 이탈률 (0=VWAP, ±0.05 = ±5%)

    # ── ADX + DI ──────────────────────────────────────
    up_move = high.diff()
    dn_move = -low.diff()
    plus_dm = up_move.where((up_move > dn_move) & (up_move > 0), 0.0)
    minus_dm = dn_move.where((dn_move > up_move) & (dn_move > 0), 0.0)

    atr14s = tr.ewm(span=14, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(span=14, adjust=False).mean() / atr14s
    minus_di = 100 * minus_dm.ewm(span=14, adjust=False).mean() / atr14s
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    df["adx"] = dx.ewm(span=14, adjust=False).mean()
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    # ── RSI (14일) ────────────────────────────────────
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
    df["rsi14"] = 100 - 100 / (1 + gain / (loss + 1e-9))

    # ── 레인지 포지션 (20일) ──────────────────────────
    h20 = high.rolling(20).max()
    l20 = low.rolling(20).min()
    df["h20"] = h20
    df["l20"] = l20
    df["range_pos"] = (close - l20) / (h20 - l20 + 1e-9)   # 0~1

    # ── 변동성 레짐 ───────────────────────────────────
    daily_ret = close.pct_change()
    df["vol20"] = daily_ret.rolling(20).std() * np.sqrt(252)
    df["vol60"] = daily_ret.rolling(60).std() * np.sqrt(252)
    df["vol_ratio"] = df["vol20"] / (df["vol60"] + 1e-9)   # >1 이면 변동성 확대

    # ── 주간 추세 슬로프 (25일 EMA 기울기) ───────────
    ema25 = close.ewm(span=25, adjust=False).mean()
    df["weekly_slope"] = ema25.pct_change(5)   # 5일 변화율

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
    백테스트 실행

    Parameters
    ----------
    df          : 지표가 추가된 OHLCV 데이터프레임
    strategy_func : 포지션 배열을 계산하는 전략 함수
    fee_rate    : 왕복 수수료 (0.001 = 0.1%)

    Returns
    -------
    equity : 자산 곡선 (numpy array, 시작 = 1.0)
    trades : 거래 내역 데이터프레임
    """
    signals = strategy_func(df.copy())
    pos = signals["position"].values  # 1=롱, -1=숏, 0=중립
    close = df["close"].values
    dates = df.index

    n = len(close)
    equity = np.ones(n, dtype=float)
    half_fee = fee_rate / 2.0   # 편도 수수료

    trade_log = []
    entry_price = np.nan
    entry_pos = 0
    entry_idx = 0

    for i in range(1, n):
        prev_p = pos[i - 1]
        curr_p = pos[i]

        # ─ 보유 수익 반영 ─
        ret = close[i] / close[i - 1]
        if prev_p == 1:
            equity[i] = equity[i - 1] * ret
        elif prev_p == -1:
            equity[i] = equity[i - 1] * (2.0 - ret)
        else:
            equity[i] = equity[i - 1]

        # ─ 포지션 변화 시 수수료 및 거래 기록 ─
        if prev_p != curr_p:
            if prev_p != 0:
                # 청산 수수료
                equity[i] *= (1.0 - half_fee)
                # 거래 기록
                if not np.isnan(entry_price):
                    if entry_pos == 1:
                        trade_ret = close[i] / entry_price - 1
                    else:
                        trade_ret = entry_price / close[i] - 1
                    trade_log.append(
                        dict(
                            entry_date=dates[entry_idx],
                            exit_date=dates[i],
                            direction="long" if entry_pos == 1 else "short",
                            entry_price=entry_price,
                            exit_price=close[i],
                            gross_return=trade_ret,
                            hold_days=i - entry_idx,
                        )
                    )
            if curr_p != 0:
                # 진입 수수료
                equity[i] *= (1.0 - half_fee)
                entry_price = close[i]
                entry_pos = curr_p
                entry_idx = i
            else:
                entry_price = np.nan
                entry_pos = 0

    trades_df = pd.DataFrame(trade_log)
    return equity, trades_df


# ══════════════════════════════════════════════════════════════════════
# 4. 성과 지표
# ══════════════════════════════════════════════════════════════════════

def calc_metrics(equity: np.ndarray, dates: pd.DatetimeIndex,
                 trades_df: pd.DataFrame = None,
                 risk_free: float = 0.05) -> dict:
    """CAGR, MDD, 샤프, 주간 수익률 분석"""
    equity_s = pd.Series(equity, index=dates)
    daily_ret = equity_s.pct_change().dropna()

    years = (dates[-1] - dates[0]).days / 365.25
    total_ret = equity[-1] / equity[0] - 1
    cagr = (equity[-1] / equity[0]) ** (1.0 / max(years, 0.01)) - 1

    # MDD
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    mdd = dd.min()

    # 샤프 (무위험 수익률 5%)
    daily_rf = (1 + risk_free) ** (1.0 / 252) - 1
    excess = daily_ret - daily_rf
    sharpe = excess.mean() / excess.std() * np.sqrt(252) if excess.std() > 0 else 0.0

    # 주간 수익률
    weekly_eq = equity_s.resample("W-FRI").last().ffill()
    weekly_ret = weekly_eq.pct_change().dropna()
    weekly_avg = weekly_ret.mean()
    weekly_1pct = (weekly_ret >= 0.01).mean()

    result = dict(
        total_ret=total_ret,
        cagr=cagr,
        mdd=mdd,
        sharpe=sharpe,
        weekly_avg=weekly_avg,
        weekly_1pct=weekly_1pct,
        weekly_returns=weekly_ret,
        years=years,
    )

    if trades_df is not None and len(trades_df) > 0:
        wins = trades_df[trades_df["gross_return"] > 0]
        loss = trades_df[trades_df["gross_return"] <= 0]
        result.update(
            dict(
                n_trades=len(trades_df),
                win_rate=len(wins) / len(trades_df),
                avg_win=wins["gross_return"].mean() if len(wins) > 0 else 0.0,
                avg_loss=loss["gross_return"].mean() if len(loss) > 0 else 0.0,
                avg_hold=trades_df["hold_days"].mean(),
                trades_per_yr=len(trades_df) / max(years, 0.01),
            )
        )

    return result


def calc_period(equity: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    """시기별 CAGR/MDD 분리 분석"""
    s = pd.Series(equity, index=dates)
    periods = {
        "2015-2018 (초기 강세장)": ("2015-01-01", "2018-12-31"),
        "2019-2021 (회복·폭등)":   ("2019-01-01", "2021-12-31"),
        "2022-현재 (제도권 편입)": ("2022-01-01", None),
    }
    out = {}
    for name, (st, en) in periods.items():
        sub = s.loc[st:en] if en else s.loc[st:]
        if len(sub) < 10:
            continue
        yr = (sub.index[-1] - sub.index[0]).days / 365.25
        if yr < 0.1:
            continue
        cagr = (sub.iloc[-1] / sub.iloc[0]) ** (1.0 / yr) - 1
        pk = np.maximum.accumulate(sub.values)
        mdd = ((sub.values - pk) / pk).min()
        out[name] = dict(cagr=cagr, mdd=mdd)
    return out


# ══════════════════════════════════════════════════════════════════════
# 5. 전략 구현
# ══════════════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────────────
# 공통: 진입·청산 헬퍼
# ──────────────────────────────────────────────────────────────────────

def _check_exit(
    curr_pos: int,
    close_i: float,
    entry_price: float,
    entry_atr: float,
    hold_days: int,
    sl_mult: float,
    tp_mult: float,
    max_hold: int,
) -> bool:
    """현재 포지션 청산 조건 체크 → True면 청산"""
    if curr_pos == 0:
        return False
    if hold_days >= max_hold:
        return True
    if curr_pos == 1:
        return close_i <= entry_price - sl_mult * entry_atr or \
               close_i >= entry_price + tp_mult * entry_atr
    else:  # short
        return close_i >= entry_price + sl_mult * entry_atr or \
               close_i <= entry_price - tp_mult * entry_atr


# ──────────────────────────────────────────────────────────────────────
# V1: TTM Squeeze Momentum (기본)
# ──────────────────────────────────────────────────────────────────────

def strategy_v1(df: pd.DataFrame) -> pd.DataFrame:
    """
    V1: TTM Squeeze Momentum 기본
    ──────────────────────────────
    · 볼린저 밴드가 켈트너 채널 안으로 수축 후 해제(squeeze release) 시 진입
    · 모멘텀이 양수면 롱, 음수면 숏
    · SL=2.5×ATR, TP=4.0×ATR, 최대 10일 보유
    """
    n = len(df)
    pos = np.zeros(n, dtype=int)
    START = 50

    cp = 0; ep = 0.0; ei = 0; ea = 0.0
    SL, TP, MH = 2.5, 4.0, 10

    for i in range(START, n):
        c = df["close"].iloc[i]
        atr = df["atr14"].iloc[i]

        if cp != 0:
            if _check_exit(cp, c, ep, ea, i - ei, SL, TP, MH):
                cp = 0
        if cp == 0:
            mom = df["sq_mom"].iloc[i]
            dm = df["sq_mom_delta"].iloc[i]
            rel = df["sq_release"].iloc[i]
            if rel and not (np.isnan(mom) or np.isnan(dm)):
                if mom > 0 and dm > 0:
                    cp, ep, ei, ea = 1, c, i, atr
                elif mom < 0 and dm < 0:
                    cp, ep, ei, ea = -1, c, i, atr
        pos[i] = cp

    df["position"] = pos
    return df


# ──────────────────────────────────────────────────────────────────────
# V2: V1 + 200MA 추세 필터
# ──────────────────────────────────────────────────────────────────────

def strategy_v2(df: pd.DataFrame) -> pd.DataFrame:
    """
    V2: TTM Squeeze + 200MA 추세 필터
    ────────────────────────────────────
    · 200MA 위에서만 롱, 200MA 아래에서만 숏
    · 추세에 역행하는 squeeze 신호 무시
    · SL=2.5×ATR, TP=4.0×ATR, 최대 12일 보유
    """
    n = len(df)
    pos = np.zeros(n, dtype=int)
    START = 210

    cp = 0; ep = 0.0; ei = 0; ea = 0.0
    SL, TP, MH = 2.5, 4.0, 12

    for i in range(START, n):
        c = df["close"].iloc[i]
        atr = df["atr14"].iloc[i]

        if cp != 0:
            if _check_exit(cp, c, ep, ea, i - ei, SL, TP, MH):
                cp = 0
        if cp == 0:
            mom = df["sq_mom"].iloc[i]
            dm = df["sq_mom_delta"].iloc[i]
            rel = df["sq_release"].iloc[i]
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


# ──────────────────────────────────────────────────────────────────────
# V3: V2 + VWAP 이탈 회귀 전략 병행
# ──────────────────────────────────────────────────────────────────────

def strategy_v3(df: pd.DataFrame) -> pd.DataFrame:
    """
    V3: TTM Squeeze + 200MA 필터 + VWAP 이탈 회귀
    ──────────────────────────────────────────────────
    · Squeeze 신호(트렌드 추종) + VWAP ±4% 이탈 회귀 신호 병행
    · VWAP 이탈 회귀 트레이드는 짧게 보유 (SL=1.5, TP=2.0, 최대 5일)
    · Squeeze 트레이드: SL=2.5, TP=4.0, 최대 12일
    · 두 신호 모두 200MA 추세와 일치할 때만 진입
    """
    n = len(df)
    pos = np.zeros(n, dtype=int)
    START = 210

    cp = 0; ep = 0.0; ei = 0; ea = 0.0
    etype = ""   # 'sq' or 'vwap'

    PARAMS = {
        "sq":   dict(sl=2.5, tp=4.0, mh=12),
        "vwap": dict(sl=1.5, tp=2.0, mh=5),
    }

    for i in range(START, n):
        c = df["close"].iloc[i]
        atr = df["atr14"].iloc[i]

        if cp != 0:
            p = PARAMS[etype]
            if _check_exit(cp, c, ep, ea, i - ei, p["sl"], p["tp"], p["mh"]):
                cp = 0; etype = ""
        if cp == 0:
            mom = df["sq_mom"].iloc[i]
            dm = df["sq_mom_delta"].iloc[i]
            rel = df["sq_release"].iloc[i]
            ma200 = df["ma200"].iloc[i]
            vd = df["vwap_dev"].iloc[i]

            if np.isnan(ma200):
                continue
            bull = c > ma200
            bear = c < ma200

            # ① Squeeze 신호
            if rel and not np.isnan(mom):
                if bull and mom > 0 and dm > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr, "sq"
                elif bear and mom < 0 and dm < 0:
                    cp, ep, ei, ea, etype = -1, c, i, atr, "sq"

            # ② VWAP 이탈 회귀 신호 (먼저 진입이 안 됐을 때)
            if cp == 0 and not np.isnan(vd):
                if vd < -0.04 and bull:   # VWAP -4% 이탈 + 상승추세 → 매수
                    cp, ep, ei, ea, etype = 1, c, i, atr, "vwap"
                elif vd > 0.04 and bear:  # VWAP +4% 이탈 + 하락추세 → 매도
                    cp, ep, ei, ea, etype = -1, c, i, atr, "vwap"

        pos[i] = cp

    df["position"] = pos
    return df


# ──────────────────────────────────────────────────────────────────────
# V4: V3 + 다중 시간프레임 RSI Pullback
# ──────────────────────────────────────────────────────────────────────

def strategy_v4(df: pd.DataFrame) -> pd.DataFrame:
    """
    V4: TTM Squeeze + 200MA + VWAP + 다중 시간프레임 RSI Pullback
    ──────────────────────────────────────────────────────────────────
    · 주간 추세(25일 EMA 기울기) + 일봉 추세가 일치할 때
    · RSI 과매도(<38) → 상승추세 Pullback 매수
    · RSI 과매수(>62) → 하락추세 반등 매도
    · ADX > 22 : 추세장 확인
    · SL=2.0, TP=3.5, 최대 10일
    """
    n = len(df)
    pos = np.zeros(n, dtype=int)
    START = 210

    cp = 0; ep = 0.0; ei = 0; ea = 0.0
    etype = ""

    PARAMS = {
        "sq":       dict(sl=2.5, tp=4.5, mh=14),
        "vwap":     dict(sl=1.5, tp=2.0, mh=5),
        "pullback": dict(sl=2.0, tp=3.5, mh=10),
    }

    for i in range(START, n):
        c = df["close"].iloc[i]
        atr = df["atr14"].iloc[i]

        if cp != 0:
            p = PARAMS[etype]
            if _check_exit(cp, c, ep, ea, i - ei, p["sl"], p["tp"], p["mh"]):
                cp = 0; etype = ""
        if cp == 0:
            mom = df["sq_mom"].iloc[i]
            dm = df["sq_mom_delta"].iloc[i]
            rel = df["sq_release"].iloc[i]
            ma200 = df["ma200"].iloc[i]
            ma50  = df["ma50"].iloc[i]
            vd    = df["vwap_dev"].iloc[i]
            rsi   = df["rsi14"].iloc[i]
            adx   = df["adx"].iloc[i]
            wslope = df["weekly_slope"].iloc[i]

            if np.isnan(ma200) or np.isnan(rsi):
                continue

            bull = c > ma200 and c > ma50
            bear = c < ma200 and c < ma50
            w_up  = wslope >  0.01
            w_dn  = wslope < -0.01

            # ① Squeeze
            if rel and not np.isnan(mom):
                if bull and w_up and mom > 0 and dm > 0:
                    cp, ep, ei, ea, etype = 1, c, i, atr, "sq"
                elif bear and w_dn and mom < 0 and dm < 0:
                    cp, ep, ei, ea, etype = -1, c, i, atr, "sq"

            # ② RSI Pullback
            if cp == 0 and adx > 22:
                if bull and w_up and rsi < 38:
                    cp, ep, ei, ea, etype = 1, c, i, atr, "pullback"
                elif bear and w_dn and rsi > 62:
                    cp, ep, ei, ea, etype = -1, c, i, atr, "pullback"

            # ③ VWAP 이탈
            if cp == 0 and not np.isnan(vd):
                if vd < -0.04 and bull:
                    cp, ep, ei, ea, etype = 1, c, i, atr, "vwap"
                elif vd > 0.04 and bear:
                    cp, ep, ei, ea, etype = -1, c, i, atr, "vwap"

        pos[i] = cp

    df["position"] = pos
    return df


# ──────────────────────────────────────────────────────────────────────
# V5: 레짐 감지 + 전략 자동 전환
# ──────────────────────────────────────────────────────────────────────

def strategy_v5(df: pd.DataFrame) -> pd.DataFrame:
    """
    V5: 레짐 감지 + 전략 자동 전환 (최종 버전)
    ──────────────────────────────────────────────
    레짐 분류:
      · Bull  : 50MA > 200MA + 가격 > 50MA + ADX > 20
      · Bear  : 50MA < 200MA + 가격 < 50MA + ADX > 20
      · Sideways: ADX < 18

    Bull 레짐:
      - Squeeze 롱 / RSI Pullback 롱 / VWAP 이탈 롱
      - 파라미터: SL=2.0, TP=5.0, 최대 15일 (큰 추세 타기)

    Bear 레짐:
      - Squeeze 숏 / RSI 과매수 숏 / VWAP 이탈 숏
      - 파라미터: SL=1.8, TP=3.5, 최대 10일 (변동성 높아 짧게)

    Sideways 레짐:
      - 레인지 하단(range_pos < 0.20) 매수 / 상단(> 0.80) 매도
      - 파라미터: SL=1.2, TP=1.8, 최대 6일 (짧은 스윙)

    추가 필터:
      · vol_ratio < 2.5 : 이상 변동성 방지
      · 주간 slope 방향 일치 확인
    """
    # 레짐 계산
    df = df.copy()
    ma50  = df["ma50"].fillna(0)
    ma200 = df["ma200"].fillna(0)
    adx   = df["adx"].fillna(0)
    close = df["close"]

    bull_mask     = (ma50 > ma200) & (close > ma50) & (adx > 18)
    bear_mask     = (ma50 < ma200) & (close < ma50) & (adx > 18)
    sideways_mask = adx < 15

    df["regime"] = "neutral"
    df.loc[sideways_mask, "regime"] = "sideways"
    df.loc[bear_mask,     "regime"] = "bear"
    df.loc[bull_mask,     "regime"] = "bull"

    n = len(df)
    pos = np.zeros(n, dtype=int)
    START = 210

    cp = 0; ep = 0.0; ei = 0; ea = 0.0
    etype = ""

    REGIME_PARAMS = {
        "bull":     dict(sl=2.0, tp=5.0, mh=15),
        "bear":     dict(sl=1.8, tp=3.5, mh=10),
        "sideways": dict(sl=1.2, tp=1.8, mh=6),
        "neutral":  dict(sl=2.0, tp=3.0, mh=8),
    }

    for i in range(START, n):
        c = df["close"].iloc[i]
        atr_i = df["atr14"].iloc[i]
        regime = df["regime"].iloc[i]
        p = REGIME_PARAMS[regime]

        # 청산 체크
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

            # 이상 변동성 방지
            if vol_r > 2.5:
                pos[i] = cp
                continue

            if np.isnan(rsi) or np.isnan(mom):
                pos[i] = cp
                continue

            w_up = wslope >  0.005
            w_dn = wslope < -0.005

            # ══ Bull 레짐 ══
            if regime == "bull":
                if rel and not np.isnan(mom):
                    if mom > 0 and dm > 0:
                        cp, ep, ei, ea, etype = 1, c, i, atr_i, "sq"
                if cp == 0 and rsi < 36 and w_up and adx_i > 20:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "pullback"
                if cp == 0 and not np.isnan(vd) and vd < -0.05:
                    cp, ep, ei, ea, etype = 1, c, i, atr_i, "vwap"

            # ══ Bear 레짐 ══
            elif regime == "bear":
                if rel and not np.isnan(mom):
                    if mom < 0 and dm < 0:
                        cp, ep, ei, ea, etype = -1, c, i, atr_i, "sq"
                if cp == 0 and rsi > 64 and w_dn and adx_i > 20:
                    cp, ep, ei, ea, etype = -1, c, i, atr_i, "pullback"
                if cp == 0 and not np.isnan(vd) and vd > 0.05:
                    cp, ep, ei, ea, etype = -1, c, i, atr_i, "vwap"

            # ══ Sideways 레짐 ══
            elif regime == "sideways":
                if not np.isnan(rpos):
                    if rpos < 0.20 and rsi < 42:
                        cp, ep, ei, ea, etype = 1, c, i, atr_i, "range"
                    elif rpos > 0.80 and rsi > 58:
                        cp, ep, ei, ea, etype = -1, c, i, atr_i, "range"

        pos[i] = cp

    df["position"] = pos
    return df


# ══════════════════════════════════════════════════════════════════════
# 6. 결과 출력 및 메인
# ══════════════════════════════════════════════════════════════════════

SEP = "=" * 80
LINE = "-" * 80


def pf(val: float, dec: int = 1) -> str:
    """퍼센트 포맷"""
    return f"{val * 100:.{dec}f}%"


def print_strategy_table(results: dict, btc_m: dict) -> None:
    hdr = f"{'전략':<38} {'CAGR':>8} {'MDD':>8} {'샤프':>7} {'주간≥1%':>8} {'주간평균':>8} {'거래수/년':>9}"
    print(hdr)
    print(LINE)
    for name, (_, trades, m) in results.items():
        n_yr = f"{m.get('trades_per_yr', 0):.0f}"
        print(
            f"{name:<38} {pf(m['cagr']):>8} {pf(m['mdd']):>8} "
            f"{m['sharpe']:>7.2f} {pf(m['weekly_1pct']):>8} "
            f"{pf(m['weekly_avg']):>8} {n_yr:>9}"
        )
    print(LINE)
    print(
        f"{'BTC Buy & Hold':<38} {pf(btc_m['cagr']):>8} {pf(btc_m['mdd']):>8} "
        f"{btc_m['sharpe']:>7.2f} {pf(btc_m['weekly_1pct']):>8} "
        f"{pf(btc_m['weekly_avg']):>8} {'N/A':>9}"
    )


def print_period_analysis(label: str, period_m: dict) -> None:
    print(f"\n{label}")
    for name, pm in period_m.items():
        print(f"  {name:<28}: CAGR {pf(pm['cagr']):>8},  MDD {pf(pm['mdd']):>8}")


def print_weekly_analysis(m: dict) -> None:
    wr = m["weekly_returns"]
    q25 = pf(wr.quantile(0.25))
    q50 = pf(wr.quantile(0.50))
    q75 = pf(wr.quantile(0.75))
    neg_weeks = pf((wr < 0).mean())
    gt1_weeks = pf(m["weekly_1pct"])
    print(f"  주간 +1% 이상 달성 비율 : {gt1_weeks}")
    print(f"  주간 평균 수익률       : {pf(m['weekly_avg'])}")
    print(f"  주간 수익률 분포       : P25={q25}  P50={q50}  P75={q75}")
    print(f"  음(-)수익 주 비율      : {neg_weeks}")


def main() -> None:
    print(SEP)
    print("  BTC 데이 트레이딩 v2  ─  새로운 접근 백테스트")
    print(f"  수수료: 매수 0.05% + 매도 0.05% = RT 0.1%")
    print(SEP)

    # ── 데이터 ────────────────────────────────────────
    df = get_btc_data()
    df = add_indicators(df)

    FEE = 0.001  # 왕복 0.1%

    STRATEGIES = [
        ("V1: Squeeze Momentum (기본)",          strategy_v1),
        ("V2: + 추세 필터 (200MA)",              strategy_v2),
        ("V3: + VWAP 이탈 회귀 병행",            strategy_v3),
        ("V4: + RSI Pullback · 다중 시간프레임", strategy_v4),
        ("V5: 레짐 감지 + 전략 자동 전환",       strategy_v5),
    ]

    # ── Buy & Hold 기준선 ─────────────────────────────
    bh_equity = df["close"].values / df["close"].values[0]
    btc_m = calc_metrics(bh_equity, df.index)

    # ── 각 전략 실행 ──────────────────────────────────
    results = {}
    print("\n백테스트 실행 중...\n")
    for name, func in STRATEGIES:
        print(f"  {name} ...", end=" ", flush=True)
        try:
            eq, tr = run_backtest(df, func, fee_rate=FEE)
            m = calc_metrics(eq, df.index, tr)
            results[name] = (eq, tr, m)
            print(f"CAGR={pf(m['cagr'])}  MDD={pf(m['mdd'])}  샤프={m['sharpe']:.2f}")
        except Exception as exc:
            print(f"오류: {exc}")

    # ── 요약 테이블 ───────────────────────────────────
    print(f"\n{SEP}")
    print("  전략별 성과 요약")
    print(SEP)
    print_strategy_table(results, btc_m)

    # ── 시기별 분석 ───────────────────────────────────
    print(f"\n{SEP}")
    print("  시기별 성과 분석")
    print(SEP)
    btc_period = calc_period(bh_equity, df.index)
    print_period_analysis("BTC Buy & Hold:", btc_period)

    for name, (eq, _, m) in results.items():
        pm = calc_period(eq, df.index)
        print_period_analysis(f"{name}:", pm)

    # ── 주간 수익률 분석 (V5) ────────────────────────
    v5_key = "V5: 레짐 감지 + 전략 자동 전환"
    if v5_key in results:
        print(f"\n{SEP}")
        print(f"  주간 +1% 목표 달성 분석 (V5)")
        print(SEP)
        _, _, v5m = results[v5_key]
        print_weekly_analysis(v5m)

    # ── 거래 상세 (V5) ────────────────────────────────
    if v5_key in results:
        _, v5_trades, v5m = results[v5_key]
        if len(v5_trades) > 0:
            print(f"\n  V5 거래 통계:")
            print(f"    총 거래 수      : {v5m['n_trades']:.0f}  ({v5m['trades_per_yr']:.1f}회/년)")
            print(f"    승률            : {pf(v5m['win_rate'])}")
            print(f"    평균 수익 (승)  : {pf(v5m['avg_win'])}")
            print(f"    평균 손실 (패)  : {pf(v5m['avg_loss'])}")
            print(f"    평균 보유 기간  : {v5m['avg_hold']:.1f}일")

            print(f"\n  V5 방향별 거래 분포:")
            for d in ["long", "short"]:
                sub = v5_trades[v5_trades["direction"] == d]
                if len(sub) > 0:
                    wr = (sub["gross_return"] > 0).mean()
                    avg = sub["gross_return"].mean()
                    print(f"    {d:5s}: {len(sub):3d}회, 승률={pf(wr)}, 평균={pf(avg, 2)}")

    # ── BTC 대비 초과 성과 ────────────────────────────
    print(f"\n{SEP}")
    print("  BTC Buy & Hold 대비 초과 성과")
    print(SEP)
    print(f"  {'전략':<38} {'초과 CAGR':>12} {'초과 샤프':>12} {'MDD 개선':>12}")
    print(LINE)
    for name, (_, _, m) in results.items():
        ex_cagr = m["cagr"] - btc_m["cagr"]
        ex_sharpe = m["sharpe"] - btc_m["sharpe"]
        mdd_improve = btc_m["mdd"] - m["mdd"]   # 양수 = 개선
        print(f"  {name:<38} {pf(ex_cagr):>12} {ex_sharpe:>12.2f} {pf(mdd_improve):>12}")

    # ── 주간 +1% 목표 달성 평가 ───────────────────────
    print(f"\n{SEP}")
    print("  주간 +1% 목표 달성 여부 요약")
    print(SEP)
    TARGET_WEEKLY = 0.01
    TARGET_RATIO  = 0.40   # 40% 이상 주에서 +1% 이상이면 달성로 간주
    for name, (_, _, m) in results.items():
        achieved = "✓ 달성" if m["weekly_1pct"] >= TARGET_RATIO else "✗ 미달"
        print(f"  {name:<38} 주간≥+1% = {pf(m['weekly_1pct'])}  [{achieved}]")

    print(f"\n{SEP}")
    print("  완료.")
    print(SEP)


if __name__ == "__main__":
    main()
