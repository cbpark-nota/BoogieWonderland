"""
V3.2 고정 스톱 vs 트레일링 스톱 비교 백테스트
══════════════════════════════════════════════════════════════
공통 기반: V3.1/V3.2 알고리즘 (US only, 격주 리밸런싱, ATR×2.5)

[고정 스톱 - V3.2 기존]
  - 진입 시 스톱가 = 최근 20일 고점 - ATR(14) × 2.5 로 고정
  - 이후 보유 중 스톱가 업데이트 없음

[트레일링 스톱 - V3.2 Trailing]
  - 진입 시 동일: 스톱가 = 최근 20일 고점 - ATR(14) × 2.5
  - 보유 중 매일: new_peak = max(기존 peak, 오늘 고가)
                  new_stop = new_peak - ATR(14) × 2.5
                  스톱가 = max(기존 스톱가, new_stop)  ← 스톱가는 오르기만 함

유니버스 : S&P500 + NASDAQ-100 (US only, ~517종목)
기간     : 2015-01-01 ~ 2026-03-31
리밸런싱 : 격주 금요일 (2W-FRI)
수수료   : 편도 0.1% (왕복 0.2%)
ATR 승수 : 2.5 (보수적 기준)
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

# ── V3.2 파라미터 ─────────────────────────────────────────────
ADX_THRESH  = 20
RSI_LO      = 50
RSI_HI      = 77
HH_HL_MIN   = 2
PRICE_52W   = 0.75
WEIGHTS     = dict(adx=0.35, ret12m=0.30, sector=0.20, vol_stab=0.15)
VOL_TARGET  = 0.15
HOLD_SPREAD = 2.5   # 보유 유지 버퍼: TOP_N × 2.5 = 25위까지 유지


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
    scores = scores.fillna(0)
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
    hist = spy_close[spy_close.index <= as_of]
    ret  = hist.pct_change().dropna()
    if len(ret) < 20:
        return 1.0
    vol = float(ret.tail(20).std() * np.sqrt(252))
    if vol <= 0:
        return 1.0
    return min(vol_target / vol, 1.0)


def regime_ok(spy_close: pd.Series, as_of) -> bool:
    hist = spy_close[spy_close.index <= as_of]
    if len(hist) < 60:
        return True
    ma20 = float(hist.rolling(20).mean().iloc[-1])
    ma60 = float(hist.rolling(60).mean().iloc[-1])
    return ma20 >= ma60


def calc_atr_stop(hist: pd.DataFrame) -> float:
    atr_s = hist["ATR"].dropna()
    if len(atr_s) == 0:
        return np.nan
    atr_val = float(atr_s.iloc[-1])
    peak20  = float(hist["High"].tail(20).max())
    return peak20 - atr_val * ATR_MULT


# ══════════════════════════════════════════════════════════════
# V3.2 스크리닝
# ══════════════════════════════════════════════════════════════
def screen_v32(df: pd.DataFrame, as_of) -> tuple[bool, dict]:
    hist = df[df.index <= as_of]
    if len(hist) < 220:
        return False, {}
    row = hist.iloc[-1]
    r5, r20, r60, r63 = hist.tail(6), hist.tail(20), hist.tail(60), hist.tail(63)

    adx = row.get("ADX", np.nan)
    if pd.isna(adx) or adx < ADX_THRESH:
        return False, {}

    ma20, ma50, ma200 = row.get("MA20"), row.get("MA50"), row.get("MA200")
    if any(pd.isna(v) for v in [ma20, ma50, ma200]) or not (ma20 > ma50 > ma200):
        return False, {}

    rsi = row.get("RSI", np.nan)
    if pd.isna(rsi) or not (RSI_LO <= rsi <= RSI_HI):
        return False, {}

    vol60 = row.get("VolMA60", np.nan)
    if pd.isna(vol60) or vol60 == 0 or (r20["Volume"] > vol60 * 3.0).any():
        return False, {}

    if (r5["Close"].pct_change().abs() > 0.10).any():
        return False, {}

    if swing_hh_hl(r60) < HH_HL_MIN:
        return False, {}

    high52 = row.get("High52w", np.nan)
    if not pd.isna(high52) and high52 > 0 and row["Close"] < high52 * PRICE_52W:
        return False, {}

    atr_stop = calc_atr_stop(hist)
    cur_px   = float(hist["Close"].iloc[-1])
    if not pd.isna(atr_stop) and cur_px <= atr_stop:
        return False, {}

    ret3m  = float(hist["Close"].iloc[-1] / r63["Close"].iloc[0]) - 1 if len(r63) >= 60 else np.nan
    vol_cv   = r20["Volume"].std() / (vol60 + 1e-9)
    vol_stab = float(1 / (vol_cv + 1e-6))

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
        "high20": float(r20["High"].max()),
    }


def rank_v32(passed: dict, etf_data: dict, as_of, sectors: dict,
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
        minmax(df["ADX"])                   * WEIGHTS["adx"] +
        minmax(df["ret12m"].fillna(0))      * WEIGHTS["ret12m"] +
        minmax(df["sec_n"])                 * WEIGHTS["sector"] +
        minmax(df["vol_stab"])              * WEIGHTS["vol_stab"]
    )
    df["mktcap"] = [mktcaps.get(t, 1.0) for t in df.index]
    df["mktcap_norm"] = minmax(np.sqrt(df["mktcap"]))
    df["score_w"] = df["score"] * (0.5 + 0.5 * df["mktcap_norm"])
    return df.sort_values("score_w", ascending=False)


# ══════════════════════════════════════════════════════════════
# 스톱로스 일별 체크 (고정 스톱)
# ══════════════════════════════════════════════════════════════
def check_stops_fixed(holdings: dict, all_data: dict, prev_dt, rd) -> tuple[dict, int]:
    """고정 스톱: 진입 시 계산한 atr_stop을 그대로 사용."""
    daily_range = pd.date_range(prev_dt, rd, freq="B")[1:]
    stop_count = 0
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
            # peak 업데이트 (고정 스톱이지만 peak는 기록)
            info["peak"] = max(info["peak"], cur_px)
            stop = info.get("atr_stop", np.nan)
            if not pd.isna(stop) and cur_px <= stop:
                to_remove.append(ticker)
        for t in to_remove:
            del holdings[t]
            stop_count += 1
    return holdings, stop_count


# ══════════════════════════════════════════════════════════════
# 스톱로스 일별 체크 (트레일링 스톱)
# ══════════════════════════════════════════════════════════════
def check_stops_trailing(holdings: dict, all_data: dict, prev_dt, rd) -> tuple[dict, int]:
    """트레일링 스톱: 고점 갱신 시 스톱가도 올라감."""
    daily_range = pd.date_range(prev_dt, rd, freq="B")[1:]
    stop_count = 0
    for day in daily_range:
        if not holdings:
            break
        to_remove = []
        for ticker, info in holdings.items():
            df_t = all_data.get(ticker)
            if df_t is None:
                continue
            day_data = df_t[df_t.index <= day]
            if len(day_data) == 0:
                continue
            day_row = day_data.iloc[-1]
            cur_px  = float(day_row["Close"])
            day_high = float(day_row["High"])
            # ATR 값 (최신)
            atr_val = day_row.get("ATR", np.nan)
            if pd.isna(atr_val):
                atr_s = day_data["ATR"].dropna()
                atr_val = float(atr_s.iloc[-1]) if len(atr_s) > 0 else np.nan

            # 고점 갱신
            new_peak = max(info["peak"], day_high)
            info["peak"] = new_peak

            # 스톱가 갱신 (올라가기만 함)
            if not pd.isna(atr_val) and atr_val > 0:
                new_stop = new_peak - atr_val * ATR_MULT
                old_stop = info.get("atr_stop", np.nan)
                if pd.isna(old_stop):
                    info["atr_stop"] = new_stop
                else:
                    info["atr_stop"] = max(old_stop, new_stop)

            stop = info.get("atr_stop", np.nan)
            if not pd.isna(stop) and cur_px <= stop:
                to_remove.append(ticker)

        for t in to_remove:
            del holdings[t]
            stop_count += 1

    return holdings, stop_count


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
def run_backtest(
    all_data_ind: dict,
    etf_data: dict,
    spy_close: pd.Series,
    sectors: dict,
    us_tickers: set,
    mktcaps: dict,
    use_trailing: bool,
    label: str,
) -> tuple[pd.Series, int, list, int, list]:
    """
    Returns: (nav_series, total_trades, period_rets, stop_exits, holding_days_list)
    """
    check_stops_fn = check_stops_trailing if use_trailing else check_stops_fixed

    rebal_dates = pd.date_range(start=START, end=END, freq="2W-FRI")
    nav         = 1.0
    holdings    = {}   # {ticker: {w, entry, peak, atr_stop, entry_date}}
    prev_dt     = None
    trades      = 0
    period_rets = []
    nav_list    = []
    nav_dates   = []
    stop_exits  = 0
    holding_days = []
    total = len(rebal_dates)

    for i, rd in enumerate(rebal_dates):
        if (i + 1) % 50 == 0 or i == total - 1:
            logger.debug(f"  {label}: {i+1}/{total} ({(i+1)/total:.0%})")

        # ── 스톱 체크 ──
        if prev_dt and holdings:
            holdings_before = set(holdings.keys())
            holdings, n_stops = check_stops_fn(holdings, all_data_ind, prev_dt, rd)
            stop_exits += n_stops
            # 스톱으로 청산된 종목 보유 기간 기록
            stopped = holdings_before - set(holdings.keys())
            for t in stopped:
                entry_dt = holdings.get(t, {}).get("entry_date") if t in holdings else None
                # holdings에서 이미 삭제됐으므로 기록 불가 → 리밸런싱 로직에서 처리

        # ── 수익 계산 ──
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

        # ── 레짐 필터 ──
        if not regime_ok(spy_close, rd):
            prev_dt = rd
            nav_list.append(nav)
            nav_dates.append(rd)
            continue

        # ── 변동성 스케일 ──
        vol_scale = spy_vol_scale(spy_close, rd, VOL_TARGET)

        # ── 스크리닝 ──
        passed = {}
        for t in us_tickers:
            df_t = all_data_ind.get(t)
            if df_t is None:
                continue
            ok, met = screen_v32(df_t, rd)
            if ok:
                passed[t] = met

        ranked = rank_v32(passed, etf_data, rd, sectors, mktcaps)

        # ── Buy/Hold Spread ──
        hold_limit   = int(TOP_N * HOLD_SPREAD)
        top_pool     = ranked.head(hold_limit)
        pool_set     = set(top_pool.index)
        existing_held = set(holdings.keys()) & pool_set
        new_entries   = [t for t in ranked.index if t not in holdings][:TOP_N]
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
                ws = ws * vol_scale
                new_h = {}
                for t in scores_final.index:
                    df_t = all_data_ind.get(t)
                    if df_t is None:
                        continue
                    entry  = float(df_t[df_t.index <= rd]["Close"].iloc[-1])
                    stop   = float(ranked.loc[t, "atr_stop"]) if t in ranked.index and "atr_stop" in ranked.columns else np.nan
                    high20 = float(ranked.loc[t, "high20"]) if t in ranked.index and "high20" in ranked.columns else entry
                    new_h[t] = {
                        "w": float(ws[t]), "entry": entry,
                        "peak": high20,      # 트레일링: 초기 peak = 진입 시 20일 고점
                        "atr_stop": stop,
                        "entry_date": rd,
                    }

        # 청산된 종목 보유 기간 기록
        exited = set(holdings.keys()) - set(new_h.keys())
        for t in exited:
            info = holdings[t]
            entry_dt = info.get("entry_date")
            if entry_dt is not None:
                days = (rd - entry_dt).days
                holding_days.append(days)

        nav *= (1 - calc_turnover_cost(holdings, new_h))
        trades += len(set(holdings.keys()) ^ set(new_h.keys()))
        holdings = new_h
        prev_dt  = rd
        nav_list.append(nav)
        nav_dates.append(rd)

    return pd.Series(nav_list, index=nav_dates), trades, period_rets, stop_exits, holding_days


# ══════════════════════════════════════════════════════════════
# 성과 지표 계산
# ══════════════════════════════════════════════════════════════
def calc_metrics(
    nav: pd.Series,
    period_rets: list,
    trades: int,
    stop_exits: int,
    holding_days: list,
    label: str,
) -> dict:
    ret   = nav.pct_change().dropna()
    n     = len(ret)
    years = n / PERIODS_PY
    cagr  = (nav.iloc[-1] ** (1 / max(years, 0.1))) - 1 if nav.iloc[-1] > 0 else -1.0
    dd    = (nav - nav.cummax()) / nav.cummax()
    mdd   = float(dd.min())
    sharpe = float((ret.mean() / (ret.std() + 1e-9)) * np.sqrt(PERIODS_PY))
    win    = float((ret > 0).mean())

    pos_rets = [r for r in period_rets if r > 0]
    neg_rets = [r for r in period_rets if r < 0]
    profit_factor = (sum(pos_rets) / abs(sum(neg_rets) + 1e-9)) if neg_rets else float("inf")

    avg_hold = float(np.mean(holding_days)) if holding_days else 0.0

    return {
        "label"     : label,
        "CAGR"      : cagr,
        "총수익"    : float(nav.iloc[-1]) - 1,
        "MDD"       : mdd,
        "샤프"      : sharpe,
        "승률"      : win,
        "손익비"    : profit_factor,
        "거래횟수"  : trades,
        "스톱청산"  : stop_exits,
        "평균보유일": avg_hold,
        "nav"       : nav,
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
        "label"     : "SPY (Buy&Hold)",
        "CAGR"      : cagr,
        "총수익"    : float(nav.iloc[-1]) - 1,
        "MDD"       : mdd,
        "샤프"      : sharpe_daily,
        "승률"      : win,
        "손익비"    : pf,
        "거래횟수"  : 0,
        "스톱청산"  : 0,
        "평균보유일": 0,
    }


def fetch_mktcaps_fast(us_tickers: list) -> dict:
    import yfinance as yf
    caps = {}
    for t in us_tickers:
        try:
            mc = yf.Ticker(t).fast_info.market_cap
            caps[t] = float(mc) if mc and mc > 0 else 1.0
        except Exception:
            caps[t] = 1.0
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
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    t0 = time.time()

    # ── 데이터 로드 ──
    all_data, spy_df, etf_data_raw, universe_map = load_full_universe("2015-01-01")
    spy_close = spy_df["Close"].squeeze()

    us_tickers = {t for t in all_data if not (t.endswith(".KS") or t.endswith(".KQ"))}

    # ── 지표 계산 ──
    all_data_ind = {}
    for t, df in all_data.items():
        all_data_ind[t] = add_indicators(df)
    etf_data = {t: add_indicators(df) for t, df in etf_data_raw.items()}

    # ── 시가총액 수집 ──
    mktcaps = fetch_mktcaps_fast(list(us_tickers))

    # ── 고정 스톱 백테스트 ──
    nav_fixed, trades_fixed, prets_fixed, stops_fixed, hdays_fixed = run_backtest(
        all_data_ind, etf_data, spy_close, universe_map, us_tickers, mktcaps,
        use_trailing=False, label="V3.2 고정스톱",
    )

    # ── 트레일링 스톱 백테스트 ──
    nav_trail, trades_trail, prets_trail, stops_trail, hdays_trail = run_backtest(
        all_data_ind, etf_data, spy_close, universe_map, us_tickers, mktcaps,
        use_trailing=True, label="V3.2 트레일링",
    )

    # ── 성과 계산 ──
    m_fixed = calc_metrics(nav_fixed, prets_fixed, trades_fixed, stops_fixed, hdays_fixed, "V3.2 고정 스톱")
    m_trail = calc_metrics(nav_trail, prets_trail, trades_trail, stops_trail, hdays_trail, "V3.2 트레일링 스톱")
    m_spy   = calc_spy_metrics(spy_close)

    total_time = time.time() - t0

    # ── 결과 출력 ──
    print("\n" + "=" * 72)
    print("  V3.2 고정 스톱 vs 트레일링 스톱 비교")
    print(f"  기간: {START} ~ {END}  |  격주 리밸런싱  |  거래비용 편도 {COST_PER_SIDE:.1%}")
    print("=" * 72)

    header = f"  {'항목':<16}  {'V3.2 고정스톱':>14}  {'V3.2 트레일링':>14}  {'SPY':>10}"
    print(header)
    print("  " + "─" * 60)

    rows = [
        ("CAGR",       f"{m_fixed['CAGR']:>+13.1%}",      f"{m_trail['CAGR']:>+13.1%}",      f"{m_spy['CAGR']:>+9.1%}"),
        ("총수익률",   f"{m_fixed['총수익']:>+13.0%}",     f"{m_trail['총수익']:>+13.0%}",     f"{m_spy['총수익']:>+9.0%}"),
        ("MDD",        f"{m_fixed['MDD']:>+13.1%}",        f"{m_trail['MDD']:>+13.1%}",        f"{m_spy['MDD']:>+9.1%}"),
        ("Sharpe",     f"{m_fixed['샤프']:>13.2f}",        f"{m_trail['샤프']:>13.2f}",        f"{m_spy['샤프']:>9.2f}"),
        ("승률",       f"{m_fixed['승률']:>13.1%}",        f"{m_trail['승률']:>13.1%}",        f"{m_spy['승률']:>9.1%}"),
        ("손익비",     f"{m_fixed['손익비']:>13.2f}",      f"{m_trail['손익비']:>13.2f}",      f"{m_spy['손익비']:>9.2f}"),
        ("거래횟수",   f"{m_fixed['거래횟수']:>13,}",      f"{m_trail['거래횟수']:>13,}",      f"{'N/A':>9}"),
        ("스톱청산",   f"{m_fixed['스톱청산']:>13,}",      f"{m_trail['스톱청산']:>13,}",      f"{'N/A':>9}"),
        ("평균보유일", f"{m_fixed['평균보유일']:>13.1f}",  f"{m_trail['평균보유일']:>13.1f}",  f"{'N/A':>9}"),
    ]
    for name, vf, vt, spy in rows:
        print(f"  {name:<16}  {vf}  {vt}  {spy}")

    print("=" * 72)
    print(f"\n총 소요 시간: {total_time:.0f}초 ({total_time/60:.1f}분)")

    # ── CSV 저장 ──
    RESULTS_DIR = Path(__file__).parent / "results"
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    csv_path  = RESULTS_DIR / f"trailing_stop_{timestamp}.csv"
    rows_data = []
    for m in [m_fixed, m_trail, m_spy]:
        rows_data.append({
            "전략"      : m["label"],
            "CAGR"      : f"{m['CAGR']:+.1%}",
            "총수익률"  : f"{m['총수익']:+.0%}",
            "MDD"       : f"{m['MDD']:+.1%}",
            "Sharpe"    : f"{m['샤프']:.2f}",
            "승률"      : f"{m['승률']:.1%}",
            "손익비"    : f"{m['손익비']:.2f}",
            "거래횟수"  : m.get("거래횟수", "N/A"),
            "스톱청산"  : m.get("스톱청산", "N/A"),
            "평균보유일": f"{m.get('평균보유일', 0):.1f}",
        })
    pd.DataFrame(rows_data).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"결과 저장: {csv_path}")
