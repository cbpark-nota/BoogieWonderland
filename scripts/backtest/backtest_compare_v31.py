"""
V3.0 vs V3.1 알고리즘 비교 백테스트
══════════════════════════════════════════════════════════════
V3.0 (기존):
  - INCLUDE_KR_MARKET = True  (한국 포함)
  - REGIME_FILTER = False     (시장 레짐 필터 없음)
  - VOL_TARGET 미적용
  - ret3m 사용
  - Buy/Hold Spread 없음
  - 시가총액 가중 없음
  - Score = ADX×0.4 + ret3m×0.3 + sector×0.2 + vol_stab×0.1

V3.1 (개선):
  - INCLUDE_KR_MARKET = False (미국만)
  - REGIME_FILTER = True      (SPY MA20 < MA60 → 진입 없음)
  - VOL_TARGET = 0.15         (SPY 실현변동성 기반 포지션 스케일)
  - ret12m_skip1 사용
  - Buy/Hold Spread = 2.5     (Top 25까지 보유 유지)
  - 시가총액 가중 활성화
  - Score = ADX×0.3 + ret3m×0.2 + ret12m×0.2 + sector×0.2 + vol_stab×0.1

유니버스 : S&P500 + NASDAQ-100 (US), KOSPI200 + KOSDAQ150 (KR)
기간     : 2015-01-01 ~ 2026-03-31
리밸런싱 : 격주 금요일 (2W-FRI)
수수료   : 편도 0.1% (왕복 0.2%)
ATR 승수 : 2.5 (균형형 기준)
══════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import logging
import sys
import time
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent))

from data_cache import load_full_universe, SECTOR_ETF

# ── 백테스트 공통 파라미터 ────────────────────────────────────
START         = "2015-01-01"
END           = "2026-03-31"
TOP_N         = 10
ATR_PERIOD    = 14
ATR_MULT      = 2.5
MAX_WEIGHT    = 0.10
COST_PER_SIDE = 0.001   # 편도 0.1%
PERIODS_PY    = 26      # 격주 기준 연간 기간수

# ── V3.0 파라미터 ─────────────────────────────────────────────
V30_ADX_THRESH  = 20
V30_RSI_LO      = 50
V30_RSI_HI      = 77
V30_HH_HL_MIN   = 2
V30_PRICE_52W   = 0.75
V30_WEIGHTS     = dict(adx=0.40, ret3m=0.30, sector=0.20, vol_stab=0.10)
V30_INCLUDE_KR  = True

# ── V3.1 파라미터 ─────────────────────────────────────────────
V31_ADX_THRESH  = 20
V31_RSI_LO      = 50
V31_RSI_HI      = 77
V31_HH_HL_MIN   = 2
V31_PRICE_52W   = 0.75
V31_WEIGHTS     = dict(adx=0.30, ret3m=0.20, ret12m=0.20, sector=0.20, vol_stab=0.10)
V31_INCLUDE_KR  = False
V31_VOL_TARGET  = 0.15
V31_HOLD_SPREAD = 2.5   # 보유 유지 버퍼: TOP_N × 2.5 = 25위까지 유지


# ══════════════════════════════════════════════════════════════
# 지표 계산
# ══════════════════════════════════════════════════════════════
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
    d["MA20"]    = ta.sma(c, 20)
    d["MA50"]    = ta.sma(c, 50)
    d["MA200"]   = ta.sma(c, 200)
    d["RSI"]     = ta.rsi(c, 14)
    adx = ta.adx(h, l, c, 14)
    d["ADX"]     = adx["ADX_14"] if adx is not None and "ADX_14" in adx.columns else np.nan
    d["VolMA20"] = v.rolling(20).mean()
    d["VolMA60"] = v.rolling(60).mean()
    d["High52w"] = h.rolling(252).max()
    atr = ta.atr(h, l, c, length=ATR_PERIOD)
    d["ATR"]     = atr if atr is not None else np.nan
    return d


# ══════════════════════════════════════════════════════════════
# 보조 함수
# ══════════════════════════════════════════════════════════════
def swing_hh_hl(df_win: pd.DataFrame, n=3) -> int:
    highs = df_win["High"].values
    lows  = df_win["Low"].values
    sh = [highs[i] for i in range(n, len(highs)-n) if highs[i] == max(highs[i-n:i+n+1])]
    sl = [lows[i]  for i in range(n, len(lows)-n)  if lows[i]  == min(lows[i-n:i+n+1])]
    hh = sum(sh[i] > sh[i-1] for i in range(1, len(sh)))
    hl = sum(sl[i] > sl[i-1] for i in range(1, len(sl)))
    return min(hh, hl)


def minmax(s: pd.Series) -> pd.Series:
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)


def position_weights_capped(scores: pd.Series, max_w: float) -> pd.Series:
    """점수 비례 + 단일 종목 상한(max_w) 적용."""
    scores = scores.fillna(0)  # NaN 점수는 0으로 처리
    n = len(scores)
    if n == 0:
        return pd.Series(dtype=float)
    total = scores.sum()
    if total <= 0 or pd.isna(total):
        return pd.Series([1.0 / n] * n, index=scores.index)
    w = scores / total
    for _ in range(20):
        if (w <= max_w + 1e-8).all():
            break
        excess = (w - max_w).clip(lower=0).sum()
        w = w.clip(upper=max_w)
        under = w < max_w
        if under.sum() == 0:
            break
        w[under] += excess * w[under] / w[under].sum()
    return w / w.sum()


def spy_vol_scale(spy_close: pd.Series, as_of, vol_target: float) -> float:
    """SPY 20일 실현변동성 기반 포지션 스케일 팩터 (0~1)."""
    hist = spy_close[spy_close.index <= as_of]
    ret  = hist.pct_change().dropna()
    if len(ret) < 20:
        return 1.0
    vol = float(ret.tail(20).std() * np.sqrt(252))
    if vol <= 0:
        return 1.0
    return min(vol_target / vol, 1.0)


def regime_ok_v31(spy_close: pd.Series, as_of) -> bool:
    """
    V3.1 레짐 필터:
    SPY MA20 >= MA60 → 진입 허용 (True)
    SPY MA20 < MA60  → 진입 차단 (False)
    """
    hist = spy_close[spy_close.index <= as_of]
    if len(hist) < 60:
        return True
    ma20 = float(hist.rolling(20).mean().iloc[-1])
    ma60 = float(hist.rolling(60).mean().iloc[-1])
    return ma20 >= ma60


def calc_atr_stop(hist: pd.DataFrame) -> float:
    """최근 20일 고점 - ATR × ATR_MULT."""
    atr_s = hist["ATR"].dropna()
    if len(atr_s) == 0:
        return np.nan
    atr_val = float(atr_s.iloc[-1])
    peak20  = float(hist["High"].tail(20).max())
    return peak20 - atr_val * ATR_MULT


# ══════════════════════════════════════════════════════════════
# V3.0 스크리닝
# ══════════════════════════════════════════════════════════════
def screen_v30(df: pd.DataFrame, as_of) -> tuple[bool, dict]:
    hist = df[df.index <= as_of]
    if len(hist) < 220:
        return False, {}
    row = hist.iloc[-1]
    r5, r20, r60, r63 = hist.tail(6), hist.tail(20), hist.tail(60), hist.tail(63)

    adx = row.get("ADX", np.nan)
    if pd.isna(adx) or adx < V30_ADX_THRESH:
        return False, {}

    ma20, ma50, ma200 = row.get("MA20"), row.get("MA50"), row.get("MA200")
    if any(pd.isna(v) for v in [ma20, ma50, ma200]) or not (ma20 > ma50 > ma200):
        return False, {}

    rsi = row.get("RSI", np.nan)
    if pd.isna(rsi) or not (V30_RSI_LO <= rsi <= V30_RSI_HI):
        return False, {}

    vol60 = row.get("VolMA60", np.nan)
    if pd.isna(vol60) or vol60 == 0 or (r20["Volume"] > vol60 * 3.0).any():
        return False, {}

    if (r5["Close"].pct_change().abs() > 0.10).any():
        return False, {}

    if swing_hh_hl(r60) < V30_HH_HL_MIN:
        return False, {}

    high52 = row.get("High52w", np.nan)
    if not pd.isna(high52) and high52 > 0 and row["Close"] < high52 * V30_PRICE_52W:
        return False, {}

    atr_stop = calc_atr_stop(hist)
    cur_px   = float(hist["Close"].iloc[-1])
    if not pd.isna(atr_stop) and cur_px <= atr_stop:
        return False, {}

    ret3m    = float(hist["Close"].iloc[-1] / r63["Close"].iloc[0]) - 1 if len(r63) >= 60 else np.nan
    vol_cv   = r20["Volume"].std() / (vol60 + 1e-9)
    vol_stab = float(1 / (vol_cv + 1e-6))

    return True, {
        "ADX": float(adx), "RSI": float(rsi),
        "ret3m": ret3m, "vol_stab": vol_stab,
        "price": cur_px, "atr_stop": atr_stop,
    }


def rank_v30(passed: dict, etf_data: dict, as_of, sectors: dict) -> pd.DataFrame:
    if not passed:
        return pd.DataFrame()
    df = pd.DataFrame(passed).T
    df["sector"] = [sectors.get(t, "Unknown") for t in df.index]
    df["sec_str"] = 0.0
    for idx, row in df.iterrows():
        sym = SECTOR_ETF.get(row["sector"])
        if sym and sym in etf_data:
            ec = etf_data[sym][etf_data[sym].index <= as_of]["Close"]
            if len(ec) >= 63 and not pd.isna(row.get("ret3m", np.nan)):
                df.loc[idx, "sec_str"] = row["ret3m"] - float(ec.iloc[-1] / ec.iloc[-63] - 1)
    df["sec_n"] = minmax(df["sec_str"])
    df["score"] = (
        minmax(df["ADX"])                     * V30_WEIGHTS["adx"] +
        minmax(df["ret3m"].fillna(0))         * V30_WEIGHTS["ret3m"] +
        minmax(df["sec_n"])                   * V30_WEIGHTS["sector"] +
        minmax(df["vol_stab"])                * V30_WEIGHTS["vol_stab"]
    )
    return df.sort_values("score", ascending=False)


# ══════════════════════════════════════════════════════════════
# V3.1 스크리닝
# ══════════════════════════════════════════════════════════════
def screen_v31(df: pd.DataFrame, as_of) -> tuple[bool, dict]:
    hist = df[df.index <= as_of]
    if len(hist) < 220:
        return False, {}
    row = hist.iloc[-1]
    r5, r20, r60, r63 = hist.tail(6), hist.tail(20), hist.tail(60), hist.tail(63)

    adx = row.get("ADX", np.nan)
    if pd.isna(adx) or adx < V31_ADX_THRESH:
        return False, {}

    ma20, ma50, ma200 = row.get("MA20"), row.get("MA50"), row.get("MA200")
    if any(pd.isna(v) for v in [ma20, ma50, ma200]) or not (ma20 > ma50 > ma200):
        return False, {}

    rsi = row.get("RSI", np.nan)
    if pd.isna(rsi) or not (V31_RSI_LO <= rsi <= V31_RSI_HI):
        return False, {}

    vol60 = row.get("VolMA60", np.nan)
    if pd.isna(vol60) or vol60 == 0 or (r20["Volume"] > vol60 * 3.0).any():
        return False, {}

    if (r5["Close"].pct_change().abs() > 0.10).any():
        return False, {}

    if swing_hh_hl(r60) < V31_HH_HL_MIN:
        return False, {}

    high52 = row.get("High52w", np.nan)
    if not pd.isna(high52) and high52 > 0 and row["Close"] < high52 * V31_PRICE_52W:
        return False, {}

    atr_stop = calc_atr_stop(hist)
    cur_px   = float(hist["Close"].iloc[-1])
    if not pd.isna(atr_stop) and cur_px <= atr_stop:
        return False, {}

    ret3m    = float(hist["Close"].iloc[-1] / r63["Close"].iloc[0]) - 1 if len(r63) >= 60 else np.nan
    vol_cv   = r20["Volume"].std() / (vol60 + 1e-9)
    vol_stab = float(1 / (vol_cv + 1e-6))

    # ret12m_skip1: 252일 수익률, 최근 21일 제외
    n = len(hist)
    if n >= 273:
        ret12m = float(hist["Close"].iloc[-22] / hist["Close"].iloc[-273]) - 1
    elif n >= 252:
        ret12m = float(hist["Close"].iloc[-22] / hist["Close"].iloc[-252]) - 1
    else:
        ret12m = np.nan

    return True, {
        "ADX": float(adx), "RSI": float(rsi),
        "ret3m": ret3m, "ret12m": ret12m, "vol_stab": vol_stab,
        "price": cur_px, "atr_stop": atr_stop,
    }


def rank_v31(passed: dict, etf_data: dict, as_of, sectors: dict,
             mktcaps: dict) -> pd.DataFrame:
    if not passed:
        return pd.DataFrame()
    df = pd.DataFrame(passed).T
    df["sector"] = [sectors.get(t, "Unknown") for t in df.index]
    df["sec_str"] = 0.0
    for idx, row in df.iterrows():
        sym = SECTOR_ETF.get(row["sector"])
        if sym and sym in etf_data:
            ec = etf_data[sym][etf_data[sym].index <= as_of]["Close"]
            if len(ec) >= 63 and not pd.isna(row.get("ret3m", np.nan)):
                df.loc[idx, "sec_str"] = row["ret3m"] - float(ec.iloc[-1] / ec.iloc[-63] - 1)
    df["sec_n"] = minmax(df["sec_str"])
    df["score"] = (
        minmax(df["ADX"])                     * V31_WEIGHTS["adx"] +
        minmax(df["ret3m"].fillna(0))         * V31_WEIGHTS["ret3m"] +
        minmax(df["ret12m"].fillna(0))        * V31_WEIGHTS["ret12m"] +
        minmax(df["sec_n"])                   * V31_WEIGHTS["sector"] +
        minmax(df["vol_stab"])                * V31_WEIGHTS["vol_stab"]
    )
    # 시가총액 가중: score × sqrt(mktcap)
    df["mktcap"] = [mktcaps.get(t, 1.0) for t in df.index]
    df["mktcap_norm"] = minmax(np.sqrt(df["mktcap"]))
    df["score_w"] = df["score"] * (0.5 + 0.5 * df["mktcap_norm"])   # 0.5~1.0 스케일
    return df.sort_values("score_w", ascending=False)


# ══════════════════════════════════════════════════════════════
# 스톱로스 일별 체크
# ══════════════════════════════════════════════════════════════
def check_stops(holdings: dict, all_data: dict, prev_dt, rd) -> dict:
    daily_range = pd.date_range(prev_dt, rd, freq="B")[1:]
    for day in daily_range:
        if not holdings:
            break
        to_remove = []
        for ticker, info in holdings.items():
            df_t = all_data.get(ticker)
            if df_t is None:
                continue
            day_close = df_t[df_t.index <= day]["Close"]
            if len(day_close) == 0:
                continue
            cur_px = float(day_close.iloc[-1])
            info["peak"] = max(info["peak"], cur_px)
            stop = info.get("atr_stop", np.nan)
            if not pd.isna(stop) and cur_px <= stop:
                to_remove.append(ticker)
        for t in to_remove:
            del holdings[t]
    return holdings


def calc_turnover_cost(old_h: dict, new_h: dict) -> float:
    all_t = set(list(old_h.keys()) + list(new_h.keys()))
    total = 0.0
    for t in all_t:
        w_old = old_h.get(t, {}).get("w", 0) or 0
        w_new = new_h.get(t, {}).get("w", 0) or 0
        diff  = abs(w_old - w_new)
        if np.isfinite(diff):
            total += diff
    return total * COST_PER_SIDE


# ══════════════════════════════════════════════════════════════
# 공통 백테스트 루프
# ══════════════════════════════════════════════════════════════
def run_v30(all_data_ind: dict, etf_data: dict, spy_close: pd.Series,
            sectors: dict, us_tickers: set, kr_tickers: set) -> tuple[pd.Series, int]:
    rebal_dates = pd.date_range(start=START, end=END, freq="2W-FRI")
    nav      = 1.0
    holdings = {}
    prev_dt  = None
    trades   = 0
    period_rets = []   # 기간별 수익률 (손익비 계산용)
    nav_list = []
    nav_dates = []
    total = len(rebal_dates)

    for i, rd in enumerate(rebal_dates):
        if (i + 1) % 50 == 0 or i == total - 1:
            logger.info(f"  V3.0: {i+1}/{total} ({(i+1)/total:.0%})")

        if prev_dt and holdings:
            holdings = check_stops(holdings, all_data_ind, prev_dt, rd)

        if prev_dt and holdings:
            ret = 0.0
            for t, info in holdings.items():
                df_t = all_data_ind.get(t)
                if df_t is None:
                    continue
                p0 = df_t[df_t.index <= prev_dt]["Close"]
                p1 = df_t[df_t.index <= rd]["Close"]
                if len(p0) and len(p1):
                    v0, v1 = float(p0.iloc[-1]), float(p1.iloc[-1])
                    if np.isfinite(v0) and np.isfinite(v1) and v0 > 0:
                        ret += info["w"] * (v1 / v0 - 1)
            if np.isfinite(ret):
                nav *= (1 + ret)
                period_rets.append(ret)

        # 유니버스: US + KR (V3.0)
        universe = list(us_tickers | kr_tickers)

        passed = {}
        for t in universe:
            df_t = all_data_ind.get(t)
            if df_t is None:
                continue
            ok, met = screen_v30(df_t, rd)
            if ok:
                passed[t] = met

        ranked = rank_v30(passed, etf_data, rd, sectors)
        top    = ranked.head(TOP_N)
        new_h  = {}
        if len(top) > 0:
            ws = position_weights_capped(top["score"], MAX_WEIGHT)
            for t in top.index:
                df_t  = all_data_ind.get(t)
                entry = float(df_t[df_t.index <= rd]["Close"].iloc[-1]) if df_t is not None else 1.0
                new_h[t] = {
                    "w": float(ws[t]), "entry": entry, "peak": entry,
                    "atr_stop": float(top.loc[t, "atr_stop"]) if "atr_stop" in top.columns else np.nan,
                }

        nav *= (1 - calc_turnover_cost(holdings, new_h))
        trades += len(set(holdings.keys()) ^ set(new_h.keys()))
        holdings = new_h
        prev_dt  = rd
        nav_list.append(nav)
        nav_dates.append(rd)

    return pd.Series(nav_list, index=nav_dates), trades, period_rets


def run_v31(all_data_ind: dict, etf_data: dict, spy_close: pd.Series,
            sectors: dict, us_tickers: set, mktcaps: dict) -> tuple[pd.Series, int]:
    rebal_dates = pd.date_range(start=START, end=END, freq="2W-FRI")
    nav         = 1.0
    holdings    = {}
    prev_dt     = None
    trades      = 0
    period_rets = []
    nav_list  = []
    nav_dates = []
    total = len(rebal_dates)

    for i, rd in enumerate(rebal_dates):
        if (i + 1) % 50 == 0 or i == total - 1:
            logger.info(f"  V3.1: {i+1}/{total} ({(i+1)/total:.0%})")

        if prev_dt and holdings:
            holdings = check_stops(holdings, all_data_ind, prev_dt, rd)

        if prev_dt and holdings:
            ret = 0.0
            for t, info in holdings.items():
                df_t = all_data_ind.get(t)
                if df_t is None:
                    continue
                p0 = df_t[df_t.index <= prev_dt]["Close"]
                p1 = df_t[df_t.index <= rd]["Close"]
                if len(p0) and len(p1):
                    v0, v1 = float(p0.iloc[-1]), float(p1.iloc[-1])
                    if np.isfinite(v0) and np.isfinite(v1) and v0 > 0:
                        ret += info["w"] * (v1 / v0 - 1)
            if np.isfinite(ret):
                nav *= (1 + ret)
                period_rets.append(ret)

        # 레짐 필터 (V3.1)
        if not regime_ok_v31(spy_close, rd):
            # 레짐 불량 → 기존 보유 유지, 신규 진입 차단
            prev_dt = rd
            nav_list.append(nav)
            nav_dates.append(rd)
            continue

        # 변동성 스케일 (V3.1)
        vol_scale = spy_vol_scale(spy_close, rd, V31_VOL_TARGET)

        # 유니버스: US only (V3.1)
        universe = list(us_tickers)

        passed = {}
        for t in universe:
            df_t = all_data_ind.get(t)
            if df_t is None:
                continue
            ok, met = screen_v31(df_t, rd)
            if ok:
                passed[t] = met

        ranked = rank_v31(passed, etf_data, rd, sectors, mktcaps)

        # Buy/Hold Spread: Top N×2.5 내 기존 보유 유지
        hold_limit = int(TOP_N * V31_HOLD_SPREAD)
        top_pool   = ranked.head(hold_limit)
        pool_set   = set(top_pool.index)

        # 신규 매수 후보: Top N 내 미보유 종목
        existing_held = set(holdings.keys()) & pool_set
        new_entries   = [t for t in ranked.index if t not in holdings][:TOP_N]

        # 최종 포트폴리오: 기존 보유(pool 내) + 신규 진입 (합쳐서 TOP_N)
        final_tickers = list(existing_held) + [t for t in new_entries if t not in existing_held]
        final_tickers = final_tickers[:TOP_N]

        if len(final_tickers) == 0:
            new_h = {}
        else:
            scores_final = ranked.loc[
                [t for t in final_tickers if t in ranked.index], "score_w"
            ].dropna()
            if len(scores_final) == 0:
                new_h = {}
            else:
                ws = position_weights_capped(scores_final, MAX_WEIGHT)
                # 변동성 스케일 적용: 포지션 전체 축소
                ws = ws * vol_scale
                new_h = {}
                for t in scores_final.index:
                    df_t  = all_data_ind.get(t)
                    if df_t is None:
                        continue
                    entry = float(df_t[df_t.index <= rd]["Close"].iloc[-1])
                    stop  = float(ranked.loc[t, "atr_stop"]) if t in ranked.index and "atr_stop" in ranked.columns else np.nan
                    new_h[t] = {
                        "w": float(ws[t]), "entry": entry, "peak": entry,
                        "atr_stop": stop,
                    }

        nav *= (1 - calc_turnover_cost(holdings, new_h))
        trades += len(set(holdings.keys()) ^ set(new_h.keys()))
        holdings = new_h
        prev_dt  = rd
        nav_list.append(nav)
        nav_dates.append(rd)

    return pd.Series(nav_list, index=nav_dates), trades, period_rets


# ══════════════════════════════════════════════════════════════
# 성과 지표 계산
# ══════════════════════════════════════════════════════════════
def calc_metrics(nav: pd.Series, period_rets: list, trades: int, label: str) -> dict:
    ret   = nav.pct_change().dropna()
    n     = len(ret)
    years = n / PERIODS_PY
    cagr  = (nav.iloc[-1] ** (1 / max(years, 0.1))) - 1 if nav.iloc[-1] > 0 else -1.0
    dd    = (nav - nav.cummax()) / nav.cummax()
    mdd   = float(dd.min())
    sharpe = float((ret.mean() / (ret.std() + 1e-9)) * np.sqrt(PERIODS_PY))
    win    = float((ret > 0).mean())

    # 손익비 (Profit Factor)
    pos_rets = [r for r in period_rets if r > 0]
    neg_rets = [r for r in period_rets if r < 0]
    profit_factor = (sum(pos_rets) / abs(sum(neg_rets) + 1e-9)) if neg_rets else float("inf")

    return {
        "label"   : label,
        "CAGR"    : cagr,
        "총수익"  : float(nav.iloc[-1]) - 1,
        "MDD"     : mdd,
        "샤프"    : sharpe,
        "승률"    : win,
        "손익비"  : profit_factor,
        "거래횟수": trades,
        "nav"     : nav,
    }


def calc_spy_metrics(spy_close: pd.Series) -> dict:
    spy = spy_close[(spy_close.index >= START) & (spy_close.index <= END)]
    if len(spy) == 0:
        return {}
    nav   = spy / float(spy.iloc[0])
    ret   = nav.pct_change().dropna()
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr  = (float(nav.iloc[-1]) ** (1 / max(years, 0.1))) - 1
    dd    = (nav - nav.cummax()) / nav.cummax()
    mdd   = float(dd.min())
    sharpe_daily = float((ret.mean() / (ret.std() + 1e-9)) * np.sqrt(252))
    win   = float((ret > 0).mean())
    pos_r = ret[ret > 0].sum()
    neg_r = ret[ret < 0].abs().sum()
    pf    = float(pos_r / (neg_r + 1e-9)) if neg_r > 0 else float("inf")
    return {
        "label"   : "SPY (Buy&Hold)",
        "CAGR"    : cagr,
        "총수익"  : float(nav.iloc[-1]) - 1,
        "MDD"     : mdd,
        "샤프"    : sharpe_daily,
        "승률"    : win,
        "손익비"  : pf,
        "거래횟수": 0,
    }


# ══════════════════════════════════════════════════════════════
# 간이 시가총액 추정 (현재 시점 yfinance fast_info 사용)
# ══════════════════════════════════════════════════════════════
def fetch_mktcaps_fast(us_tickers: list) -> dict:
    """US 종목 시가총액을 yfinance fast_info로 일괄 수집 (V3.1용)."""
    import yfinance as yf
    caps = {}
    logger.info(f"  시가총액 수집: {len(us_tickers)}개...")
    for i, t in enumerate(us_tickers):
        if (i + 1) % 100 == 0:
            logger.info(f"    {i+1}/{len(us_tickers)}")
        try:
            mc = yf.Ticker(t).fast_info.market_cap
            caps[t] = float(mc) if mc and mc > 0 else 1.0
        except Exception:
            caps[t] = 1.0
    logger.info(f"  시가총액 수집 완료: {sum(1 for v in caps.values() if v > 1.0)}/{len(us_tickers)}개")
    return caps


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    t0 = time.time()
    print("=" * 68)
    print("  V3.0 vs V3.1 모멘텀 알고리즘 비교 백테스트")
    print(f"  기간: {START} ~ {END}  |  격주 리밸런싱  |  거래비용 편도 {COST_PER_SIDE:.1%}")
    print("=" * 68)

    # ── 데이터 로드 ──
    print("\n[1/5] 데이터 로드 중...")
    all_data, spy_df, etf_data_raw, universe_map = load_full_universe("2015-01-01")
    spy_close = spy_df["Close"].squeeze()
    print(f"  종목 {len(all_data)}개, SPY {len(spy_df)}행, ETF {len(etf_data_raw)}개 로드 완료")

    # 유니버스 분류
    us_tickers = {t for t in all_data if not (t.endswith(".KS") or t.endswith(".KQ"))}
    kr_tickers = {t for t in all_data if t.endswith(".KS") or t.endswith(".KQ")}
    print(f"  US {len(us_tickers)}개 / KR {len(kr_tickers)}개")

    # ── 지표 계산 ──
    print(f"\n[2/5] 지표 계산 중... ({len(all_data)}개)")
    t_ind = time.time()
    all_data_ind = {}
    for i, (t, df) in enumerate(all_data.items()):
        if (i + 1) % 100 == 0:
            print(f"\r  {i+1}/{len(all_data)}", end="", flush=True)
        all_data_ind[t] = add_indicators(df)
    etf_data = {t: add_indicators(df) for t, df in etf_data_raw.items()}
    print(f"\r  {len(all_data_ind)}개 완료 ({time.time()-t_ind:.0f}초)")

    # ── 시가총액 수집 (V3.1) ──
    print(f"\n[3/5] 시가총액 수집 (V3.1용)...")
    mktcaps = fetch_mktcaps_fast(list(us_tickers))

    # ── V3.0 백테스트 ──
    print(f"\n[4/5] V3.0 백테스트 실행 중...")
    t_v30 = time.time()
    nav_v30, trades_v30, prets_v30 = run_v30(
        all_data_ind, etf_data, spy_close, universe_map, us_tickers, kr_tickers
    )
    print(f"  완료 ({time.time()-t_v30:.0f}초)")

    # ── V3.1 백테스트 ──
    print(f"\n[5/5] V3.1 백테스트 실행 중...")
    t_v31 = time.time()
    nav_v31, trades_v31, prets_v31 = run_v31(
        all_data_ind, etf_data, spy_close, universe_map, us_tickers, mktcaps
    )
    print(f"  완료 ({time.time()-t_v31:.0f}초)")

    # ── 결과 계산 ──
    m30  = calc_metrics(nav_v30, prets_v30, trades_v30, "V3.0 (기존)")
    m31  = calc_metrics(nav_v31, prets_v31, trades_v31, "V3.1 (개선)")
    mspy = calc_spy_metrics(spy_close)

    # ── 결과 출력 ──
    total_time = time.time() - t0
    print(f"\n총 소요 시간: {total_time:.0f}초 ({total_time/60:.1f}분)")
    print("\n" + "=" * 68)
    print("  알고리즘 비교 결과")
    print("=" * 68)

    header = f"  {'항목':<14}  {'V3.0 (기존)':>14}  {'V3.1 (개선)':>14}  {'SPY':>12}"
    print(header)
    print("  " + "─" * 64)

    rows = [
        ("CAGR",    f"{m30['CAGR']:>+13.1%}",  f"{m31['CAGR']:>+13.1%}",  f"{mspy['CAGR']:>+11.1%}"),
        ("총수익률", f"{m30['총수익']:>+13.0%}", f"{m31['총수익']:>+13.0%}", f"{mspy['총수익']:>+11.0%}"),
        ("MDD",     f"{m30['MDD']:>+13.1%}",   f"{m31['MDD']:>+13.1%}",   f"{mspy['MDD']:>+11.1%}"),
        ("Sharpe",  f"{m30['샤프']:>13.2f}",   f"{m31['샤프']:>13.2f}",   f"{mspy['샤프']:>11.2f}"),
        ("승률",    f"{m30['승률']:>13.1%}",   f"{m31['승률']:>13.1%}",   f"{mspy['승률']:>11.1%}"),
        ("손익비",  f"{m30['손익비']:>13.2f}",  f"{m31['손익비']:>13.2f}",  f"{mspy['손익비']:>11.2f}"),
        ("거래횟수", f"{m30['거래횟수']:>13,}",  f"{m31['거래횟수']:>13,}",  f"{'N/A':>11}"),
    ]
    for name, v30, v31, spy in rows:
        print(f"  {name:<14}  {v30}  {v31}  {spy}")

    print("=" * 68)

    # ── 변경 항목 요약 ──
    print("\n[V3.0 → V3.1 주요 변경 사항]")
    changes = [
        ("한국 시장", "포함 (US+KR)",           "제외 (US only)"),
        ("레짐 필터", "없음",                    "SPY MA20≥MA60 정배열만 진입"),
        ("변동성 조절", "없음",                  f"VOL_TARGET={V31_VOL_TARGET} (SPY 20일 변동성)"),
        ("모멘텀 지표", "ret3m (3개월)",         "ret12m_skip1 (12개월, 최근 1개월 제외)"),
        ("Buy/Hold Spread", "없음 (매번 Top10)", f"Top {int(TOP_N*V31_HOLD_SPREAD)}까지 보유 유지"),
        ("시가총액 가중", "없음",                 "score × sqrt(mktcap) 적용"),
        ("스코어 가중치", "ADX×0.4 ret3m×0.3",  "ADX×0.3 ret3m×0.2 ret12m×0.2"),
    ]
    for item, v30_val, v31_val in changes:
        print(f"  {item:<18}: {v30_val:<28} → {v31_val}")

    # ── CSV 저장 ──
    RESULTS_DIR = Path(__file__).parent / "results"
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    csv_path  = RESULTS_DIR / f"compare_v31_{timestamp}.csv"
    rows_data = []
    for m, tag in [(m30, "V3.0"), (m31, "V3.1"), (mspy, "SPY")]:
        rows_data.append({
            "알고리즘": m["label"],
            "CAGR": f"{m['CAGR']:+.1%}",
            "총수익률": f"{m['총수익']:+.0%}",
            "MDD": f"{m['MDD']:+.1%}",
            "Sharpe": f"{m['샤프']:.2f}",
            "승률": f"{m['승률']:.1%}",
            "손익비": f"{m['손익비']:.2f}",
            "거래횟수": m.get("거래횟수", "N/A"),
        })
    pd.DataFrame(rows_data).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n결과 저장: {csv_path}")
