"""
백테스트: 하이브리드 진입 전략 비교
══════════════════════════════════════════════════════════════
핵심 아이디어:
  기존 전략(A)은 '종목 레벨' MA 정배열을 사용했으나,
  시장 레벨(SPY)의 바닥 확인은 '스크리닝 활성화 타이밍' 역할만 한다.
  개별 종목 선별은 기존 v3 MA 정배열(ADX≥20, RSI 50~77, MA20>MA50>MA200)을 유지.

비교 전략:
  A) 기존 방식       : MA20>MA50>MA200 정배열, 시장 상태 무관하게 항상 스크리닝
  B) 하이브리드      : SPY 바닥 확인 → 스크리닝 활성화 + 개별 종목 MA 정배열 유지
  C) 하이브리드+3단계: B + SPY 기반 3단계 점진 진입
  D) SPY 벤치마크

시장 레벨 타이밍 (SPY):
  - Dead Cross : SPY MA20 < MA60 → 하락 국면, 스크리닝 비활성화 / 포지션 축소
  - 바닥 확인  : 데드크로스 이후 30일 저점 미갱신 → 스크리닝 재활성화
  - 2단계 신호 : SPY MA50 기울기 양전환 (하락→상승)
  - 골든크로스 : SPY MA50 > MA200 → 풀 투자

개별 종목 필터 (기존 v3 파라미터 유지):
  ADX≥20, RSI 50~77, MA20>MA50>MA200 정배열,
  HH-HL≥2(60d), 52주고점≥75%, 거래량스파이크 3배 필터

수수료: 편도 0.2% (왕복 0.4%, 턴오버 비례)
기간  : 2015-01-01 ~ 현재
══════════════════════════════════════════════════════════════
"""
import logging
import warnings
warnings.filterwarnings("ignore")

import sys
import numpy as np
import pandas as pd
import yfinance as yf
import pandas_ta as ta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# 공용 데이터 캐시 모듈 (scripts/data_cache.py)
sys.path.insert(0, str(Path(__file__).parent.parent))
from data_cache import load_full_universe

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── 파라미터 ───────────────────────────────────────────────────
START         = "2015-01-01"
END           = datetime.today().strftime("%Y-%m-%d")
COMMISSION    = 0.002    # 편도 0.2%
TOP_N         = 10
MAX_WEIGHT    = 0.10
ATR_PERIOD    = 14
ATR_MULT      = 2.0      # 균형형

ADX_THRESH    = 20
RSI_LO        = 50
RSI_HI        = 77
HH_HL_MIN     = 2
HH_HL_WINDOW  = 60
PRICE_52W_THR = 0.75
VOL_SPIKE     = 3.0
DAILY_MOVE    = 0.10
CONFIRM_DAYS  = 30       # 30 영업일 바닥 미갱신 → SPY 바닥 확인

WEIGHTS = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)

# ── 섹터 ETF ──────────────────────────────────────────────────
SECTOR_ETF = {
    "Technology":    "XLK",
    "Health Care":   "XLV",
    "Financials":    "XLF",
    "Consumer Disc": "XLY",
    "Industrials":   "XLI",
    "Energy":        "XLE",
    "Materials":     "XLB",
    "Communication": "XLC",
}

# ── 유니버스 (S&P500 + Nasdaq100 대표 + KOSPI/KOSDAQ) ─────────
US_UNIVERSE = {
    # Technology
    "NVDA":"Technology","AAPL":"Technology","MSFT":"Technology","AVGO":"Technology",
    "AMD":"Technology","QCOM":"Technology","AMAT":"Technology","LRCX":"Technology",
    "MU":"Technology","KLAC":"Technology","ORCL":"Technology","ADBE":"Technology",
    "CRM":"Technology","NOW":"Technology","PANW":"Technology","SNPS":"Technology",
    "CDNS":"Technology","MRVL":"Technology","TXN":"Technology","INTC":"Technology",
    "IBM":"Technology","DELL":"Technology",
    # Communication
    "META":"Communication","GOOGL":"Communication","NFLX":"Communication",
    "TMUS":"Communication","DIS":"Communication","CMCSA":"Communication","T":"Communication",
    # Consumer Disc
    "AMZN":"Consumer Disc","TSLA":"Consumer Disc","HD":"Consumer Disc","LULU":"Consumer Disc",
    "NKE":"Consumer Disc","SBUX":"Consumer Disc","MCD":"Consumer Disc","LOW":"Consumer Disc",
    "TGT":"Consumer Disc","BKNG":"Consumer Disc","COST":"Consumer Disc","WMT":"Consumer Disc",
    # Health Care
    "LLY":"Health Care","UNH":"Health Care","ABBV":"Health Care","ISRG":"Health Care",
    "VRTX":"Health Care","MRK":"Health Care","JNJ":"Health Care","PFE":"Health Care",
    "TMO":"Health Care","DHR":"Health Care","AMGN":"Health Care","GILD":"Health Care",
    # Financials
    "V":"Financials","MA":"Financials","JPM":"Financials","GS":"Financials",
    "BAC":"Financials","WFC":"Financials","BLK":"Financials","SCHW":"Financials",
    "AXP":"Financials","MS":"Financials",
    # Energy
    "XOM":"Energy","CVX":"Energy","SLB":"Energy","COP":"Energy","EOG":"Energy",
    # Industrials
    "CAT":"Industrials","GE":"Industrials","ETN":"Industrials","LMT":"Industrials",
    "RTX":"Industrials","HON":"Industrials","UNP":"Industrials","BA":"Industrials",
    # Materials
    "FCX":"Materials","NEM":"Materials","LIN":"Materials","APD":"Materials",
}
KR_UNIVERSE = {
    # KOSPI Technology
    "005930.KS":"Technology","000660.KS":"Technology","009150.KS":"Technology",
    "006400.KS":"Technology","373220.KS":"Technology",
    # KOSPI Health Care
    "207940.KS":"Health Care","068270.KS":"Health Care","091990.KS":"Health Care",
    # KOSPI Materials/Consumer/Communication/Financials/Energy/Industrials
    "051910.KS":"Materials","011170.KS":"Materials",
    "005380.KS":"Consumer Disc","000270.KS":"Consumer Disc",
    "035420.KS":"Communication","035720.KS":"Communication",
    "105560.KS":"Financials","055550.KS":"Financials",
    "096770.KS":"Energy","011200.KS":"Industrials","009540.KS":"Industrials",
    # KOSDAQ
    "263750.KQ":"Technology","293490.KQ":"Technology","357780.KQ":"Technology",
    "086900.KQ":"Technology",
}
ALL_UNIVERSE = {**US_UNIVERSE, **KR_UNIVERSE}


# ══════════════════════════════════════════════════════════════
# 데이터 다운로드
# ══════════════════════════════════════════════════════════════
def download_all(tickers: list, start: str, end: str) -> dict:
    data = {}
    for i in range(0, len(tickers), 40):
        chunk = tickers[i:i + 40]
        try:
            raw = yf.download(chunk, start=start, end=end,
                              auto_adjust=True, progress=False, threads=True)
            if raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                for t in chunk:
                    try:
                        df = raw.xs(t, axis=1, level=1).dropna(how="all")
                        if len(df) >= 220:
                            data[t] = df
                    except KeyError:
                        pass
            else:
                if len(raw) >= 220:
                    data[chunk[0]] = raw
        except Exception as e:
            logging.debug("backtest_hybrid_entry download_all: 배치(offset=%d) 다운로드 실패 — %s", i, e)
    return data


# ══════════════════════════════════════════════════════════════
# 지표 계산
# ══════════════════════════════════════════════════════════════
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
    d["MA20"]    = ta.sma(c, 20)
    d["MA50"]    = ta.sma(c, 50)
    d["MA60"]    = ta.sma(c, 60)   # SPY 데드크로스 감지용
    d["MA200"]   = ta.sma(c, 200)
    d["RSI"]     = ta.rsi(c, 14)
    adx_res      = ta.adx(h, l, c, 14)
    d["ADX"]     = adx_res["ADX_14"] if adx_res is not None and "ADX_14" in adx_res.columns else np.nan
    d["VolMA20"] = v.rolling(20).mean()
    d["VolMA60"] = v.rolling(60).mean()
    d["High52w"] = h.rolling(252).max()
    atr_res      = ta.atr(h, l, c, length=ATR_PERIOD)
    d["ATR"]     = atr_res if atr_res is not None else np.nan
    return d


# ══════════════════════════════════════════════════════════════
# HH-HL 스윙 카운트
# ══════════════════════════════════════════════════════════════
def swing_hh_hl(df_win: pd.DataFrame, n: int = 3) -> int:
    highs = df_win["High"].values
    lows  = df_win["Low"].values
    sh = [highs[i] for i in range(n, len(highs) - n)
          if highs[i] == max(highs[i - n:i + n + 1])]
    sl = [lows[i]  for i in range(n, len(lows) - n)
          if lows[i] == min(lows[i - n:i + n + 1])]
    return min(
        sum(sh[i] > sh[i - 1] for i in range(1, len(sh))),
        sum(sl[i] > sl[i - 1] for i in range(1, len(sl))),
    )


def minmax(s: pd.Series) -> pd.Series:
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)


# ══════════════════════════════════════════════════════════════
# SPY 시장 상태 감지 (핵심: 시장 레벨 타이밍)
# ══════════════════════════════════════════════════════════════
def detect_spy_market_state(spy_hist: pd.DataFrame,
                             confirm_days: int = CONFIRM_DAYS) -> dict:
    """
    SPY 데이터를 기준으로 시장 상태를 판별한다.

    Returns
    -------
    dict with keys:
      state        : "dead_cross" | "bottom_confirmed" | "stage2" | "golden_cross" | "neutral"
      stage        : 0 (dead_cross/관망) | 1 (바닥확인) | 2 (MA50 반등) | 3 (골든크로스)
      weight_mult  : 0.0 | 0.50 | 0.80 | 1.00
      bottom_date  : Timestamp | None
      days_since   : int | None

    State 우선순위: golden_cross > stage2 > bottom_confirmed > dead_cross > neutral
    """
    result = {
        "state":       "neutral",
        "stage":       0,
        "weight_mult": 0.0,
        "bottom_date": None,
        "days_since":  None,
    }

    if spy_hist is None or len(spy_hist) < 220:
        return result

    ma20  = spy_hist["MA20"]
    ma50  = spy_hist["MA50"]
    ma60  = spy_hist["MA60"]
    ma200 = spy_hist["MA200"]
    lows  = spy_hist["Low"]

    # 현재 MA 값
    if ma20.isna().all() or ma60.isna().all():
        return result

    cur_ma20 = float(ma20.iloc[-1]) if not pd.isna(ma20.iloc[-1]) else None
    cur_ma50 = float(ma50.iloc[-1]) if not pd.isna(ma50.iloc[-1]) else None
    cur_ma60 = float(ma60.iloc[-1]) if not pd.isna(ma60.iloc[-1]) else None
    cur_ma200 = float(ma200.iloc[-1]) if not pd.isna(ma200.iloc[-1]) else None

    if any(v is None for v in [cur_ma20, cur_ma50, cur_ma60, cur_ma200]):
        return result

    # ── 1) 골든크로스 확인: MA50 > MA200
    if cur_ma50 > cur_ma200:
        # 골든크로스 상태 (최고 단계) → 풀 투자
        result["state"]       = "golden_cross"
        result["stage"]       = 3
        result["weight_mult"] = 1.00
        return result

    # ── 2) 가장 최근 데드크로스 탐색 (최근 250일 이내)
    lookback = min(250, len(spy_hist) - 1)
    death_pos = None
    for i in range(len(spy_hist) - 1, len(spy_hist) - lookback - 1, -1):
        if i < 1:
            break
        m20_t  = ma20.iloc[i];   m60_t  = ma60.iloc[i]
        m20_t1 = ma20.iloc[i-1]; m60_t1 = ma60.iloc[i-1]
        if any(pd.isna(v) for v in [m20_t, m60_t, m20_t1, m60_t1]):
            continue
        if m20_t < m60_t and m20_t1 >= m60_t1:
            death_pos = i
            break

    # 데드크로스가 없으면 — 중립 상태 (항상 스크리닝 활성화)
    if death_pos is None:
        result["state"]       = "neutral"
        result["stage"]       = 3  # 중립=데드크로스 없음 → 풀 투자
        result["weight_mult"] = 1.00
        return result

    # ── 3) 현재 MA20 < MA60 여부 확인 (여전히 데드크로스 상태)
    if cur_ma20 < cur_ma60:
        # 아직 데드크로스 유지 중 → 바닥 확인은 했는지 체크
        # 데드크로스 이후 최저점 탐색
        post_death_lows = lows.iloc[death_pos:]
        if len(post_death_lows) < confirm_days + 1:
            result["state"]       = "dead_cross"
            result["stage"]       = 0
            result["weight_mult"] = 0.0
            return result

        low_idx   = post_death_lows.idxmin()
        low_pos   = spy_hist.index.get_loc(low_idx)
        low_price = float(lows.loc[low_idx])

        days_since = len(spy_hist) - 1 - low_pos
        if days_since < confirm_days:
            result["state"]       = "dead_cross"
            result["stage"]       = 0
            result["weight_mult"] = 0.0
            return result

        # 저점 이후 신저점 발생 여부
        post_low_lows = lows.iloc[low_pos + 1:]
        if len(post_low_lows) > 0 and post_low_lows.min() < low_price:
            result["state"]       = "dead_cross"
            result["stage"]       = 0
            result["weight_mult"] = 0.0
            return result

        # 바닥 확인! — MA50 기울기 체크
        ma50_valid = ma50.dropna()
        if len(ma50_valid) >= 6:
            ma50_slope = float(ma50_valid.iloc[-1]) - float(ma50_valid.iloc[-6])
            if ma50_slope > 0:
                result["state"]       = "stage2"
                result["stage"]       = 2
                result["weight_mult"] = 0.80
                result["bottom_date"] = low_idx
                result["days_since"]  = days_since
                return result

        result["state"]       = "bottom_confirmed"
        result["stage"]       = 1
        result["weight_mult"] = 0.50
        result["bottom_date"] = low_idx
        result["days_since"]  = days_since
        return result

    else:
        # 데드크로스 이후 골든크로스 복구 전 (MA20 > MA60이지만 MA50 < MA200)
        # MA50 기울기 확인
        ma50_valid = ma50.dropna()
        if len(ma50_valid) >= 6:
            ma50_slope = float(ma50_valid.iloc[-1]) - float(ma50_valid.iloc[-6])
            if ma50_slope > 0:
                result["state"]       = "stage2"
                result["stage"]       = 2
                result["weight_mult"] = 0.80
                return result

        # 바닥 확인 이후 회복 중
        result["state"]       = "bottom_confirmed"
        result["stage"]       = 1
        result["weight_mult"] = 0.50
        return result


# ══════════════════════════════════════════════════════════════
# 공통 필터 (RSI, 거래량, 변동성, HH-HL, 52주고점, ATR 스톱)
# ══════════════════════════════════════════════════════════════
def _common_filters(hist: pd.DataFrame, row: pd.Series, adx: float,
                    atr_mult: float = ATR_MULT) -> tuple:
    """
    v3 표준 필터 — RSI 조건 포함 (MA 정배열 방식 유지)
    Returns (ok: bool, metrics: dict)
    """
    r5  = hist.tail(6)
    r20 = hist.tail(20)
    r60 = hist.tail(HH_HL_WINDOW)
    r63 = hist.tail(63)

    # RSI 필터
    rsi = row.get("RSI", np.nan)
    if pd.isna(rsi) or not (RSI_LO <= rsi <= RSI_HI):
        return False, {}

    # 거래량 스파이크
    vol60 = row.get("VolMA60", np.nan)
    if pd.isna(vol60) or vol60 == 0 or (r20["Volume"] > vol60 * VOL_SPIKE).any():
        return False, {}

    # 단기 급등락
    if (r5["Close"].pct_change().abs() > DAILY_MOVE).any():
        return False, {}

    # HH-HL (스윙 추세 확인)
    if len(r60) >= 2 * 3 + 1 and swing_hh_hl(r60) < HH_HL_MIN:
        return False, {}

    # 52주 고점 대비 가격
    high52 = row.get("High52w", np.nan)
    if not pd.isna(high52) and high52 > 0 and row["Close"] < high52 * PRICE_52W_THR:
        return False, {}

    # 수익률 지표
    ret3m    = float(hist["Close"].iloc[-1] / r63["Close"].iloc[0]) - 1 \
               if len(r63) >= 60 else np.nan
    vol_cv   = r20["Volume"].std() / (vol60 + 1e-9)
    vol_stab = float(1 / (vol_cv + 1e-6))

    # ATR 스톱
    atr_series = hist["ATR"].dropna() if "ATR" in hist.columns else pd.Series(dtype=float)
    atr_val    = float(atr_series.iloc[-1]) if len(atr_series) > 0 else np.nan
    peak20     = float(hist["High"].tail(20).max())
    atr_stop   = peak20 - atr_val * atr_mult if not pd.isna(atr_val) else np.nan

    # 현재가가 이미 ATR 스톱 이하인 종목은 제외 (스톱 트리거 상태)
    cur_price = float(hist["Close"].iloc[-1])
    if not pd.isna(atr_stop) and cur_price <= atr_stop:
        return False, {}

    return True, {
        "ADX":      float(adx),
        "RSI":      float(rsi),
        "ret3m":    ret3m,
        "vol_stab": vol_stab,
        "price":    float(hist["Close"].iloc[-1]),
        "atr_stop": atr_stop,
        "atr":      atr_val,
    }


# ══════════════════════════════════════════════════════════════
# 전략별 스크리닝 함수
# ══════════════════════════════════════════════════════════════
def screen_A(df: pd.DataFrame, as_of, atr_mult: float = ATR_MULT) -> tuple:
    """
    전략 A — 기존 방식: MA20 > MA50 > MA200 정배열
    시장 상태 무관하게 항상 스크리닝
    """
    hist = df[df.index <= as_of]
    if len(hist) < 220:
        return False, {}
    row  = hist.iloc[-1]
    adx  = row.get("ADX", np.nan)
    if pd.isna(adx) or adx < ADX_THRESH:
        return False, {}
    ma20, ma50, ma200 = row.get("MA20"), row.get("MA50"), row.get("MA200")
    if any(pd.isna(v) for v in [ma20, ma50, ma200]) or not (ma20 > ma50 > ma200):
        return False, {}
    return _common_filters(hist, row, adx, atr_mult)


def screen_B(df: pd.DataFrame, as_of, market_state: dict,
             atr_mult: float = ATR_MULT) -> tuple:
    """
    전략 B — 하이브리드:
    - 시장 레벨: SPY 바닥 확인 시에만 스크리닝 활성화
    - 종목 레벨: 기존 v3 MA 정배열 (MA20>MA50>MA200) 유지
    - SPY 데드크로스(stage=0) 시 비활성화
    """
    # 시장 상태 체크: stage 0이면 스크리닝 안 함
    if market_state["stage"] == 0:
        return False, {}

    hist = df[df.index <= as_of]
    if len(hist) < 220:
        return False, {}
    row  = hist.iloc[-1]
    adx  = row.get("ADX", np.nan)
    if pd.isna(adx) or adx < ADX_THRESH:
        return False, {}
    # 종목 레벨: 기존 MA 정배열 유지
    ma20, ma50, ma200 = row.get("MA20"), row.get("MA50"), row.get("MA200")
    if any(pd.isna(v) for v in [ma20, ma50, ma200]) or not (ma20 > ma50 > ma200):
        return False, {}
    return _common_filters(hist, row, adx, atr_mult)


def screen_C(df: pd.DataFrame, as_of, market_state: dict,
             atr_mult: float = ATR_MULT) -> tuple:
    """
    전략 C — 하이브리드 + 3단계 점진 진입:
    B와 동일한 종목 선별 + SPY 단계별 포지션 비중 조절
    """
    ok, m = screen_B(df, as_of, market_state, atr_mult)
    if ok:
        m["market_stage"]   = market_state["stage"]
        m["market_wt_mult"] = market_state["weight_mult"]
    return ok, m


# ══════════════════════════════════════════════════════════════
# 랭킹 & 포지션 사이징
# ══════════════════════════════════════════════════════════════
def rank_stocks(passed: dict, etf_data: dict, as_of) -> pd.DataFrame:
    if not passed:
        return pd.DataFrame()
    df = pd.DataFrame(passed).T
    df["sector"]  = [ALL_UNIVERSE.get(t, "Unknown") for t in df.index]
    df["sec_str"] = 0.0
    for idx, row in df.iterrows():
        sym = SECTOR_ETF.get(row["sector"])
        if sym and sym in etf_data:
            ec = etf_data[sym][etf_data[sym].index <= as_of]["Close"]
            if len(ec) >= 63:
                df.loc[idx, "sec_str"] = (
                    row["ret3m"] - float(ec.iloc[-1] / ec.iloc[-63] - 1)
                ) if not pd.isna(row["ret3m"]) else 0.0
    df["sec_n"] = minmax(df["sec_str"])
    df["score"] = (
        minmax(df["ADX"])                    * WEIGHTS["adx"] +
        minmax(df["ret3m"].fillna(0))        * WEIGHTS["ret3m"] +
        minmax(df["sec_n"])                  * WEIGHTS["sector"] +
        minmax(df["vol_stab"])               * WEIGHTS["vol_stab"]
    )
    return df.sort_values("score", ascending=False)


def position_weights(scores: pd.Series, market_wt_mult: float = 1.0,
                     max_w: float = MAX_WEIGHT) -> pd.Series:
    """
    점수 비례 가중치 (상한 max_w).
    market_wt_mult: SPY 단계별 전체 포지션 비율 (0.5/0.8/1.0)
    → 전체 포트폴리오 중 (1 - market_wt_mult) 는 현금으로 유지
    """
    n = len(scores)
    if n == 0:
        return pd.Series(dtype=float)
    adj = scores.copy().clip(lower=1e-9)
    w   = adj / adj.sum()
    # 상한 클리핑 (반복 수렴)
    for _ in range(20):
        if (w <= max_w + 1e-8).all():
            break
        excess = (w - max_w).clip(lower=0).sum()
        w      = w.clip(upper=max_w)
        under  = w < max_w
        if under.sum() > 0:
            w[under] += excess * w[under] / w[under].sum()
    w = w / w.sum()
    # 시장 단계별 전체 비중 조절 (나머지는 현금)
    w = w * market_wt_mult
    return w


# ══════════════════════════════════════════════════════════════
# 월중 ATR 스톱 체크
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
            day_px = df_t[df_t.index <= day]["Close"]
            if len(day_px) == 0:
                continue
            cur_px   = float(day_px.iloc[-1])
            new_peak = max(info["peak"], cur_px)
            info["peak"] = new_peak
            stop = info.get("atr_stop", np.nan)
            if not pd.isna(stop) and cur_px <= stop:
                to_remove.append(ticker)
        for t in to_remove:
            del holdings[t]
    return holdings


# ══════════════════════════════════════════════════════════════
# SPY 데이터에서 월별 시장 상태 캐시 생성
# ══════════════════════════════════════════════════════════════
def build_spy_state_cache(spy_data: pd.DataFrame,
                           rebal_dates: pd.DatetimeIndex) -> dict:
    """
    각 리밸런싱 날짜에 대한 SPY 시장 상태를 미리 계산하여 캐시로 반환.
    """
    cache = {}
    for rd in rebal_dates:
        spy_hist = spy_data[spy_data.index <= rd]
        cache[rd] = detect_spy_market_state(spy_hist)
    return cache


# ══════════════════════════════════════════════════════════════
# 백테스트 메인 루프
# ══════════════════════════════════════════════════════════════
def run_backtest(all_data: dict, etf_data: dict, spy_data: pd.DataFrame,
                 strategy: str = "A",
                 atr_mult: float = ATR_MULT,
                 top_n: int = TOP_N,
                 rebal_freq: str = "BME",
                 adaptive: bool = False) -> list:
    """
    strategy   : "A" | "B" | "C"
    atr_mult   : ATR 스톱 배수
    top_n      : 상위 종목 수
    rebal_freq : 리밸런싱 주기 (pandas offset alias)
    adaptive   : True이면 시장 국면별로 atr_mult/top_n 동적 전환
                 (데드크로스→ATR2.5/TOP7, 바닥/stage2→ATR2.0/TOP10, 골든/중립→ATR1.5/TOP15)
    Returns rebal-period NAV list (시작=1.0)
    """
    rebal_dates = pd.date_range(start=START, end=END, freq=rebal_freq)

    # SPY 시장 상태 캐시 (B, C 전략 또는 adaptive용)
    spy_state_cache = {}
    if strategy in ("B", "C") or adaptive:
        logger.debug(f"  SPY 시장 상태 캐시 생성 중 ({len(rebal_dates)}개 날짜)...")
        spy_state_cache = build_spy_state_cache(spy_data, rebal_dates)
        logger.debug("  SPY 시장 상태 캐시 생성 완료")

    nav      = [1.0]
    holdings = {}
    prev_dt  = None

    for rd in rebal_dates:
        # ── 시장 상태 (B, C 전략 또는 adaptive)
        market_state = spy_state_cache.get(rd, {
            "state": "neutral", "stage": 3, "weight_mult": 1.0,
            "bottom_date": None, "days_since": None,
        })

        # ── adaptive: 국면별 파라미터 동적 전환
        cur_atr_mult = atr_mult
        cur_top_n    = top_n
        if adaptive:
            stage = market_state.get("stage", 3)
            if stage == 0:                    # 데드크로스 → 보수적
                cur_atr_mult, cur_top_n = 2.5, 7
            elif stage in (1, 2):            # 바닥확인/Stage2 → 균형형
                cur_atr_mult, cur_top_n = 2.0, 10
            else:                            # 골든크로스/중립 → 공격적
                cur_atr_mult, cur_top_n = 1.5, 15

        # ── 구간 스톱 체크
        if prev_dt and holdings:
            holdings = check_stops(holdings, all_data, prev_dt, rd)

        # ── 시장 데드크로스 시 포지션 청산 (B, C 전략)
        if strategy in ("B", "C") and market_state["stage"] == 0 and holdings:
            holdings = {}  # 전량 현금화

        # ── 구간 수익 반영
        if prev_dt and holdings:
            ret = 0.0
            for ticker, info in holdings.items():
                df_t = all_data.get(ticker)
                if df_t is None:
                    continue
                p0 = df_t[df_t.index <= prev_dt]["Close"]
                p1 = df_t[df_t.index <= rd]["Close"]
                if len(p0) and len(p1) and float(p0.iloc[-1]) > 0:
                    ret += info["w"] * (float(p1.iloc[-1]) / float(p0.iloc[-1]) - 1)
            nav.append(nav[-1] * (1 + ret))
        elif prev_dt:
            nav.append(nav[-1])

        # ── 스크리닝
        passed = {}
        for ticker, df_t in all_data.items():
            if strategy == "A":
                ok, m = screen_A(df_t, rd, cur_atr_mult)
            elif strategy == "B":
                ok, m = screen_B(df_t, rd, market_state, cur_atr_mult)
            else:  # C
                ok, m = screen_C(df_t, rd, market_state, cur_atr_mult)
            if ok:
                passed[ticker] = m

        # ── 랭킹
        ranked = rank_stocks(passed, etf_data, rd)
        top    = ranked.head(cur_top_n)

        # ── 시장 단계별 비중 배율 결정
        if strategy == "C":
            mkt_wt = market_state["weight_mult"]
        else:
            mkt_wt = 1.0  # A/B는 on/off만, 비중은 100%

        # ── 수수료 (턴오버 기반)
        if prev_dt and len(top) > 0:
            new_set = set(top.index)
            old_set = set(holdings.keys())
            sold_w  = sum(holdings[t]["w"] for t in old_set - new_set)
            ws_tmp  = position_weights(top["score"], market_wt_mult=mkt_wt)
            bought_w = sum(float(ws_tmp.get(t, 0)) for t in new_set - old_set)
            rebal_w  = sum(
                abs(float(ws_tmp.get(t, 0)) - holdings[t]["w"])
                for t in old_set & new_set
            )
            total_comm = (sold_w + bought_w + rebal_w) * COMMISSION
            nav[-1] *= (1 - total_comm)

        # ── 포지션 구성
        holdings = {}
        if len(top) > 0:
            ws = position_weights(top["score"], market_wt_mult=mkt_wt)
            for ticker in top.index:
                df_t  = all_data.get(ticker)
                entry = float(df_t[df_t.index <= rd]["Close"].iloc[-1]) \
                        if df_t is not None else 1.0
                atr_s = float(top.loc[ticker, "atr_stop"]) \
                        if "atr_stop" in top.columns and \
                           not pd.isna(top.loc[ticker, "atr_stop"]) else np.nan
                w_eff = float(ws.get(ticker, 0))
                holdings[ticker] = {
                    "w":        w_eff,
                    "entry":    entry,
                    "peak":     entry,
                    "atr_stop": atr_s,
                }

        prev_dt = rd

    return nav


# ══════════════════════════════════════════════════════════════
# 시장 상태 분포 분석
# ══════════════════════════════════════════════════════════════
def analyze_market_states(spy_data: pd.DataFrame) -> pd.DataFrame:
    """SPY 시장 상태의 시계열 분포를 분석한다."""
    rebal_dates = pd.date_range(start=START, end=END, freq="BME")
    records = []
    for rd in rebal_dates:
        spy_hist = spy_data[spy_data.index <= rd]
        state = detect_spy_market_state(spy_hist)
        records.append({
            "date":        rd,
            "state":       state["state"],
            "stage":       state["stage"],
            "weight_mult": state["weight_mult"],
        })
    return pd.DataFrame(records)


# ══════════════════════════════════════════════════════════════
# 성과 지표 계산
# ══════════════════════════════════════════════════════════════
def calc_metrics(nav_list: list, label: str) -> dict:
    s   = pd.Series(nav_list, dtype=float)
    ret = s.pct_change().dropna()
    n   = len(ret)
    years = n / 12
    cagr  = (s.iloc[-1] ** (1 / max(years, 0.1))) - 1 if s.iloc[-1] > 0 else -1.0
    mdd   = ((s - s.cummax()) / s.cummax()).min()
    sharp = (ret.mean() / (ret.std() + 1e-9)) * np.sqrt(12)
    return {
        "label":   label,
        "총수익률": s.iloc[-1] - 1,
        "CAGR":    cagr,
        "MDD":     mdd,
        "샤프":    sharp,
        "월승률":  (ret > 0).mean(),
        "nav":     nav_list,
    }


def print_metrics(m: dict):
    print(f"  {'─'*60}")
    print(f"  {m['label']}")
    print(f"  총수익률 {m['총수익률']:>+8.1%}   CAGR {m['CAGR']:>+8.1%}")
    print(f"  MDD      {m['MDD']:>+8.1%}   샤프 {m['샤프']:>8.2f}   월승률 {m['월승률']:.1%}")


# ══════════════════════════════════════════════════════════════
# 차트 저장
# ══════════════════════════════════════════════════════════════
def plot_results(results: list, spy_nav: list, state_df: pd.DataFrame):
    colors = ["#2E75B6", "#ED7D31", "#70AD47", "#A020F0"]
    dates  = [pd.Timestamp(START)] + list(pd.date_range(START, END, freq="BME"))

    fig = plt.figure(figsize=(16, 12))
    gs  = gridspec.GridSpec(3, 2, hspace=0.50, wspace=0.35)
    ax1 = fig.add_subplot(gs[0, :])   # NAV 곡선
    ax2 = fig.add_subplot(gs[1, 0])   # MDD 비교
    ax3 = fig.add_subplot(gs[1, 1])   # 샤프 비교
    ax4 = fig.add_subplot(gs[2, :])   # SPY 시장 상태 히트맵

    fig.suptitle(
        f"하이브리드 진입 전략 비교 (수수료 0.2%RT, {START}~{END[:7]})",
        fontsize=13, fontweight="bold"
    )

    # ── NAV 곡선
    for i, (label, nav) in enumerate(results):
        n = min(len(nav), len(dates))
        ax1.plot(dates[:n], nav[:n], label=label, color=colors[i], lw=2.0)
    n_spy = min(len(spy_nav), len(dates))
    ax1.plot(dates[:n_spy], spy_nav[:n_spy], label="SPY",
             color="gray", lw=1.2, ls="--", alpha=0.7)
    ax1.set_ylabel("누적 자산 (배)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.1f}x"))
    ax1.legend(fontsize=9); ax1.grid(alpha=0.25)

    # ── MDD/샤프 비교
    labels_bar = [r[0] for r in results]
    mdds   = [abs(calc_metrics(r[1], r[0])["MDD"]) * 100 for r in results]
    sharps = [calc_metrics(r[1], r[0])["샤프"] for r in results]

    ax2.bar(labels_bar, mdds, color=colors[:len(results)], alpha=0.8)
    ax2.set_ylabel("MDD (%)"); ax2.set_title("최대 낙폭 비교")
    for i, v in enumerate(mdds):
        ax2.text(i, v + 0.3, f"{v:.1f}%", ha="center", fontsize=9)
    ax2.grid(axis="y", alpha=0.25)
    plt.sca(ax2); plt.xticks(rotation=15, fontsize=8)

    ax3.bar(labels_bar, sharps, color=colors[:len(results)], alpha=0.8)
    ax3.set_ylabel("샤프지수"); ax3.set_title("샤프지수 비교")
    for i, v in enumerate(sharps):
        ax3.text(i, max(v, 0) + 0.02, f"{v:.2f}", ha="center", fontsize=9)
    ax3.grid(axis="y", alpha=0.25)
    plt.sca(ax3); plt.xticks(rotation=15, fontsize=8)

    # ── SPY 시장 상태 히트맵
    state_colors = {
        "dead_cross":      "#FF4444",
        "bottom_confirmed": "#FFA500",
        "stage2":          "#90EE90",
        "golden_cross":    "#006400",
        "neutral":         "#4444AA",
    }
    state_labels_map = {
        "dead_cross":       "데드크로스(현금)",
        "bottom_confirmed": "바닥확인(50%)",
        "stage2":           "MA50반등(80%)",
        "golden_cross":     "골든크로스(100%)",
        "neutral":          "중립(100%)",
    }
    if not state_df.empty:
        for _, row in state_df.iterrows():
            color = state_colors.get(row["state"], "gray")
            ax4.axvline(x=row["date"], color=color, alpha=0.4, linewidth=1.5)
        # 범례
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor=c, label=state_labels_map.get(s, s), alpha=0.7)
            for s, c in state_colors.items()
        ]
        ax4.legend(handles=legend_elements, loc="upper left",
                   fontsize=8, ncol=3)
    ax4.set_title("SPY 시장 상태 (하이브리드 전략 스크리닝 활성화 타이밍)")
    ax4.set_xlabel("날짜")
    ax4.set_ylabel("상태")
    ax4.grid(alpha=0.20)
    ax4.set_yticks([])

    path = RESULTS_DIR / "hybrid_entry_comparison.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"\n  차트 저장: {path}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true", help="상세 출력 활성화")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    logger.debug("=" * 70)
    logger.debug("  하이브리드 진입 전략 백테스트 — 4전략 × 3진입방식")
    logger.debug(f"  기간: {START} ~ {END}")
    logger.debug(f"  수수료: 편도 {COMMISSION*100:.1f}% (왕복 {COMMISSION*2*100:.1f}%)")
    logger.debug(f"  유니버스: 풀 유니버스 (S&P500 + NASDAQ-100 + KOSPI200 + KOSDAQ150)")
    logger.debug("=" * 70)
    logger.debug("")
    logger.debug("  [전략 파라미터]")
    logger.debug("  공격적: ATR1.5, 주간 리밸런싱, TOP15")
    logger.debug("  균형형: ATR2.0, 월간 리밸런싱, TOP10")
    logger.debug("  보수적: ATR2.5, 월간 리밸런싱, TOP7")
    logger.debug("  적응형: 국면별 동적 전환 (데드→ATR2.5/7, 바닥→ATR2.0/10, 골든→ATR1.5/15)")
    logger.debug("")
    logger.debug("  [진입방식]")
    logger.debug("  A: 기존 MA 정배열 — 시장 상태 무관하게 항상 스크리닝")
    logger.debug("  B: 하이브리드    — SPY 바닥확인 시 스크리닝 ON + 종목 MA 정배열 유지")
    logger.debug("  C: 하이브리드+3단계 — B + SPY 단계별 포지션 비중 조절(50→80→100%)")
    logger.debug("")

    # ── 데이터 로드 (공용 캐시 → 없으면 자동 다운로드)
    logger.debug("[1] 데이터 로드")
    all_data_raw, spy_df, etf_raw, universe_map = load_full_universe(START)
    ALL_UNIVERSE.update(universe_map)
    logger.debug(f"  → 종목 {len(all_data_raw)}개 로드 완료 (유니버스: {len(universe_map)}개)")

    etf_data = {t: add_indicators(df) for t, df in etf_raw.items()}
    logger.debug(f"  섹터 ETF {len(etf_data)}개 완료")
    logger.debug("  SPY 지표 계산...")
    spy_data  = add_indicators(spy_df)
    spy_close = spy_df["Close"].squeeze()
    spy_monthly = spy_close.resample("BME").last().pct_change().fillna(0)
    spy_nav     = [1.0] + list((1 + spy_monthly).cumprod().values.flatten())

    # ── 지표 계산
    logger.debug(f"\n[2] 종목 지표 계산 ({len(all_data_raw)}종목)...")
    all_data = {t: add_indicators(df) for t, df in all_data_raw.items()}
    logger.debug("  완료")

    # ── SPY 시장 상태 분석
    logger.debug("\n[3] SPY 시장 상태 분석...")
    state_df = analyze_market_states(spy_data)
    state_counts = state_df["state"].value_counts()
    total_months = len(state_df)
    logger.debug(f"  분석 기간: {total_months}개월")
    state_label_map = {
        "dead_cross":       "데드크로스(현금화)",
        "bottom_confirmed": "바닥확인(50%)",
        "stage2":           "MA50반등(80%)",
        "golden_cross":     "골든크로스(100%)",
        "neutral":          "중립(100%)",
    }
    for state, cnt in state_counts.items():
        pct = cnt / total_months * 100
        label = state_label_map.get(state, state)
        logger.debug(f"  {label:<22}: {cnt:>4}개월 ({pct:.1f}%)")

    # ── 전략 정의
    # (이름, atr_mult, top_n, rebal_freq, adaptive)
    strategy_configs = [
        ("공격적", 1.5, 15, "W-FRI", False),
        ("균형형", 2.0, 10, "BME",   False),
        ("보수적", 2.5,  7, "BME",   False),
        ("적응형", 2.0, 10, "BME",   True),   # adaptive=True → 국면별 동적 전환
    ]
    entry_methods = [
        ("A", "기존MA정배열"),
        ("B", "하이브리드"),
        ("C", "하이브리드+3단계"),
    ]

    all_metrics = []
    results_for_chart = []   # 차트용 (전략명, nav)

    for strat_name, atr_m, tn, freq, is_adaptive in strategy_configs:
        logger.debug("\n" + "═" * 70)
        logger.debug(f"  [{strat_name}] ATR{atr_m}, TOP{tn}, freq={freq}"
                     + (" (adaptive)" if is_adaptive else ""))
        logger.debug("═" * 70)

        group_metrics = []
        for entry_code, entry_name in entry_methods:
            label = f"{strat_name}-{entry_code}({entry_name})"
            logger.debug(f"\n  ▶ {label}")
            nav = run_backtest(
                all_data, etf_data, spy_data,
                strategy=entry_code,
                atr_mult=atr_m,
                top_n=tn,
                rebal_freq=freq,
                adaptive=is_adaptive,
            )
            m = calc_metrics(nav, label)
            print_metrics(m)
            group_metrics.append(m)
            all_metrics.append(m)
            if strat_name == "균형형":   # 차트에는 균형형만 표시 (기존 동작 유지)
                results_for_chart.append((label, nav))

        # 그룹 내 A 대비 B/C 비교
        m_a = group_metrics[0]
        for m_x in group_metrics[1:]:
            tag = m_x["label"].split("-")[1][0]
            dc = m_x["CAGR"] - m_a["CAGR"]
            dm = m_x["MDD"]  - m_a["MDD"]
            print(f"  {tag} vs A → CAGR {dc:+.1%}  MDD {dm:+.1%}")

    # ── SPY 벤치마크
    m_spy = calc_metrics(spy_nav, "SPY 벤치마크")
    all_metrics.append(m_spy)

    # ── 종합 비교 표
    print("\n" + "═" * 70)
    print("  종합 성과 비교 (4전략 × 3진입방식 + SPY)")
    print("═" * 70)
    print(f"  {'전략':<35} {'CAGR':>8} {'MDD':>8} {'샤프':>7} {'월승률':>7}")
    print("  " + "─" * 67)
    prev_strat = None
    for m in all_metrics:
        cur_strat = m["label"].split("-")[0] if "-" in m["label"] else m["label"]
        if cur_strat != prev_strat:
            if prev_strat is not None:
                print("  " + "─" * 67)
            prev_strat = cur_strat
        print(f"  {m['label']:<35} {m['CAGR']:>+8.1%} "
              f"{m['MDD']:>+8.1%} {m['샤프']:>7.2f} {m['월승률']:>7.1%}")

    # ── CSV 저장
    rows = [{
        "전략":     m["label"],
        "총수익률": f"{m['총수익률']:+.1%}",
        "CAGR":     f"{m['CAGR']:+.1%}",
        "MDD":      f"{m['MDD']:+.1%}",
        "샤프지수": f"{m['샤프']:.2f}",
        "월간승률": f"{m['월승률']:.1%}",
    } for m in all_metrics]
    csv_path = RESULTS_DIR / "hybrid_entry_all_strategies.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n  결과 CSV: {csv_path}")

    # 시장 상태 CSV
    state_csv = RESULTS_DIR / "spy_market_states.csv"
    state_df.to_csv(state_csv, index=False, encoding="utf-8-sig")
    print(f"  SPY 상태 CSV:  {state_csv}")

    # ── 차트 (균형형 3개 + SPY)
    if results_for_chart:
        plot_results(results_for_chart, spy_nav, state_df)

    print("\n" + "=" * 70)
    print("  백테스트 완료")
    print("=" * 70)
