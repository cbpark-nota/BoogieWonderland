"""
스크리너 v3.2 알고리즘 — 서비스 레이어
══════════════════════════════════════════════════════════
버전 히스토리:
  v3.0: ATR 기반 동적 스톱로스 + 복합점수 비례 포지션 사이징
  v3.1: 한국 시장 제외 플래그 / 시장 레짐 필터 / 변동성 스케일링
        ret12m_skip1 / Buy/Hold Spread / 시가총액 가중
  v3.2: US/KR 분리 스크리닝 (이 파일)
        - US: S&P 500 + NASDAQ 100 동적 수집 (Wikipedia/GitHub)
        - KR: KOSPI 200 + KOSDAQ 150 동적 수집 (pykrx)
        - 하드코딩 유니버스 제거
        - 예외 처리 강화 (HTTPException 500)

scripts/ 에서 직접 import 하지 말 것 — backend는 독립 구현.
══════════════════════════════════════════════════════════
"""
import io
import logging
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import requests
import yfinance as yf
import pandas_ta as ta
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ── 동적 유니버스 캐시 (run_screening() 실행 시 업데이트) ──────
# router에서 ALL_UNIVERSE, KR_NAMES를 import 해 쓰는 하위 호환 유지
ALL_UNIVERSE: dict[str, str] = {}
KR_NAMES: dict[str, str] = {}

# ── 섹터 ETF 매핑 (GICS 표준 + 구형 섹터명 모두 지원) ──────────
SECTOR_ETF = {
    "Information Technology": "XLK",
    "Technology":             "XLK",
    "Health Care":            "XLV",
    "Financials":             "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Disc":          "XLY",
    "Industrials":            "XLI",
    "Energy":                 "XLE",
    "Materials":              "XLB",
    "Communication Services": "XLC",
    "Communication":          "XLC",
    "Consumer Staples":       "XLP",
    "Utilities":              "XLU",
    "Real Estate":            "XLRE",
}

# ── ICB → GICS 매핑 (NASDAQ-100 Wikipedia 파싱용) ───────────────
_ICB_TO_GICS = {
    "Technology":             "Information Technology",
    "Consumer Discretionary": "Consumer Discretionary",
    "Health Care":            "Health Care",
    "Utilities":              "Utilities",
    "Industrials":            "Industrials",
    "Energy":                 "Energy",
    "Telecommunications":     "Communication Services",
    "Consumer Staples":       "Consumer Staples",
    "Real Estate":            "Real Estate",
    "Basic Materials":        "Materials",
    "Financials":             "Financials",
}

# ── v3.2 스크리닝 파라미터 ─────────────────────────────────────
ATR_PERIOD = 14
ATR_MULT   = 2.5    # 보수적 전략 기본값 (공격적 1.5 / 균형형 2.0 / 보수적 2.5)
TOP_N      = 10
MAX_WEIGHT = 0.10   # 단일 종목 최대 비중 (v3.0: 0.20 → v3.2: 0.10)

# ── v3.2 스크리닝 임계값 ──────────────────────────────────────
ADX_THRESH = 20     # v3.0: 25 → v3.2: 20 (더 넓은 필터)
RSI_LO     = 50
RSI_HI     = 77     # v3.0: 75 → v3.2: 77
HH_HL_MIN  = 2      # v3.0: 3  → v3.2: 2
PRICE_52W  = 0.75   # v3.0: 0.80 → v3.2: 0.75

# ── v3.1 이후 유지 파라미터 ───────────────────────────────────
REGIME_FILTER_MODE = "info"   # "off" | "info" | "block"
VOL_TARGET         = 0.15     # SPY 변동성 스케일링 목표
HOLD_SPREAD        = 2.5      # Buy/Hold Spread: 보유 종목 Top N×2.5까지 유지
USE_MKTCAP_WEIGHT  = True     # score × sqrt(market_cap) 가중

# ── 복합점수 가중치 ────────────────────────────────────────────
SCORE_WEIGHTS = dict(
    adx      = 0.30,   # ADX (추세 강도)
    ret3m    = 0.20,   # 3개월 수익률
    ret12m   = 0.20,   # 12개월 수익률 (최근 1개월 제외, ret12m_skip1)
    sector   = 0.20,   # 섹터 상대 강도 (ETF 초과수익률)
    vol_stab = 0.10,   # 거래량 안정성
)


# ══════════════════════════════════════════════════════════════
# 동적 유니버스 수집
# ══════════════════════════════════════════════════════════════

def _fetch_sp500() -> tuple[list[str], dict[str, str]]:
    """S&P 500 구성 종목 및 GICS 섹터 수집 (GitHub datasets)."""
    try:
        url = ("https://raw.githubusercontent.com/datasets/"
               "s-and-p-500-companies/main/data/constituents.csv")
        df = pd.read_csv(url)
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        sectors = dict(zip(
            df["Symbol"].str.replace(".", "-", regex=False),
            df["GICS Sector"],
        ))
        logger.info("  S&P500 %d개 종목 수집 완료", len(tickers))
        return tickers, sectors
    except Exception as e:
        logger.warning("  S&P500 수집 실패 (%s)", e)
        return [], {}


def _fetch_nasdaq100() -> tuple[list[str], dict[str, str]]:
    """NASDAQ-100 구성 종목 및 섹터 수집 (Wikipedia)."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            )
        }
        r = requests.get(
            "https://en.wikipedia.org/wiki/Nasdaq-100",
            headers=headers,
            timeout=15,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        ndx = tables[4]
        tickers = ndx["Ticker"].str.replace(".", "-", regex=False).tolist()
        sectors = {
            row["Ticker"].replace(".", "-"): _ICB_TO_GICS.get(
                row["ICB Industry[14]"], row["ICB Industry[14]"]
            )
            for _, row in ndx.iterrows()
        }
        logger.info("  NASDAQ-100 %d개 종목 수집 완료", len(tickers))
        return tickers, sectors
    except Exception as e:
        logger.warning("  NASDAQ-100 수집 실패 (%s)", e)
        return [], {}


def fetch_us_universe() -> tuple[list[str], dict[str, str]]:
    """S&P 500 + NASDAQ 100 동적 수집. 중복 제거 후 (tickers, sectors) 반환."""
    sp500_tickers, sp500_sectors = _fetch_sp500()
    ndx_tickers, ndx_sectors = _fetch_nasdaq100()
    sp500_set = set(sp500_tickers)
    ndx_new = [t for t in ndx_tickers if t not in sp500_set]
    ndx_new_sec = {t: s for t, s in ndx_sectors.items() if t not in sp500_set}
    tickers = sp500_tickers + ndx_new
    sectors = {**sp500_sectors, **ndx_new_sec}
    logger.info(
        "  US 유니버스: S&P500 %d + NASDAQ100 신규 %d = %d종목",
        len(sp500_tickers), len(ndx_new), len(tickers),
    )
    return tickers, sectors


def fetch_kr_universe(kospi_n: int = 200, kosdaq_n: int = 150) -> tuple[list[str], dict[str, str]]:
    """KOSPI 상위 kospi_n + KOSDAQ 상위 kosdaq_n 종목을 pykrx로 수집."""
    try:
        from pykrx import stock as pkstock  # type: ignore
        from datetime import datetime as _dt
        today_str = _dt.now().strftime("%Y%m%d")
        kospi_df = pkstock.get_market_cap_by_ticker(today_str, market="KOSPI")
        kospi_df = kospi_df.sort_values("시가총액", ascending=False).head(kospi_n)
        kospi_tickers = [f"{code}.KS" for code in kospi_df.index.tolist()]
        kosdaq_df = pkstock.get_market_cap_by_ticker(today_str, market="KOSDAQ")
        kosdaq_df = kosdaq_df.sort_values("시가총액", ascending=False).head(kosdaq_n)
        kosdaq_tickers = [f"{code}.KQ" for code in kosdaq_df.index.tolist()]
        all_tickers = kospi_tickers + kosdaq_tickers
        sectors = {t: "Unknown" for t in all_tickers}
        logger.info(
            "  KR 유니버스: KOSPI %d + KOSDAQ %d = %d종목",
            len(kospi_tickers), len(kosdaq_tickers), len(all_tickers),
        )
        return all_tickers, sectors
    except Exception as e:
        logger.warning("  pykrx 유니버스 수집 실패 (%s)", e)
        return [], {}


def fetch_kr_names(tickers: list[str]) -> dict[str, str]:
    """pykrx로 KR 종목명 수집."""
    try:
        from pykrx import stock as pkstock  # type: ignore
        names: dict[str, str] = {}
        for ticker in tickers:
            code = ticker.split(".")[0]
            name = pkstock.get_market_ticker_name(code)
            if name:
                names[ticker] = name
        return names
    except Exception as e:
        logger.warning("  pykrx 종목명 수집 실패 (%s)", e)
        return {}


# ══════════════════════════════════════════════════════════════
# 데이터 다운로드
# ══════════════════════════════════════════════════════════════

def download_tickers(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """yfinance로 US 종목 OHLCV 배치 다운로드."""
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
                except Exception as e:
                    logger.debug("download_tickers: %s 슬라이스 실패 — %s", t, e)
        else:
            if len(raw) >= 60:
                result[tickers[0]] = raw
        return result
    except Exception as e:
        logger.warning("download_tickers: 배치 다운로드 실패 — %s", e)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "detail": str(e)},
        )


def download_kr_pykrx(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """pykrx로 KR 종목 OHLCV 수집. screener_v3 형식(영문 컬럼명)으로 반환."""
    try:
        from pykrx import stock as pkstock  # type: ignore
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "detail": f"pykrx 미설치: {e}"},
        )

    from datetime import datetime as _dt, timedelta
    today = _dt.now()
    end_fmt = today.strftime("%Y%m%d")
    start_fmt = (today - timedelta(days=400)).strftime("%Y%m%d")

    result: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            code = ticker.split(".")[0]
            df = pkstock.get_market_ohlcv_by_date(start_fmt, end_fmt, code)
            if df is None or df.empty or len(df) < 60:
                continue
            rename_map = {
                "시가": "Open", "고가": "High", "저가": "Low",
                "종가": "Close", "거래량": "Volume",
            }
            df = df.rename(columns=rename_map)
            keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            if len(keep) < 4:
                continue
            df = df[keep].copy()
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            df = df[~df.index.duplicated(keep="last")]
            result[ticker] = df
        except Exception as e:
            logger.debug("download_kr_pykrx: %s 실패 — %s", ticker, e)

    return result


# ══════════════════════════════════════════════════════════════
# 기술적 지표 계산
# ══════════════════════════════════════════════════════════════

def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """MA20/50/200, RSI, ADX, VolMA, 52w 고점, ATR 계산."""
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


def count_hh_hl_swing(df_window: pd.DataFrame, n: int = 3) -> int:
    """60일 윈도우에서 HH-HL 스윙 횟수 계산 (상승 추세 확인)."""
    highs = df_window["High"].values
    lows  = df_window["Low"].values
    sh = [highs[i] for i in range(n, len(highs) - n)
          if highs[i] == max(highs[i - n:i + n + 1])]
    sl = [lows[i]  for i in range(n, len(lows) - n)
          if lows[i]  == min(lows[i - n:i + n + 1])]
    hh = sum(sh[i] > sh[i - 1] for i in range(1, len(sh)))
    hl = sum(sl[i] > sl[i - 1] for i in range(1, len(sl)))
    return min(hh, hl)


def calc_atr_stop(df: pd.DataFrame) -> float:
    """최근 20일 고점 - ATR(14) × ATR_MULT 동적 스톱가 계산."""
    atr_val = df["ATR"].dropna().iloc[-1] if "ATR" in df.columns and len(df["ATR"].dropna()) > 0 else np.nan
    if pd.isna(atr_val):
        return np.nan
    peak_20 = float(df["High"].tail(20).max())
    return round(peak_20 - atr_val * ATR_MULT, 2)


def calc_spy_vol_scale(spy_close: pd.Series) -> float:
    """SPY 20일 실현변동성(연환산) 기반 포지션 스케일 팩터 (0~1).
    변동성 낮을수록 포지션 확대, 높을수록 축소.
    """
    ret = spy_close.pct_change().dropna()
    if len(ret) < 20:
        return 1.0
    vol = float(ret.tail(20).std() * np.sqrt(252))
    if vol <= 0:
        return 1.0
    return min(VOL_TARGET / vol, 1.0)


# ══════════════════════════════════════════════════════════════
# 스크리닝 + 랭킹
# ══════════════════════════════════════════════════════════════

def screen_stock(df: pd.DataFrame) -> tuple[bool, dict]:
    """단일 종목 스크리닝. v3.2 임계값 적용."""
    if len(df) < 200:
        return False, {}
    row = df.iloc[-1]
    r5, r20, r60, r63 = df.tail(6), df.tail(20), df.tail(60), df.tail(63)

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

    if count_hh_hl_swing(r60) < HH_HL_MIN:
        return False, {}

    high52 = row.get("High52w", np.nan)
    if not pd.isna(high52) and high52 > 0 and row["Close"] < high52 * PRICE_52W:
        return False, {}

    ret3m = float(df["Close"].iloc[-1] / r63["Close"].iloc[0]) - 1 if len(r63) >= 60 else np.nan
    vol_cv   = r20["Volume"].std() / (vol60 + 1e-9)
    vol_stab = float(1 / (vol_cv + 1e-6))

    # ret12m_skip1: 252일 수익률, 최근 21일 제외 (형성 기간 확장)
    n = len(df)
    if n >= 273:
        ret12m_skip1 = float(df["Close"].iloc[-22] / df["Close"].iloc[-273]) - 1
    elif n >= 252:
        ret12m_skip1 = float(df["Close"].iloc[-22] / df["Close"].iloc[-252]) - 1
    else:
        ret12m_skip1 = np.nan

    stop_price = calc_atr_stop(df)
    cur_price  = float(df["Close"].iloc[-1])

    # 현재가가 ATR 스톱 이하인 종목 제외 (스톱 트리거 상태)
    if not pd.isna(stop_price) and cur_price <= stop_price:
        return False, {}

    stop_dist = (stop_price - cur_price) / cur_price if not pd.isna(stop_price) else np.nan

    return True, {
        "ADX":          float(adx),
        "RSI":          float(rsi),
        "ret3m":        ret3m,
        "ret12m_skip1": ret12m_skip1,
        "vol_stab":     vol_stab,
        "price":        cur_price,
        "stop_price":   stop_price,
        "stop_dist":    stop_dist,
        "atr":          float(df["ATR"].dropna().iloc[-1])
                        if "ATR" in df.columns and len(df["ATR"].dropna()) > 0 else np.nan,
    }


def minmax(s: pd.Series) -> pd.Series:
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)


def calc_position_weights(scores: pd.Series, max_w: float = MAX_WEIGHT) -> pd.Series:
    """점수 비례 포지션 비중 계산 (단일 종목 max_w 상한 + 반복 재배분)."""
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


def rank_stocks(
    passed: dict,
    etf_data: dict,
    universe: dict,
    market_caps: dict | None = None,
) -> pd.DataFrame:
    """복합점수 계산 및 정렬.

    Args:
        passed: {ticker: metrics_dict} 스크리닝 통과 종목
        etf_data: {etf_ticker: df} 섹터 ETF 데이터
        universe: {ticker: sector} 유니버스 섹터 매핑
        market_caps: {ticker: float} 시가총액 (None이면 가중 비활성)
    """
    if not passed:
        return pd.DataFrame()
    df = pd.DataFrame(passed).T
    df["sector"] = [universe.get(t, "Unknown") for t in df.index]

    # ETF 초과수익률 기준 섹터 강도
    df["sec_str"] = 0.0
    for idx, row in df.iterrows():
        sec     = row["sector"]
        etf_sym = SECTOR_ETF.get(sec)
        if etf_sym and etf_sym in etf_data:
            etf_close = etf_data[etf_sym]["Close"]
            if len(etf_close) >= 63:
                etf_ret = float(etf_close.iloc[-1] / etf_close.iloc[-63]) - 1
                df.loc[idx, "sec_str"] = (row["ret3m"] - etf_ret) if not pd.isna(row["ret3m"]) else 0.0
    df["sec_str_norm"] = minmax(df["sec_str"])

    ret12m_col = df["ret12m_skip1"].fillna(0) if "ret12m_skip1" in df.columns else pd.Series(0.0, index=df.index)
    df["score"] = (
        minmax(df["ADX"])                  * SCORE_WEIGHTS["adx"]     +
        minmax(df["ret3m"].fillna(0))      * SCORE_WEIGHTS["ret3m"]   +
        minmax(ret12m_col)                 * SCORE_WEIGHTS["ret12m"]  +
        minmax(df["sec_str_norm"])         * SCORE_WEIGHTS["sector"]  +
        minmax(df["vol_stab"])             * SCORE_WEIGHTS["vol_stab"]
    )

    # 시가총액 가중: score × sqrt(market_cap)
    if USE_MKTCAP_WEIGHT and market_caps:
        df["mktcap"] = [market_caps.get(t, 1.0) for t in df.index]
        df["mktcap"] = df["mktcap"].clip(lower=1.0)
        df["score"]  = df["score"] * np.sqrt(df["mktcap"])

    return df.sort_values("score", ascending=False)


def check_market() -> dict:
    """SPY MA20 vs MA60 골든/데드크로스 확인.

    Raises:
        HTTPException(500): SPY 데이터를 가져올 수 없을 때
    """
    try:
        spy   = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
        close = spy["Close"].squeeze()
        ma20  = float(close.rolling(20).mean().iloc[-1])
        ma60  = float(close.rolling(60).mean().iloc[-1])
        price = float(close.iloc[-1])
        gap   = (ma20 - ma60) / ma60 * 100
        return {
            "price": price, "ma20": ma20, "ma60": ma60,
            "gap_pct": gap, "is_golden": ma20 > ma60,
            "close": close,
        }
    except Exception as e:
        logger.error("check_market: SPY 다운로드 실패 — %s", e)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal server error", "detail": str(e)},
        )


# ══════════════════════════════════════════════════════════════
# 메인 스크리닝 파이프라인
# ══════════════════════════════════════════════════════════════

def run_screening(market: str = "US", held_tickers: list[str] | None = None) -> dict:
    """전체 스크리닝 파이프라인 실행.

    Args:
        market: "US" (S&P500+NASDAQ100) 또는 "KR" (KOSPI200+KOSDAQ150)
        held_tickers: 현재 보유 종목 — Buy/Hold Spread 적용
    Returns:
        스크리닝 결과 dict
    Raises:
        HTTPException(500): 유니버스 수집 실패 또는 데이터 다운로드 실패
    """
    global ALL_UNIVERSE, KR_NAMES
    if held_tickers is None:
        held_tickers = []

    # ── 시장 레짐 필터 (US only) ──────────────────────────────
    market_obj = None
    vol_scale  = 1.0
    if market == "US":
        market_obj = check_market()  # 실패 시 HTTPException(500) 발생
        spy_close_series = market_obj["close"]
        if REGIME_FILTER_MODE == "block" and not market_obj["is_golden"]:
            return {
                "market": {k: v for k, v in market_obj.items() if k != "close"},
                "regime_blocked": True,
                "total_screened": 0,
                "total_passed": 0,
                "results": [],
            }
        vol_scale = calc_spy_vol_scale(spy_close_series)

    # ── 유니버스 수집 ─────────────────────────────────────────
    if market == "KR":
        tickers, sectors = fetch_kr_universe()
        if not tickers:
            raise HTTPException(
                status_code=500,
                detail={"error": "Internal server error", "detail": "KR 유니버스 수집 실패"},
            )
        ALL_UNIVERSE.update(sectors)
        all_data_raw: dict = {}
        for i in range(0, len(tickers), 30):
            all_data_raw.update(download_kr_pykrx(tickers[i:i + 30]))
    else:  # US
        tickers, sectors = fetch_us_universe()
        if not tickers:
            raise HTTPException(
                status_code=500,
                detail={"error": "Internal server error", "detail": "US 유니버스 수집 실패"},
            )
        ALL_UNIVERSE.update(sectors)
        all_data_raw = {}
        for i in range(0, len(tickers), 50):
            all_data_raw.update(download_tickers(tickers[i:i + 50]))

    # ── ETF 데이터 ────────────────────────────────────────────
    etf_data: dict = {}
    try:
        etf_raw = download_tickers(list(set(SECTOR_ETF.values())))
        for t, df in etf_raw.items():
            etf_data[t] = calc_indicators(df)
    except HTTPException:
        pass  # ETF 실패 시 섹터 강도 없이 진행

    # ── 스크리닝 ──────────────────────────────────────────────
    passed: dict = {}
    for t, df in all_data_raw.items():
        df_ind = calc_indicators(df)
        ok, metrics = screen_stock(df_ind)
        if ok:
            passed[t] = metrics

    # ── 시가총액 수집 (US only) ───────────────────────────────
    market_caps: dict = {}
    if USE_MKTCAP_WEIGHT and passed and market == "US":
        for t in passed:
            try:
                mc = yf.Ticker(t).fast_info.market_cap
                market_caps[t] = float(mc) if mc and mc > 0 else 1.0
            except Exception as e:
                logger.debug("market_cap: %s 실패 — %s", t, e)
                market_caps[t] = 1.0

    # ── KR 종목명 수집 ────────────────────────────────────────
    if market == "KR" and passed:
        names = fetch_kr_names(list(passed.keys()))
        KR_NAMES.update(names)

    # ── 랭킹 ──────────────────────────────────────────────────
    ranked = rank_stocks(passed, etf_data, ALL_UNIVERSE, market_caps)

    # ── Buy/Hold Spread ───────────────────────────────────────
    hold_n  = int(TOP_N * HOLD_SPREAD)
    top_new = ranked.head(TOP_N) if len(ranked) > 0 else ranked

    if held_tickers and len(ranked) > 0:
        hold_extended = ranked.head(hold_n)
        held_valid    = [t for t in held_tickers if t in hold_extended.index]
        held_extra    = [t for t in held_valid if t not in top_new.index]
        top = pd.concat([top_new, ranked.loc[held_extra]]) if held_extra else top_new
    else:
        top = top_new

    # ── 포지션 비중 계산 ──────────────────────────────────────
    results = []
    if len(top) > 0:
        raw_weights = calc_position_weights(top["score"])
        weights     = raw_weights * vol_scale

        for rank_idx, (ticker, row) in enumerate(top.iterrows(), 1):
            is_kr = ticker.endswith(".KS") or ticker.endswith(".KQ")
            results.append({
                "rank":           rank_idx,
                "ticker":         ticker,
                "market":         "KR" if is_kr else "US",
                "name":           KR_NAMES.get(ticker) if is_kr else None,
                "sector":         ALL_UNIVERSE.get(ticker, "Unknown"),
                "score":          float(row["score"]),
                "weight_pct":     float(weights[ticker]) * 100,
                "weight_raw_pct": float(raw_weights[ticker]) * 100,
                "price":          float(row["price"]),
                "adx":            float(row["ADX"])          if not pd.isna(row["ADX"])        else None,
                "rsi":            float(row["RSI"])          if not pd.isna(row["RSI"])        else None,
                "ret_3m":         float(row["ret3m"])        if not pd.isna(row["ret3m"])      else None,
                "ret_12m_skip1":  float(row["ret12m_skip1"]) if "ret12m_skip1" in row and not pd.isna(row["ret12m_skip1"]) else None,
                "stop_price":     float(row["stop_price"])   if not pd.isna(row["stop_price"]) else None,
                "stop_dist_pct":  float(row["stop_dist"]) * 100 if not pd.isna(row.get("stop_dist")) else None,
                "atr":            float(row["atr"])          if not pd.isna(row["atr"])        else None,
                "is_held":        ticker in held_tickers,
            })

    market_out = {k: v for k, v in market_obj.items() if k != "close"} if market_obj else None

    market_regime = None
    if REGIME_FILTER_MODE == "info" and market_obj:
        market_regime = {
            "golden_cross": market_obj["is_golden"],
            "spy_ma20":     round(market_obj["ma20"], 2),
            "spy_ma60":     round(market_obj["ma60"], 2),
            "gap_pct":      round(market_obj["gap_pct"], 2),
        }

    return {
        "market":         market_out,
        "market_regime":  market_regime,
        "vol_scale":      vol_scale,
        "regime_blocked": False,
        "total_screened": len(all_data_raw),
        "total_passed":   len(passed),
        "results":        results,
    }
