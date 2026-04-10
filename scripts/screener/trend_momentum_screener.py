"""
트렌드+모멘텀 스크리너 (튜닝 버전)
══════════════════════════════════════════════════════════
screener_v3 기반 + 3가지 튜닝 적용:
  1. 활성 섹터: 신규 진입 종목의 섹터만 (기존: Top N 전체 섹터)
       → 스탠드얼론 운용 시: 섹터 ETF가 20MA 위에 있는 섹터만 활성
       → 상태 파일(trend_momentum_state.json)에 이전 기간 신규 진입 섹터 저장
  2. 상관관계 임계값: 0.8 (기존: 0.6)
       → Top N 선택 시 이미 선택된 종목과 0.8 초과 상관 종목 제외
  3. Top N: 10 (기존: 20)
══════════════════════════════════════════════════════════
유니버스: 풀 유니버스 (S&P500 + NASDAQ-100 + KOSPI200 + KOSDAQ150)
"""
import warnings
warnings.filterwarnings("ignore")

import json
import sys
import numpy as np
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime
from pathlib import Path

# ── 경로 설정 ──────────────────────────────────────────────────
_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent))
from data_cache import load_full_universe, SECTOR_ETF as CACHE_SECTOR_ETF

STATE_FILE = _THIS_DIR / "trend_momentum_state.json"

# ── 파라미터 (튜닝 버전) ────────────────────────────────────────
ATR_PERIOD   = 14
ATR_MULT     = 2.0
TOP_N        = 10          # 튜닝: 20 → 10
CORR_THRESH  = 0.8         # 튜닝: 0.6 → 0.8
CORR_WINDOW  = 60          # 상관관계 계산용 일봉 기간 (영업일)
SIZING_MODE  = "score_capped"
MAX_WEIGHT   = 0.10

ADX_THRESH   = 20
RSI_LO       = 50
RSI_HI       = 77
HH_HL_MIN    = 2
HH_HL_WINDOW = 60
PRICE_52W    = 0.75
VOL_SPIKE    = 3.0
DAILY_MOVE   = 0.10

WEIGHTS = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)

# 섹터 ETF (data_cache 기준)
SECTOR_ETF = CACHE_SECTOR_ETF


# ══════════════════════════════════════════════════════════════
# 상태 파일 I/O (이전 기간 신규 진입 섹터 저장)
# ══════════════════════════════════════════════════════════════
def load_state() -> dict:
    """이전 스크리닝 결과 상태 로드"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"active_sectors": None, "holdings": []}


def save_state(active_sectors: list | None, holdings: list):
    """스크리닝 결과 상태 저장 (다음 실행 시 활성 섹터 결정에 사용)"""
    STATE_FILE.write_text(json.dumps({
        "active_sectors": active_sectors,
        "holdings":       holdings,
        "updated_at":     datetime.now().isoformat(),
    }, ensure_ascii=False, indent=2))


# ══════════════════════════════════════════════════════════════
# 활성 섹터 판별
# ══════════════════════════════════════════════════════════════
def get_active_sectors_from_etf(etf_data: dict, all_sectors: set) -> set:
    """
    섹터 ETF가 20MA 위에 있는 섹터만 활성으로 판별.
    (스탠드얼론 실행 시 state 없을 때 fallback)
    """
    active = set()
    for sec, etf_sym in SECTOR_ETF.items():
        if sec not in all_sectors:
            continue
        if etf_sym not in etf_data:
            active.add(sec)  # 데이터 없으면 허용
            continue
        close = etf_data[etf_sym]["Close"]
        if len(close) < 20:
            active.add(sec)
            continue
        ma20 = float(close.rolling(20).mean().iloc[-1])
        cur  = float(close.iloc[-1])
        if cur > ma20:
            active.add(sec)
    return active if active else all_sectors  # fallback: 전체 허용


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
          if lows[i]  == min(lows[i - n:i + n + 1])]
    return min(
        sum(sh[i] > sh[i - 1] for i in range(1, len(sh))),
        sum(sl[i] > sl[i - 1] for i in range(1, len(sl))),
    )


# ══════════════════════════════════════════════════════════════
# 스크리닝 (기존 v3 기준)
# ══════════════════════════════════════════════════════════════
def screen(df: pd.DataFrame) -> tuple:
    if len(df) < 200:
        return False, {}

    row  = df.iloc[-1]
    r5   = df.tail(6)
    r20  = df.tail(20)
    r60  = df.tail(HH_HL_WINDOW)
    r63  = df.tail(63)

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
    if pd.isna(vol60) or vol60 == 0 or (r20["Volume"] > vol60 * VOL_SPIKE).any():
        return False, {}

    if (r5["Close"].pct_change().abs() > DAILY_MOVE).any():
        return False, {}

    if len(r60) >= 7 and swing_hh_hl(r60) < HH_HL_MIN:
        return False, {}

    high52 = row.get("High52w", np.nan)
    if not pd.isna(high52) and high52 > 0 and row["Close"] < high52 * PRICE_52W:
        return False, {}

    ret3m    = float(df["Close"].iloc[-1] / r63["Close"].iloc[0]) - 1 \
               if len(r63) >= 60 else np.nan
    vol_cv   = r20["Volume"].std() / (vol60 + 1e-9)
    vol_stab = float(1 / (vol_cv + 1e-6))

    atr_series = df["ATR"].dropna() if "ATR" in df.columns else pd.Series(dtype=float)
    atr_val    = float(atr_series.iloc[-1]) if len(atr_series) > 0 else np.nan
    peak20     = float(df["High"].tail(20).max())
    atr_stop   = peak20 - atr_val * ATR_MULT if not pd.isna(atr_val) else np.nan

    cur_price = float(df["Close"].iloc[-1])
    if not pd.isna(atr_stop) and cur_price <= atr_stop:
        return False, {}

    return True, {
        "ADX":      float(adx),
        "RSI":      float(rsi),
        "ret3m":    ret3m,
        "vol_stab": vol_stab,
        "price":    cur_price,
        "atr_stop": atr_stop,
        "atr":      atr_val,
    }


# ══════════════════════════════════════════════════════════════
# 랭킹 (섹터 강도 포함)
# ══════════════════════════════════════════════════════════════
def minmax(s: pd.Series) -> pd.Series:
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)


def rank_stocks(passed: dict, etf_data: dict, universe_map: dict) -> pd.DataFrame:
    if not passed:
        return pd.DataFrame()
    df = pd.DataFrame(passed).T
    df["sector"]  = [universe_map.get(t, "Unknown") for t in df.index]
    df["sec_str"] = 0.0
    for idx, row in df.iterrows():
        sym = SECTOR_ETF.get(row["sector"])
        if sym and sym in etf_data:
            ec = etf_data[sym]["Close"]
            if len(ec) >= 63:
                df.loc[idx, "sec_str"] = (
                    row["ret3m"] - float(ec.iloc[-1] / ec.iloc[-63] - 1)
                ) if not pd.isna(row["ret3m"]) else 0.0
    df["sec_n"] = minmax(df["sec_str"])
    df["score"] = (
        minmax(df["ADX"])                 * WEIGHTS["adx"] +
        minmax(df["ret3m"].fillna(0))     * WEIGHTS["ret3m"] +
        minmax(df["sec_n"])               * WEIGHTS["sector"] +
        minmax(df["vol_stab"])            * WEIGHTS["vol_stab"]
    )
    return df.sort_values("score", ascending=False)


# ══════════════════════════════════════════════════════════════
# 상관관계 필터 (튜닝 1: 임계값 0.8)
# ══════════════════════════════════════════════════════════════
def apply_correlation_filter(
    ranked: pd.DataFrame,
    all_data: dict,
    corr_thresh: float = CORR_THRESH,
    window: int = CORR_WINDOW,
    top_n: int = TOP_N,
) -> pd.DataFrame:
    """
    그리디 방식으로 상관관계 0.8 초과 종목 제거.
    - 점수 높은 순서대로 추가
    - 이미 선택된 종목과 상관계수 > corr_thresh이면 제외
    """
    if ranked.empty:
        return ranked

    # 후보 종목의 최근 window일 수익률 시계열 추출
    ret_series: dict = {}
    for t in ranked.index:
        df_t = all_data.get(t)
        if df_t is None or len(df_t) < window + 1:
            continue
        ret = df_t["Close"].tail(window + 1).pct_change().dropna()
        if len(ret) >= window // 2:
            ret_series[t] = ret

    selected = []
    for ticker in ranked.index:
        if len(selected) >= top_n:
            break
        if ticker not in ret_series:
            selected.append(ticker)
            continue

        # 이미 선택된 종목과 상관관계 체크
        too_correlated = False
        for prev in selected:
            if prev not in ret_series:
                continue
            r1 = ret_series[ticker]
            r2 = ret_series[prev]
            common_idx = r1.index.intersection(r2.index)
            if len(common_idx) < 20:
                continue
            corr = float(r1.loc[common_idx].corr(r2.loc[common_idx]))
            if corr > corr_thresh:
                too_correlated = True
                break

        if not too_correlated:
            selected.append(ticker)

    return ranked.loc[selected] if selected else ranked.head(0)


# ══════════════════════════════════════════════════════════════
# 포지션 사이징
# ══════════════════════════════════════════════════════════════
def calc_position_weights(scores: pd.Series, max_w: float = MAX_WEIGHT) -> pd.Series:
    n = len(scores)
    if n == 0:
        return pd.Series(dtype=float)
    w = scores.clip(lower=1e-9)
    w = w / w.sum()
    for _ in range(20):
        if (w <= max_w + 1e-8).all():
            break
        excess = (w - max_w).clip(lower=0).sum()
        w = w.clip(upper=max_w)
        under = w < max_w
        if under.sum() > 0:
            w[under] += excess * w[under] / w[under].sum()
    return w / w.sum()


# ══════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    print("=" * 70)
    print(f"  트렌드+모멘텀 스크리너 (튜닝 버전)   기준일: {today}")
    print(f"  TOP_N={TOP_N}  |  상관관계 임계값={CORR_THRESH}  |  ATR×{ATR_MULT}")
    print("=" * 70)

    # ── [0] 이전 상태 로드 (활성 섹터 / 보유 종목)
    state = load_state()
    prev_holdings  = set(state.get("holdings", []))
    prev_act_sec   = state.get("active_sectors")   # None이면 전체 허용

    print(f"\n[0] 이전 상태")
    print(f"  보유 종목 : {prev_holdings or '없음'}")
    if prev_act_sec:
        print(f"  활성 섹터 : {prev_act_sec}")
    else:
        print("  활성 섹터 : 전체 (초기 실행)")

    # ── [1] 데이터 로드
    print("\n[1] 데이터 로드 (캐시 또는 yfinance 다운로드)...")
    START = "2023-01-01"
    all_data_raw, spy_df, etf_raw, universe_map = load_full_universe(START)
    all_data = {t: add_indicators(df) for t, df in all_data_raw.items()}
    etf_data = {t: add_indicators(df) for t, df in etf_raw.items()}
    all_sectors = set(universe_map.values())
    print(f"  → 종목 {len(all_data)}개 로드 완료 (유니버스: {len(universe_map)}개)")

    # ── [2] 활성 섹터 결정
    # 튜닝 1: 이전 기간 신규 진입 종목의 섹터만 활성
    if prev_act_sec is not None:
        active_sectors = set(prev_act_sec)
        print(f"\n[2] 활성 섹터 (이전 신규 진입 기준): {active_sectors}")
    else:
        # 초기 실행: 섹터 ETF 20MA 기준으로 활성 섹터 판별
        active_sectors = get_active_sectors_from_etf(etf_data, all_sectors)
        print(f"\n[2] 활성 섹터 (ETF 20MA 기준, 초기): {active_sectors}")

    # ── [3] 스크리닝 (모멘텀 기준)
    print(f"\n[3] 스크리닝 ({len(all_data)}종목)...")
    passed_all = {}
    for t, df in all_data.items():
        ok, metrics = screen(df)
        if ok:
            passed_all[t] = metrics
    print(f"  모멘텀 통과: {len(passed_all)}개")

    # 활성 섹터 필터 (신규 진입 후보에만 적용)
    # - 기존 보유 종목: 제외 없이 포함 (스톱 조건은 별도 처리)
    # - 신규 진입 후보: 활성 섹터만 허용
    passed = {}
    for t, metrics in passed_all.items():
        sector = universe_map.get(t, "Unknown")
        if t in prev_holdings:
            passed[t] = metrics  # 기존 보유: 섹터 필터 미적용
        elif sector in active_sectors:
            passed[t] = metrics  # 신규: 활성 섹터만 허용
    print(f"  활성 섹터 필터 후: {len(passed)}개")

    if not passed:
        print("\n  ※ 조건을 통과한 종목이 없습니다.")
        save_state(None, [])
        exit()

    # ── [4] 랭킹
    ranked = rank_stocks(passed, etf_data, universe_map)

    # ── [5] 상관관계 필터 (튜닝 2: 임계값 0.8)
    print(f"\n[4] 상관관계 필터 (임계값 {CORR_THRESH})...")
    top = apply_correlation_filter(ranked, all_data, CORR_THRESH, CORR_WINDOW, TOP_N)
    print(f"  상관관계 필터 후: {len(top)}개")

    # ── [6] 포지션 사이징
    weights = calc_position_weights(top["score"])
    top = top.copy()
    top["weight"] = weights

    # ── [7] 결과 출력
    print("\n" + "=" * 70)
    print(f"  ★ 트렌드+모멘텀 Top {len(top)} (튜닝 버전)")
    print("=" * 70)
    print(f"  {'순위'} {'종목':<13} {'비중':>6} {'점수':>6} "
          f"{'ADX':>5} {'RSI':>5} {'3M수익':>7} {'섹터':<22}")
    print("  " + "─" * 70)
    for rank, (ticker, row) in enumerate(top.iterrows(), 1):
        flag    = "🇺🇸" if not ticker.endswith(".KS") and not ticker.endswith(".KQ") else "🇰🇷"
        ret_str = f"{row['ret3m']:+.1%}" if not pd.isna(row["ret3m"]) else "  N/A"
        is_new  = "✦NEW" if ticker not in prev_holdings else "    "
        print(
            f"  {rank:2d}위 {flag} {ticker:<11}"
            f" {row['weight']:>5.1%}"
            f" {row['score']:>6.3f}"
            f" {row['ADX']:>5.1f}"
            f" {row['RSI']:>5.1f}"
            f" {ret_str:>7}"
            f"  {row['sector']:<20}"
            f" {is_new}"
        )

    # ── [8] 신규 진입 종목의 섹터 → 다음 기간 활성 섹터로 저장
    new_entrants = [t for t in top.index if t not in prev_holdings]
    if new_entrants:
        next_active_sectors = list({universe_map.get(t, "Unknown") for t in new_entrants})
        print(f"\n  [신규 진입] {new_entrants}")
        print(f"  [다음 기간 활성 섹터] {next_active_sectors}")
    else:
        next_active_sectors = list(active_sectors)  # 변화 없으면 유지
        print(f"\n  [신규 진입 없음 → 활성 섹터 유지] {next_active_sectors}")

    save_state(next_active_sectors, list(top.index))
    print(f"\n  상태 저장 완료: {STATE_FILE}")
    print(f"\n  결과: Top {len(top)} | 신규 진입 {len(new_entrants)}개")
    print("=" * 70)
