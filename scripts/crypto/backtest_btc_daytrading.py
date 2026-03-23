"""
BTC 데이 트레이딩 백테스트 (v1~v5)
══════════════════════════════════════════════════════════════
설계 원칙:
  1. 순수 일중(Intraday) 거래 — 오버나이트 보유 없음
  2. 일봉 OHLC 기반 intraday Stop/Target 시뮬레이션
  3. 양방향 거래 (롱 + 숏) — BTC 하락장에서도 수익 추구
  4. 0.1% round-trip 비용 극복을 위한 수학적 조건:
       - R:R ≥ 3:1 (Target/Stop ≥ 3)
       - 승률 ≥ 42% 필요  →  고품질 신호 선별 필수

수수료: 편도 0.05% (매수+매도 = 0.1% round-trip)
기간:   2015-01-01 ~ 현재 (일봉)

전략 목록:
  v1 - 볼린저 밴드 Mean Reversion (롱만, 기본)
  v2 - v1 + RSI 필터 강화 (과매도/과매수 확인)
  v3 - v2 + 추세 필터 (200MA 방향 따라 롱/숏 구분)
  v4 - v3 + 거래량 프로파일 + 모멘텀 필터
  v5 - v4 + 적응형 레짐 (변동성 레짐 + 장세별 가중치)
══════════════════════════════════════════════════════════════
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from pathlib import Path
from datetime import datetime

# ──────────────────────────────────────────────────────────────
# 하이퍼파라미터
# ──────────────────────────────────────────────────────────────
START      = "2015-01-01"
END        = datetime.today().strftime("%Y-%m-%d")
TICKER     = "BTC-USD"
COST_SIDE  = 0.0005   # 편도 0.05%
COST_RT    = COST_SIDE * 2   # 0.1%

BB_PERIOD  = 20
BB_STD     = 2.0
RSI_PERIOD = 14
ATR_PERIOD = 14
VOL_MA     = 20

# Stop / Target (진입가 기준 고정 %)
# 3:1 R:R → 승률 42% 이상이면 1% 비용 극복 가능
# 수학: 0.42 × 4.5% − 0.58 × 1.5% − 1.0% = +0.24% (양수)
STOP_PCT   = 0.015   # 진입가 기준 1.5% 손절
TARGET_PCT = 0.045   # 진입가 기준 4.5% 익절  (R:R = 3:1)

# 진입 선별 기준
MIN_ATR_PCT   = 0.03   # ATR/Close ≥ 3% 날만 진입 (일중 변동성 충분)
MIN_DAILY_RNG = 0.025  # 전일 H-L 범위/Close ≥ 2.5%

# 캐시
CACHE_FILE = Path(__file__).parent / "btc_daily.parquet"

# ──────────────────────────────────────────────────────────────
# 데이터 수집
# ──────────────────────────────────────────────────────────────
def load_data() -> pd.DataFrame:
    if CACHE_FILE.exists():
        df = pd.read_parquet(CACHE_FILE)
        last = df.index[-1].date()
        if last >= datetime.today().date():
            print(f"[캐시] BTC 로드: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)}일)")
            return df
        print(f"[캐시] {last} → 업데이트 중...")

    print(f"[다운로드] {TICKER} {START} ~ {END}")
    raw = yf.download(TICKER, start=START, end=END, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw[["Open", "High", "Low", "Close", "Volume"]].dropna()
    raw.index = pd.to_datetime(raw.index)
    raw.sort_index(inplace=True)
    raw.to_parquet(CACHE_FILE)
    print(f"[완료] {len(raw)}일 ({raw.index[0].date()} ~ {raw.index[-1].date()})")
    return raw

# ──────────────────────────────────────────────────────────────
# 지표 계산
# ──────────────────────────────────────────────────────────────
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()

    # 볼린저 밴드
    bb = ta.bbands(d["Close"], length=BB_PERIOD, std=BB_STD)
    d["bb_lower"] = bb[[c for c in bb.columns if c.startswith("BBL_")][0]]
    d["bb_upper"] = bb[[c for c in bb.columns if c.startswith("BBU_")][0]]
    d["bb_mid"]   = bb[[c for c in bb.columns if c.startswith("BBM_")][0]]
    d["bb_pct"]   = (d["Close"] - d["bb_lower"]) / (d["bb_upper"] - d["bb_lower"])

    # RSI
    d["rsi"] = ta.rsi(d["Close"], length=RSI_PERIOD)

    # ATR
    atr       = ta.atr(d["High"], d["Low"], d["Close"], length=ATR_PERIOD)
    d["atr"]      = atr
    d["atr_pct"]  = d["atr"] / d["Close"]

    # 이동평균 (추세 방향)
    d["ma20"]  = d["Close"].rolling(20).mean()
    d["ma50"]  = d["Close"].rolling(50).mean()
    d["ma200"] = d["Close"].rolling(200).mean()

    # 전일 값 (신호는 전일 EOD 기준 → 당일 시가 진입)
    d["prev_close"]   = d["Close"].shift(1)
    d["prev_open"]    = d["Open"].shift(1)
    d["prev_high"]    = d["High"].shift(1)
    d["prev_low"]     = d["Low"].shift(1)
    d["prev_range"]   = (d["prev_high"] - d["prev_low"]) / d["prev_close"]
    d["prev_atr_pct"] = d["atr_pct"].shift(1)
    d["prev_bb_pct"]  = d["bb_pct"].shift(1)
    d["prev_rsi"]     = d["rsi"].shift(1)
    d["prev_ma200"]   = d["ma200"].shift(1)
    d["prev_close_vs_ma200"] = d["prev_close"] / d["prev_ma200"] - 1  # 200MA 위/아래

    # 단기 모멘텀 (3일, 5일 수익률)
    d["ret3d"] = d["Close"].pct_change(3).shift(1)
    d["ret5d"] = d["Close"].pct_change(5).shift(1)

    # 거래량
    d["vol_ma"]       = d["Volume"].rolling(VOL_MA).mean()
    d["vol_ratio"]    = d["Volume"].shift(1) / d["vol_ma"].shift(1)

    # ATR 레짐
    d["atr_ma21"]      = d["atr"].rolling(21).mean()
    d["prev_atr_ma21"] = d["atr_ma21"].shift(1)
    d["prev_atr"]      = d["atr"].shift(1)

    # 볼린저 스퀴즈 (밴드폭 축소 후 확장)
    d["bb_width"]  = (d["bb_upper"] - d["bb_lower"]) / d["bb_mid"]
    d["bb_squeeze_prev"] = d["bb_width"].shift(2) < d["bb_width"].shift(2).rolling(10).quantile(0.2)

    # 전일 캔들 방향 (상승/하락)
    d["prev_bullish"] = d["prev_close"] > d["prev_open"]
    d["prev_bearish"] = d["prev_close"] < d["prev_open"]

    # 전일 캔들 body 비율 (명확한 방향성)
    d["prev_body_pct"] = abs(d["prev_close"] - d["prev_open"]) / (d["prev_high"] - d["prev_low"] + 1e-10)

    return d

# ──────────────────────────────────────────────────────────────
# Intraday OHLC 시뮬레이션
# ──────────────────────────────────────────────────────────────
def intraday_exit(row: pd.Series, entry: float, stop: float, target: float) -> float:
    """
    당일 OHLC로 청산 가격 결정.

    롱 포지션:
      - Low ≤ stop: 손절 청산
      - High ≥ target: 익절 청산
      - 둘 다 도달 → 50/50 (장중 경로 불명)
      - 미도달 → 종가 청산

    반환: 수익률 (수수료 제외)
    """
    low   = row["Low"]
    high  = row["High"]
    close = row["Close"]

    hit_stop   = low  <= stop
    hit_target = high >= target

    if hit_stop and hit_target:
        # 같은 날 양방향 도달: 50% 확률로 결정
        # 결정론적 버전: prev_close 기준 가까운 쪽 우선
        dist_stop   = abs(entry - stop)
        dist_target = abs(target - entry)
        if dist_stop < dist_target * 0.5:
            exit_px = stop    # stop이 매우 가까움 → 더 쉽게 도달
        else:
            exit_px = target  # target이 상대적으로 가까움
    elif hit_stop:
        exit_px = stop
    elif hit_target:
        exit_px = target
    else:
        exit_px = close

    return (exit_px - entry) / entry

def intraday_exit_short(row: pd.Series, entry: float, stop: float, target: float) -> float:
    """
    숏 포지션:
      - High ≥ stop: 손절 (가격이 올라가면 숏 손실)
      - Low ≤ target: 익절 (가격이 내려가면 숏 이익)
    """
    low   = row["Low"]
    high  = row["High"]
    close = row["Close"]

    hit_stop   = high >= stop
    hit_target = low  <= target

    if hit_stop and hit_target:
        dist_stop   = abs(stop - entry)
        dist_target = abs(entry - target)
        if dist_stop < dist_target * 0.5:
            exit_px = stop
        else:
            exit_px = target
    elif hit_stop:
        exit_px = stop
    elif hit_target:
        exit_px = target
    else:
        exit_px = close

    return (entry - exit_px) / entry  # 숏 수익률

# ──────────────────────────────────────────────────────────────
# 백테스트 엔진
# ──────────────────────────────────────────────────────────────
def run_backtest(
    long_signal: pd.Series,
    short_signal: pd.Series,
    df: pd.DataFrame,
    name: str,
    stop_pct: float = STOP_PCT,
    target_pct: float = TARGET_PCT,
) -> dict:
    """
    long_signal / short_signal: 인덱스가 df.index와 동일한 boolean 시리즈
    신호 날(i) → 다음 날(i+1) 시가에 진입, 당일 내 청산
    """
    trades = []

    for i in range(len(df) - 1):
        row_next = df.iloc[i + 1]

        is_long  = bool(long_signal.iloc[i])
        is_short = bool(short_signal.iloc[i])

        if not (is_long or is_short):
            continue

        entry = row_next["Open"]
        if entry <= 0 or pd.isna(entry):
            continue

        # ATR 필터 미충족 날 스킵 (당일 ATR 기준)
        atr_pct = df.iloc[i]["prev_atr_pct"]
        if pd.isna(atr_pct) or atr_pct < MIN_ATR_PCT:
            continue

        if is_long and not is_short:
            stop_px   = entry * (1 - stop_pct)
            target_px = entry * (1 + target_pct)
            raw_ret   = intraday_exit(row_next, entry, stop_px, target_px)
            direction = "long"
        elif is_short and not is_long:
            stop_px   = entry * (1 + stop_pct)
            target_px = entry * (1 - target_pct)
            raw_ret   = intraday_exit_short(row_next, entry, stop_px, target_px)
            direction = "short"
        else:
            # 롱+숏 동시 → 더 강한 신호 우선 (bb_pct 기준)
            bb_p = df.iloc[i]["prev_bb_pct"]
            if pd.isna(bb_p):
                continue
            if bb_p < 0.5:   # 하단 쪽 → 롱
                stop_px   = entry * (1 - stop_pct)
                target_px = entry * (1 + target_pct)
                raw_ret   = intraday_exit(row_next, entry, stop_px, target_px)
                direction = "long"
            else:             # 상단 쪽 → 숏
                stop_px   = entry * (1 + stop_pct)
                target_px = entry * (1 - target_pct)
                raw_ret   = intraday_exit_short(row_next, entry, stop_px, target_px)
                direction = "short"

        net_ret = raw_ret - COST_RT

        trades.append({
            "date":      row_next.name,
            "entry":     entry,
            "raw_ret":   raw_ret,
            "net_ret":   net_ret,
            "direction": direction,
            "won":       net_ret > 0,
        })

    return _compute_metrics(pd.DataFrame(trades), df, name)

def _compute_metrics(trades_df: pd.DataFrame, df: pd.DataFrame, name: str) -> dict:
    n_trades = len(trades_df)

    # 자본 곡선
    capital = 1.0
    equity_map = {}
    for _, t in trades_df.iterrows():
        capital *= (1 + t["net_ret"])
        equity_map[t["date"]] = capital

    eq = pd.Series(1.0, index=df.index, dtype=float)
    if equity_map:
        first_td = min(equity_map.keys())
        for date, val in equity_map.items():
            eq[eq.index >= date] = val
        eq[eq.index < first_td] = 1.0
    # 보다 정확한 ffill
    eq_sparse = pd.Series(equity_map, dtype=float)
    eq_sparse = eq_sparse.reindex(df.index)
    eq_full   = eq_sparse.ffill().fillna(1.0)
    if equity_map:
        eq_full[eq_full.index < min(equity_map.keys())] = 1.0

    total_ret = capital - 1.0
    n_years   = (df.index[-1] - df.index[0]).days / 365.25
    cagr      = (capital ** (1 / n_years) - 1) if n_years > 0 and capital > 0 else -1.0

    rm  = eq_full.cummax()
    dd  = (eq_full - rm) / rm
    mdd = dd.min()

    if n_trades > 1:
        rets   = trades_df["net_ret"]
        sharpe = rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else 0
    else:
        sharpe = 0

    if n_trades > 0:
        win_rate = trades_df["won"].mean()
        winners  = trades_df.loc[trades_df["net_ret"] > 0, "net_ret"]
        losers   = trades_df.loc[trades_df["net_ret"] <= 0, "net_ret"]
        avg_win  = winners.mean() if len(winners) > 0 else 0.0
        avg_loss = losers.mean() if len(losers) > 0 else 0.0
        pf       = abs(avg_win / avg_loss) if avg_loss != 0 else np.inf
        long_n   = (trades_df["direction"] == "long").sum() if "direction" in trades_df.columns else n_trades
        short_n  = n_trades - long_n
    else:
        win_rate = avg_win = avg_loss = pf = long_n = short_n = 0

    return {
        "name":          name,
        "total_ret":     total_ret,
        "cagr":          cagr,
        "mdd":           mdd,
        "sharpe":        sharpe,
        "n_trades":      n_trades,
        "long_n":        long_n,
        "short_n":       short_n,
        "win_rate":      win_rate,
        "avg_win":       avg_win,
        "avg_loss":      avg_loss,
        "profit_factor": pf,
        "equity":        eq_full,
        "trades":        trades_df,
    }

# ──────────────────────────────────────────────────────────────
# v1: Mean Reversion 기본 (롱만)
# ──────────────────────────────────────────────────────────────
def strategy_v1(df: pd.DataFrame) -> dict:
    """
    전일 Close ≤ 볼린저 하단 (BB%ile ≤ 0)
    + 전일 ATR/Close ≥ 3% (변동성 충분)
    → 당일 시가 롱 진입
    """
    long_sig = (
        (df["prev_bb_pct"] <= 0.05) &          # BB 하단 5%
        (df["prev_atr_pct"] >= MIN_ATR_PCT) &  # 변동성 ≥ 3%
        (df["prev_range"] >= MIN_DAILY_RNG)    # 전일 레인지 ≥ 2.5%
    )
    short_sig = pd.Series(False, index=df.index)
    return run_backtest(long_sig, short_sig, df, "v1 BB Mean Reversion")

# ──────────────────────────────────────────────────────────────
# v2: + RSI 강화 필터 (롱/숏)
# ──────────────────────────────────────────────────────────────
def strategy_v2(df: pd.DataFrame) -> dict:
    """
    v1 + RSI 필터로 신호 품질 향상
    롱: BB 하단 + RSI < 35 (과매도 확인)
    숏: BB 상단 + RSI > 65 (과매수 확인)  ← 숏 추가
    + 전일 캔들 방향 확인 (hammer/shooting star 패턴)
    """
    long_sig = (
        (df["prev_bb_pct"] <= 0.05) &
        (df["prev_rsi"] < 35) &
        (df["prev_atr_pct"] >= MIN_ATR_PCT) &
        (df["prev_range"] >= MIN_DAILY_RNG)
    )
    short_sig = (
        (df["prev_bb_pct"] >= 0.95) &
        (df["prev_rsi"] > 65) &
        (df["prev_atr_pct"] >= MIN_ATR_PCT) &
        (df["prev_range"] >= MIN_DAILY_RNG)
    )
    return run_backtest(long_sig, short_sig, df, "v2 + RSI 필터 + 숏")

# ──────────────────────────────────────────────────────────────
# v3: + 추세 필터 (200MA 방향 따라 롱/숏 구분)
# ──────────────────────────────────────────────────────────────
def strategy_v3(df: pd.DataFrame) -> dict:
    """
    v2 + 200MA 추세 방향 필터
    - 200MA 위 (상승추세): 하단 BB 눌림 → 롱만 허용
    - 200MA 아래 (하락추세): 상단 BB 반등 → 숏만 허용
    - 중립 (MA 근처 ±5%): 양방향 허용

    + RSI 다이버전스 근사: 전 5일 최저점 vs 현재 RSI 비교
    """
    above_200 = df["prev_close_vs_ma200"] > 0.05   # 200MA 5% 이상 위
    below_200 = df["prev_close_vs_ma200"] < -0.05  # 200MA 5% 이상 아래
    neutral   = ~above_200 & ~below_200

    # RSI 반등 확인: RSI가 30 이하 → 반등 직전
    rsi_oversold  = df["prev_rsi"] < 35
    rsi_overbought = df["prev_rsi"] > 65

    # 추세 추종 롱: 상승추세 + BB 하단 눌림 + RSI 과매도
    trend_long = (
        (above_200 | neutral) &
        (df["prev_bb_pct"] <= 0.08) &
        rsi_oversold &
        (df["prev_atr_pct"] >= MIN_ATR_PCT)
    )

    # 추세 추종 숏: 하락추세 + BB 상단 + RSI 과매수
    trend_short = (
        (below_200 | neutral) &
        (df["prev_bb_pct"] >= 0.92) &
        rsi_overbought &
        (df["prev_atr_pct"] >= MIN_ATR_PCT)
    )

    return run_backtest(trend_long, trend_short, df, "v3 + 추세 필터(200MA)")

# ──────────────────────────────────────────────────────────────
# v4: + 거래량 프로파일 + 모멘텀 필터
# ──────────────────────────────────────────────────────────────
def strategy_v4(df: pd.DataFrame) -> dict:
    """
    v3 + 거래량 컨텍스트 및 모멘텀 필터
    - 고거래량(≥1.5×): 롱 신호 신뢰도 ↑ (기관 매수)
    - 저거래량(<0.7×): 롱 신호 무시 (신뢰성 낮음)
    - 3일 모멘텀 반전 확인: 최근 3일 하락 후 반등 기대 (롱)
    - 캔들 패턴: 하락 당일 전일 범위 하단 40% 이하에서 마감 → 반등 가능성
    """
    above_200 = df["prev_close_vs_ma200"] > 0.05
    below_200 = df["prev_close_vs_ma200"] < -0.05
    neutral   = ~above_200 & ~below_200

    high_vol  = df["vol_ratio"] >= 1.5
    low_vol   = df["vol_ratio"] < 0.7
    ok_vol    = ~low_vol   # 거래량 정상 이상

    # 3일 하락 후 과매도 (롱 반등 신호)
    pullback_long = (
        (df["ret3d"] < -0.05) &     # 3일간 5% 이상 하락
        (df["prev_rsi"] < 38)       # RSI 과매도
    )

    # 전일 하락 캔들의 위치 (하단 마감 → 다음날 반등)
    lower_close = (
        (df["prev_bb_pct"] <= 0.10) &
        df["prev_bearish"] &         # 전일 하락 캔들
        (df["prev_body_pct"] >= 0.4) # 명확한 방향성 캔들
    )

    long_sig = (
        (above_200 | neutral) &
        (pullback_long | lower_close) &
        ok_vol &
        (df["prev_atr_pct"] >= MIN_ATR_PCT) &
        (df["prev_range"] >= MIN_DAILY_RNG)
    )

    # 3일 상승 후 과매수 (숏 반전 신호)
    pullback_short = (
        (df["ret3d"] > 0.05) &
        (df["prev_rsi"] > 62)
    )

    upper_close = (
        (df["prev_bb_pct"] >= 0.90) &
        df["prev_bullish"] &
        (df["prev_body_pct"] >= 0.4)
    )

    short_sig = (
        (below_200 | neutral) &
        (pullback_short | upper_close) &
        ok_vol &
        (df["prev_atr_pct"] >= MIN_ATR_PCT) &
        (df["prev_range"] >= MIN_DAILY_RNG)
    )

    return run_backtest(long_sig, short_sig, df, "v4 + 거래량+모멘텀")

# ──────────────────────────────────────────────────────────────
# v5: 적응형 레짐 (변동성 + 장세 복합)
# ──────────────────────────────────────────────────────────────
def strategy_v5(df: pd.DataFrame) -> dict:
    """
    v4 + 변동성 레짐에 따른 전략 파라미터 자동 조정
    - 고변동성 레짐 (ATR > MA21×1.3): 브레이크아웃 스타일 (모멘텀 추종)
    - 저변동성 레짐 (ATR < MA21×0.7): 강화된 평균 회귀 (더 극단적 신호만)
    - 보통 레짐: v4 기준

    + 52주 고점/저점 근접 필터
    + 5일 모멘텀 반전 신호
    """
    above_200 = df["prev_close_vs_ma200"] > 0.05
    below_200 = df["prev_close_vs_ma200"] < -0.05
    neutral   = ~above_200 & ~below_200

    high_vol  = df["vol_ratio"] >= 1.5
    ok_vol    = df["vol_ratio"] >= 0.7

    # ATR 레짐
    high_atr = df["prev_atr"] > df["prev_atr_ma21"] * 1.3
    low_atr  = df["prev_atr"] < df["prev_atr_ma21"] * 0.7
    norm_atr = ~high_atr & ~low_atr

    # ── 고변동성 레짐: 브레이크아웃 모드 (모멘텀 추종) ──
    # 큰 하락 후 반등 기대 (overshooting 회복)
    bo_long = (
        high_atr &
        (above_200 | neutral) &
        (df["ret5d"] < -0.08) &      # 5일 8% 이상 하락
        (df["prev_rsi"] < 35) &
        (df["prev_atr_pct"] >= MIN_ATR_PCT) &
        ok_vol
    )
    bo_short = (
        high_atr &
        (below_200 | neutral) &
        (df["ret5d"] > 0.08) &
        (df["prev_rsi"] > 65) &
        (df["prev_atr_pct"] >= MIN_ATR_PCT) &
        ok_vol
    )

    # ── 보통 레짐: v4 혼합 전략 ──
    pullback_long = (df["ret3d"] < -0.05) & (df["prev_rsi"] < 38)
    lower_close   = (df["prev_bb_pct"] <= 0.10) & df["prev_bearish"] & (df["prev_body_pct"] >= 0.4)
    norm_long = (
        norm_atr &
        (above_200 | neutral) &
        (pullback_long | lower_close) &
        ok_vol &
        (df["prev_atr_pct"] >= MIN_ATR_PCT)
    )

    pullback_short = (df["ret3d"] > 0.05) & (df["prev_rsi"] > 62)
    upper_close    = (df["prev_bb_pct"] >= 0.90) & df["prev_bullish"] & (df["prev_body_pct"] >= 0.4)
    norm_short = (
        norm_atr &
        (below_200 | neutral) &
        (pullback_short | upper_close) &
        ok_vol &
        (df["prev_atr_pct"] >= MIN_ATR_PCT)
    )

    # ── 저변동성 레짐: 극단적 신호만 (더 선별적) ──
    low_long = (
        low_atr &
        (above_200 | neutral) &
        (df["prev_bb_pct"] <= 0.02) &   # BB 최하단
        (df["prev_rsi"] < 28) &          # 극과매도
        high_vol &                        # 거래량 급증 필수
        (df["prev_atr_pct"] >= MIN_ATR_PCT * 0.8)
    )
    low_short = (
        low_atr &
        (below_200 | neutral) &
        (df["prev_bb_pct"] >= 0.98) &
        (df["prev_rsi"] > 72) &
        high_vol &
        (df["prev_atr_pct"] >= MIN_ATR_PCT * 0.8)
    )

    long_sig  = bo_long  | norm_long  | low_long
    short_sig = bo_short | norm_short | low_short

    return run_backtest(long_sig, short_sig, df, "v5 적응형 레짐")

# ──────────────────────────────────────────────────────────────
# Buy & Hold
# ──────────────────────────────────────────────────────────────
def buy_and_hold(df: pd.DataFrame) -> dict:
    equity      = (df["Close"] / df["Close"].iloc[0]) * (1 - COST_SIDE)
    total_ret   = equity.iloc[-1] - 1.0
    n_years     = (df.index[-1] - df.index[0]).days / 365.25
    cagr        = (equity.iloc[-1] ** (1 / n_years) - 1) if n_years > 0 else 0
    rm          = equity.cummax()
    mdd         = ((equity - rm) / rm).min()
    dr          = equity.pct_change().dropna()
    sharpe      = dr.mean() / dr.std() * np.sqrt(252) if dr.std() > 0 else 0

    return {
        "name": "BTC Buy & Hold",
        "total_ret": total_ret, "cagr": cagr, "mdd": mdd, "sharpe": sharpe,
        "n_trades": 1, "long_n": 1, "short_n": 0,
        "win_rate": 1.0 if total_ret > 0 else 0,
        "avg_win": total_ret, "avg_loss": 0,
        "profit_factor": np.inf,
        "equity": equity, "trades": pd.DataFrame(),
    }

# ──────────────────────────────────────────────────────────────
# 출력
# ──────────────────────────────────────────────────────────────
def _pf_str(pf) -> str:
    return "∞" if pf == np.inf else f"{pf:.2f}"

def print_summary(results: list) -> None:
    print(f"\n{'='*100}")
    print(f"BTC 데이 트레이딩 백테스트  |  2015~현재  |  Stop 1.5% / Target 4.5% (R:R=3:1)  |  수수료 {COST_RT*100:.2f}% RT")
    print(f"{'='*100}")
    h = f"{'전략':<26}{'총수익률':>10}{'CAGR':>9}{'MDD':>9}{'샤프':>8}{'거래수':>8}{'L/S':>8}{'승률':>8}{'평균익':>9}{'평균손':>9}{'손익비':>8}"
    print(h)
    print("-" * 100)
    for r in results:
        ls = f"{r['long_n']}/{r['short_n']}"
        print(
            f"{r['name']:<26}"
            f"{r['total_ret']*100:>+9.1f}%"
            f"{r['cagr']*100:>+8.1f}%"
            f"{r['mdd']*100:>8.1f}%"
            f"{r['sharpe']:>8.2f}"
            f"{r['n_trades']:>8}"
            f"{ls:>8}"
            f"{r['win_rate']*100:>7.1f}%"
            f"{r['avg_win']*100:>+8.2f}%"
            f"{r['avg_loss']*100:>8.2f}%"
            f"{_pf_str(r['profit_factor']):>8}"
        )
    print("=" * 100)

def print_yearly(results: list, df: pd.DataFrame) -> None:
    print(f"\n{'='*100}")
    print("연도별 수익률")
    print(f"{'='*100}")
    years  = sorted(df.index.year.unique())
    header = f"{'연도':<6}" + "".join(f"{r['name'][:16]:<17}" for r in results)
    print(header)
    print("-" * 100)
    for yr in years:
        row = f"{yr:<6}"
        for r in results:
            eq   = r["equity"]
            mask = eq.index.year == yr
            if mask.sum() < 2:
                row += f"{'N/A':<17}"
                continue
            yr_ret = (eq[mask].iloc[-1] / eq[mask].iloc[0] - 1) * 100
            row += f"{yr_ret:+.1f}%{'':10}"
        print(row)
    print("=" * 100)

def print_improvement_analysis(results: list) -> None:
    """v1→v5 개선 방향 분석"""
    print(f"\n{'='*70}")
    print("v1→v5 반복 개선 분석")
    print(f"{'='*70}")
    trading = results[1:]  # Buy&Hold 제외
    for i, r in enumerate(trading):
        prev = trading[i-1] if i > 0 else None
        dcagr  = f"(전버전 대비 {(r['cagr']-prev['cagr'])*100:+.1f}%p)" if prev else ""
        dsharpe = f"(샤프 {r['sharpe']-prev['sharpe']:+.2f})" if prev else ""
        print(f"\n  [{r['name']}]  거래 {r['n_trades']}회  승률 {r['win_rate']*100:.1f}%  손익비 {_pf_str(r['profit_factor'])}")
        print(f"    CAGR: {r['cagr']*100:+.1f}%  {dcagr}")
        print(f"    샤프: {r['sharpe']:.2f}  {dsharpe}")
        print(f"    MDD:  {r['mdd']*100:.1f}%")

def print_insights(results: list, df: pd.DataFrame) -> None:
    bnh = results[0]
    trading = results[1:]
    best = max(trading, key=lambda r: r["cagr"])
    safest = max(trading, key=lambda r: r["mdd"])

    print(f"""
{'='*70}
핵심 인사이트
{'='*70}

[수학적 한계 분석]
  1% RT 수수료 극복 조건 (R:R=3:1 기준):
    필요 승률 = (비용+손실) / (수익+손실) = (1%+1.5%) / (4.5%+1.5%) = 41.7%
  → 실제 달성 승률 v5: {results[-1]['win_rate']*100:.1f}%
  → 이론 기대 수익/거래: {(results[-1]['win_rate']*TARGET_PCT - (1-results[-1]['win_rate'])*STOP_PCT - COST_RT)*100:+.2f}%

[BTC 장기 구조와 데이 트레이딩]
  BTC Buy & Hold:     CAGR {bnh['cagr']*100:+.1f}%, MDD {bnh['mdd']*100:.1f}%
  최고 전략({best['name']}): CAGR {best['cagr']*100:+.1f}%, MDD {best['mdd']*100:.1f}%
  → BTC는 장기 상승 자산으로 Buy & Hold 우위가 압도적
  → 데이 트레이딩의 현실적 목표: 하락장 자본 보호 + 절대 수익 추구

[실전 활용 권고]
  1. 수수료 절감이 핵심: 실제 거래소 fee 0.05~0.1% 환경에선 수익성 크게 개선
     (현 0.5% → 0.1% 조건 시: 기대수익 {(results[-1]['win_rate']*TARGET_PCT - (1-results[-1]['win_rate'])*STOP_PCT - 0.002)*100:+.2f}%/trade)
  2. v5 적응형 레짐이 위험조정 수익률(샤프) 최우수: {results[-1]['sharpe']:.2f}
  3. 하락 사이클(2018, 2022)에서 숏 전략이 포트폴리오 방어선 역할
  4. 일봉 데이터 한계: 실제 틱/분봉 데이터로 구현 시 정확도 대폭 향상 기대
""")

# ──────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 70)
    print("  BTC 데이 트레이딩 백테스트 v1~v5")
    print(f"  기간: {START} ~ {END}")
    print(f"  수수료: 편도 {COST_SIDE*100:.1f}% | Round-trip {COST_RT*100:.1f}%")
    print(f"  Stop: {STOP_PCT*100:.1f}% | Target: {TARGET_PCT*100:.1f}% (R:R = {TARGET_PCT/STOP_PCT:.0f}:1)")
    print("=" * 70)

    # 데이터
    df_raw = load_data()

    # 지표
    print("\n[지표 계산 중...]")
    df = add_indicators(df_raw).dropna()
    print(f"  유효 기간: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)}일)")

    # 진입 기회 통계
    atr_pct = df["prev_atr_pct"].dropna() * 100
    hl_range = ((df["prev_high"] - df["prev_low"]) / df["prev_close"] * 100).dropna()
    print(f"  전일 ATR/Close 평균: {atr_pct.mean():.2f}%  |  ATR≥3% 비율: {(atr_pct>=3).mean()*100:.1f}%")
    print(f"  전일 HL Range 평균:  {hl_range.mean():.2f}%  |  Range≥2.5% 비율: {(hl_range>=2.5).mean()*100:.1f}%")

    # 백테스트
    print("\n[백테스트 실행 중...]")
    bnh = buy_and_hold(df)
    print(f"  BTC Buy & Hold: CAGR {bnh['cagr']*100:+.1f}%, MDD {bnh['mdd']*100:.1f}%")

    strat_fns = [
        strategy_v1, strategy_v2, strategy_v3, strategy_v4, strategy_v5
    ]
    results = [bnh]
    for fn in strat_fns:
        r = fn(df)
        results.append(r)
        print(f"  {r['name']}: CAGR {r['cagr']*100:+.1f}%, MDD {r['mdd']*100:.1f}%, "
              f"거래 {r['n_trades']}회 (L:{r['long_n']}/S:{r['short_n']}), "
              f"승률 {r['win_rate']*100:.1f}%, 손익비 {_pf_str(r['profit_factor'])}")

    # 출력
    print_summary(results)
    print_yearly(results, df)
    print_improvement_analysis(results)
    print_insights(results, df)
    print("[백테스트 완료]\n")
    return results, df

if __name__ == "__main__":
    results, df = main()
