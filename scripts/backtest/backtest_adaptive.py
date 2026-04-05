"""
적응형 전략 백테스트 — 시장 국면별 공격/균형/보수 동적 전환
══════════════════════════════════════════════════════════════════
전략 논리 (주식/경제 전문가 관점):
  시장은 단일 국면이 아니라 강세/보통/약세를 순환한다.
  고정 파라미터는 특정 국면에서 최적이지만, 다른 국면에선 비효율적이다.

  → 시장 국면을 감지하여 ATR 승수 + 리밸런싱 주기를 동적 전환:

  ┌─────────────────────────────────────────────────────────┐
  │ 국면 판별 (SPY 기준, 매 리밸런싱 시점)                      │
  │                                                         │
  │ 1차: 추세 (골든/데드크로스)                                │
  │   SPY 50MA > 200MA → 상승 추세                           │
  │   SPY 50MA < 200MA → 하락 추세                           │
  │                                                         │
  │ 2차: 추세 강도 (50MA vs 200MA gap)                        │
  │   gap > 5%  → 강한 상승 → 공격적 (ATR=2.0, 주간)          │
  │   gap 0~5%  → 보통 상승 → 균형형 (ATR=2.5, 격주)          │
  │   gap < 0%  → 하락/횡보 → 보수적 (ATR=3.5, 월간)          │
  │                                                         │
  │ 3차: 변동성 필터 (SPY ATR 20일 이동평균)                    │
  │   ATR 상위 20% (고변동성) → 한 단계 보수적으로 이동          │
  │   → 공격적→균형형, 균형형→보수적, 보수적은 유지+현금비중↑     │
  └─────────────────────────────────────────────────────────┘

비교 대상:
  A. 적응형 (Adaptive)   — 위 규칙대로 동적 전환
  B. 공격적 고정          — ATR=2.0, 주간
  C. 균형형 고정          — ATR=2.5, 격주
  D. 보수적 고정          — ATR=3.5, 월간
  E. SPY (벤치마크)
══════════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import json
import logging
import os
import sys

import numpy as np
import pandas as pd
import pandas_ta as ta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent.parent))

START = "2010-01-01"  # 기본값 (윈도우별로 덮어씀)
END   = "2024-12-31"
TOP_N = 10

ATR_PERIOD    = 14
MAX_WEIGHT    = 0.20
COST_PER_SIDE = 0.001

WEIGHTS = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)

DATA_DIR = "data"
MANIFEST = os.path.join(DATA_DIR, "manifest.json")

# ── 세 가지 전략 프리셋 ─────────────────────────────────────────
PRESETS = {
    "aggressive":   {"atr_mult": 2.0, "freq": "W",  "label": "공격적"},
    "balanced":     {"atr_mult": 2.5, "freq": "2W", "label": "균형형"},
    "conservative": {"atr_mult": 3.5, "freq": "M",  "label": "보수적"},
}

# ── 국면 판별 임계값 ─────────────────────────────────────────────
GAP_STRONG_BULL = 0.05   # 50MA-200MA gap > 5% → 강한 상승
VOL_HIGH_PCTILE = 80     # SPY ATR 상위 20% → 고변동성

from core.constants import US_UNIVERSE, KR_UNIVERSE, ALL_UNIVERSE, SECTOR_ETF


# ══════════════════════════════════════════════════════════════════
# 공통 함수 (backtest_atr_tuning.py 기반)
# ══════════════════════════════════════════════════════════════════

def load_local_data():
    if not os.path.exists(MANIFEST):
        logger.warning(f"  ✗ {MANIFEST} 없음. 먼저 python download_data.py 를 실행하세요.")
        sys.exit(1)
    with open(MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    all_data = {}
    for ticker, info in manifest["stocks"].items():
        path = os.path.join(DATA_DIR, info["file"])
        if os.path.exists(path):
            df = pd.read_parquet(path, engine="pyarrow")
            if len(df) >= 220:
                all_data[ticker] = df

    etf_data = {}
    for ticker, info in manifest["etfs"].items():
        path = os.path.join(DATA_DIR, info["file"])
        if os.path.exists(path):
            etf_data[ticker] = pd.read_parquet(path, engine="pyarrow")

    spy_close = None
    spy_path = os.path.join(DATA_DIR, "spy.parquet")
    if os.path.exists(spy_path):
        spy_df = pd.read_parquet(spy_path, engine="pyarrow")
        spy_close = spy_df["Close"].squeeze()

    return all_data, etf_data, spy_close


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
    d["ATR"] = atr if atr is not None else np.nan
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
    if pd.isna(adx) or adx < 25:
        return False, {}
    ma20, ma50, ma200 = row.get("MA20"), row.get("MA50"), row.get("MA200")
    if any(pd.isna(v) for v in [ma20, ma50, ma200]) or not (ma20>ma50>ma200):
        return False, {}
    rsi = row.get("RSI", np.nan)
    if pd.isna(rsi) or not (50 <= rsi <= 75):
        return False, {}
    vol60 = row.get("VolMA60", np.nan)
    if pd.isna(vol60) or vol60==0 or (r20["Volume"]>vol60*3.0).any():
        return False, {}
    if (r5["Close"].pct_change().abs() > 0.10).any():
        return False, {}
    if swing_hh_hl(r60) < 3:
        return False, {}
    high52 = row.get("High52w", np.nan)
    if not pd.isna(high52) and high52>0 and row["Close"] < high52*0.80:
        return False, {}

    ret3m    = float(hist["Close"].iloc[-1]/r63["Close"].iloc[0])-1 if len(r63)>=60 else np.nan
    vol_cv   = r20["Volume"].std()/(vol60+1e-9)
    vol_stab = float(1/(vol_cv+1e-6))

    atr_val  = float(hist["ATR"].dropna().iloc[-1]) \
               if "ATR" in hist.columns and len(hist["ATR"].dropna())>0 else np.nan
    peak20   = float(hist["High"].tail(20).max())
    atr_stop = peak20 - atr_val * atr_mult if not pd.isna(atr_val) else np.nan

    # 현재가가 이미 ATR 스톱 이하인 종목은 제외 (스톱 트리거 상태)
    if not pd.isna(atr_stop) and float(hist["Close"].iloc[-1]) <= atr_stop:
        return False, {}

    return True, {
        "ADX": float(adx), "RSI": float(rsi),
        "ret3m": ret3m, "vol_stab": vol_stab,
        "price": float(hist["Close"].iloc[-1]),
        "atr_stop": atr_stop, "atr": atr_val,
    }


def rank_stocks(passed, etf_data, as_of):
    if not passed:
        return pd.DataFrame()
    df = pd.DataFrame(passed).T
    df["sector"] = [ALL_UNIVERSE.get(t,"Unknown") for t in df.index]
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
    if n == 0:
        return pd.Series(dtype=float)
    total = scores.sum()
    if total == 0 or pd.isna(total):
        return pd.Series([1.0/n]*n, index=scores.index)
    adj = scores.copy()
    adj[adj <= 0] = 1e-6
    w = adj / adj.sum()
    for _ in range(20):
        if (w <= max_w + 1e-8).all():
            break
        excess = (w - max_w).clip(lower=0).sum()
        w      = w.clip(upper=max_w)
        under  = w < max_w
        if under.sum() > 0:
            w[under] += excess * w[under] / w[under].sum()
    return w / w.sum()


def check_stops(holdings, all_data, prev_dt, rd):
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


def calc_turnover_cost(old_h, new_h, cost_per_side):
    all_t = set(list(old_h.keys()) + list(new_h.keys()))
    turnover = sum(abs(old_h.get(t,{}).get("w",0) - new_h.get(t,{}).get("w",0)) for t in all_t)
    return turnover * cost_per_side


def make_rebal_dates(freq):
    if freq == "W":
        return pd.date_range(start=START, end=END, freq="W-FRI")
    elif freq == "2W":
        weekly = pd.date_range(start=START, end=END, freq="W-FRI")
        return weekly[::2]
    else:
        return pd.date_range(start=START, end=END, freq="BME")


# ══════════════════════════════════════════════════════════════════
# 시장 국면 판별
# ══════════════════════════════════════════════════════════════════

def detect_regime(spy_close, as_of):
    """
    SPY 데이터를 기반으로 현재 시장 국면을 판별한다.

    반환: ("aggressive" | "balanced" | "conservative", regime_info)
    """
    spy = spy_close[spy_close.index <= as_of]
    if len(spy) < 200:
        return "conservative", {"reason": "데이터 부족", "gap": 0, "vol_pctile": 0}

    ma50  = float(spy.rolling(50).mean().iloc[-1])
    ma200 = float(spy.rolling(200).mean().iloc[-1])
    gap   = (ma50 - ma200) / ma200  # 50MA vs 200MA gap (비율)

    # SPY ATR 기반 변동성 (최근값의 1년 내 백분위)
    spy_df = pd.DataFrame({"Close": spy, "High": spy, "Low": spy})  # 간이 ATR
    spy_atr = ta.atr(spy_df["High"], spy_df["Low"], spy_df["Close"], length=14)
    if spy_atr is not None and len(spy_atr.dropna()) > 0:
        cur_atr = float(spy_atr.dropna().iloc[-1])
        atr_1y  = spy_atr.dropna().tail(252)
        vol_pctile = float((atr_1y < cur_atr).mean() * 100)
    else:
        vol_pctile = 50

    # 1차: 추세 방향 + 강도
    if gap > GAP_STRONG_BULL:
        regime = "aggressive"
    elif gap > 0:
        regime = "balanced"
    else:
        regime = "conservative"

    # 2차: 고변동성 필터 — 한 단계 보수적으로
    if vol_pctile >= VOL_HIGH_PCTILE:
        if regime == "aggressive":
            regime = "balanced"
        elif regime == "balanced":
            regime = "conservative"
        # conservative는 유지

    return regime, {
        "gap": gap, "ma50": ma50, "ma200": ma200,
        "vol_pctile": vol_pctile, "regime": regime,
    }


def detect_regime_v2(spy_close, as_of):
    """
    v2: 3계층 복합 국면 판별
    ─────────────────────────────────
    Layer 1: 추세 (MA gap)        — 기본 국면 결정
    Layer 2: 모멘텀 (RSI + 기울기)  — 1단계 보수적 조정
    Layer 3: 리스크 (급락 + 지지선)  — 즉시 보수적 전환
    + 비대칭 전환: 공격→보수 즉시, 보수→공격 2주 확인
    """
    spy = spy_close[spy_close.index <= as_of]
    if len(spy) < 200:
        return "conservative", {"reason": "데이터 부족", "gap": 0,
                                 "vol_pctile": 0, "layer": "L0"}

    close = spy
    ma20  = float(close.rolling(20).mean().iloc[-1])
    ma50  = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])
    gap   = (ma50 - ma200) / ma200
    price = float(close.iloc[-1])

    # SPY RSI
    spy_rsi_series = ta.rsi(close, 14)
    spy_rsi = float(spy_rsi_series.dropna().iloc[-1]) if spy_rsi_series is not None and len(spy_rsi_series.dropna()) > 0 else 50.0

    # SPY ATR 변동성 백분위
    spy_df = pd.DataFrame({"Close": close, "High": close, "Low": close})
    spy_atr = ta.atr(spy_df["High"], spy_df["Low"], spy_df["Close"], length=14)
    if spy_atr is not None and len(spy_atr.dropna()) > 0:
        cur_atr = float(spy_atr.dropna().iloc[-1])
        atr_1y  = spy_atr.dropna().tail(252)
        vol_pctile = float((atr_1y < cur_atr).mean() * 100)
    else:
        vol_pctile = 50

    # 20MA 기울기 (20일 전 대비 변화율)
    ma20_20ago = close.rolling(20).mean()
    if len(ma20_20ago.dropna()) >= 20:
        ma20_slope = (ma20 - float(ma20_20ago.dropna().iloc[-20])) / float(ma20_20ago.dropna().iloc[-20])
    else:
        ma20_slope = 0

    # 주간 수익률
    weekly_ret = float(close.iloc[-1] / close.iloc[-5] - 1) if len(close) >= 5 else 0

    # 3주 연속 하락 체크
    if len(close) >= 15:
        w1 = float(close.iloc[-1] / close.iloc[-5] - 1)
        w2 = float(close.iloc[-5] / close.iloc[-10] - 1)
        w3 = float(close.iloc[-10] / close.iloc[-15] - 1)
        three_week_decline = (w1 < 0 and w2 < 0 and w3 < 0)
    else:
        three_week_decline = False

    triggered_layer = "L1"

    # ── Layer 1: 추세 (기본 국면) ──
    if gap > GAP_STRONG_BULL:
        regime = "aggressive"
    elif gap > 0:
        regime = "balanced"
    else:
        regime = "conservative"

    # ── Layer 2: 모멘텀 오버라이드 ──
    # 개선: RSI < 35로 강화, 기울기 -3%로 완화하여 과민 반응 방지
    downgrade = False

    # RSI < 35: 명확한 과매도 진입
    if spy_rsi < 35:
        downgrade = True
        triggered_layer = "L2_RSI<35"

    # RSI > 70 + 3주 연속 하락: 과매수 후 꺾임
    if spy_rsi > 70 and three_week_decline:
        downgrade = True
        triggered_layer = "L2_RSI>70+decline"

    # 20MA 기울기: 20일간 3% 이상 하락 시에만 (완화)
    if ma20_slope < -0.03:
        downgrade = True
        triggered_layer = "L2_slope"

    if downgrade:
        if regime == "aggressive":
            regime = "balanced"
        elif regime == "balanced":
            regime = "conservative"

    # ── Layer 3: 리스크 트리거 (즉시 보수적) ──
    # 개선: 200MA 하회는 RSI < 40 복합 조건으로 변경
    force_conservative = False

    # 주간 수익률 -5% 이하: 급락 (유지)
    if weekly_ret < -0.05:
        force_conservative = True
        triggered_layer = "L3_crash"

    # 200MA 하회 + RSI < 40: 복합 조건 (단독 → 복합으로 강화)
    if price < ma200 and spy_rsi < 40:
        force_conservative = True
        triggered_layer = "L3_below200MA+RSI"

    # 고변동성(상위 10%) + 하락 추세 (유지)
    if vol_pctile >= 90 and weekly_ret < 0:
        force_conservative = True
        triggered_layer = "L3_highvol"

    if force_conservative:
        regime = "conservative"

    return regime, {
        "gap": gap, "ma50": ma50, "ma200": ma200,
        "vol_pctile": vol_pctile, "regime": regime,
        "spy_rsi": spy_rsi, "weekly_ret": weekly_ret,
        "ma20_slope": ma20_slope, "layer": triggered_layer,
    }


# ══════════════════════════════════════════════════════════════════
# 비대칭 전환 래퍼
# ══════════════════════════════════════════════════════════════════

class AsymmetricTransition:
    """
    공격적 → 보수적: 즉시 전환
    보수적 → 공격적: 2주 연속 공격적 시그널 확인 후 전환
    """
    def __init__(self):
        self.pending_upgrade = None   # ("aggressive", 확인 시작 날짜)
        self.current_regime = None

    def apply(self, raw_regime, date):
        if self.current_regime is None:
            self.current_regime = raw_regime
            return raw_regime

        regime_order = {"conservative": 0, "balanced": 1, "aggressive": 2}
        cur_level  = regime_order[self.current_regime]
        raw_level  = regime_order[raw_regime]

        # 다운그레이드 (더 보수적) → 즉시 적용
        if raw_level < cur_level:
            self.current_regime = raw_regime
            self.pending_upgrade = None
            return raw_regime

        # 업그레이드 (더 공격적) → 2주 확인
        if raw_level > cur_level:
            if self.pending_upgrade and self.pending_upgrade[0] == raw_regime:
                days_waiting = (date - self.pending_upgrade[1]).days
                if days_waiting >= 7:  # 1주 확인 완료
                    self.current_regime = raw_regime
                    self.pending_upgrade = None
                    return raw_regime
                else:
                    return self.current_regime  # 아직 확인 중
            else:
                self.pending_upgrade = (raw_regime, date)
                return self.current_regime  # 확인 시작

        # 동일 레벨
        self.pending_upgrade = None
        return raw_regime


# ══════════════════════════════════════════════════════════════════
# 백테스트 — 고정 전략
# ══════════════════════════════════════════════════════════════════

def run_fixed_backtest(all_data, etf_data, freq, atr_mult, cost_per_side):
    """기존 고정 파라미터 백테스트."""
    rebal_dates = make_rebal_dates(freq)
    nav = 1.0
    holdings = {}
    prev_dt  = None
    trades   = 0
    nav_series = pd.Series(dtype=float)

    for rd in rebal_dates:
        if prev_dt and holdings:
            holdings = check_stops(holdings, all_data, prev_dt, rd)
        if prev_dt and holdings:
            ret = sum(
                info["w"] * (float(all_data[t][all_data[t].index<=rd]["Close"].iloc[-1]) /
                             float(all_data[t][all_data[t].index<=prev_dt]["Close"].iloc[-1]) - 1)
                for t, info in holdings.items()
                if t in all_data and len(all_data[t][all_data[t].index<=prev_dt]["Close"]) > 0
                   and len(all_data[t][all_data[t].index<=rd]["Close"]) > 0
            )
            nav *= (1 + ret)

        passed = {}
        for t, df_t in all_data.items():
            ok, met = screen(df_t, rd, atr_mult)
            if ok:
                passed[t] = met

        ranked = rank_stocks(passed, etf_data, rd)
        top = ranked.head(TOP_N)
        new_h = {}
        if len(top) > 0:
            ws = position_weights(top["score"])
            for t in top.index:
                df_t  = all_data.get(t)
                entry = float(df_t[df_t.index<=rd]["Close"].iloc[-1]) if df_t is not None else 1.0
                new_h[t] = {
                    "w": float(ws[t]), "entry": entry, "peak": entry,
                    "atr_stop": float(top.loc[t, "atr_stop"]) if "atr_stop" in top.columns else np.nan,
                }

        nav *= (1 - calc_turnover_cost(holdings, new_h, cost_per_side))
        trades += len(set(holdings.keys()) ^ set(new_h.keys()))
        holdings = new_h
        prev_dt  = rd
        nav_series[rd] = nav

    return nav_series, trades


# ══════════════════════════════════════════════════════════════════
# 백테스트 — 적응형 전략
# ══════════════════════════════════════════════════════════════════

def run_adaptive_backtest(all_data, etf_data, spy_close, cost_per_side,
                          detect_fn=None, use_asymmetric=False):
    """
    매주 금요일마다 시장 국면을 판별하고,
    국면에 맞는 전략의 리밸런싱 주기가 도래했을 때만 리밸런싱한다.

    detect_fn: 국면 판별 함수 (기본: detect_regime v1)
    use_asymmetric: 비대칭 전환 적용 여부 (v2용)
    """
    if detect_fn is None:
        detect_fn = detect_regime

    # 주간 단위로 체크 (모든 금요일)
    all_fridays  = pd.date_range(start=START, end=END, freq="W-FRI")
    biweekly     = set(pd.date_range(start=START, end=END, freq="W-FRI")[::2])
    monthly      = set(pd.date_range(start=START, end=END, freq="BME"))

    nav = 1.0
    holdings    = {}
    prev_dt     = None
    prev_regime = None
    trades      = 0
    cur_atr_mult = 2.5  # 초기값
    transition  = AsymmetricTransition() if use_asymmetric else None

    nav_series    = pd.Series(dtype=float)
    regime_log    = []

    for rd in all_fridays:
        # 국면 판별
        raw_regime, info = detect_fn(spy_close, rd)

        # 비대칭 전환 적용
        if transition:
            regime = transition.apply(raw_regime, rd)
        else:
            regime = raw_regime

        preset = PRESETS[regime]
        regime_changed = (regime != prev_regime) and prev_regime is not None

        # 리밸런싱 판단: 현재 국면의 주기에 맞는 날인가?
        should_rebal = False
        if regime == "aggressive":
            should_rebal = True  # 매주
        elif regime == "balanced":
            should_rebal = rd in biweekly
        elif regime == "conservative":
            # 월말에 가장 가까운 금요일
            should_rebal = rd in monthly or any(abs((rd - m).days) <= 3 for m in monthly)

        # 국면 전환 시 즉시 리밸런싱 (리스크 관리)
        if regime_changed:
            should_rebal = True

        # 스톱로스 체크 (매주 수행)
        if prev_dt and holdings:
            holdings = check_stops(holdings, all_data, prev_dt, rd)

        # 구간 수익 반영 (매주)
        if prev_dt and holdings:
            ret = sum(
                info_h["w"] * (float(all_data[t][all_data[t].index<=rd]["Close"].iloc[-1]) /
                               float(all_data[t][all_data[t].index<=prev_dt]["Close"].iloc[-1]) - 1)
                for t, info_h in holdings.items()
                if t in all_data and len(all_data[t][all_data[t].index<=prev_dt]["Close"]) > 0
                   and len(all_data[t][all_data[t].index<=rd]["Close"]) > 0
            )
            nav *= (1 + ret)

        # 리밸런싱
        if should_rebal:
            cur_atr_mult = preset["atr_mult"]

            passed = {}
            for t, df_t in all_data.items():
                ok, met = screen(df_t, rd, cur_atr_mult)
                if ok:
                    passed[t] = met

            ranked = rank_stocks(passed, etf_data, rd)
            top = ranked.head(TOP_N)
            new_h = {}
            if len(top) > 0:
                ws = position_weights(top["score"])
                for t in top.index:
                    df_t  = all_data.get(t)
                    entry = float(df_t[df_t.index<=rd]["Close"].iloc[-1]) if df_t is not None else 1.0
                    new_h[t] = {
                        "w": float(ws[t]), "entry": entry, "peak": entry,
                        "atr_stop": float(top.loc[t, "atr_stop"]) if "atr_stop" in top.columns else np.nan,
                    }

            nav *= (1 - calc_turnover_cost(holdings, new_h, cost_per_side))
            trades += len(set(holdings.keys()) ^ set(new_h.keys()))
            holdings = new_h

        regime_log.append({
            "date": rd, "regime": regime,
            "gap": info["gap"], "vol_pctile": info["vol_pctile"],
            "rebalanced": should_rebal, "regime_changed": regime_changed,
        })

        prev_dt     = rd
        prev_regime = regime
        nav_series[rd] = nav

    return nav_series, trades, pd.DataFrame(regime_log)


# ══════════════════════════════════════════════════════════════════
# 성과 지표
# ══════════════════════════════════════════════════════════════════

def calc_metrics(nav, label):
    ret   = nav.pct_change().dropna()
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr  = (nav.iloc[-1] ** (1/years)) - 1 if years > 0 else 0
    dd    = (nav - nav.cummax()) / nav.cummax()
    mdd   = dd.min()
    ann   = np.sqrt(52)  # 주간 단위로 통일
    sharpe = (ret.mean() / (ret.std() + 1e-9)) * ann
    win    = (ret > 0).mean()
    return {
        "label": label, "CAGR": cagr, "총수익": nav.iloc[-1]-1,
        "MDD": mdd, "샤프": sharpe, "승률": win, "nav": nav,
    }


# ══════════════════════════════════════════════════════════════════
# 시각화
# ══════════════════════════════════════════════════════════════════

def plot_results(results, spy_close, regime_df, window_label, start, end):
    fig, axes = plt.subplots(2, 1, figsize=(14, 10), height_ratios=[3, 1],
                             gridspec_kw={"hspace": 0.15})

    # ── 상단: NAV 곡선 ──
    ax = axes[0]
    colors = {"적응형 v1 (MA gap)": "#f4845f", "적응형 v2 (3계층)": "#e63946",
              "공격적 (ATR=2.0 주간)": "#457b9d",
              "균형형 (ATR=2.5 격주)": "#2a9d8f", "보수적 (ATR=3.5 월간)": "#e9c46a",
              "SPY": "black"}
    styles = {"적응형 v1 (MA gap)": "-.", "적응형 v2 (3계층)": "-",
              "공격적 (ATR=2.0 주간)": "--",
              "균형형 (ATR=2.5 격주)": "--", "보수적 (ATR=3.5 월간)": "--", "SPY": ":"}

    for r in results:
        lbl = r["label"]
        ax.plot(r["nav"].index, r["nav"].values,
                label=f"{lbl}  CAGR {r['CAGR']:+.1%}  MDD {r['MDD']:+.1%}  샤프 {r['샤프']:.2f}",
                color=colors.get(lbl, "gray"), ls=styles.get(lbl, "-"),
                lw=2.5 if "v2" in lbl else (1.8 if "v1" in lbl else 1.2),
                alpha=1.0 if "v2" in lbl else 0.7)

    ax.set_ylabel("NAV (x)")
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}x"))
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(alpha=0.25)
    ax.set_title(f"[{window_label}] 적응형 vs 고정 전략 ({start} ~ {end})",
                 fontsize=13, fontweight="bold")

    # ── 하단: 국면 타임라인 ──
    ax2 = axes[1]
    regime_colors = {"aggressive": "#e63946", "balanced": "#2a9d8f", "conservative": "#e9c46a"}
    regime_labels = {"aggressive": "공격적", "balanced": "균형형", "conservative": "보수적"}

    for _, row in regime_df.iterrows():
        ax2.axvspan(row["date"], row["date"] + pd.Timedelta(days=7),
                    color=regime_colors[row["regime"]], alpha=0.6)

    from matplotlib.patches import Patch
    legend_patches = [Patch(color=c, label=regime_labels[r]) for r, c in regime_colors.items()]
    ax2.legend(handles=legend_patches, fontsize=8, loc="upper right")
    ax2.set_ylabel("국면")
    ax2.set_yticks([])
    ax2.set_xlabel("Date")
    ax2.grid(alpha=0.25)

    plt.tight_layout()
    fname = f"backtest_adaptive_{window_label}.png"
    plt.savefig(RESULTS_DIR / fname, dpi=150, bbox_inches="tight")
    logger.info(f"  차트 저장: {fname}")
    plt.close()


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def run_window(all_data, etf_data, spy_close, start, end, window_label):
    """단일 윈도우 백테스트 실행 — 적응형 v1, v2 + 고정 3종 + SPY."""
    global START, END
    START, END = start, end

    logger.info(f"\n{'█'*70}")
    logger.info(f"  [{window_label}] {start} ~ {end}")
    logger.info(f"{'█'*70}")

    # 적응형 v1 (MA gap only)
    logger.info(f"\n  [1/6] 적응형 v1 (MA gap)")
    nav_v1, _, regime_v1 = run_adaptive_backtest(
        all_data, etf_data, spy_close, COST_PER_SIDE,
        detect_fn=detect_regime, use_asymmetric=False)
    m_v1 = calc_metrics(nav_v1, "적응형 v1 (MA gap)")

    dist_v1 = regime_v1["regime"].value_counts(normalize=True)
    regime_line_v1 = "    국면: " + "".join(
        f"{PRESETS[r]['label']} {dist_v1.get(r,0):.0%}  "
        for r in ["aggressive","balanced","conservative"]
    ) + f"| 전환 {int(regime_v1['regime_changed'].sum())}회"
    logger.info(regime_line_v1)

    # 적응형 v2 (3계층 + 비대칭 전환)
    logger.info(f"  [2/6] 적응형 v2 (3계층+비대칭)")
    nav_v2, _, regime_v2 = run_adaptive_backtest(
        all_data, etf_data, spy_close, COST_PER_SIDE,
        detect_fn=detect_regime_v2, use_asymmetric=True)
    m_v2 = calc_metrics(nav_v2, "적응형 v2 (3계층)")

    dist_v2 = regime_v2["regime"].value_counts(normalize=True)
    regime_line_v2 = "    국면: " + "".join(
        f"{PRESETS[r]['label']} {dist_v2.get(r,0):.0%}  "
        for r in ["aggressive","balanced","conservative"]
    ) + f"| 전환 {int(regime_v2['regime_changed'].sum())}회"
    logger.info(regime_line_v2)

    # 고정 전략들
    logger.info(f"  [3/6] 공격적 (ATR=2.0, 주간)")
    nav_agg, _ = run_fixed_backtest(all_data, etf_data, "W", 2.0, COST_PER_SIDE)
    m_agg = calc_metrics(nav_agg, "공격적 (ATR=2.0 주간)")

    logger.info(f"  [4/6] 균형형 (ATR=2.5, 격주)")
    nav_bal, _ = run_fixed_backtest(all_data, etf_data, "2W", 2.5, COST_PER_SIDE)
    m_bal = calc_metrics(nav_bal, "균형형 (ATR=2.5 격주)")

    logger.info(f"  [5/6] 보수적 (ATR=3.5, 월간)")
    nav_con, _ = run_fixed_backtest(all_data, etf_data, "M", 3.5, COST_PER_SIDE)
    m_con = calc_metrics(nav_con, "보수적 (ATR=3.5 월간)")

    # SPY
    spy_start = spy_close[spy_close.index >= start]
    if len(spy_start) == 0:
        spy_nav = pd.Series([1.0], index=[pd.Timestamp(start)])
    else:
        spy_nav = spy_start / float(spy_start.iloc[0])
        spy_nav = spy_nav[spy_nav.index <= end]
    m_spy = calc_metrics(spy_nav, "SPY")

    all_results = [m_v1, m_v2, m_agg, m_bal, m_con, m_spy]

    # 결과 출력
    logger.info(f"\n  {'전략':<25} {'CAGR':>8} {'총수익':>10} {'MDD':>8} {'샤프':>6} {'승률':>6}")
    logger.info("  " + "─" * 65)
    for r in all_results:
        marker = " ★" if r is m_v2 else ""
        logger.info(f"  {r['label']:<25} {r['CAGR']:>+8.1%} {r['총수익']:>+9.0%}"
                    f" {r['MDD']:>+8.1%} {r['샤프']:>6.2f} {r['승률']:>6.1%}{marker}")

    # v1 vs v2 비교
    logger.info(f"\n  [v1 vs v2]")
    logger.info(f"    CAGR: {m_v1['CAGR']:+.1%} → {m_v2['CAGR']:+.1%}  ({m_v2['CAGR']-m_v1['CAGR']:+.1%}p)")
    logger.info(f"    MDD:  {m_v1['MDD']:+.1%} → {m_v2['MDD']:+.1%}  ({'개선' if m_v2['MDD'] > m_v1['MDD'] else '악화'} {abs(m_v2['MDD']-m_v1['MDD']):.1%}p)")
    logger.info(f"    샤프: {m_v1['샤프']:.2f} → {m_v2['샤프']:.2f}  ({m_v2['샤프']-m_v1['샤프']:+.2f})")

    # 차트 — v2 국면 타임라인 사용
    plot_results(all_results, spy_close, regime_v2, window_label, start, end)

    # CSV 저장
    rows = []
    for r in all_results:
        rows.append({
            "윈도우": window_label, "기간": f"{start}~{end}",
            "전략": r["label"],
            "CAGR": f"{r['CAGR']:+.1%}", "총수익": f"{r['총수익']:+.0%}",
            "MDD": f"{r['MDD']:+.1%}", "샤프": f"{r['샤프']:.2f}",
            "승률": f"{r['승률']:.1%}",
        })

    return rows, regime_v2


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true", help="상세 출력 활성화")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    # ── 멀티 윈도우 정의 ──
    WINDOWS = [
        ("A_풀사이클",   "2007-01-01", "2024-12-31"),  # GFC 포함 전체
        ("B_현대시장",   "2015-01-01", "2024-12-31"),  # 핵심 평가 구간
        ("C_최근변동성", "2020-01-01", "2024-12-31"),  # 코로나→금리→AI
    ]

    if args.verbose:
        print("=" * 70)
        print("  멀티 윈도우 적응형 전략 백테스트")
        print("  시장 국면별 공격/균형/보수 동적 전환")
        print(f"  거래비용: 편도 {COST_PER_SIDE*100:.1f}%")
        print(f"  윈도우: {len(WINDOWS)}개")
        for label, s, e in WINDOWS:
            print(f"    {label}: {s} ~ {e}")
        print("=" * 70)

    # ── 데이터 로드 ──
    if args.verbose:
        print("\n[데이터 로드]")
    all_data, etf_raw, spy_close = load_local_data()
    if args.verbose:
        print(f"  종목 {len(all_data)}개, ETF {len(etf_raw)}개, SPY ✓")

        print(f"  지표 계산 ({len(all_data)}개)...")
    for t in list(all_data.keys()):
        all_data[t] = add_indicators(all_data[t])
    etf_data = {t: add_indicators(df) for t, df in etf_raw.items()}

    # ── 각 윈도우 실행 ──
    all_rows = []
    for label, start, end in WINDOWS:
        rows, regime_df = run_window(all_data, etf_data, spy_close, start, end, label)
        all_rows.extend(rows)

    # ── 통합 CSV ──
    pd.DataFrame(all_rows).to_csv(RESULTS_DIR / "backtest_adaptive_multiwindow.csv",
                                   index=False, encoding="utf-8-sig")
    if args.verbose:
        print(f"\n  통합 결과 저장: backtest_adaptive_multiwindow.csv")

    # ── 크로스 윈도우 비교 요약 ──
    if args.verbose:
        print(f"\n{'═'*70}")
        print("  크로스 윈도우 요약 — v1 vs v2 비교")
        print("═" * 70)
        print(f"  {'윈도우':<15} {'v1 CAGR':>9} {'v1 MDD':>9} {'v2 CAGR':>9} {'v2 MDD':>9} {'MDD개선':>8}")
        print("  " + "─" * 60)
        for label, _, _ in WINDOWS:
            v1r = [r for r in all_rows if r["윈도우"]==label and "v1" in r["전략"]]
            v2r = [r for r in all_rows if r["윈도우"]==label and "v2" in r["전략"]]
            if v1r and v2r:
                print(f"  {label:<15} {v1r[0]['CAGR']:>9} {v1r[0]['MDD']:>9}"
                      f" {v2r[0]['CAGR']:>9} {v2r[0]['MDD']:>9}")
        print()
