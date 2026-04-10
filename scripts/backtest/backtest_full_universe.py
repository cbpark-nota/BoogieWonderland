"""
풀 유니버스 백테스트 — 시가총액 기반 동적 유니버스
══════════════════════════════════════════════════════════════════
유니버스:
  US: S&P500 전체 (~503개)
  KR: KOSPI 시총 상위 200 + KOSDAQ 시총 상위 150

매 리밸런싱 시점마다:
  현재 발행주식수 × 해당 시점 가격 = 근사 시가총액
  → 시총 순위로 유니버스 재구성 후 스크리닝

4전략: 공격적 / 균형형 / 보수적 / 적응형
══════════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import io
import json
import logging
import os
import sys
import time

import numpy as np
import pandas as pd
import pandas_ta as ta
import requests
import yfinance as yf
import matplotlib
matplotlib.use("Agg")

logger = logging.getLogger(__name__)
import matplotlib.pyplot as plt
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "full_universe"

sys.path.insert(0, str(Path(__file__).parent.parent))
from data_cache import fetch_sp500_tickers

# 백테스트 기간 (윈도우별로 덮어씀)
START = "2015-01-01"
END   = "2024-12-31"

TOP_N         = 10
ATR_PERIOD    = 14
MAX_WEIGHT    = 0.20
COST_PER_SIDE = 0.001
WEIGHTS       = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)

# 시총 필터
US_TOP_N   = 500  # S&P500 전체
KR_KOSPI_N = 200
KR_KOSDAQ_N = 150

# 전략 프리셋
PRESETS = {
    "aggressive":   {"atr_mult": 2.0, "freq": "W",  "label": "공격적"},
    "balanced":     {"atr_mult": 2.5, "freq": "2W", "label": "균형형"},
    "conservative": {"atr_mult": 3.5, "freq": "M",  "label": "보수적"},
}
GAP_STRONG_BULL = 0.05

# 섹터 ETF (미국 종목의 섹터 매핑용)
SECTOR_ETF = {
    "Information Technology":"XLK", "Health Care":"XLV", "Financials":"XLF",
    "Consumer Discretionary":"XLY", "Industrials":"XLI", "Energy":"XLE",
    "Materials":"XLB", "Communication Services":"XLC", "Consumer Staples":"XLP",
    "Utilities":"XLU", "Real Estate":"XLRE",
    # 한국 종목용 (간이 매핑)
    "Technology":"XLK", "Consumer Disc":"XLY",
}


# ══════════════════════════════════════════════════════════════════
# STEP 1: 유니버스 구축 및 데이터 다운로드
# ══════════════════════════════════════════════════════════════════

def fetch_kr_tickers():
    """KRX에서 KOSPI/KOSDAQ 전체 종목 가져오기."""
    url = "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    krx = pd.read_html(io.StringIO(r.text))[0]

    kospi = krx[(krx["시장구분"] == "유가") & (krx["종목코드"].str.match(r"^\d{6}$"))].copy()
    kosdaq = krx[(krx["시장구분"] == "코스닥") & (krx["종목코드"].str.match(r"^\d{6}$"))].copy()

    kospi_tickers = [f"{c}.KS" for c in kospi["종목코드"].tolist()]
    kosdaq_tickers = [f"{c}.KQ" for c in kosdaq["종목코드"].tolist()]

    return kospi_tickers, kosdaq_tickers


def get_shares_outstanding(tickers, batch_size=50):
    """yfinance에서 현재 발행주식수 가져오기."""
    shares = {}
    total = len(tickers)
    for i in range(0, total, batch_size):
        batch = tickers[i:i+batch_size]
        logger.debug(f"    발행주식수: {i}/{total}")
        for t in batch:
            try:
                info = yf.Ticker(t).fast_info
                s = info.get("shares", None)
                if s and s > 0:
                    shares[t] = int(s)
            except Exception:
                pass
    logger.debug(f"    발행주식수: {total}/{total} → {len(shares)}개 확보")
    return shares


def download_prices(tickers, start, end, label=""):
    """yfinance로 가격 데이터 일괄 다운로드."""
    all_data = {}
    batch_size = 50
    total = len(tickers)

    for i in range(0, total, batch_size):
        batch = tickers[i:i+batch_size]
        logger.debug(f"    {label} 다운로드: {i}/{total}")
        try:
            raw = yf.download(batch, start=start, end=end,
                              auto_adjust=True, progress=False, threads=True)
            if isinstance(raw.columns, pd.MultiIndex):
                for t in batch:
                    try:
                        df = raw.xs(t, axis=1, level=1).dropna(how="all")
                        if len(df) >= 220:
                            all_data[t] = df
                    except Exception:
                        pass
            elif len(batch) == 1 and len(raw) >= 220:
                all_data[batch[0]] = raw
        except Exception:
            pass

    logger.debug(f"    {label} 다운로드: {total}/{total} → {len(all_data)}개 확보")
    return all_data


def save_universe_cache(all_data, shares, spy_close, etf_data, us_sectors):
    """다운로드 데이터를 캐시."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {"stocks": {}, "shares": shares, "us_sectors": us_sectors}
    for t, df in all_data.items():
        fname = t.replace(".", "_") + ".parquet"
        df.to_parquet(DATA_DIR / fname)
        manifest["stocks"][t] = fname

    for t, df in etf_data.items():
        fname = f"etf_{t}.parquet"
        df.to_parquet(DATA_DIR / fname)
        manifest.setdefault("etfs", {})[t] = fname

    spy_close.to_frame("Close").to_parquet(DATA_DIR / "spy.parquet")

    with open(DATA_DIR / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    logger.debug(f"  캐시 저장: {DATA_DIR} ({len(all_data)}종목)")


def load_universe_cache():
    """캐시된 데이터 로드."""
    manifest_path = DATA_DIR / "manifest.json"
    if not manifest_path.exists():
        return None, None, None, None, None

    with open(manifest_path) as f:
        manifest = json.load(f)

    all_data = {}
    for t, fname in manifest["stocks"].items():
        path = DATA_DIR / fname
        if path.exists():
            all_data[t] = pd.read_parquet(path)

    etf_data = {}
    for t, fname in manifest.get("etfs", {}).items():
        path = DATA_DIR / fname
        if path.exists():
            etf_data[t] = pd.read_parquet(path)

    spy_df = pd.read_parquet(DATA_DIR / "spy.parquet")
    spy_close = spy_df["Close"].squeeze()

    shares = manifest.get("shares", {})
    us_sectors = manifest.get("us_sectors", {})

    return all_data, shares, spy_close, etf_data, us_sectors


# ══════════════════════════════════════════════════════════════════
# STEP 2: 지표 및 스크리닝 (backtest_adaptive.py 기반)
# ══════════════════════════════════════════════════════════════════

def add_indicators(df):
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


def swing_hh_hl(df_win, n=3):
    highs = df_win["High"].values
    lows  = df_win["Low"].values
    sh = [highs[i] for i in range(n, len(highs)-n) if highs[i]==max(highs[i-n:i+n+1])]
    sl = [lows[i]  for i in range(n, len(lows)-n)  if lows[i]==min(lows[i-n:i+n+1])]
    return min(sum(sh[i]>sh[i-1] for i in range(1,len(sh))),
               sum(sl[i]>sl[i-1] for i in range(1,len(sl))))

def minmax(s):
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)


def screen(df, as_of, atr_mult):
    hist = df[df.index <= as_of]
    if len(hist) < 220:
        return False, {}
    row = hist.iloc[-1]
    r5, r20, r60, r63 = hist.tail(6), hist.tail(20), hist.tail(60), hist.tail(63)

    adx = row.get("ADX", np.nan)
    if pd.isna(adx) or adx < 25: return False, {}
    ma20, ma50, ma200 = row.get("MA20"), row.get("MA50"), row.get("MA200")
    if any(pd.isna(v) for v in [ma20, ma50, ma200]) or not (ma20>ma50>ma200): return False, {}
    rsi = row.get("RSI", np.nan)
    if pd.isna(rsi) or not (50 <= rsi <= 75): return False, {}
    vol60 = row.get("VolMA60", np.nan)
    if pd.isna(vol60) or vol60==0 or (r20["Volume"]>vol60*3.0).any(): return False, {}
    if (r5["Close"].pct_change().abs() > 0.10).any(): return False, {}
    if swing_hh_hl(r60) < 3: return False, {}
    high52 = row.get("High52w", np.nan)
    if not pd.isna(high52) and high52>0 and row["Close"] < high52*0.80: return False, {}

    ret3m    = float(hist["Close"].iloc[-1]/r63["Close"].iloc[0])-1 if len(r63)>=60 else np.nan
    vol_cv   = r20["Volume"].std()/(vol60+1e-9)
    vol_stab = float(1/(vol_cv+1e-6))
    atr_val  = float(hist["ATR"].dropna().iloc[-1]) if "ATR" in hist.columns and len(hist["ATR"].dropna())>0 else np.nan
    peak20   = float(hist["High"].tail(20).max())
    atr_stop = peak20 - atr_val * atr_mult if not pd.isna(atr_val) else np.nan

    return True, {
        "ADX": float(adx), "RSI": float(rsi), "ret3m": ret3m, "vol_stab": vol_stab,
        "price": float(hist["Close"].iloc[-1]), "atr_stop": atr_stop, "atr": atr_val,
    }


def rank_stocks(passed, etf_data, as_of, sectors):
    if not passed: return pd.DataFrame()
    df = pd.DataFrame(passed).T
    df["sector"] = [sectors.get(t, "Unknown") for t in df.index]
    df["sec_str"] = 0.0
    for idx, row in df.iterrows():
        sym = SECTOR_ETF.get(row["sector"])
        if sym and sym in etf_data:
            ec = etf_data[sym][etf_data[sym].index <= as_of]["Close"]
            if len(ec) >= 63:
                df.loc[idx,"sec_str"] = (row["ret3m"] - float(ec.iloc[-1]/ec.iloc[-63]-1)) \
                    if not pd.isna(row["ret3m"]) else 0.0
    df["sec_n"] = minmax(df["sec_str"])
    df["score"] = (minmax(df["ADX"])*WEIGHTS["adx"] +
                   minmax(df["ret3m"].fillna(0))*WEIGHTS["ret3m"] +
                   minmax(df["sec_n"])*WEIGHTS["sector"] +
                   minmax(df["vol_stab"])*WEIGHTS["vol_stab"])
    return df.sort_values("score", ascending=False)


def position_weights(scores, max_w=MAX_WEIGHT):
    n = len(scores)
    if n == 0: return pd.Series(dtype=float)
    total = scores.sum()
    if total == 0 or pd.isna(total): return pd.Series([1.0/n]*n, index=scores.index)
    w = scores / scores.sum()
    w[w <= 0] = 1e-6
    w = w / w.sum()
    for _ in range(20):
        if (w <= max_w + 1e-8).all(): break
        excess = (w - max_w).clip(lower=0).sum()
        w = w.clip(upper=max_w)
        under = w < max_w
        if under.sum() > 0: w[under] += excess * w[under] / w[under].sum()
    return w / w.sum()


def check_stops(holdings, all_data, prev_dt, rd):
    daily_range = pd.date_range(prev_dt, rd, freq="B")[1:]
    for day in daily_range:
        if not holdings: break
        to_remove = []
        for ticker, info in holdings.items():
            df_t = all_data.get(ticker)
            if df_t is None: continue
            day_close = df_t[df_t.index <= day]["Close"]
            if len(day_close) == 0: continue
            cur_px = float(day_close.iloc[-1])
            info["peak"] = max(info["peak"], cur_px)
            stop = info.get("atr_stop", np.nan)
            if not pd.isna(stop) and cur_px <= stop: to_remove.append(ticker)
        for t in to_remove: del holdings[t]
    return holdings


def calc_turnover_cost(old_h, new_h, cost_per_side):
    all_t = set(list(old_h.keys()) + list(new_h.keys()))
    return sum(abs(old_h.get(t,{}).get("w",0) - new_h.get(t,{}).get("w",0)) for t in all_t) * cost_per_side


def make_rebal_dates(freq):
    if freq == "W": return pd.date_range(start=START, end=END, freq="W-FRI")
    elif freq == "2W": return pd.date_range(start=START, end=END, freq="W-FRI")[::2]
    else: return pd.date_range(start=START, end=END, freq="BME")


# ══════════════════════════════════════════════════════════════════
# STEP 3: 시가총액 기반 동적 유니버스 필터링
# ══════════════════════════════════════════════════════════════════

def filter_by_marketcap(all_data_ind, shares, as_of):
    """특정 시점의 시가총액 기준으로 유니버스 필터링.

    US: 전체 (S&P500 이미 시총 상위)
    KR_KOSPI (.KS): 시총 상위 200개
    KR_KOSDAQ (.KQ): 시총 상위 150개
    """
    us_tickers = []
    kr_ks_caps = {}
    kr_kq_caps = {}

    for t, df in all_data_ind.items():
        hist = df[df.index <= as_of]
        if len(hist) < 220:
            continue

        price = float(hist["Close"].iloc[-1])
        sh = shares.get(t, 0)

        if t.endswith(".KS"):
            if sh > 0:
                kr_ks_caps[t] = price * sh
        elif t.endswith(".KQ"):
            if sh > 0:
                kr_kq_caps[t] = price * sh
        else:
            us_tickers.append(t)  # S&P500은 전체 포함

    # KOSPI 상위 200
    kr_ks_sorted = sorted(kr_ks_caps.items(), key=lambda x: x[1], reverse=True)
    kr_ks_top = [t for t, _ in kr_ks_sorted[:KR_KOSPI_N]]

    # KOSDAQ 상위 150
    kr_kq_sorted = sorted(kr_kq_caps.items(), key=lambda x: x[1], reverse=True)
    kr_kq_top = [t for t, _ in kr_kq_sorted[:KR_KOSDAQ_N]]

    return us_tickers + kr_ks_top + kr_kq_top


# ══════════════════════════════════════════════════════════════════
# STEP 4: 국면 판별 (backtest_adaptive.py v2)
# ══════════════════════════════════════════════════════════════════

def detect_regime(spy_close, as_of):
    spy = spy_close[spy_close.index <= as_of]
    if len(spy) < 200:
        return "balanced", 2.5

    close = spy
    ma50  = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])
    gap   = (ma50 - ma200) / ma200
    price = float(close.iloc[-1])

    spy_rsi_s = ta.rsi(close, 14)
    spy_rsi = float(spy_rsi_s.dropna().iloc[-1]) if spy_rsi_s is not None and len(spy_rsi_s.dropna()) > 0 else 50.0

    spy_df = pd.DataFrame({"Close": close, "High": close, "Low": close})
    spy_atr = ta.atr(spy_df["High"], spy_df["Low"], spy_df["Close"], length=14)
    if spy_atr is not None and len(spy_atr.dropna()) > 0:
        cur_atr = float(spy_atr.dropna().iloc[-1])
        atr_1y = spy_atr.dropna().tail(252)
        vol_pctile = float((atr_1y < cur_atr).mean() * 100)
    else:
        vol_pctile = 50

    ma20_series = close.rolling(20).mean()
    if len(ma20_series.dropna()) >= 20:
        ma20_slope = (float(ma20_series.dropna().iloc[-1]) - float(ma20_series.dropna().iloc[-20])) / float(ma20_series.dropna().iloc[-20])
    else:
        ma20_slope = 0

    weekly_ret = float(close.iloc[-1] / close.iloc[-5] - 1) if len(close) >= 5 else 0

    # Layer 1
    if gap > GAP_STRONG_BULL: regime = "aggressive"
    elif gap > 0: regime = "balanced"
    else: regime = "conservative"

    # Layer 2
    downgrade = False
    if spy_rsi < 35: downgrade = True
    if ma20_slope < -0.03: downgrade = True
    if downgrade:
        if regime == "aggressive": regime = "balanced"
        elif regime == "balanced": regime = "conservative"

    # Layer 3
    if weekly_ret < -0.05: regime = "conservative"
    if price < ma200 and spy_rsi < 40: regime = "conservative"
    if vol_pctile >= 90 and weekly_ret < 0: regime = "conservative"

    atr_mult = PRESETS.get(regime, PRESETS["balanced"])["atr_mult"]
    return regime, atr_mult


# ══════════════════════════════════════════════════════════════════
# STEP 5: 백테스트 루프
# ══════════════════════════════════════════════════════════════════

def run_backtest(all_data_ind, etf_data, spy_close, shares, sectors,
                 freq, atr_mult, cost_per_side, strategy_name,
                 adaptive=False):
    """단일 전략 백테스트."""
    rebal_dates = make_rebal_dates(freq) if not adaptive else \
                  pd.date_range(start=START, end=END, freq="W-FRI")
    biweekly = set(pd.date_range(start=START, end=END, freq="W-FRI")[::2])
    monthly  = set(pd.date_range(start=START, end=END, freq="BME"))

    nav = 1.0
    holdings = {}
    prev_dt = None
    prev_regime = None
    trades = 0
    nav_series = pd.Series(dtype=float)
    total = len(rebal_dates)

    for i, rd in enumerate(rebal_dates):
        if (i+1) % 100 == 0 or i == total-1:
            logger.debug(f"    {strategy_name}: {i+1}/{total} ({(i+1)/total:.0%})")

        cur_atr = atr_mult
        should_rebal = True

        if adaptive:
            regime, cur_atr = detect_regime(spy_close, rd)
            regime_changed = (regime != prev_regime) and prev_regime is not None

            should_rebal = False
            if regime == "aggressive": should_rebal = True
            elif regime == "balanced": should_rebal = rd in biweekly
            elif regime == "conservative":
                should_rebal = rd in monthly or any(abs((rd - m).days) <= 3 for m in monthly)
            if regime_changed: should_rebal = True
            prev_regime = regime

        if prev_dt and holdings:
            holdings = check_stops(holdings, all_data_ind, prev_dt, rd)

        if prev_dt and holdings:
            ret = 0.0
            for t, info in holdings.items():
                df_t = all_data_ind.get(t)
                if df_t is None: continue
                p0 = df_t[df_t.index <= prev_dt]["Close"]
                p1 = df_t[df_t.index <= rd]["Close"]
                if len(p0) and len(p1) and float(p0.iloc[-1]) > 0:
                    ret += info["w"] * (float(p1.iloc[-1]) / float(p0.iloc[-1]) - 1)
            nav *= (1 + ret)

        if should_rebal:
            # 시가총액 기반 유니버스 필터링
            universe = filter_by_marketcap(all_data_ind, shares, rd)

            passed = {}
            for t in universe:
                df_t = all_data_ind.get(t)
                if df_t is None: continue
                ok, met = screen(df_t, rd, cur_atr)
                if ok: passed[t] = met

            ranked = rank_stocks(passed, etf_data, rd, sectors)
            top = ranked.head(TOP_N)
            new_h = {}
            if len(top) > 0:
                ws = position_weights(top["score"])
                for t in top.index:
                    df_t = all_data_ind.get(t)
                    entry = float(df_t[df_t.index<=rd]["Close"].iloc[-1]) if df_t is not None else 1.0
                    new_h[t] = {
                        "w": float(ws[t]), "entry": entry, "peak": entry,
                        "atr_stop": float(top.loc[t,"atr_stop"]) if "atr_stop" in top.columns else np.nan,
                    }

            nav *= (1 - calc_turnover_cost(holdings, new_h, cost_per_side))
            trades += len(set(holdings.keys()) ^ set(new_h.keys()))
            holdings = new_h

        prev_dt = rd
        nav_series[rd] = nav

    logger.debug("")
    return nav_series, trades


def calc_metrics(nav, label):
    ret   = nav.pct_change().dropna()
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr  = (nav.iloc[-1] ** (1/years)) - 1 if years > 0 else 0
    dd    = (nav - nav.cummax()) / nav.cummax()
    mdd   = dd.min()
    sharpe = (ret.mean() / (ret.std() + 1e-9)) * np.sqrt(52)
    win    = (ret > 0).mean()
    return {"label": label, "CAGR": cagr, "총수익": nav.iloc[-1]-1,
            "MDD": mdd, "샤프": sharpe, "승률": win, "nav": nav}


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true", help="상세 출력 활성화")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    t0_total = time.time()

    WINDOWS = [
        ("B_현대시장",   "2015-01-01", "2024-12-31"),
        ("C_최근변동성", "2020-01-01", "2024-12-31"),
    ]

    logger.debug("=" * 70)
    logger.debug("  풀 유니버스 백테스트")
    logger.debug("  US: S&P500 전체 / KR: KOSPI 상위200 + KOSDAQ 상위150")
    logger.debug(f"  거래비용: 편도 {COST_PER_SIDE*100:.1f}%")
    logger.debug("=" * 70)

    # ── 데이터 로드 또는 다운로드 ──
    cached = load_universe_cache()
    if cached[0] is not None and len(cached[0]) > 100:
        logger.debug("\n[캐시 로드]")
        all_data, shares, spy_close, etf_data_raw, us_sectors = cached
        logger.debug(f"  종목 {len(all_data)}개, 발행주식수 {len(shares)}개")
    else:
        logger.debug("\n[유니버스 구축]")
        t0 = time.time()

        # S&P500
        logger.debug("  S&P500 목록 가져오기...")
        us_tickers, us_sectors = fetch_sp500_tickers()
        logger.debug(f"    {len(us_tickers)}개")

        # 한국
        logger.debug("  KRX 목록 가져오기...")
        kr_ks, kr_kq = fetch_kr_tickers()
        logger.debug(f"    KOSPI {len(kr_ks)}개, KOSDAQ {len(kr_kq)}개")

        # 발행주식수 (시총 계산용)
        logger.debug("  발행주식수 가져오기 (한국 종목)...")
        kr_shares = get_shares_outstanding(kr_ks + kr_kq)

        # 가격 다운로드
        logger.debug("\n  가격 데이터 다운로드...")
        t_dl = time.time()

        all_data = {}
        us_data = download_prices(us_tickers, "2014-01-01", "2024-12-31", "US")
        all_data.update(us_data)

        kr_data = download_prices(kr_ks + kr_kq, "2014-01-01", "2024-12-31", "KR")
        all_data.update(kr_data)

        # ETF
        etf_tickers = list(set(SECTOR_ETF.values()))
        etf_data_raw = download_prices(etf_tickers, "2014-01-01", "2024-12-31", "ETF")

        # SPY
        spy_raw = yf.download("SPY", start="2014-01-01", end="2024-12-31",
                              auto_adjust=True, progress=False)
        spy_close = spy_raw["Close"].squeeze()

        dl_time = time.time() - t_dl
        logger.debug(f"\n  다운로드 완료: {len(all_data)}종목, {dl_time:.0f}초")

        # 발행주식수 병합
        shares = kr_shares

        # 캐시 저장
        save_universe_cache(all_data, shares, spy_close, etf_data_raw, us_sectors)

        build_time = time.time() - t0
        logger.debug(f"  유니버스 구축 총 시간: {build_time:.0f}초 ({build_time/60:.1f}분)")

    # 지표 계산
    logger.debug(f"\n[지표 계산] {len(all_data)}개 종목...")
    t_ind = time.time()
    all_data_ind = {}
    for i, (t, df) in enumerate(all_data.items()):
        if (i+1) % 100 == 0:
            logger.debug(f"  {i+1}/{len(all_data)}")
        all_data_ind[t] = add_indicators(df)
    etf_data = {t: add_indicators(df) for t, df in etf_data_raw.items()}
    ind_time = time.time() - t_ind
    logger.debug(f"  {len(all_data_ind)}개 완료 ({ind_time:.0f}초)")

    # 섹터 매핑 (한국 종목은 Unknown으로)
    sectors = dict(us_sectors) if us_sectors else {}

    # ── 윈도우별 백테스트 ──
    all_rows = []
    for wlabel, wstart, wend in WINDOWS:
        START, END = wstart, wend

        logger.debug(f"\n{'█'*70}")
        logger.debug(f"  [{wlabel}] {wstart} ~ {wend}")
        logger.debug(f"{'█'*70}")

        strategies = [
            ("공격적 (ATR=2.0 주간)", "W",  2.0, False),
            ("균형형 (ATR=2.5 격주)", "2W", 2.5, False),
            ("보수적 (ATR=3.5 월간)", "M",  3.5, False),
            ("적응형 (3계층)",        "W",  2.5, True),
        ]

        results = []
        for sname, freq, atr_m, adaptive in strategies:
            t_s = time.time()
            nav, trades = run_backtest(
                all_data_ind, etf_data, spy_close, shares, sectors,
                freq, atr_m, COST_PER_SIDE, sname, adaptive=adaptive)
            elapsed = time.time() - t_s
            m = calc_metrics(nav, sname)
            m["elapsed"] = elapsed
            results.append(m)
            logger.debug(f"      → {elapsed:.0f}초")

        # SPY
        spy_start = spy_close[spy_close.index >= wstart]
        spy_nav = spy_start / float(spy_start.iloc[0])
        spy_nav = spy_nav[spy_nav.index <= wend]
        m_spy = calc_metrics(spy_nav, "SPY")
        m_spy["elapsed"] = 0
        results.append(m_spy)

        # 출력
        print(f"\n  {'전략':<22} {'CAGR':>8} {'총수익':>10} {'MDD':>8} {'샤프':>6} {'승률':>6} {'시간':>6}")
        print("  " + "─" * 68)
        for r in results:
            t_str = f"{r['elapsed']:.0f}s" if r['elapsed'] > 0 else "-"
            print(f"  {r['label']:<22} {r['CAGR']:>+8.1%} {r['총수익']:>+9.0%}"
                  f" {r['MDD']:>+8.1%} {r['샤프']:>6.2f} {r['승률']:>6.1%} {t_str:>6}")

        for r in results:
            all_rows.append({
                "윈도우": wlabel, "전략": r["label"],
                "CAGR": f"{r['CAGR']:+.1%}", "총수익": f"{r['총수익']:+.0%}",
                "MDD": f"{r['MDD']:+.1%}", "샤프": f"{r['샤프']:.2f}",
                "승률": f"{r['승률']:.1%}", "소요시간": f"{r['elapsed']:.0f}s",
            })

        # 차트
        fig, ax = plt.subplots(figsize=(14, 7))
        colors = ["#e63946","#457b9d","#2a9d8f","#e9c46a","#9b59b6","black"]
        for i, r in enumerate(results):
            lw = 2.5 if "적응" in r["label"] else (1.2 if r["label"]=="SPY" else 1.5)
            ls = ":" if r["label"]=="SPY" else "-"
            ax.plot(r["nav"].index, r["nav"].values,
                    label=f"{r['label']}  CAGR {r['CAGR']:+.1%}  MDD {r['MDD']:+.1%}",
                    color=colors[i], lw=lw, ls=ls, alpha=0.9 if "적응" in r["label"] else 0.7)
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x,_: f"{x:.0f}x"))
        ax.legend(fontsize=8)
        ax.grid(alpha=0.25)
        ax.set_title(f"[풀 유니버스] {wlabel} ({wstart}~{wend})", fontsize=13, fontweight="bold")
        plt.tight_layout()
        plt.savefig(RESULTS_DIR / f"backtest_full_{wlabel}.png", dpi=150, bbox_inches="tight")
        print(f"  차트: backtest_full_{wlabel}.png")
        plt.close()

    # 통합 CSV
    pd.DataFrame(all_rows).to_csv(RESULTS_DIR / "backtest_full_universe.csv",
                                   index=False, encoding="utf-8-sig")

    total_time = time.time() - t0_total
    print(f"\n{'═'*70}")
    print(f"  총 소요 시간: {total_time:.0f}초 ({total_time/60:.1f}분)")
    print(f"  결과: backtest_full_universe.csv")
    print(f"{'═'*70}")
