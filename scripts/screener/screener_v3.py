"""
모멘텀 종목 스크리너 v3.2 — US 전용
══════════════════════════════════════════════════════════
버전 히스토리:
  v3.0  ATR 기반 동적 스톱로스 / 복합점수 비례 포지션 사이징
  v3.1  ③ 한국 시장 제외 플래그  (INCLUDE_KR_MARKET = False)
        ④ 시장 레짐 필터         (SPY MA20 < MA60 → 빈 결과)
        ⑤ 변동성 스케일링        (SPY 20일 실현변동성 → VOL_TARGET 기준 포지션 조절)
        ⑥ 형성 기간 확장         (ret12m_skip1: 252일, 최근 21일 제외)
        ⑦ Buy/Hold Spread        (보유 종목 Top N×2.5까지 유지)
        ⑧ 시가총액 가중          (score × sqrt(market_cap))
  v3.2  ⑨ US/KR 분리 스크리닝   (이 파일 = US 전용)
        - 유니버스: S&P 500 + NASDAQ 100 동적 수집 (data_cache.py)
        - KR 스크리닝은 screener_v3_kr.py 참조
        - 스크리닝 임계값 조정:
            ADX_THRESH  25 → 20
            RSI_HI      75 → 77
            HH_HL_MIN    3 →  2
            PRICE_52W   0.80 → 0.75
            MAX_WEIGHT  0.20 → 0.10

주요 상수:
  ATR_PERIOD   = 14   ATR 계산 기간
  ATR_MULT     = 2.5  스톱로스 = 20일 고점 - ATR×2.5
  TOP_N        = 10   최종 선정 종목 수
  MAX_WEIGHT   = 0.10 단일 종목 최대 비중 (10%)
  ADX_THRESH   = 20   최소 추세 강도
  RSI_LO/HI    = 50/77  RSI 필터 범위
  HH_HL_MIN    = 2    60일 HH-HL 스윙 최소 횟수
  PRICE_52W    = 0.75 52주 고점의 75% 이상 위치
  VOL_TARGET   = 0.15 변동성 스케일링 목표 (연환산 15%)
  HOLD_SPREAD  = 2.5  Buy/Hold Spread 배수 (Top N×2.5까지 보유 유지)
══════════════════════════════════════════════════════════
"""
import logging
import os
import sys
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*yfinance.*")

import numpy as np
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.constants import US_UNIVERSE, KR_UNIVERSE, ALL_UNIVERSE, SECTOR_ETF

# ── 배포 환경 설정 ────────────────────────────────────────────
# DEPLOY_ENV: "serverless" | "local" | "cloud"  (기본값: "local")
DEPLOY_ENV = os.environ.get("DEPLOY_ENV", "local")

# 환경별 CSV 출력 경로 결정
_SCRIPT_DIR = Path(__file__).parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
_OUTPUT_DIR: Path
if DEPLOY_ENV == "serverless":
    _OUTPUT_DIR = _PROJECT_ROOT / "frontend" / "web" / "data"
elif DEPLOY_ENV == "cloud":
    _OUTPUT_DIR = _SCRIPT_DIR / "results"
else:  # local
    _OUTPUT_DIR = _SCRIPT_DIR / "results"

# ── 기본 스크리닝 파라미터 ────────────────────────────────────
ATR_PERIOD   = 14
ATR_MULT     = 2.5
TOP_N        = 10
# 포지션 사이징 방식: "equal"(동일비중) | "score"(점수 비례) | "score_capped"(점수 비례+상한)
SIZING_MODE  = "score_capped"
MAX_WEIGHT   = 0.10   # 단일 종목 최대 비중 (score_capped 모드)

# ── 스크리닝 임계값 ───────────────────────────────────────────
ADX_THRESH   = 20     # v3 최적: 25 → 20
RSI_LO       = 50
RSI_HI       = 77     # v3 최적: 75 → 77
HH_HL_MIN    = 2      # v3 최적: 3 → 2
PRICE_52W    = 0.75   # v3 최적: 80% → 75%

# ── v3.1 신규 파라미터 ────────────────────────────────────────
INCLUDE_KR_MARKET  = False   # 변경 1: 한국 시장 제외 (True = 포함)
# 변경 2: 레짐 필터 모드
#   "off"   — 레짐 필터 적용 안 함
#   "info"  — 레짐 상태를 결과에 포함하되 필터링하지 않음 (배포 기본값)
#   "block" — 데드크로스 시 빈 결과 반환 (백테스트용)
REGIME_FILTER_MODE = "info"
VOL_TARGET         = 0.15    # 변경 3: 변동성 스케일링 목표 연환산 변동성
HOLD_SPREAD        = 2.5     # 변경 5: 보유 종목 Top N×HOLD_SPREAD까지 유지
USE_MKTCAP_WEIGHT  = True    # 변경 6: 시가총액 가중 활성화

# ── 복합점수 가중치 (변경 4: ret12m_skip1 추가, 가중치 재배분) ─
WEIGHTS = dict(
    adx      = 0.30,   # v3: 0.40 → 0.30
    ret3m    = 0.20,   # v3: 0.30 → 0.20
    ret12m   = 0.20,   # 신규: 12개월(최근 1개월 제외) 수익률
    sector   = 0.20,   # 유지
    vol_stab = 0.10,   # 유지
)


# ── 다운로드 ──────────────────────────────────────────────────
def download(tickers, period="1y"):
    """yfinance로 티커 목록 OHLCV 배치 다운로드. 60일 미만 종목은 제외."""
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
                    logging.debug("screener_v3 download: %s 슬라이스 실패 — %s", t, e)
        else:
            if len(raw) >= 60:
                result[tickers[0]] = raw
        return result
    except Exception as e:
        logging.debug("screener_v3 download: 배치 다운로드 실패 — %s", e)
        return {}


# ── 지표 계산 ─────────────────────────────────────────────────
def calc_indicators(df):
    """MA20/50/200, RSI, ADX, VolMA20/60, 52주 고점, ATR(14) 계산."""
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
    # ATR 계산
    atr = ta.atr(h, l, c, length=ATR_PERIOD)
    d["ATR"]     = atr if atr is not None else np.nan
    return d


# ── 스윙 HH-HL ───────────────────────────────────────────────
def count_hh_hl_swing(df_window, n=3):
    """60일 윈도우에서 HH(Higher High)-HL(Higher Low) 스윙 횟수 반환.
    min(hh_count, hl_count) ≥ HH_HL_MIN 이면 상승 추세로 판단.
    """
    highs = df_window["High"].values
    lows  = df_window["Low"].values
    sh = [highs[i] for i in range(n, len(highs)-n)
          if highs[i] == max(highs[i-n:i+n+1])]
    sl = [lows[i]  for i in range(n, len(lows)-n)
          if lows[i]  == min(lows[i-n:i+n+1])]
    hh = sum(sh[i] > sh[i-1] for i in range(1, len(sh)))
    hl = sum(sl[i] > sl[i-1] for i in range(1, len(sl)))
    return min(hh, hl)


# ── ATR 기반 동적 스톱로스 계산 ──────────────────────────────
def calc_atr_stop(df) -> float:
    """
    최근 20일 고점 - ATR(14) × ATR_MULT
    변동성이 높은 종목은 스톱이 넓어지고,
    변동성이 낮은 종목은 스톱이 좁아집니다.
    """
    atr_val = df["ATR"].dropna().iloc[-1] if "ATR" in df.columns else np.nan
    if pd.isna(atr_val):
        return np.nan
    peak_20  = float(df["High"].tail(20).max())
    return round(peak_20 - atr_val * ATR_MULT, 2)


# ── SPY 실현변동성 기반 포지션 스케일 팩터 (변경 3) ──────────
def calc_spy_vol_scale(spy_close: pd.Series) -> float:
    """
    SPY 20일 실현변동성(연환산)을 VOL_TARGET과 비교해
    전체 포지션 크기를 0~1 사이로 조절한다.
    변동성이 낮을수록 포지션 확대, 높을수록 축소.
    """
    ret = spy_close.pct_change().dropna()
    if len(ret) < 20:
        return 1.0
    vol = float(ret.tail(20).std() * np.sqrt(252))
    if vol <= 0:
        return 1.0
    return min(VOL_TARGET / vol, 1.0)


# ── 시가총액 수집 (변경 6) ────────────────────────────────────
def fetch_market_caps(tickers: list) -> dict:
    """passed 종목들의 시가총액을 yfinance fast_info로 수집한다."""
    caps = {}
    for t in tickers:
        try:
            mc = yf.Ticker(t).fast_info.market_cap
            caps[t] = float(mc) if mc and mc > 0 else 1.0
        except Exception:
            caps[t] = 1.0
    return caps


# ── 스크리닝 ──────────────────────────────────────────────────
def screen(df):
    """단일 종목 스크리닝. v3.2 임계값 적용.

    통과 조건:
      - ADX ≥ ADX_THRESH (추세 강도)
      - MA20 > MA50 > MA200 (상승 정배열)
      - RSI_LO ≤ RSI ≤ RSI_HI (과매수 제외)
      - 최근 20일 거래량이 60일 평균×3 이하 (급등 제외)
      - 최근 5일 일간 변동 10% 이하 (급등락 제외)
      - HH-HL 스윙 ≥ HH_HL_MIN (상승 추세 구조)
      - 현재가 ≥ 52주 고점×PRICE_52W (고점 근접)
      - 현재가 > ATR 스톱가 (스톱 트리거 상태 제외)

    Returns:
        (True, metrics_dict) 또는 (False, {})
    """
    if len(df) < 200:
        return False, {}

    row = df.iloc[-1]
    r5  = df.tail(6)
    r20 = df.tail(20)
    r60 = df.tail(60)
    r63 = df.tail(63)

    adx = row.get("ADX", np.nan)
    if pd.isna(adx) or adx < ADX_THRESH:
        return False, {}

    ma20, ma50, ma200 = row.get("MA20"), row.get("MA50"), row.get("MA200")
    if any(pd.isna(v) for v in [ma20, ma50, ma200]):
        return False, {}
    if not (ma20 > ma50 > ma200):
        return False, {}

    rsi = row.get("RSI", np.nan)
    if pd.isna(rsi) or not (RSI_LO <= rsi <= RSI_HI):
        return False, {}

    vol60 = row.get("VolMA60", np.nan)
    if pd.isna(vol60) or vol60 == 0:
        return False, {}
    if (r20["Volume"] > vol60 * 3.0).any():
        return False, {}

    if (r5["Close"].pct_change().abs() > 0.10).any():
        return False, {}

    if count_hh_hl_swing(r60) < HH_HL_MIN:
        return False, {}

    high52 = row.get("High52w", np.nan)
    if not pd.isna(high52) and high52 > 0:
        if row["Close"] < high52 * PRICE_52W:
            return False, {}

    ret3m = float(df["Close"].iloc[-1] / r63["Close"].iloc[0]) - 1 \
            if len(r63) >= 60 else np.nan
    vol_cv   = r20["Volume"].std() / (vol60 + 1e-9)
    vol_stab = float(1 / (vol_cv + 1e-6))

    # ── 변경 4: ret12m_skip1 (252일 수익률, 최근 21일 제외) ──
    n = len(df)
    if n >= 273:   # 252 + 21
        ret12m_skip1 = float(df["Close"].iloc[-22] / df["Close"].iloc[-273]) - 1
    elif n >= 252:
        ret12m_skip1 = float(df["Close"].iloc[-22] / df["Close"].iloc[-252]) - 1
    else:
        ret12m_skip1 = np.nan

    # ATR 기반 동적 스톱가
    stop_price = calc_atr_stop(df)
    cur_price  = float(df["Close"].iloc[-1])

    # 현재가가 이미 ATR 스톱 이하인 종목은 제외 (스톱 트리거 상태)
    if not pd.isna(stop_price) and cur_price <= stop_price:
        return False, {}

    stop_dist = (stop_price - cur_price) / cur_price if not pd.isna(stop_price) else np.nan

    return True, {
        "ADX"         : float(adx),
        "RSI"         : float(rsi),
        "ret3m"       : ret3m,
        "ret12m_skip1": ret12m_skip1,
        "vol_stab"    : vol_stab,
        "price"       : cur_price,
        "stop_price"  : stop_price,
        "stop_dist"   : stop_dist,
        "high52w"     : float(high52) if not pd.isna(high52) else np.nan,
        "atr"         : float(df["ATR"].dropna().iloc[-1])
                        if "ATR" in df.columns else np.nan,
    }


# ── 복합점수 및 포지션 사이징 ────────────────────────────────
def minmax(s):
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)

def calc_position_weights(scores: pd.Series, mode: str, max_w: float) -> pd.Series:
    """
    equal      : 동일비중 (1/n)
    score      : 점수 비례 (score / sum)
    score_capped: 점수 비례 + 단일 종목 최대 비중 cap
    """
    n = len(scores)
    if mode == "equal" or n == 0:
        return pd.Series([1.0 / n] * n, index=scores.index)

    raw_w = scores / scores.sum()

    if mode == "score":
        return raw_w

    # score_capped: max_w 초과분을 나머지에 재배분 (반복)
    w = raw_w.copy()
    for _ in range(20):   # 최대 20회 반복으로 수렴
        capped  = w.clip(upper=max_w)
        excess  = w[w > max_w].sum() - max_w * (w > max_w).sum()
        if excess <= 1e-8:
            break
        under   = capped < max_w
        if under.sum() == 0:
            break
        capped[under] += excess * (capped[under] / capped[under].sum())
        w = capped

    return w / w.sum()   # 합산 = 1.0 정규화


def rank_stocks(passed, etf_data, market_caps=None):
    """복합점수 계산 및 정렬.

    score = ADX×0.30 + ret3m×0.20 + ret12m_skip1×0.20 + 섹터강도×0.20 + 거래량안정성×0.10
    USE_MKTCAP_WEIGHT=True 시: score × sqrt(market_cap) 로 대형주 우대

    Args:
        passed: {ticker: metrics_dict} 스크리닝 통과 종목
        etf_data: {etf_ticker: df} 섹터 ETF 데이터 (섹터 강도 계산용)
        market_caps: {ticker: float} 시가총액 (None이면 가중 비활성)
    """
    if not passed:
        return pd.DataFrame()

    df = pd.DataFrame(passed).T
    df["sector"] = [ALL_UNIVERSE.get(t, "Unknown") for t in df.index]

    # ETF 초과수익률 기준 섹터 강도
    df["sec_str"] = 0.0
    for idx, row in df.iterrows():
        sec     = row["sector"]
        etf_sym = SECTOR_ETF.get(sec)
        if etf_sym and etf_sym in etf_data:
            etf_close = etf_data[etf_sym]["Close"]
            if len(etf_close) >= 63:
                etf_ret = float(etf_close.iloc[-1] / etf_close.iloc[-63]) - 1
                df.loc[idx, "sec_str"] = (row["ret3m"] - etf_ret) \
                    if not pd.isna(row["ret3m"]) else 0.0
    df["sec_str_norm"] = minmax(df["sec_str"])

    # ── 변경 4: ret12m_skip1 포함 복합점수 ─────────────────────
    df["score"] = (
        minmax(df["ADX"])                            * WEIGHTS["adx"]     +
        minmax(df["ret3m"].fillna(0))                * WEIGHTS["ret3m"]   +
        minmax(df["ret12m_skip1"].fillna(0))         * WEIGHTS["ret12m"]  +
        minmax(df["sec_str_norm"])                   * WEIGHTS["sector"]  +
        minmax(df["vol_stab"])                       * WEIGHTS["vol_stab"]
    )

    # ── 변경 6: 시가총액 가중 (score × sqrt(market_cap)) ───────
    if USE_MKTCAP_WEIGHT and market_caps:
        df["mktcap"] = [market_caps.get(t, 1.0) for t in df.index]
        df["mktcap"] = df["mktcap"].clip(lower=1.0)
        df["score"]  = df["score"] * np.sqrt(df["mktcap"])

    return df.sort_values("score", ascending=False)


# ── 시장 상태 ─────────────────────────────────────────────────
def check_market():
    """SPY MA20 vs MA60 골든/데드크로스 확인.

    Returns:
        dict: price, ma20, ma60, gap_pct, is_golden, close (Series)
        None: SPY 데이터 다운로드 실패 시
    """
    try:
        spy   = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
        close = spy["Close"].squeeze()
        ma20  = float(close.rolling(20).mean().iloc[-1])
        ma60  = float(close.rolling(60).mean().iloc[-1])
        price = float(close.iloc[-1])
        gap   = (ma20 - ma60) / ma60 * 100
        return {"price": price, "ma20": ma20, "ma60": ma60,
                "gap_pct": gap, "is_golden": ma20 > ma60,
                "close": close}
    except Exception as e:
        logging.debug("screener_v3 check_market: SPY 다운로드 실패 — %s", e)
        return None


# ── 메인 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse as _argparse
    _parser = _argparse.ArgumentParser(description="모멘텀 종목 스크리너 v3")
    _parser.add_argument("--verbose", action="store_true", help="진행 상황 출력")
    _parser.add_argument("--held", nargs="*", default=[],
                         help="현재 보유 중인 종목 코드 목록 (Buy/Hold Spread 적용)")
    _parser.add_argument("--regime-block", action="store_true",
                         help="백테스트용: 데드크로스 시 빈 결과 반환 (block 모드 강제)")
    _args = _parser.parse_args()

    # --regime-block 플래그로 block 모드 강제 활성화
    if _args.regime_block:
        REGIME_FILTER_MODE = "block"

    logging.basicConfig(
        level=logging.INFO if _args.verbose else logging.WARNING,
        format="%(message)s",
    )
    _v = _args.verbose
    _held_tickers = list(_args.held)   # 변경 5: 보유 종목

    from data_cache import fetch_sp500_tickers, fetch_nasdaq100_tickers, fetch_kr_tickers

    today = datetime.now().strftime("%Y-%m-%d")

    # ── 동적 유니버스 수집 ────────────────────────────────────
    if _v:
        print("유니버스 수집 중...")
    _us_tickers, _us_sectors = fetch_sp500_tickers()
    _ndx_tickers, _ndx_sectors = fetch_nasdaq100_tickers()
    _sp500_set = set(_us_tickers)
    _ndx_new = [t for t in _ndx_tickers if t not in _sp500_set]
    _ndx_new_sec = {t: s for t, s in _ndx_sectors.items() if t not in _sp500_set}
    _us_tickers = _us_tickers + _ndx_new
    _us_sectors = {**_us_sectors, **_ndx_new_sec}

    # ── 변경 1: 한국 시장 제외 플래그 ────────────────────────
    if INCLUDE_KR_MARKET:
        _kr_tickers = fetch_kr_tickers()
        _kr_sectors = {t: "Unknown" for t in _kr_tickers}
    else:
        _kr_tickers = []
        _kr_sectors = {}
        if _v:
            print("  KR 시장 제외 (INCLUDE_KR_MARKET = False)")

    ALL_UNIVERSE.clear()
    ALL_UNIVERSE.update({**_us_sectors, **_kr_sectors})
    _all_tickers = list(ALL_UNIVERSE.keys())

    if _v:
        kr_label = f"KR {len(_kr_tickers)}종목" if INCLUDE_KR_MARKET else "KR 제외"
        print(f"  유니버스: US {len(_us_tickers)}종목 + {kr_label} = {len(_all_tickers)}종목")
        print("=" * 64)
        print(f"  모멘텀 종목 스크리너 v3.1   기준일: {today}")
        print(f"  스톱로스: ATR({ATR_PERIOD}) × {ATR_MULT}  │  "
              f"포지션: {SIZING_MODE} (상한 {MAX_WEIGHT:.0%})")
        print(f"  레짐 필터: {REGIME_FILTER_MODE}  │  "
              f"변동성 목표: {VOL_TARGET:.0%}  │  "
              f"시가총액 가중: {'ON' if USE_MKTCAP_WEIGHT else 'OFF'}")
        print("=" * 64)

    # ── 시장 상태 (변경 2: 레짐 필터) ────────────────────────
    if _v:
        print("\n[0/3] 시장 상태 확인...")
    mkt = check_market()
    spy_close_series = mkt["close"] if mkt else None

    if mkt and _v:
        status = "골든크로스 ✅" if mkt["is_golden"] else "데드크로스 ⚠️"
        arrow  = "▲" if mkt["gap_pct"] >= 0 else "▼"
        print(f"  SPY ${mkt['price']:.2f}  │  20MA ${mkt['ma20']:.2f}  │  "
              f"60MA ${mkt['ma60']:.2f}  │  {arrow}{abs(mkt['gap_pct']):.2f}%  {status}")

    # 변경 2: 레짐 필터 — block 모드에서 데드크로스면 빈 결과 반환
    if REGIME_FILTER_MODE == "block" and mkt and not mkt["is_golden"]:
        if _v:
            print()
            print("  ┌──────────────────────────────────────────────────┐")
            print("  │  ⚠️  레짐 필터(block): SPY MA20 < MA60 데드크로스    │")
            print("  │  신규 진입 차단 — 빈 결과를 반환합니다.             │")
            print("  └──────────────────────────────────────────────────┘")
        exit()

    # ── 변경 3: SPY 변동성 스케일 팩터 계산 ──────────────────
    vol_scale = 1.0
    if spy_close_series is not None:
        vol_scale = calc_spy_vol_scale(spy_close_series)
        if _v:
            print(f"  변동성 스케일: {vol_scale:.2%}  (VOL_TARGET={VOL_TARGET:.0%})")

    # ── 다운로드 ─────────────────────────────────────────────
    if _v:
        print("\n[1/3] 데이터 다운로드 중...")
    us_data, kr_data, etf_data = {}, {}, {}
    for i in range(0, len(_us_tickers), 50):
        us_data.update(download(_us_tickers[i:i+50]))
    if INCLUDE_KR_MARKET:
        for i in range(0, len(_kr_tickers), 30):
            kr_data.update(download(_kr_tickers[i:i+30]))
    etf_raw = download(list(set(SECTOR_ETF.values())))
    for t, df in etf_raw.items():
        etf_data[t] = calc_indicators(df)

    all_data = {**us_data, **kr_data}
    if _v:
        print(f"  종목 {len(all_data)}개, ETF {len(etf_data)}개 수신 완료")
        print("\n[2/3] 지표 계산 및 스크리닝 중...")

    passed = {}
    for t, df in all_data.items():
        df_ind = calc_indicators(df)
        ok, metrics = screen(df_ind)
        if ok:
            passed[t] = metrics

    if _v:
        print(f"  스크리닝 통과: {len(passed)}개 / {len(all_data)}개")

    if not passed:
        if _v:
            print("\n  ※ 현재 조건을 통과한 종목이 없습니다.")
        exit()

    # ── 변경 6: 시가총액 수집 ────────────────────────────────
    market_caps = {}
    if USE_MKTCAP_WEIGHT:
        if _v:
            print("  시가총액 수집 중...")
        market_caps = fetch_market_caps(list(passed.keys()))

    # ── 랭킹 ─────────────────────────────────────────────────
    if _v:
        print("\n[3/3] 복합점수 계산 및 포지션 배분 중...")
    ranked = rank_stocks(passed, etf_data, market_caps)

    # ── 변경 5: Buy/Hold Spread ───────────────────────────────
    hold_n    = int(TOP_N * HOLD_SPREAD)  # 예: 10 × 2.5 = 25
    top_new   = ranked.head(TOP_N)

    if _held_tickers:
        hold_extended = ranked.head(hold_n)
        held_valid    = [t for t in _held_tickers if t in hold_extended.index]
        held_extra    = [t for t in held_valid if t not in top_new.index]
        if held_extra:
            top_final = pd.concat([top_new, ranked.loc[held_extra]])
            if _v:
                print(f"  Buy/Hold Spread: 신규 {len(top_new)}개 + 유지 {len(held_extra)}개 = {len(top_final)}개")
        else:
            top_final = top_new
    else:
        top_final = top_new

    # ── 포지션 비중 계산 (변경 3: vol_scale 적용) ────────────
    raw_weights = calc_position_weights(top_final["score"], SIZING_MODE, MAX_WEIGHT)
    top_final   = top_final.copy()
    top_final["weight"]    = raw_weights * vol_scale   # 실제 투자 비중 (합산 ≤ 1)
    top_final["weight_raw"]= raw_weights               # vol_scale 미반영 원본 비중

    # ── 결과 출력 ─────────────────────────────────────────────
    if _v:
        cash_pct = 1.0 - vol_scale
        print("\n" + "=" * 64)
        print(f"  ★ 복합점수 상위 {len(top_final)}개  "
              f"(v3.1 — ATR스톱 + 점수비례 + 변동성스케일링)")
        print(f"  현금 비중: {cash_pct:.1%}  (vol_scale={vol_scale:.2%})")
        print("=" * 64)
        print(f"  {'순위'} {'종목':<13} {'비중':>6} {'원비중':>7} {'점수':>6} "
              f"{'ADX':>5} {'RSI':>5} {'3M수익':>7} {'12M수익':>8} "
              f"{'스톱가':>9} {'스톱거리':>8}")
        print("  " + "─" * 80)

        for rank, (ticker, row) in enumerate(top_final.iterrows(), 1):
            flag     = "🇺🇸" if not ticker.endswith(".KS") else "🇰🇷"
            ret3_str = f"{row['ret3m']:+.1%}" if not pd.isna(row["ret3m"]) else " N/A"
            ret12_str= f"{row['ret12m_skip1']:+.1%}" \
                       if "ret12m_skip1" in row and not pd.isna(row["ret12m_skip1"]) else " N/A"
            stop_s   = f"{row['stop_price']:>9,.2f}" \
                       if not pd.isna(row["stop_price"]) else "      N/A"
            dist_s   = f"{row['stop_dist']:>+.1%}" \
                       if not pd.isna(row["stop_dist"]) else "   N/A"
            hold_mark= " [H]" if ticker in _held_tickers else ""
            print(
                f"  {rank:2d}위 {flag} {ticker:<11}{hold_mark}"
                f" {row['weight']:>5.1%}"
                f" {row['weight_raw']:>6.1%}"
                f" {row['score']:>6.3f}"
                f" {row['ADX']:>5.1f}"
                f" {row['RSI']:>5.1f}"
                f" {ret3_str:>7}"
                f" {ret12_str:>8}"
                f" {stop_s}"
                f" {dist_s}"
            )

    # ── info 모드: market_regime 필드 출력 ───────────────────────
    if REGIME_FILTER_MODE == "info" and mkt:
        regime_info = {
            "golden_cross": mkt["is_golden"],
            "spy_ma20"    : round(mkt["ma20"], 2),
            "spy_ma60"    : round(mkt["ma60"], 2),
            "gap_pct"     : round(mkt["gap_pct"], 2),
        }
        if _v:
            status = "골든크로스" if regime_info["golden_cross"] else "데드크로스"
            print(f"\n  market_regime: {regime_info}  ({status})")

    # ── CSV 저장 ──────────────────────────────────────────────
    save_cols = ["weight", "weight_raw", "score", "ADX", "RSI",
                 "ret3m", "ret12m_skip1", "stop_price", "stop_dist",
                 "atr", "sector", "price"]
    save_cols = [c for c in save_cols if c in top_final.columns]
    out = top_final[save_cols].copy()
    out.index.name = "종목코드"
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = _OUTPUT_DIR / "screener_v3_result.csv"
    out.to_csv(csv_path, encoding="utf-8-sig")
    if _v:
        print(f"\n  결과 저장: {csv_path}  [DEPLOY_ENV={DEPLOY_ENV}]")
