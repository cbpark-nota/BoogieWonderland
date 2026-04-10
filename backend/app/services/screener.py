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
KR_NAMES = {
    "005930.KS": "삼성전자",
    "000660.KS": "SK하이닉스",
    "009150.KS": "삼성전기",
    "006400.KS": "삼성SDI",
    "373220.KS": "LG에너지솔루션",
    "207940.KS": "삼성바이오로직스",
    "068270.KS": "셀트리온",
    "051910.KS": "LG화학",
    "247540.KS": "에코프로비엠",
    "005380.KS": "현대차",
    "000270.KS": "기아",
    "035420.KS": "NAVER",
    "035720.KS": "카카오",
    "105560.KS": "KB금융",
    "055550.KS": "신한지주",
    "096770.KS": "SK이노베이션",
    "011200.KS": "HMM",
}
ALL_UNIVERSE = {**US_UNIVERSE, **KR_UNIVERSE}

SECTOR_ETF = {
    "Technology":"XLK","Health Care":"XLV","Financials":"XLF",
    "Consumer Disc":"XLY","Industrials":"XLI","Energy":"XLE",
    "Materials":"XLB","Communication":"XLC",
}

# ── 기본 파라미터 ─────────────────────────────────────────────
ATR_PERIOD = 14
ATR_MULT   = 2.5
TOP_N      = 10
MAX_WEIGHT = 0.20

# ── v3.1 신규 파라미터 ────────────────────────────────────────
INCLUDE_KR_MARKET = False   # 변경 1: 한국 시장 제외
# 변경 2: 레짐 필터 모드
#   "off"   — 레짐 필터 적용 안 함
#   "info"  — 레짐 상태를 결과에 포함하되 필터링하지 않음 (배포 기본값)
#   "block" — 데드크로스 시 빈 결과 반환 (백테스트용)
REGIME_FILTER_MODE = "info"
VOL_TARGET        = 0.15    # 변경 3: 변동성 스케일링 목표 연환산 변동성
HOLD_SPREAD       = 2.5     # 변경 5: 보유 종목 Top N×HOLD_SPREAD까지 유지
USE_MKTCAP_WEIGHT = True    # 변경 6: 시가총액 가중 활성화

# ── 복합점수 가중치 (변경 4: ret12m_skip1 추가) ───────────────
SCORE_WEIGHTS = dict(
    adx      = 0.30,   # v3: 0.40 → 0.30
    ret3m    = 0.20,   # v3: 0.30 → 0.20
    ret12m   = 0.20,   # 신규: 12개월(최근 1개월 제외) 수익률
    sector   = 0.20,   # 유지
    vol_stab = 0.10,   # 유지
)


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


def calc_spy_vol_scale(spy_close: pd.Series) -> float:
    """SPY 20일 실현변동성(연환산) 기반 전체 포지션 스케일 팩터 (변경 3)."""
    ret = spy_close.pct_change().dropna()
    if len(ret) < 20:
        return 1.0
    vol = float(ret.tail(20).std() * np.sqrt(252))
    if vol <= 0:
        return 1.0
    return min(VOL_TARGET / vol, 1.0)


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

    # ── 변경 4: ret12m_skip1 (252일 수익률, 최근 21일 제외) ──
    n = len(df)
    if n >= 273:
        ret12m_skip1 = float(df["Close"].iloc[-22] / df["Close"].iloc[-273]) - 1
    elif n >= 252:
        ret12m_skip1 = float(df["Close"].iloc[-22] / df["Close"].iloc[-252]) - 1
    else:
        ret12m_skip1 = np.nan

    stop_price = calc_atr_stop(df)
    cur_price = float(df["Close"].iloc[-1])
    stop_dist = (stop_price - cur_price) / cur_price if not pd.isna(stop_price) else np.nan

    return True, {
        "ADX": float(adx), "RSI": float(rsi), "ret3m": ret3m,
        "ret12m_skip1": ret12m_skip1,
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


def rank_stocks(passed: dict, etf_data: dict, market_caps: dict | None = None) -> pd.DataFrame:
    """
    복합점수 계산 및 정렬.
    market_caps: {ticker: float} — 변경 6 시가총액 가중에 사용
    """
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

    # ── 변경 4: ret12m_skip1 포함 복합점수 ─────────────────────
    ret12m_col = df["ret12m_skip1"].fillna(0) if "ret12m_skip1" in df.columns else pd.Series(0.0, index=df.index)
    df["score"] = (
        minmax(df["ADX"])                  * SCORE_WEIGHTS["adx"]     +
        minmax(df["ret3m"].fillna(0))      * SCORE_WEIGHTS["ret3m"]   +
        minmax(ret12m_col)                 * SCORE_WEIGHTS["ret12m"]  +
        minmax(df["sec_str_norm"])         * SCORE_WEIGHTS["sector"]  +
        minmax(df["vol_stab"])             * SCORE_WEIGHTS["vol_stab"]
    )

    # ── 변경 6: 시가총액 가중 (score × sqrt(market_cap)) ───────
    if USE_MKTCAP_WEIGHT and market_caps:
        df["mktcap"] = [market_caps.get(t, 1.0) for t in df.index]
        df["mktcap"] = df["mktcap"].clip(lower=1.0)
        df["score"]  = df["score"] * np.sqrt(df["mktcap"])

    return df.sort_values("score", ascending=False)


def check_market() -> dict | None:
    """SPY MA20 vs MA60 골든/데드크로스 확인 (변경 2)."""
    try:
        spy = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
        close = spy["Close"].squeeze()
        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma60 = float(close.rolling(60).mean().iloc[-1])
        price = float(close.iloc[-1])
        gap = (ma20 - ma60) / ma60 * 100
        return {"price": price, "ma20": ma20, "ma60": ma60,
                "gap_pct": gap, "is_golden": ma20 > ma60,
                "close": close}
    except Exception:
        return None


def run_screening(held_tickers: list[str] | None = None) -> dict:
    """전체 스크리닝 파이프라인 실행. 결과 dict 반환."""
    if held_tickers is None:
        held_tickers = []

    # ── 변경 2: 시장 레짐 필터 ───────────────────────────────
    market = check_market()
    spy_close_series = market["close"] if market else None

    if REGIME_FILTER_MODE == "block" and market and not market["is_golden"]:
        return {
            "market": {k: v for k, v in market.items() if k != "close"},
            "regime_blocked": True,
            "total_screened": 0,
            "total_passed": 0,
            "results": [],
        }

    # ── 변경 3: 변동성 스케일 팩터 ───────────────────────────
    vol_scale = calc_spy_vol_scale(spy_close_series) if spy_close_series is not None else 1.0

    # ── 변경 1: KR 시장 제외 ─────────────────────────────────
    universe = US_UNIVERSE if not INCLUDE_KR_MARKET else ALL_UNIVERSE

    # 데이터 다운로드
    all_data: dict = {}
    for i in range(0, len(universe), 30):
        chunk = list(universe.keys())[i:i + 30]
        all_data.update(download_tickers(chunk))

    etf_data: dict = {}
    etf_raw = download_tickers(list(set(SECTOR_ETF.values())))
    for t, df in etf_raw.items():
        etf_data[t] = calc_indicators(df)

    # 스크리닝
    passed: dict = {}
    for t, df in all_data.items():
        df_ind = calc_indicators(df)
        ok, metrics = screen_stock(df_ind)
        if ok:
            passed[t] = metrics

    # ── 변경 6: 시가총액 수집 ─────────────────────────────────
    market_caps: dict = {}
    if USE_MKTCAP_WEIGHT and passed:
        for t in passed:
            try:
                mc = yf.Ticker(t).fast_info.market_cap
                market_caps[t] = float(mc) if mc and mc > 0 else 1.0
            except Exception:
                market_caps[t] = 1.0

    # 랭킹
    ranked = rank_stocks(passed, etf_data, market_caps)

    # ── 변경 5: Buy/Hold Spread ───────────────────────────────
    hold_n  = int(TOP_N * HOLD_SPREAD)
    top_new = ranked.head(TOP_N) if len(ranked) > 0 else ranked

    if held_tickers and len(ranked) > 0:
        hold_extended = ranked.head(hold_n)
        held_valid    = [t for t in held_tickers if t in hold_extended.index]
        held_extra    = [t for t in held_valid if t not in top_new.index]
        top = pd.concat([top_new, ranked.loc[held_extra]]) if held_extra else top_new
    else:
        top = top_new

    results = []
    if len(top) > 0:
        raw_weights = calc_position_weights(top["score"])
        weights = raw_weights * vol_scale   # 변경 3: vol_scale 적용

        for rank_idx, (ticker, row) in enumerate(top.iterrows(), 1):
            results.append({
                "rank": rank_idx,
                "ticker": ticker,
                "market": "KR" if ticker.endswith(".KS") else "US",
                "name": KR_NAMES.get(ticker) if ticker.endswith(".KS") else None,
                "sector": ALL_UNIVERSE.get(ticker, "Unknown"),
                "score": float(row["score"]),
                "weight_pct": float(weights[ticker]) * 100,
                "weight_raw_pct": float(raw_weights[ticker]) * 100,
                "price": float(row["price"]),
                "adx": float(row["ADX"]) if not pd.isna(row["ADX"]) else None,
                "rsi": float(row["RSI"]) if not pd.isna(row["RSI"]) else None,
                "ret_3m": float(row["ret3m"]) if not pd.isna(row["ret3m"]) else None,
                "ret_12m_skip1": float(row["ret12m_skip1"]) if "ret12m_skip1" in row and not pd.isna(row["ret12m_skip1"]) else None,
                "stop_price": float(row["stop_price"]) if not pd.isna(row["stop_price"]) else None,
                "stop_dist_pct": float(row["stop_dist"]) * 100 if not pd.isna(row.get("stop_dist")) else None,
                "atr": float(row["atr"]) if not pd.isna(row["atr"]) else None,
                "is_held": ticker in held_tickers,
            })

    market_out = {k: v for k, v in market.items() if k != "close"} if market else None

    # info 모드: market_regime 필드 구성
    market_regime = None
    if REGIME_FILTER_MODE == "info" and market:
        market_regime = {
            "golden_cross": market["is_golden"],
            "spy_ma20"    : round(market["ma20"], 2),
            "spy_ma60"    : round(market["ma60"], 2),
            "gap_pct"     : round(market["gap_pct"], 2),
        }

    return {
        "market": market_out,
        "market_regime": market_regime,
        "vol_scale": vol_scale,
        "regime_blocked": False,
        "total_screened": len(all_data),
        "total_passed": len(passed),
        "results": results,
    }
