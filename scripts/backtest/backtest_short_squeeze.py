"""
숏스퀴즈 스크리너 백테스트 — 대형주 vs 소형주 vs 전체 유니버스 비교
══════════════════════════════════════════════════════════════
숏스퀴즈 시그널 조건:
  1. 거래량 스파이크: 당일 거래량 ≥ 20일 평균 × 2.0
  2. 직전 하락: 최근 5일 수익률 ≤ -5%
  3. 당일 반등: 당일 수익률 ≥ +1.5%
  4. 변동성 확인: 직전 하락폭 ≥ ATR × 1.3

포지션 관리:
  - 스톱로스: ATR × 2.0 이하 하락 시 청산
  - 보유기간: 최대 20일 후 청산
  - 동시 최대 포지션: 10개 (진입 순서 기준)
  - 수수료: 편도 0.2% (왕복 0.4%)

유니버스 비교:
  A) 대형주: S&P500 + NASDAQ-100
  B) 소형주: S&P SmallCap 600
  C) 전체  : A + B

성과 지표: 승률, CAGR, MDD, Sharpe, 손익비, 거래 횟수
기간: 2015-01-01 ~ 현재
══════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

# ── 경로 설정 ──────────────────────────────────────────────
_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent))

from data_cache import (
    fetch_sp500_tickers,
    fetch_nasdaq100_tickers,
    fetch_sp600_tickers,
    _download_batch,
    _clean_ohlcv,
    CACHE_DIR,
)

RESULTS_DIR = _THIS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

START      = "2015-01-01"
END        = datetime.today().strftime("%Y-%m-%d")
COMMISSION = 0.002    # 편도 0.2%

# ── 숏스퀴즈 파라미터 ────────────────────────────────────────
VOL_MULT      = 2.0   # 거래량 스파이크: 20일 평균 대비
DROP_THRESH   = -0.05 # 직전 하락 임계값 (5일 누적 수익률)
BOUNCE_THRESH = 0.015 # 반등 임계값 (당일 수익률)
ATR_ENTRY_MULT = 1.3  # 진입 ATR 배수 (직전 하락폭 필터)
ATR_STOP_MULT  = 2.0  # 스톱로스 ATR 배수
ATR_PERIOD     = 14   # ATR 계산 기간
HOLD_DAYS      = 20   # 최대 보유일
MAX_POSITIONS  = 10   # 동시 최대 포지션 수


# ══════════════════════════════════════════════════════════════
# 지표 계산
# ══════════════════════════════════════════════════════════════
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """ATR, 거래량 이동평균, 이전 수익률 계산."""
    df = df.copy()
    high = df["High"]
    low  = df["Low"]
    close = df["Close"]

    # ATR (True Range의 EMA)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(span=ATR_PERIOD, adjust=False).mean()

    # 거래량 20일 이동평균
    df["VolMA20"] = df["Volume"].rolling(20).mean()

    # 수익률
    df["Ret1"]  = close.pct_change(1)   # 당일 수익률
    df["Ret5"]  = close.pct_change(5)   # 5일 수익률 (직전 하락 확인용)

    return df


def detect_signals(df: pd.DataFrame) -> pd.Series:
    """숏스퀴즈 진입 시그널 감지. True인 날이 진입일."""
    vol_spike  = df["Volume"] >= df["VolMA20"] * VOL_MULT
    prev_drop  = df["Ret5"].shift(1) <= DROP_THRESH       # 전날 기준 5일 하락
    bounce     = df["Ret1"] >= BOUNCE_THRESH               # 당일 반등
    atr_filter = df["Ret5"].shift(1).abs() * df["Close"].shift(1) >= df["ATR"].shift(1) * ATR_ENTRY_MULT

    signal = vol_spike & prev_drop & bounce & atr_filter
    return signal.fillna(False)


# ══════════════════════════════════════════════════════════════
# 종목별 트레이드 생성
# ══════════════════════════════════════════════════════════════
def extract_trades(ticker: str, df: pd.DataFrame) -> list[dict]:
    """종목의 숏스퀴즈 시그널로부터 개별 트레이드 리스트 생성."""
    df = compute_indicators(df)
    signals = detect_signals(df)
    signal_dates = df.index[signals]

    trades = []
    for entry_date in signal_dates:
        entry_idx = df.index.get_loc(entry_date)
        entry_price = df["Close"].iloc[entry_idx]
        atr = df["ATR"].iloc[entry_idx]
        stop_price = entry_price - atr * ATR_STOP_MULT

        # 보유기간 동안 청산 조건 체크
        exit_price = None
        exit_date  = None
        hit_stop   = False

        for j in range(1, HOLD_DAYS + 1):
            if entry_idx + j >= len(df):
                break
            row = df.iloc[entry_idx + j]
            # 스톱로스 (저가 기준)
            if row["Low"] <= stop_price:
                exit_price = stop_price
                exit_date  = df.index[entry_idx + j]
                hit_stop   = True
                break
            # 마지막 보유일: 종가 청산
            if j == HOLD_DAYS:
                exit_price = row["Close"]
                exit_date  = df.index[entry_idx + j]

        if exit_price is None or exit_date is None:
            continue

        ret = (exit_price / entry_price - 1) * (1 - COMMISSION) ** 2 - 1
        trades.append({
            "ticker":      ticker,
            "entry_date":  entry_date,
            "exit_date":   exit_date,
            "entry_price": entry_price,
            "exit_price":  exit_price,
            "ret":         ret,
            "hit_stop":    hit_stop,
        })

    return trades


# ══════════════════════════════════════════════════════════════
# NAV 시뮬레이션 (포지션 상한 적용)
# ══════════════════════════════════════════════════════════════
def simulate_nav(trades: list[dict]) -> tuple[list[float], pd.DatetimeIndex]:
    """
    트레이드 목록으로 NAV 시뮬레이션.
    동시 최대 MAX_POSITIONS 포지션 유지. 균등 배분.
    반환: (daily_nav, date_index)
    """
    if not trades:
        return [1.0], pd.DatetimeIndex([pd.Timestamp(START)])

    df_trades = pd.DataFrame(trades).sort_values("entry_date").reset_index(drop=True)

    date_range = pd.date_range(START, END, freq="B")
    nav_series = pd.Series(1.0, index=date_range, dtype=float)

    # 간략한 이벤트 기반 NAV 계산
    # 각 날짜에 활성 포지션 집합을 유지하고 일별 P&L 합산
    active: list[dict] = []  # 현재 열린 포지션
    cash   = 1.0
    equity = 0.0  # 포지션에 투자된 금액의 현재 가치 합

    # trades를 날짜별로 정렬하여 이벤트 처리
    entry_by_date: dict = {}
    exit_by_date:  dict = {}
    for t in trades:
        entry_by_date.setdefault(t["entry_date"], []).append(t)
        exit_by_date.setdefault(t["exit_date"], []).append(t)

    all_dates = sorted(set(list(entry_by_date.keys()) + list(exit_by_date.keys())))

    portfolio_value = 1.0
    open_trades: list[dict] = []  # 현재 열린 트레이드

    nav_by_date = {}
    prev_date   = None

    for d in all_dates:
        # 청산 처리
        for t in exit_by_date.get(d, []):
            if t in open_trades:
                open_trades.remove(t)

        # 진입 처리 (슬롯 여유 있을 때만)
        for t in entry_by_date.get(d, []):
            if len(open_trades) < MAX_POSITIONS:
                open_trades.append(t)

        nav_by_date[d] = portfolio_value

    # 실제 NAV 계산: 각 트레이드의 ret을 균등 비중으로 반영
    # 날짜별로 당일 청산 트레이드의 수익을 NAV에 가산
    nav_val = 1.0
    nav_records = []

    # 트레이드를 청산일 기준으로 그룹화
    exit_groups: dict = {}
    active_set: set = set()

    for t in df_trades.itertuples():
        exit_groups.setdefault(t.exit_date, []).append(t)

    for t in df_trades.itertuples():
        pass

    # 단순화된 NAV: 각 트레이드를 독립적으로 (1/MAX_POSITIONS) 비중으로 반영
    nav_val = 1.0
    date_nav_map = {pd.Timestamp(START): 1.0}
    open_pos: list = []

    all_event_dates = sorted(set(
        [t["entry_date"] for t in trades] + [t["exit_date"] for t in trades]
    ))

    for d in all_event_dates:
        # 당일 청산
        closed = [p for p in open_pos if p["exit_date"] == d]
        for p in closed:
            weight = 1.0 / MAX_POSITIONS
            nav_val *= (1 + p["ret"] * weight)
            open_pos.remove(p)

        # 당일 진입
        new_entries = [t for t in trades if t["entry_date"] == d]
        for t in new_entries:
            if len(open_pos) < MAX_POSITIONS:
                open_pos.append(t)

        date_nav_map[d] = nav_val

    # 일별 NAV 보간
    nav_index = pd.date_range(START, END, freq="B")
    nav_s = pd.Series(date_nav_map).reindex(nav_index).ffill().bfill()
    nav_s = nav_s.fillna(1.0)

    return nav_s.tolist(), nav_index


# ══════════════════════════════════════════════════════════════
# 성과 지표 계산
# ══════════════════════════════════════════════════════════════
def calc_metrics(trades: list[dict], label: str) -> dict:
    """트레이드 목록으로 성과 지표 계산."""
    if not trades:
        return {
            "label": label, "trade_cnt": 0, "win_rate": 0,
            "CAGR": 0, "MDD": 0, "Sharpe": 0, "pnl_ratio": 0,
            "nav": [1.0],
        }

    df = pd.DataFrame(trades)
    win_rate  = (df["ret"] > 0).mean()
    avg_win   = df.loc[df["ret"] > 0, "ret"].mean() if (df["ret"] > 0).any() else 0
    avg_loss  = df.loc[df["ret"] < 0, "ret"].mean() if (df["ret"] < 0).any() else 0
    pnl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    nav_list, nav_idx = simulate_nav(trades)
    nav_s   = pd.Series(nav_list, index=nav_idx[:len(nav_list)])
    ret_s   = nav_s.pct_change().dropna()
    n_years = len(ret_s) / 252
    cagr    = (nav_s.iloc[-1] ** (1 / max(n_years, 0.1))) - 1 if nav_s.iloc[-1] > 0 else -1.0
    mdd     = ((nav_s - nav_s.cummax()) / nav_s.cummax()).min()
    sharpe  = (ret_s.mean() / (ret_s.std() + 1e-9)) * np.sqrt(252)

    return {
        "label":     label,
        "trade_cnt": len(df),
        "win_rate":  win_rate,
        "CAGR":      cagr,
        "MDD":       mdd,
        "Sharpe":    sharpe,
        "pnl_ratio": pnl_ratio,
        "nav":       nav_list,
    }


def print_metrics(m: dict):
    print(f"  {'─'*65}")
    print(f"  {m['label']}")
    print(f"  거래횟수 {m['trade_cnt']:>6}   승률     {m['win_rate']:>7.1%}")
    print(f"  CAGR     {m['CAGR']:>+7.1%}   MDD      {m['MDD']:>+7.1%}")
    print(f"  Sharpe   {m['Sharpe']:>7.2f}   손익비   {m['pnl_ratio']:>7.2f}")


# ══════════════════════════════════════════════════════════════
# 차트 저장
# ══════════════════════════════════════════════════════════════
def plot_results(metrics_list: list[dict]):
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    colors = ["#2E75B6", "#ED7D31", "#70AD47"]
    fig.suptitle(
        f"숏스퀴즈 스크리너 백테스트: 대형주 vs 소형주 vs 전체  "
        f"({START}~{END[:7]})",
        fontsize=13, fontweight="bold",
    )

    # NAV 곡선
    ax1 = axes[0]
    for i, m in enumerate(metrics_list):
        nav = m["nav"]
        idx = pd.date_range(START, periods=len(nav), freq="B")
        ax1.plot(idx[:len(nav)], nav, label=m["label"], color=colors[i], lw=2.0)
    ax1.set_ylabel("누적 자산 (배)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.1f}x"))
    ax1.set_title("NAV 곡선")
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.25)

    # 지표 비교 막대
    ax2 = axes[1]
    labels  = [m["label"] for m in metrics_list]
    cagrs   = [m["CAGR"] * 100 for m in metrics_list]
    mdds    = [abs(m["MDD"]) * 100 for m in metrics_list]
    sharpes = [m["Sharpe"] for m in metrics_list]

    x = np.arange(len(labels))
    w = 0.25
    ax2.bar(x - w, cagrs,   width=w, label="CAGR(%)",  color="#2E75B6", alpha=0.8)
    ax2.bar(x,     mdds,    width=w, label="|MDD|(%)", color="#FF4444", alpha=0.8)
    ax2.bar(x + w, sharpes, width=w, label="Sharpe",   color="#70AD47", alpha=0.8)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=10, fontsize=9)
    ax2.set_title("CAGR / MDD / Sharpe 비교")
    ax2.legend(fontsize=9)
    ax2.grid(axis="y", alpha=0.25)

    path = RESULTS_DIR / "short_squeeze_universe_comparison.png"
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"\n  차트 저장: {path}")


# ══════════════════════════════════════════════════════════════
# 유니버스 데이터 로드 (캐시 활용)
# ══════════════════════════════════════════════════════════════
def load_tickers_data(tickers: list[str], label: str) -> dict:
    """티커 목록의 OHLCV 데이터를 다운로드 또는 캐시에서 로드."""
    import json
    from data_cache import _safe_fname
    import yfinance as yf

    # 캐시에서 로드 시도
    manifest_path = CACHE_DIR / "manifest.json"
    cached_data = {}
    if manifest_path.exists():
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
            stocks = manifest.get("stocks", {})
            for t in tickers:
                fname = stocks.get(t)
                if fname:
                    path = CACHE_DIR / fname
                    if path.exists():
                        cached_data[t] = pd.read_parquet(path)
        except Exception:
            pass

    missing = [t for t in tickers if t not in cached_data]
    if missing:
        print(f"  {label}: 캐시 미스 {len(missing)}개 → 다운로드 중...")
        new_data = _download_batch(missing, START, END, batch_size=50, label=label)
        cached_data.update(new_data)
    else:
        print(f"  {label}: {len(cached_data)}개 캐시에서 로드 완료")

    return {t: v for t, v in cached_data.items() if t in tickers}


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 70)
    print("  숏스퀴즈 스크리너 백테스트 — 대형주 vs 소형주 vs 전체")
    print(f"  기간     : {START} ~ {END}")
    print(f"  수수료   : 편도 {COMMISSION*100:.1f}% (왕복 {COMMISSION*2*100:.1f}%)")
    print(f"  파라미터 : 거래량 {VOL_MULT:.0f}x, 하락 {DROP_THRESH*100:.0f}%, "
          f"반등 {BOUNCE_THRESH*100:.1f}%, ATR진입 {ATR_ENTRY_MULT:.1f}x, "
          f"스톱 ATR×{ATR_STOP_MULT:.1f}, 보유 {HOLD_DAYS}일")
    print("=" * 70)

    # ── [1] 유니버스 수집 ─────────────────────────────────────
    print("\n[1] 유니버스 티커 수집...")
    large_tickers_sp500, sp500_sec = fetch_sp500_tickers()
    large_tickers_ndx, ndx_sec     = fetch_nasdaq100_tickers()

    sp500_set = set(large_tickers_sp500)
    ndx_new   = [t for t in large_tickers_ndx if t not in sp500_set]
    large_tickers = large_tickers_sp500 + ndx_new
    print(f"  대형주 유니버스: S&P500 {len(large_tickers_sp500)}개 + NASDAQ-100 신규 {len(ndx_new)}개 = {len(large_tickers)}개")

    small_tickers, sp600_sec = fetch_sp600_tickers()
    # 대형주와 중복 제거
    large_set     = set(large_tickers)
    small_unique  = [t for t in small_tickers if t not in large_set]
    print(f"  소형주 유니버스: S&P600 {len(small_unique)}개 (대형주 중복 제거 후)")

    all_tickers = large_tickers + small_unique
    print(f"  전체 유니버스: {len(all_tickers)}개")

    # ── [2] 데이터 다운로드 ───────────────────────────────────
    print("\n[2] OHLCV 데이터 로드...")
    large_data = load_tickers_data(large_tickers, "대형주")
    small_data = load_tickers_data(small_unique,  "소형주")
    all_data   = {**large_data, **small_data}
    print(f"  대형주 {len(large_data)}개, 소형주 {len(small_data)}개, 전체 {len(all_data)}개 로드 완료")

    # ── [3] 트레이드 추출 ─────────────────────────────────────
    print("\n[3] 숏스퀴즈 시그널 탐지 및 트레이드 추출...")

    def run_universe(data: dict, label: str) -> list[dict]:
        trades = []
        for i, (ticker, df) in enumerate(data.items()):
            if (i + 1) % 100 == 0:
                print(f"\r  {label}: {i+1}/{len(data)} 처리 중...", end="", flush=True)
            try:
                t = extract_trades(ticker, df)
                trades.extend(t)
            except Exception:
                pass
        print(f"\r  {label}: {len(data)}개 처리 완료, 트레이드 {len(trades)}건    ")
        return trades

    large_trades = run_universe(large_data, "대형주")
    small_trades = run_universe(small_data, "소형주")
    all_trades   = large_trades + small_trades

    # ── [4] 성과 계산 ─────────────────────────────────────────
    print("\n[4] 성과 지표 계산...")
    m_large = calc_metrics(large_trades, f"대형주 (S&P500+NDX100, {len(large_data)}종목)")
    m_small = calc_metrics(small_trades, f"소형주 (S&P600, {len(small_data)}종목)")
    m_all   = calc_metrics(all_trades,   f"전체 ({len(all_data)}종목)")

    for m in [m_large, m_small, m_all]:
        print_metrics(m)

    # ── [5] 종합 비교 표 ──────────────────────────────────────
    print("\n" + "═" * 70)
    print("  종합 성과 비교")
    print("═" * 70)
    header = f"  {'유니버스':<36} {'거래수':>6} {'승률':>7} {'CAGR':>8} {'MDD':>8} {'Sharpe':>7} {'손익비':>7}"
    print(header)
    print("  " + "─" * 67)
    for m in [m_large, m_small, m_all]:
        print(
            f"  {m['label']:<36} {m['trade_cnt']:>6} "
            f"{m['win_rate']:>7.1%} {m['CAGR']:>+8.1%} "
            f"{m['MDD']:>+8.1%} {m['Sharpe']:>7.2f} {m['pnl_ratio']:>7.2f}"
        )

    # ── [6] CSV 저장 ──────────────────────────────────────────
    rows = [{
        "유니버스":  m["label"],
        "거래횟수":  m["trade_cnt"],
        "승률":      f"{m['win_rate']:.1%}",
        "CAGR":      f"{m['CAGR']:+.1%}",
        "MDD":       f"{m['MDD']:+.1%}",
        "Sharpe":    f"{m['Sharpe']:.2f}",
        "손익비":    f"{m['pnl_ratio']:.2f}",
    } for m in [m_large, m_small, m_all]]
    csv_path = RESULTS_DIR / "short_squeeze_universe_comparison.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n  결과 CSV: {csv_path}")

    # ── [7] 차트 ─────────────────────────────────────────────
    plot_results([m_large, m_small, m_all])

    print("\n" + "=" * 70)
    print("  백테스트 완료")
    print("=" * 70)
