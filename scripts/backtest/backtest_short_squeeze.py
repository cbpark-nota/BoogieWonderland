"""
숏스퀴즈(Short Squeeze) 백테스트
══════════════════════════════════════════════════════════════
접근 방식:
  과거 공매도 잔량 데이터는 무료로 구할 수 없으므로,
  주가 기반 프록시 지표(3가지 동시 충족) 사용:
    1. 거래량 스파이크   : 20일 평균 대비 2x+ 거래량 폭발
    2. 최근 하락 + 반등  : 20일 수익률 < -5%, 당일 수익률 > +1.5%
    3. ATR 급증         : 20일 평균 ATR 대비 1.3x+ 변동성 폭발

진입: 시그널 발생 다음 영업일 시가
청산: ATR 스톱로스 OR 최대 보유기간 도달 (더 빠른 쪽)
포지션: 동일 비중, 최대 MAX_POSITIONS 동시 보유 (슬롯 제약)
유니버스: S&P500 + NASDAQ-100 + KOSPI200 + KOSDAQ150 (동적 수집)
수수료  : 편도 0.2% (왕복 0.4%)
══════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import pandas_ta as ta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent))
from data_cache import load_full_universe

RESULTS_DIR = _THIS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════
# 파라미터 상수 (튜닝 포인트 — 모두 여기서 관리)
# 최적 파라미터: 시나리오 A (베이스라인) — 7개 시나리오 튜닝 결과
#   조건(거래수≥20, 손익비≥1.0)을 충족하는 유일 시나리오
#   승률 48%, 손익비 1.66, MDD -24.7%, 127건
# ══════════════════════════════════════════════════════════════
START = "2022-01-01"        # 백테스트 시작일 (~3년)

# ── 시그널 파라미터 ──────────────────────────────────────────
VOL_SPIKE_MULT = 2.0        # 거래량 스파이크: 20일 평균 대비 배수
VOL_MA_PERIOD  = 20         # 거래량 이동평균 기간
RECENT_DECLINE = -0.05      # 최근 20일 수익률 기준 (하락 판단: -5% 이하)
REVERSAL_MIN   = 0.015      # 당일 반등 최소값 (+1.5% 이상)
ATR_PERIOD     = 14         # ATR 계산 기간 (일)
ATR_MA_PERIOD  = 20         # ATR 이동평균 기간 (급증 판단용)
ATR_SURGE_MULT = 1.3        # ATR 급증 배수: 20일 평균 ATR 대비
USE_MA_FILTER  = False      # MA 정배열 필터 (MA20 > MA50) — 튜닝 결과 비활성화

# ── 리스크 / 포지션 파라미터 ─────────────────────────────────
ATR_STOP_MULT  = 2.0        # 스톱로스: 진입가 − ATR × 배수
MAX_HOLD_DAYS  = 20         # 최대 보유기간 (거래일)
MAX_POSITIONS  = 5          # 최대 동시 포지션 수
COMMISSION     = 0.002      # 편도 수수료 (0.2%)

# ── 종목 필터 ─────────────────────────────────────────────────
MIN_PRICE      = 5.0        # 최소 주가 (페니스톡 제외)
MIN_VOL_AVG    = 100_000    # 최소 20일 평균 거래량


# ══════════════════════════════════════════════════════════════
# 시그널 계산 (벡터화)
# ══════════════════════════════════════════════════════════════
def add_signals(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame | None:
    """
    숏스퀴즈 프록시 시그널 컬럼 추가.
    데이터가 부족하면 None 반환.
    params: 오버라이드 파라미터 딕셔너리 (None이면 전역 상수 사용)
    """
    p = params or {}
    vol_spike  = p.get("VOL_SPIKE_MULT", VOL_SPIKE_MULT)
    decline    = p.get("RECENT_DECLINE",  RECENT_DECLINE)
    reversal   = p.get("REVERSAL_MIN",    REVERSAL_MIN)
    atr_surge  = p.get("ATR_SURGE_MULT",  ATR_SURGE_MULT)
    ma_filter  = p.get("USE_MA_FILTER",   USE_MA_FILTER)

    min_rows = ATR_PERIOD + ATR_MA_PERIOD + 55  # MA50을 위해 여유 추가
    if len(df) < min_rows:
        return None

    df = df.copy()

    # ATR + 이동평균
    df["atr"]    = ta.atr(df["High"], df["Low"], df["Close"], length=ATR_PERIOD)
    df["atr_ma"] = df["atr"].rolling(ATR_MA_PERIOD).mean()

    # 거래량 이동평균
    df["vol_ma"] = df["Volume"].rolling(VOL_MA_PERIOD).mean()

    # 조건 1: 거래량 스파이크
    c_vol_spike = df["Volume"]               > vol_spike * df["vol_ma"]
    # 조건 2a: 최근 하락 (20일 수익률)
    c_decline   = df["Close"].pct_change(20) < decline
    # 조건 2b: 당일 반등
    c_reversal  = df["Close"].pct_change()   > reversal
    # 조건 3: ATR 급증
    c_atr_surge = df["atr"]                  > atr_surge * df["atr_ma"]
    # 기본 필터
    c_price_ok  = df["Close"]                > MIN_PRICE
    c_vol_ok    = df["vol_ma"]               > MIN_VOL_AVG

    # MA 정배열 필터 (MA20 > MA50)
    if ma_filter:
        df["ma20"] = df["Close"].rolling(20).mean()
        df["ma50"] = df["Close"].rolling(50).mean()
        c_ma_align = df["ma20"] > df["ma50"]
    else:
        c_ma_align = pd.Series(True, index=df.index)

    df["signal"] = (
        c_vol_spike & c_decline & c_reversal & c_atr_surge
        & c_price_ok & c_vol_ok & c_ma_align
    ).fillna(False)

    return df


# ══════════════════════════════════════════════════════════════
# 개별 거래 추출 (종목별)
# ══════════════════════════════════════════════════════════════
def extract_trades(ticker: str, df: pd.DataFrame, params: dict | None = None) -> list[dict]:
    """
    단일 종목 OHLCV + 시그널 데이터에서 모든 거래 추출.

    진입: 시그널 발생 다음 영업일 시가
    청산: 스톱로스(저가 기준) OR 최대 보유기간 도달
    """
    p = params or {}
    atr_stop  = p.get("ATR_STOP_MULT",  ATR_STOP_MULT)
    max_hold  = p.get("MAX_HOLD_DAYS",  MAX_HOLD_DAYS)

    trades   = []
    n        = len(df)
    closes   = df["Close"].values
    opens    = df["Open"].values
    lows     = df["Low"].values
    atrs     = df["atr"].values
    dates    = df.index.to_list()
    sigs     = df["signal"].values

    for sig_idx in range(n - 2):
        if not sigs[sig_idx]:
            continue

        entry_idx   = sig_idx + 1
        entry_date  = dates[entry_idx]
        entry_price = opens[entry_idx]
        atr_e       = atrs[entry_idx]

        if np.isnan(entry_price) or np.isnan(atr_e):
            continue
        if entry_price <= 0 or atr_e <= 0:
            continue

        stop_loss = entry_price - atr_stop * atr_e

        exit_price  = None
        exit_date   = None
        exit_reason = None
        hold_days   = 0

        for k in range(1, max_hold + 2):
            idx = entry_idx + k
            if idx >= n:
                exit_price  = closes[idx - 1]
                exit_date   = dates[idx - 1]
                exit_reason = "data_end"
                hold_days   = k - 1
                break

            hold_days = k

            if lows[idx] <= stop_loss:
                exit_price  = stop_loss
                exit_date   = dates[idx]
                exit_reason = "stop_loss"
                break

            if k >= max_hold:
                exit_price  = closes[idx]
                exit_date   = dates[idx]
                exit_reason = "max_hold"
                break

        if exit_price is None or exit_date is None:
            continue

        eff_entry  = entry_price * (1 + COMMISSION)
        eff_exit   = exit_price  * (1 - COMMISSION)
        net_return = eff_exit / eff_entry - 1

        trades.append({
            "ticker":      ticker,
            "signal_date": dates[sig_idx],
            "entry_date":  entry_date,
            "exit_date":   exit_date,
            "entry_price": entry_price,
            "exit_price":  exit_price,
            "stop_loss":   stop_loss,
            "exit_reason": exit_reason,
            "net_return":  net_return,
            "hold_days":   hold_days,
        })

    return trades


# ══════════════════════════════════════════════════════════════
# 포지션 슬롯 제약 필터
# ══════════════════════════════════════════════════════════════
def select_with_capacity(all_trades: list[dict]) -> list[dict]:
    """
    MAX_POSITIONS 동시 포지션 제약 하에 체결 가능한 거래 선택.
    entry_date 순 탐욕 알고리즘 (먼저 진입한 거래 우선).
    같은 종목의 중복 포지션 방지.
    """
    trades_sorted = sorted(all_trades, key=lambda t: t["entry_date"])
    active_slots  = []
    selected      = []

    for trade in trades_sorted:
        entry = trade["entry_date"]
        active_slots = [(t, e) for t, e in active_slots if e > entry]
        active_tickers = {t for t, _ in active_slots}
        if trade["ticker"] in active_tickers:
            continue
        if len(active_slots) < MAX_POSITIONS:
            active_slots.append((trade["ticker"], trade["exit_date"]))
            selected.append(trade)

    return selected


# ══════════════════════════════════════════════════════════════
# Equity 곡선 생성
# ══════════════════════════════════════════════════════════════
def build_equity_curve(selected_trades: list[dict]) -> pd.Series:
    if not selected_trades:
        return pd.Series([1.0], index=[pd.Timestamp(START)])

    records = [(pd.Timestamp(START), 1.0)]
    equity  = 1.0

    for trade in sorted(selected_trades, key=lambda t: t["exit_date"]):
        pos_size = equity / MAX_POSITIONS
        equity  += pos_size * trade["net_return"]
        records.append((trade["exit_date"], equity))

    dates = [r[0] for r in records]
    vals  = [r[1] for r in records]
    return pd.Series(vals, index=dates)


# ══════════════════════════════════════════════════════════════
# 성과 지표 계산
# ══════════════════════════════════════════════════════════════
def calc_metrics(selected_trades: list[dict], equity: pd.Series) -> dict:
    if not selected_trades:
        return {}

    returns   = np.array([t["net_return"] for t in selected_trades])
    hold_days = np.array([t["hold_days"]  for t in selected_trades])
    reasons   = [t["exit_reason"] for t in selected_trades]

    wins  = returns[returns >  0]
    loses = returns[returns <= 0]

    win_rate = len(wins) / len(returns)
    avg_win  = wins.mean()  if len(wins)  > 0 else 0.0
    avg_loss = loses.mean() if len(loses) > 0 else 0.0

    profit_factor = (
        (wins.sum() / abs(loses.sum()))
        if len(loses) > 0 and loses.sum() != 0 else np.inf
    )

    max_loss = returns.min()

    eq_vals = equity.values
    mdd     = ((eq_vals - np.maximum.accumulate(eq_vals)) / np.maximum.accumulate(eq_vals)).min()

    avg_hold = hold_days.mean()
    trades_per_year = 252 / max(avg_hold, 1)
    ret_std = returns.std()
    sharpe  = (returns.mean() / (ret_std + 1e-9)) * np.sqrt(trades_per_year) if ret_std > 0 else 0.0

    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years > 0 and equity.iloc[-1] > 0:
        cagr = equity.iloc[-1] ** (1 / years) - 1
    else:
        cagr = 0.0

    n_stop    = reasons.count("stop_loss")
    n_maxhold = reasons.count("max_hold")
    n_dataend = reasons.count("data_end")

    return {
        "총거래수":       len(returns),
        "승률":           win_rate,
        "평균수익":       avg_win,
        "평균손실":       avg_loss,
        "최대손실":       max_loss,
        "손익비":         profit_factor,
        "Sharpe":         sharpe,
        "CAGR":           cagr,
        "MDD":            mdd,
        "평균보유일":     avg_hold,
        "스톱청산수":     n_stop,
        "기간청산수":     n_maxhold,
        "데이터종료수":   n_dataend,
        "총수익률":       equity.iloc[-1] - 1,
    }


def print_metrics(m: dict):
    print(f"\n  {'═'*60}")
    print(f"  숏스퀴즈 전략 성과")
    print(f"  {'─'*60}")
    print(f"  총 거래수     : {m['총거래수']:>6}건")
    print(f"  승률          : {m['승률']:>+8.1%}")
    print(f"  평균 수익     : {m['평균수익']:>+8.2%}   평균 손실: {m['평균손실']:>+8.2%}")
    print(f"  최대 단일 손실: {m['최대손실']:>+8.2%}")
    print(f"  손익비        : {m['손익비']:>8.2f}")
    print(f"  Sharpe Ratio  : {m['Sharpe']:>8.2f}")
    print(f"  CAGR          : {m['CAGR']:>+8.1%}")
    print(f"  MDD           : {m['MDD']:>+8.1%}")
    print(f"  평균 보유일   : {m['평균보유일']:>8.1f}일")
    print(f"  총수익률      : {m['총수익률']:>+8.1%}")
    print(f"  청산 사유     : 스톱 {m['스톱청산수']}건 / 기간초과 {m['기간청산수']}건 / 데이터종료 {m['데이터종료수']}건")
    print(f"  {'═'*60}")


# ══════════════════════════════════════════════════════════════
# 차트 저장
# ══════════════════════════════════════════════════════════════
def plot_results(equity: pd.Series, selected_trades: list[dict], spy_df: pd.DataFrame):
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle(
        f"숏스퀴즈 전략 백테스트  "
        f"(유니버스: 풀, 수수료 0.2%, {START}~{datetime.today():%Y-%m})",
        fontsize=13, fontweight="bold",
    )

    ax1 = axes[0, 0]
    ax1.plot(equity.index, equity.values, color="#2E75B6", lw=2.0, label="숏스퀴즈")

    if spy_df is not None and not spy_df.empty:
        spy_close = spy_df["Close"].squeeze()
        spy_close = spy_close[spy_close.index >= pd.Timestamp(START)]
        if len(spy_close) > 0:
            spy_norm = spy_close / spy_close.iloc[0]
            ax1.plot(spy_norm.index, spy_norm.values,
                     color="gray", lw=1.2, ls="--", alpha=0.7, label="SPY")

    ax1.set_title("누적 Equity 곡선")
    ax1.set_ylabel("자산 (배)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.2f}x"))
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.25)

    ax2 = axes[0, 1]
    returns = [t["net_return"] * 100 for t in selected_trades]
    ax2.hist(returns, bins=30, color="#2E75B6", alpha=0.7, edgecolor="white")
    ax2.axvline(0, color="red", lw=1.5, ls="--")
    ax2.axvline(np.mean(returns), color="orange", lw=1.5, ls="-.", label=f"평균 {np.mean(returns):.1f}%")
    ax2.set_title("거래 수익률 분포")
    ax2.set_xlabel("수익률 (%)")
    ax2.set_ylabel("거래 수")
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.25)

    ax3 = axes[1, 0]
    reasons = [t["exit_reason"] for t in selected_trades]
    reason_labels = {"stop_loss": "스톱로스", "max_hold": "기간초과", "data_end": "데이터종료"}
    counts = {}
    for r in reasons:
        counts[reason_labels.get(r, r)] = counts.get(reason_labels.get(r, r), 0) + 1
    ax3.pie(
        counts.values(), labels=counts.keys(),
        autopct="%1.1f%%", colors=["#FF4444", "#70AD47", "#AAAAAA"],
        startangle=90,
    )
    ax3.set_title("청산 사유 분포")

    ax4 = axes[1, 1]
    hold_days = [t["hold_days"] for t in selected_trades]
    ax4.hist(hold_days, bins=range(0, MAX_HOLD_DAYS + 3), color="#ED7D31", alpha=0.7, edgecolor="white")
    ax4.axvline(np.mean(hold_days), color="red", lw=1.5, ls="--",
                label=f"평균 {np.mean(hold_days):.1f}일")
    ax4.set_title("보유 기간 분포")
    ax4.set_xlabel("거래일")
    ax4.set_ylabel("거래 수")
    ax4.legend(fontsize=9)
    ax4.grid(alpha=0.25)

    plt.tight_layout()
    path = RESULTS_DIR / "short_squeeze_backtest.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"\n  차트 저장: {path}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    END = datetime.today().strftime("%Y-%m-%d")

    print("=" * 70)
    print("  숏스퀴즈(Short Squeeze) 백테스트")
    print(f"  기간    : {START} ~ {END}")
    print(f"  수수료  : 편도 {COMMISSION*100:.1f}% (왕복 {COMMISSION*2*100:.1f}%)")
    print(f"  유니버스: 풀 유니버스 (S&P500 + NASDAQ-100 + KOSPI200 + KOSDAQ150)")
    print(f"  파라미터: VOL_SPIKE×{VOL_SPIKE_MULT} | DECLINE{RECENT_DECLINE:.0%} | "
          f"REVERSAL+{REVERSAL_MIN:.1%} | ATR_SURGE×{ATR_SURGE_MULT} | MA_FILTER={USE_MA_FILTER}")
    print(f"  청산    : ATR×{ATR_STOP_MULT} 스톱로스 OR {MAX_HOLD_DAYS}일 보유기간")
    print(f"  포지션  : 최대 {MAX_POSITIONS}개 동시 (동일 비중)")
    print("=" * 70)
    print()

    print("[1] 데이터 로드 (캐시 또는 yfinance 다운로드)...")
    all_data_raw, spy_df, _etf_raw, _universe_map = load_full_universe(START)
    print(f"  → {len(all_data_raw)}개 종목 로드 완료")

    print(f"\n[2] 시그널 계산 ({len(all_data_raw)}종목)...")
    all_signals: dict[str, pd.DataFrame] = {}
    for ticker, df in all_data_raw.items():
        result = add_signals(df)
        if result is not None:
            all_signals[ticker] = result
    print(f"  → 시그널 계산 완료: {len(all_signals)}종목")

    total_signals = sum(df["signal"].sum() for df in all_signals.values())
    print(f"  → 전체 시그널 발생: {total_signals}건")

    print(f"\n[3] 거래 추출 중...")
    start_ts = pd.Timestamp(START)
    all_trades: list[dict] = []
    for ticker, df in all_signals.items():
        df_slice = df[df.index >= start_ts]
        if len(df_slice) < ATR_PERIOD + 5:
            continue
        trades = extract_trades(ticker, df_slice)
        all_trades.extend(trades)

    all_trades.sort(key=lambda t: t["entry_date"])
    print(f"  → 원시 거래 추출: {len(all_trades)}건")

    print(f"\n[4] 포지션 슬롯 제약 적용 (최대 {MAX_POSITIONS}개 동시)...")
    selected_trades = select_with_capacity(all_trades)
    print(f"  → 실제 체결 거래: {len(selected_trades)}건")

    if len(selected_trades) == 0:
        print("\n  ⚠ 체결 거래가 없습니다. 파라미터를 완화해보세요.")
        sys.exit(0)

    print(f"\n[5] Equity 곡선 생성...")
    equity_curve = build_equity_curve(selected_trades)

    print(f"\n[6] 성과 지표 계산...")
    metrics = calc_metrics(selected_trades, equity_curve)
    print_metrics(metrics)

    print(f"\n  [상위 10개 수익 거래]")
    print(f"  {'종목':<12} {'진입일':<12} {'청산일':<12} {'수익률':>8} {'보유일':>6} {'사유'}")
    print("  " + "─" * 62)
    top_wins = sorted(selected_trades, key=lambda t: t["net_return"], reverse=True)[:10]
    for t in top_wins:
        print(f"  {t['ticker']:<12} {str(t['entry_date'])[:10]:<12} "
              f"{str(t['exit_date'])[:10]:<12} {t['net_return']:>+8.2%} "
              f"{t['hold_days']:>6}일  {t['exit_reason']}")

    print(f"\n  [하위 10개 손실 거래]")
    print(f"  {'종목':<12} {'진입일':<12} {'청산일':<12} {'수익률':>8} {'보유일':>6} {'사유'}")
    print("  " + "─" * 62)
    top_losses = sorted(selected_trades, key=lambda t: t["net_return"])[:10]
    for t in top_losses:
        print(f"  {t['ticker']:<12} {str(t['entry_date'])[:10]:<12} "
              f"{str(t['exit_date'])[:10]:<12} {t['net_return']:>+8.2%} "
              f"{t['hold_days']:>6}일  {t['exit_reason']}")

    trades_df = pd.DataFrame(selected_trades)
    csv_path  = RESULTS_DIR / "short_squeeze_trades.csv"
    trades_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n  거래 CSV: {csv_path}")

    metrics_row = {k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in metrics.items()}
    metrics_df  = pd.DataFrame([metrics_row])
    metrics_csv = RESULTS_DIR / "short_squeeze_metrics.csv"
    metrics_df.to_csv(metrics_csv, index=False, encoding="utf-8-sig")
    print(f"  지표 CSV: {metrics_csv}")

    print(f"\n[9] 차트 저장...")
    plot_results(equity_curve, selected_trades, spy_df)

    print("\n" + "=" * 70)
    print("  백테스트 완료")
    print("=" * 70)
