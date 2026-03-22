"""스크리너 v3 알고리즘 — 서비스 레이어 (print 제거, 데이터 반환)"""
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
import pandas_ta as ta

US_UNIVERSE = {
    "NVDA":"Technology","AAPL":"Technology","MSFT":"Technology","AVGO":"Technology",
    "AMD":"Technology","QCOM":"Technology","AMAT":"Technology","LRCX":"Technology",
    "MU":"Technology","KLAC":"Technology","ORCL":"Technology","ADBE":"Technology",
    "CRM":"Technology","NOW":"Technology","PANW":"Technology","SNPS":"Technology",
    "META":"Communication","GOOGL":"Communication","NFLX":"Communication","TMUS":"Communication",
    "AMZN":"Consumer Disc","TSLA":"Consumer Disc","HD":"Consumer Disc","LULU":"Consumer Disc",
    "LLY":"Health Care","UNH":"Health Care","ABBV":"Health Care","ISRG":"Health Care","VRTX":"Health Care",
    "V":"Financials","MA":"Financials","JPM":"Financials","GS":"Financials",
    "XOM":"Energy","CVX":"Energy","SLB":"Energy",
    "CAT":"Industrials","GE":"Industrials","ETN":"Industrials","LMT":"Industrials",
    "FCX":"Materials","NEM":"Materials",
}
KR_UNIVERSE = {
    "005930.KS":"Technology","000660.KS":"Technology","009150.KS":"Technology",
    "006400.KS":"Technology","373220.KS":"Technology",
    "207940.KS":"Health Care","068270.KS":"Health Care",
    "051910.KS":"Materials","247540.KS":"Materials",
    "005380.KS":"Consumer Disc","000270.KS":"Consumer Disc",
    "035420.KS":"Communication","035720.KS":"Communication",
    "105560.KS":"Financials","055550.KS":"Financials",
    "096770.KS":"Energy","011200.KS":"Industrials",
}
ALL_UNIVERSE = {**US_UNIVERSE, **KR_UNIVERSE}

SECTOR_ETF = {
    "Technology":"XLK","Health Care":"XLV","Financials":"XLF",
    "Consumer Disc":"XLY","Industrials":"XLI","Energy":"XLE",
    "Materials":"XLB","Communication":"XLC",
}

ATR_PERIOD = 14
ATR_MULT = 2.5
SCORE_WEIGHTS = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)
TOP_N = 10
MAX_WEIGHT = 0.20


def download_tickers(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    try:
        raw = yf.download(tickers, period=period, auto_adjust=True,
                          progress=False, threads=True)
        result = {}
        if isinstance(raw.columns, pd.MultiIndex):
            for t in tickers:
                try:
                    df = raw.xs(t, axis=1, level=1).dropna(how="all")
                    if len(df) >= 60:
                        result[t] = df
                except Exception:
                    pass
        else:
            if len(raw) >= 60:
                result[tickers[0]] = raw
        return result
    except Exception:
        return {}


def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
    d["MA20"] = ta.sma(c, 20)
    d["MA50"] = ta.sma(c, 50)
    d["MA200"] = ta.sma(c, 200)
    d["RSI"] = ta.rsi(c, 14)
    adx = ta.adx(h, l, c, 14)
    d["ADX"] = adx["ADX_14"] if adx is not None and "ADX_14" in adx.columns else np.nan
    d["VolMA20"] = v.rolling(20).mean()
    d["VolMA60"] = v.rolling(60).mean()
    d["High52w"] = h.rolling(252).max()
    atr = ta.atr(h, l, c, length=ATR_PERIOD)
    d["ATR"] = atr if atr is not None else np.nan
    return d


def count_hh_hl_swing(df_window: pd.DataFrame, n: int = 3) -> int:
    highs = df_window["High"].values
    lows = df_window["Low"].values
    sh = [highs[i] for i in range(n, len(highs) - n)
          if highs[i] == max(highs[i - n:i + n + 1])]
    sl = [lows[i] for i in range(n, len(lows) - n)
          if lows[i] == min(lows[i - n:i + n + 1])]
    hh = sum(sh[i] > sh[i - 1] for i in range(1, len(sh)))
    hl = sum(sl[i] > sl[i - 1] for i in range(1, len(sl)))
    return min(hh, hl)


def calc_atr_stop(df: pd.DataFrame) -> float:
    atr_val = df["ATR"].dropna().iloc[-1] if "ATR" in df.columns and len(df["ATR"].dropna()) > 0 else np.nan
    if pd.isna(atr_val):
        return np.nan
    peak_20 = float(df["High"].tail(20).max())
    return round(peak_20 - atr_val * ATR_MULT, 2)


def screen_stock(df: pd.DataFrame) -> tuple[bool, dict]:
    if len(df) < 200:
        return False, {}
    row = df.iloc[-1]
    r5, r20, r60, r63 = df.tail(6), df.tail(20), df.tail(60), df.tail(63)

    adx = row.get("ADX", np.nan)
    if pd.isna(adx) or adx < 25:
        return False, {}

    ma20, ma50, ma200 = row.get("MA20"), row.get("MA50"), row.get("MA200")
    if any(pd.isna(v) for v in [ma20, ma50, ma200]) or not (ma20 > ma50 > ma200):
        return False, {}

    rsi = row.get("RSI", np.nan)
    if pd.isna(rsi) or not (50 <= rsi <= 75):
        return False, {}

    vol60 = row.get("VolMA60", np.nan)
    if pd.isna(vol60) or vol60 == 0 or (r20["Volume"] > vol60 * 3.0).any():
        return False, {}

    if (r5["Close"].pct_change().abs() > 0.10).any():
        return False, {}

    if count_hh_hl_swing(r60) < 3:
        return False, {}

    high52 = row.get("High52w", np.nan)
    if not pd.isna(high52) and high52 > 0 and row["Close"] < high52 * 0.80:
        return False, {}

    ret3m = float(df["Close"].iloc[-1] / r63["Close"].iloc[0]) - 1 if len(r63) >= 60 else np.nan
    vol_cv = r20["Volume"].std() / (vol60 + 1e-9)
    vol_stab = float(1 / (vol_cv + 1e-6))

    stop_price = calc_atr_stop(df)
    cur_price = float(df["Close"].iloc[-1])
    stop_dist = (stop_price - cur_price) / cur_price if not pd.isna(stop_price) else np.nan

    return True, {
        "ADX": float(adx), "RSI": float(rsi), "ret3m": ret3m,
        "vol_stab": vol_stab, "price": cur_price,
        "stop_price": stop_price, "stop_dist": stop_dist,
        "atr": float(df["ATR"].dropna().iloc[-1]) if "ATR" in df.columns and len(df["ATR"].dropna()) > 0 else np.nan,
    }


def minmax(s: pd.Series) -> pd.Series:
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)


def calc_position_weights(scores: pd.Series, max_w: float = MAX_WEIGHT) -> pd.Series:
    n = len(scores)
    if n == 0:
        return pd.Series(dtype=float)
    total = scores.sum()
    if total == 0 or pd.isna(total):
        return pd.Series([1.0 / n] * n, index=scores.index)
    adj = scores.copy()
    adj[adj <= 0] = 1e-6
    w = adj / adj.sum()
    for _ in range(20):
        if (w <= max_w + 1e-8).all():
            break
        excess = (w - max_w).clip(lower=0).sum()
        w = w.clip(upper=max_w)
        under = w < max_w
        if under.sum() > 0:
            w[under] += excess * w[under] / w[under].sum()
    return w / w.sum()


def rank_stocks(passed: dict, etf_data: dict) -> pd.DataFrame:
    if not passed:
        return pd.DataFrame()
    df = pd.DataFrame(passed).T
    df["sector"] = [ALL_UNIVERSE.get(t, "Unknown") for t in df.index]
    df["sec_str"] = 0.0
    for idx, row in df.iterrows():
        sec = row["sector"]
        etf_sym = SECTOR_ETF.get(sec)
        if etf_sym and etf_sym in etf_data:
            etf_close = etf_data[etf_sym]["Close"]
            if len(etf_close) >= 63:
                etf_ret = float(etf_close.iloc[-1] / etf_close.iloc[-63]) - 1
                df.loc[idx, "sec_str"] = (row["ret3m"] - etf_ret) if not pd.isna(row["ret3m"]) else 0.0
    df["sec_str_norm"] = minmax(df["sec_str"])
    df["score"] = (
        minmax(df["ADX"]) * SCORE_WEIGHTS["adx"] +
        minmax(df["ret3m"].fillna(0)) * SCORE_WEIGHTS["ret3m"] +
        minmax(df["sec_str_norm"]) * SCORE_WEIGHTS["sector"] +
        minmax(df["vol_stab"]) * SCORE_WEIGHTS["vol_stab"]
    )
    return df.sort_values("score", ascending=False)


def check_market() -> dict | None:
    try:
        spy = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
        close = spy["Close"].squeeze()
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        price = float(close.iloc[-1])
        gap = (ma50 - ma200) / ma200 * 100
        return {"price": price, "ma50": ma50, "ma200": ma200,
                "gap_pct": gap, "is_golden": ma50 > ma200}
    except Exception:
        return None


def run_screening() -> dict:
    """전체 스크리닝 파이프라인 실행. 결과 dict 반환."""
    market = check_market()

    # 데이터 다운로드
    all_data = {}
    for i in range(0, len(ALL_UNIVERSE), 30):
        chunk = list(ALL_UNIVERSE.keys())[i:i + 30]
        all_data.update(download_tickers(chunk))

    etf_data = {}
    etf_raw = download_tickers(list(set(SECTOR_ETF.values())))
    for t, df in etf_raw.items():
        etf_data[t] = calc_indicators(df)

    # 스크리닝
    passed = {}
    for t, df in all_data.items():
        df_ind = calc_indicators(df)
        ok, metrics = screen_stock(df_ind)
        if ok:
            passed[t] = metrics

    # 랭킹
    ranked = rank_stocks(passed, etf_data)
    top = ranked.head(TOP_N).copy()

    results = []
    if len(top) > 0:
        weights = calc_position_weights(top["score"])
        for rank_idx, (ticker, row) in enumerate(top.iterrows(), 1):
            results.append({
                "rank": rank_idx,
                "ticker": ticker,
                "market": "KR" if ticker.endswith(".KS") else "US",
                "sector": ALL_UNIVERSE.get(ticker, "Unknown"),
                "score": float(row["score"]),
                "weight_pct": float(weights[ticker]) * 100,
                "price": float(row["price"]),
                "adx": float(row["ADX"]) if not pd.isna(row["ADX"]) else None,
                "rsi": float(row["RSI"]) if not pd.isna(row["RSI"]) else None,
                "ret_3m": float(row["ret3m"]) if not pd.isna(row["ret3m"]) else None,
                "stop_price": float(row["stop_price"]) if not pd.isna(row["stop_price"]) else None,
                "stop_dist_pct": float(row["stop_dist"]) * 100 if not pd.isna(row.get("stop_dist")) else None,
                "atr": float(row["atr"]) if not pd.isna(row["atr"]) else None,
            })

    return {
        "market": market,
        "total_screened": len(all_data),
        "total_passed": len(passed),
        "results": results,
    }
