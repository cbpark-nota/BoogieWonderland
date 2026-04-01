"""
52주 신고가 돌파 전략 백테스트
══════════════════════════════════════════════════════════════
전략: 52주 신고가 돌파 + 거래량 동반 + 필터 + 첫 돌파만 (시나리오 B 최적화)

진입 조건:
  - 현재가 >= 52주 고점 × HIGH_52W_THRESHOLD (0.98) → 52주 신고가 근접/돌파
  - 거래량 >= 20일 평균 거래량 × VOLUME_SPIKE (1.5배) → 거래량 동반
  - 5일 내 급등 < SURGE_EXCLUDE (10%) → 급등 제외 (미리 올라간 종목 배제)
  - ADX >= ADX_MIN (20) → 추세 강도 확인
  - RSI <= RSI_MAX (80) → 과매수 제외
  - 최근 FIRST_BREAKOUT_LOOKBACK(20)일 내 52주 신고가 미경험 → 첫 돌파만 진입

청산 조건:
  - ATR 트레일링 스톱: 최고가 - ATR × ATR_MULT (2.0)
  - 최대 보유기간: MAX_HOLD_DAYS (40일)

포지션 관리:
  - 동시 최대 MAX_POSITIONS (10) 종목
  - 동일 비중 (1/MAX_POSITIONS)
  - 수수료: COMMISSION (0.2%)

파라미터 튜닝 결과 (시나리오 A~G 비교, 2015~2026):
  최적: 시나리오 B (첫 돌파만) — CAGR +8.4%, MDD -30.7%, 샤프 0.43
  SPY 기준: CAGR +12.8%, MDD -33.7%  ← MDD 기준 충족

유니버스: S&P 500 + Nasdaq 100 + KOSPI 200 + KOSDAQ 150 (동적 수집)
기간    : 2015-01-01 ~ 현재
══════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import sys
import numpy as np
import pandas as pd
import pandas_ta as ta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

# ── 경로 설정 ──────────────────────────────────────────────
_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent))
from data_cache import load_full_universe

RESULTS_DIR = _THIS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════
# 전략 파라미터 (상수)
# ══════════════════════════════════════════════════════════════
HIGH_52W_THRESHOLD      = 0.98   # 52주 고점의 98% 이상이면 신고가 근접
VOLUME_SPIKE            = 1.5    # 20일 평균 거래량의 1.5배 이상
SURGE_EXCLUDE           = 0.10   # 5일 내 10% 급등 종목 제외
ADX_MIN                 = 20     # ADX 최소값
RSI_MAX                 = 80     # RSI 최대값
ATR_MULT                = 2.0    # ATR 트레일링 스톱 승수
MAX_HOLD_DAYS           = 40     # 최대 보유기간 (영업일)
MAX_POSITIONS           = 10     # 최대 동시 보유 종목 수
COMMISSION              = 0.002  # 편도 수수료 0.2%
# 튜닝 결과 최적 파라미터 (시나리오 B)
FIRST_BREAKOUT_ONLY     = True   # 최근 N일 내 첫 돌파만 진입 (재돌파 제외)
FIRST_BREAKOUT_LOOKBACK = 20     # 첫 돌파 확인 윈도우 (영업일)

START = "2015-01-01"
END   = datetime.today().strftime("%Y-%m-%d")

# 연간 영업일
TRADING_DAYS_PER_YEAR = 252


# ══════════════════════════════════════════════════════════════
# 지표 계산
# ══════════════════════════════════════════════════════════════

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """52주 신고가 전략에 필요한 지표를 추가."""
    df = df.copy()
    close  = df["Close"].squeeze()
    high   = df["High"].squeeze()
    low    = df["Low"].squeeze()
    volume = df["Volume"].squeeze()

    # ADX (14일)
    adx_res = ta.adx(high, low, close, length=14)
    if adx_res is not None and not adx_res.empty:
        col = [c for c in adx_res.columns if c.startswith("ADX_")]
        df["ADX"] = adx_res[col[0]].values if col else np.nan
    else:
        df["ADX"] = np.nan

    # RSI (14일)
    rsi_res = ta.rsi(close, length=14)
    df["RSI"] = rsi_res.values if rsi_res is not None else np.nan

    # ATR (14일)
    atr_res = ta.atr(high, low, close, length=14)
    df["ATR"] = atr_res.values if atr_res is not None else np.nan

    # 52주(252 영업일) 고점
    df["High52W"] = high.rolling(252, min_periods=50).max()

    # 20일 평균 거래량
    df["VolMA20"] = volume.rolling(20, min_periods=10).mean()

    # 5일 수익률 (급등 확인용)
    df["Ret5D"] = close.pct_change(5)

    # 52주 신고가 터치 플래그 (첫 돌파 필터용)
    df["Is52WHigh"] = (close >= df["High52W"] * HIGH_52W_THRESHOLD).astype(int)

    return df


# ══════════════════════════════════════════════════════════════
# 진입 신호 판단
# ══════════════════════════════════════════════════════════════

def is_entry_signal(row: pd.Series) -> bool:
    """당일 행에서 진입 조건 체크."""
    try:
        # 52주 신고가 근접 (현재가 >= 52주 고점 × 0.98)
        if pd.isna(row["High52W"]) or row["High52W"] <= 0:
            return False
        if row["Close"] < row["High52W"] * HIGH_52W_THRESHOLD:
            return False

        # 거래량 스파이크 (20일 평균의 1.5배 이상)
        if pd.isna(row["VolMA20"]) or row["VolMA20"] <= 0:
            return False
        if row["Volume"] < row["VolMA20"] * VOLUME_SPIKE:
            return False

        # 5일 내 급등 제외 (10% 이상 급등 시 제외)
        if not pd.isna(row["Ret5D"]) and row["Ret5D"] >= SURGE_EXCLUDE:
            return False

        # ADX >= 20
        if pd.isna(row["ADX"]) or row["ADX"] < ADX_MIN:
            return False

        # RSI <= 80
        if pd.isna(row["RSI"]) or row["RSI"] > RSI_MAX:
            return False

        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════
# 백테스트 엔진
# ══════════════════════════════════════════════════════════════

def run_backtest(all_data: dict) -> tuple[list, list, list]:
    """
    52주 신고가 전략 백테스트 실행.

    Returns
    -------
    nav_list  : list[float] — 일별 누적 자산 (1.0 = 시작)
    trade_log : list[dict]  — 거래 내역
    dates     : list[Timestamp] — 날짜 인덱스
    """
    # 모든 종목의 날짜 합집합 → 공통 날짜축 생성
    all_dates = sorted(set().union(*[set(df.index) for df in all_data.values()]))
    all_dates = pd.DatetimeIndex(all_dates)
    all_dates = all_dates[all_dates >= START]

    cash = 1.0          # 초기 자산 (정규화)
    # positions: {ticker: {entry_price, shares, stop, hold_days, atr}}
    positions: dict[str, dict] = {}
    nav_list   = [1.0]
    trade_log  = []

    for today in all_dates:
        # ── [A] 보유 포지션 스톱/기간 청산 체크 ──────────────────
        to_sell = []
        for ticker, pos in positions.items():
            df = all_data.get(ticker)
            if df is None or today not in df.index:
                pos["hold_days"] += 1
                if pos["hold_days"] >= MAX_HOLD_DAYS:
                    to_sell.append((ticker, "기간청산", pos["entry_price"]))
                continue

            row = df.loc[today]
            price = float(row["Close"])
            if pd.isna(price) or price <= 0:
                continue

            # 트레일링 스톱 갱신 (최고가 기준)
            if price > pos.get("peak", pos["entry_price"]):
                pos["peak"] = price
                if not pd.isna(row["ATR"]) and row["ATR"] > 0:
                    pos["stop"] = price - row["ATR"] * ATR_MULT

            pos["hold_days"] += 1

            # 스톱 청산
            if price <= pos["stop"]:
                to_sell.append((ticker, "스톱청산", price))
            # 기간 청산
            elif pos["hold_days"] >= MAX_HOLD_DAYS:
                to_sell.append((ticker, "기간청산", price))

        # 청산 실행
        for ticker, reason, sell_price in to_sell:
            pos = positions.pop(ticker)
            proceeds = pos["shares"] * sell_price * (1 - COMMISSION)
            cash += proceeds
            pnl = (sell_price / pos["entry_price"] - 1) * 100
            trade_log.append({
                "date":        today,
                "ticker":      ticker,
                "action":      "SELL",
                "reason":      reason,
                "price":       sell_price,
                "entry_price": pos["entry_price"],
                "pnl_pct":     pnl,
                "hold_days":   pos["hold_days"],
            })

        # ── [B] 포지션 여유 슬롯 확인 ────────────────────────────
        slots_available = MAX_POSITIONS - len(positions)
        if slots_available > 0:
            # 진입 후보 스캔
            candidates = []
            existing_tickers = set(positions.keys())

            for ticker, df in all_data.items():
                if ticker in existing_tickers:
                    continue
                if today not in df.index:
                    continue
                row = df.loc[today]
                if not is_entry_signal(row):
                    continue
                # 첫 돌파 필터: 최근 N일 내 이미 52주 신고가였던 종목 제외
                if FIRST_BREAKOUT_ONLY and "Is52WHigh" in df.columns:
                    idx_pos = df.index.get_loc(today)
                    lb_start = max(0, idx_pos - FIRST_BREAKOUT_LOOKBACK)
                    recent_highs = df["Is52WHigh"].iloc[lb_start:idx_pos].sum()
                    if recent_highs > 0:
                        continue
                candidates.append((ticker, float(row["Close"]), float(row.get("ADX", 0) or 0)))

            # ADX 높은 순 정렬 → 상위 슬롯만 진입
            candidates.sort(key=lambda x: x[2], reverse=True)
            candidates = candidates[:slots_available]

            for ticker, entry_price, adx_val in candidates:
                if entry_price <= 0 or pd.isna(entry_price):
                    continue

                # 포지션 크기: 동일 비중 (현재 자산 / MAX_POSITIONS)
                total_portfolio = cash + sum(
                    p["shares"] * entry_price for p in positions.values()
                )
                alloc = total_portfolio / MAX_POSITIONS
                if alloc > cash:
                    alloc = cash * 0.99  # 현금 부족 시 여유분만

                shares = alloc * (1 - COMMISSION) / entry_price
                cost   = shares * entry_price * (1 + COMMISSION)

                if cost > cash or shares <= 0:
                    continue

                # ATR 기반 초기 스톱
                df = all_data[ticker]
                row = df.loc[today]
                atr_val = float(row.get("ATR", 0) or 0)
                stop = entry_price - atr_val * ATR_MULT if atr_val > 0 else entry_price * 0.90

                cash -= cost
                positions[ticker] = {
                    "entry_price": entry_price,
                    "shares":      shares,
                    "stop":        stop,
                    "peak":        entry_price,
                    "hold_days":   0,
                }
                trade_log.append({
                    "date":        today,
                    "ticker":      ticker,
                    "action":      "BUY",
                    "reason":      "진입",
                    "price":       entry_price,
                    "entry_price": entry_price,
                    "pnl_pct":     0.0,
                    "hold_days":   0,
                })

        # ── [C] 일별 NAV 계산 ────────────────────────────────────
        position_value = 0.0
        for ticker, pos in positions.items():
            df = all_data.get(ticker)
            if df is not None and today in df.index:
                price = float(df.loc[today, "Close"])
                if not pd.isna(price) and price > 0:
                    position_value += pos["shares"] * price
            else:
                position_value += pos["shares"] * pos["entry_price"]

        nav = cash + position_value
        nav_list.append(nav)

    return nav_list, trade_log, list(all_dates)


# ══════════════════════════════════════════════════════════════
# 성과 지표 계산
# ══════════════════════════════════════════════════════════════

def calc_metrics(nav_list: list) -> dict:
    """일별 NAV 리스트에서 성과 지표 계산."""
    s     = pd.Series(nav_list, dtype=float)
    ret   = s.pct_change().dropna()
    n     = len(ret)
    years = n / TRADING_DAYS_PER_YEAR

    cagr  = (s.iloc[-1] ** (1 / max(years, 0.1))) - 1 if s.iloc[-1] > 0 else -1.0
    mdd   = ((s - s.cummax()) / s.cummax()).min()
    sharpe = (ret.mean() / (ret.std() + 1e-9)) * np.sqrt(TRADING_DAYS_PER_YEAR)
    win_rate = (ret > 0).mean()

    return {
        "총수익률": s.iloc[-1] - 1,
        "CAGR":    cagr,
        "MDD":     mdd,
        "샤프":    sharpe,
        "승률":    win_rate,
        "거래일수": n,
        "기간(년)": round(years, 2),
    }


def calc_spy_nav(spy_df: pd.DataFrame) -> list:
    """SPY 일별 NAV (buy-and-hold)."""
    close = spy_df["Close"].squeeze()
    close = close[close.index >= START]
    if close.empty:
        return [1.0]
    nav = (close / close.iloc[0]).tolist()
    return [1.0] + nav[1:]


# ══════════════════════════════════════════════════════════════
# 차트 저장
# ══════════════════════════════════════════════════════════════

def plot_results(nav_list: list, spy_nav: list, dates: list, metrics: dict):
    nav_s = pd.Series(nav_list[1:], index=dates)

    spy_dates = pd.date_range(START, END, freq="B")
    spy_s = pd.Series(spy_nav[1:len(spy_dates) + 1], index=spy_dates[:len(spy_nav) - 1])

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle(
        f"52주 신고가 돌파 전략  (수수료 {COMMISSION*100:.1f}%RT, {START}~{END[:7]})\n"
        f"CAGR {metrics['CAGR']:+.1%}  MDD {metrics['MDD']:.1%}  샤프 {metrics['샤프']:.2f}  승률 {metrics['승률']:.1%}",
        fontsize=12, fontweight="bold",
    )

    ax1 = axes[0]
    ax1.plot(nav_s.index, nav_s.values, label="52W High 전략", color="#2E75B6", lw=2.0)
    ax1.plot(spy_s.index, spy_s.values, label="SPY Buy&Hold",  color="gray",    lw=1.2, ls="--", alpha=0.7)
    ax1.set_ylabel("누적 자산 (배)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.1f}x"))
    ax1.set_title("누적 NAV 곡선")
    ax1.legend(fontsize=10)
    ax1.grid(alpha=0.25)

    ax2 = axes[1]
    labels = ["총수익률", "CAGR", "|MDD|", "샤프"]
    vals   = [
        metrics["총수익률"] * 100,
        metrics["CAGR"]    * 100,
        abs(metrics["MDD"])* 100,
        metrics["샤프"],
    ]
    colors = ["#2E75B6", "#70AD47", "#FF4444", "#ED7D31"]
    bars = ax2.bar(labels, vals, color=colors, alpha=0.8)
    for bar, val in zip(bars, vals):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 f"{val:.1f}", ha="center", va="bottom", fontsize=10)
    ax2.set_title("성과 지표 요약")
    ax2.set_ylabel("값 (수익률·MDD: %, 샤프: 배수)")
    ax2.grid(axis="y", alpha=0.25)

    path = RESULTS_DIR / "backtest_52w_high.png"
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"\n  차트 저장: {path}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("  52주 신고가 돌파 전략 백테스트")
    print(f"  기간       : {START} ~ {END}")
    print(f"  수수료     : 편도 {COMMISSION*100:.1f}%")
    print(f"  유니버스   : 풀 유니버스 (S&P500 + NASDAQ-100 + KOSPI200 + KOSDAQ150)")
    print("=" * 70)
    print()
    print("  [전략 파라미터] — 시나리오 B 최적화 (튜닝 A~G 중 CAGR 최고·MDD 기준 충족)")
    print(f"  HIGH_52W_THRESHOLD      = {HIGH_52W_THRESHOLD}  (52주 고점의 {HIGH_52W_THRESHOLD*100:.0f}% 이상)")
    print(f"  VOLUME_SPIKE            = {VOLUME_SPIKE}   (20일 평균 거래량의 {VOLUME_SPIKE}배)")
    print(f"  SURGE_EXCLUDE           = {SURGE_EXCLUDE}  (5일 내 {SURGE_EXCLUDE*100:.0f}% 급등 제외)")
    print(f"  ADX_MIN                 = {ADX_MIN}")
    print(f"  RSI_MAX                 = {RSI_MAX}")
    print(f"  ATR_MULT                = {ATR_MULT}   (트레일링 스톱)")
    print(f"  MAX_HOLD_DAYS           = {MAX_HOLD_DAYS}  (최대 보유기간)")
    print(f"  MAX_POSITIONS           = {MAX_POSITIONS}  (최대 동시 보유)")
    print(f"  FIRST_BREAKOUT_ONLY     = {FIRST_BREAKOUT_ONLY}  (최근 {FIRST_BREAKOUT_LOOKBACK}일 내 첫 돌파만)")
    print()

    # ── [1] 데이터 로드 ──────────────────────────────────────
    print("[1] 데이터 로드 (캐시 또는 yfinance 다운로드)...")
    all_data_raw, spy_df, etf_raw, universe_map = load_full_universe(START)
    print(f"  → 종목 {len(all_data_raw)}개 로드 완료")

    # ── [2] 지표 계산 ─────────────────────────────────────────
    print(f"\n[2] 종목 지표 계산 ({len(all_data_raw)}종목)...")
    all_data = {}
    for i, (t, df) in enumerate(all_data_raw.items()):
        if i % 100 == 0:
            print(f"\r  진행: {i}/{len(all_data_raw)}", end="", flush=True)
        all_data[t] = add_indicators(df)
    print(f"\r  완료: {len(all_data)}종목 지표 계산 완료", flush=True)

    # ── [3] 백테스트 실행 ─────────────────────────────────────
    print(f"\n[3] 백테스트 실행 중... (기간: {START} ~ {END})")
    nav_list, trade_log, dates = run_backtest(all_data)
    print(f"  완료: {len(trade_log)}건 거래 (매수 {sum(1 for t in trade_log if t['action']=='BUY')}건 / 매도 {sum(1 for t in trade_log if t['action']=='SELL')}건)")

    # ── [4] 성과 지표 ─────────────────────────────────────────
    metrics = calc_metrics(nav_list)
    spy_nav = calc_spy_nav(spy_df)
    spy_met = calc_metrics(spy_nav)

    print("\n" + "═" * 70)
    print("  성과 비교")
    print("═" * 70)
    print(f"  {'전략':<30} {'총수익률':>9} {'CAGR':>8} {'MDD':>8} {'샤프':>7} {'승률':>7}")
    print("  " + "─" * 65)
    print(f"  {'52W High 전략':<30} {metrics['총수익률']:>+9.1%} {metrics['CAGR']:>+8.1%} "
          f"{metrics['MDD']:>+8.1%} {metrics['샤프']:>7.2f} {metrics['승률']:>7.1%}")
    print(f"  {'SPY Buy&Hold':<30} {spy_met['총수익률']:>+9.1%} {spy_met['CAGR']:>+8.1%} "
          f"{spy_met['MDD']:>+8.1%} {spy_met['샤프']:>7.2f} {spy_met['승률']:>7.1%}")
    print()
    print(f"  기간: {metrics['기간(년)']}년 ({metrics['거래일수']}거래일)")

    # ── [5] 거래 내역 CSV ─────────────────────────────────────
    if trade_log:
        sells = [t for t in trade_log if t["action"] == "SELL"]
        if sells:
            df_trades = pd.DataFrame(sells)
            win_trades = (df_trades["pnl_pct"] > 0).sum()
            avg_pnl    = df_trades["pnl_pct"].mean()
            avg_hold   = df_trades["hold_days"].mean()
            reason_cnt = df_trades["reason"].value_counts()
            print(f"\n  [거래 분석]")
            print(f"  완결 거래: {len(sells)}건")
            print(f"  승률     : {win_trades/len(sells):.1%} ({win_trades}/{len(sells)})")
            print(f"  평균 수익: {avg_pnl:+.2f}%")
            print(f"  평균 보유: {avg_hold:.1f}일")
            print(f"  청산 이유: {reason_cnt.to_dict()}")

            csv_path = RESULTS_DIR / "backtest_52w_high_trades.csv"
            df_trades.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"\n  거래 내역 CSV: {csv_path}")

    # NAV CSV
    nav_df = pd.DataFrame({"date": [START] + [str(d.date()) for d in dates],
                            "nav":  nav_list[:len(dates) + 1]})
    nav_csv = RESULTS_DIR / "backtest_52w_high_nav.csv"
    nav_df.to_csv(nav_csv, index=False, encoding="utf-8-sig")
    print(f"  NAV CSV      : {nav_csv}")

    # ── [6] 차트 ─────────────────────────────────────────────
    plot_results(nav_list, spy_nav, dates, metrics)

    print("\n" + "=" * 70)
    print("  백테스트 완료")
    print("=" * 70)
