"""
숏스퀴즈 파라미터 튜닝 — 7개 시나리오 비교
══════════════════════════════════════════════════════════════
목표: 승률 최대화 (거래수 ≥20, 손익비 ≥1.0 조건 하에)

시나리오:
  A: 베이스라인 (VOL×2, DECLINE-5%, REVERSAL+1.5%, ATR×1.3, STOP×2.0, HOLD20)
  B: 엄격한 시그널 (VOL×3, DECLINE-10%, REVERSAL+2.0%, ATR×1.5)
  C: 타이트 스톱 + 짧은 보유 (STOP×1.5, HOLD10)
  D: MA 정배열 필터 (MA20 > MA50)
  E: 엄격 시그널 + 타이트 스톱 (B + C)
  F: 엄격 시그널 + MA 필터 (B + D)
  G: 전부 조합 (B + C + D)
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

START      = "2022-01-01"
COMMISSION = 0.002
MAX_POSITIONS = 5
MIN_PRICE  = 5.0
MIN_VOL_AVG = 100_000
ATR_PERIOD = 14
ATR_MA_PERIOD = 20
VOL_MA_PERIOD = 20

# ══════════════════════════════════════════════════════════════
# 7개 시나리오 정의
# ══════════════════════════════════════════════════════════════
SCENARIOS = {
    "A (베이스라인)": {
        "VOL_SPIKE_MULT": 2.0,
        "RECENT_DECLINE":  -0.05,
        "REVERSAL_MIN":    0.015,
        "ATR_SURGE_MULT":  1.3,
        "ATR_STOP_MULT":   2.0,
        "MAX_HOLD_DAYS":   20,
        "USE_MA_FILTER":   False,
    },
    "B (엄격 시그널)": {
        "VOL_SPIKE_MULT": 3.0,
        "RECENT_DECLINE":  -0.10,
        "REVERSAL_MIN":    0.020,
        "ATR_SURGE_MULT":  1.5,
        "ATR_STOP_MULT":   2.0,
        "MAX_HOLD_DAYS":   20,
        "USE_MA_FILTER":   False,
    },
    "C (타이트 스톱+단기)": {
        "VOL_SPIKE_MULT": 2.0,
        "RECENT_DECLINE":  -0.05,
        "REVERSAL_MIN":    0.015,
        "ATR_SURGE_MULT":  1.3,
        "ATR_STOP_MULT":   1.5,
        "MAX_HOLD_DAYS":   10,
        "USE_MA_FILTER":   False,
    },
    "D (MA 정배열)": {
        "VOL_SPIKE_MULT": 2.0,
        "RECENT_DECLINE":  -0.05,
        "REVERSAL_MIN":    0.015,
        "ATR_SURGE_MULT":  1.3,
        "ATR_STOP_MULT":   2.0,
        "MAX_HOLD_DAYS":   20,
        "USE_MA_FILTER":   True,
    },
    "E (엄격+타이트)": {
        "VOL_SPIKE_MULT": 3.0,
        "RECENT_DECLINE":  -0.10,
        "REVERSAL_MIN":    0.020,
        "ATR_SURGE_MULT":  1.5,
        "ATR_STOP_MULT":   1.5,
        "MAX_HOLD_DAYS":   10,
        "USE_MA_FILTER":   False,
    },
    "F (엄격+MA)": {
        "VOL_SPIKE_MULT": 3.0,
        "RECENT_DECLINE":  -0.10,
        "REVERSAL_MIN":    0.020,
        "ATR_SURGE_MULT":  1.5,
        "ATR_STOP_MULT":   2.0,
        "MAX_HOLD_DAYS":   20,
        "USE_MA_FILTER":   True,
    },
    "G (전부 조합)": {
        "VOL_SPIKE_MULT": 3.0,
        "RECENT_DECLINE":  -0.10,
        "REVERSAL_MIN":    0.020,
        "ATR_SURGE_MULT":  1.5,
        "ATR_STOP_MULT":   1.5,
        "MAX_HOLD_DAYS":   10,
        "USE_MA_FILTER":   True,
    },
}


# ══════════════════════════════════════════════════════════════
# 시그널 계산
# ══════════════════════════════════════════════════════════════
def add_signals(df: pd.DataFrame, p: dict) -> pd.DataFrame | None:
    min_rows = ATR_PERIOD + ATR_MA_PERIOD + 55
    if len(df) < min_rows:
        return None

    df = df.copy()
    df["atr"]    = ta.atr(df["High"], df["Low"], df["Close"], length=ATR_PERIOD)
    df["atr_ma"] = df["atr"].rolling(ATR_MA_PERIOD).mean()
    df["vol_ma"] = df["Volume"].rolling(VOL_MA_PERIOD).mean()

    c_vol_spike = df["Volume"]               > p["VOL_SPIKE_MULT"] * df["vol_ma"]
    c_decline   = df["Close"].pct_change(20) < p["RECENT_DECLINE"]
    c_reversal  = df["Close"].pct_change()   > p["REVERSAL_MIN"]
    c_atr_surge = df["atr"]                  > p["ATR_SURGE_MULT"] * df["atr_ma"]
    c_price_ok  = df["Close"]                > MIN_PRICE
    c_vol_ok    = df["vol_ma"]               > MIN_VOL_AVG

    if p["USE_MA_FILTER"]:
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
# 거래 추출
# ══════════════════════════════════════════════════════════════
def extract_trades(ticker: str, df: pd.DataFrame, p: dict) -> list[dict]:
    trades    = []
    n         = len(df)
    closes    = df["Close"].values
    opens     = df["Open"].values
    lows      = df["Low"].values
    atrs      = df["atr"].values
    dates     = df.index.to_list()
    sigs      = df["signal"].values
    max_hold  = p["MAX_HOLD_DAYS"]
    atr_stop  = p["ATR_STOP_MULT"]

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

        exit_price = exit_date = exit_reason = None
        hold_days  = 0

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

        if exit_price is None:
            continue

        eff_entry  = entry_price * (1 + COMMISSION)
        eff_exit   = exit_price  * (1 - COMMISSION)
        net_return = eff_exit / eff_entry - 1

        trades.append({
            "ticker":      ticker,
            "entry_date":  entry_date,
            "exit_date":   exit_date,
            "exit_reason": exit_reason,
            "net_return":  net_return,
            "hold_days":   hold_days,
        })

    return trades


def select_with_capacity(all_trades: list[dict]) -> list[dict]:
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


def calc_metrics(selected_trades: list[dict], equity: pd.Series) -> dict:
    if not selected_trades:
        return {k: None for k in ["총거래수","승률","평균수익","평균손실","손익비","Sharpe","CAGR","MDD","총수익률"]}

    returns   = np.array([t["net_return"] for t in selected_trades])
    hold_days = np.array([t["hold_days"]  for t in selected_trades])

    wins  = returns[returns >  0]
    loses = returns[returns <= 0]

    win_rate      = len(wins) / len(returns)
    avg_win       = wins.mean()  if len(wins)  > 0 else 0.0
    avg_loss      = loses.mean() if len(loses) > 0 else 0.0
    profit_factor = (wins.sum() / abs(loses.sum())) if len(loses) > 0 and loses.sum() != 0 else np.inf

    eq_vals = equity.values
    mdd     = ((eq_vals - np.maximum.accumulate(eq_vals)) / np.maximum.accumulate(eq_vals)).min()

    avg_hold = hold_days.mean()
    ret_std  = returns.std()
    sharpe   = (returns.mean() / (ret_std + 1e-9)) * np.sqrt(252 / max(avg_hold, 1)) if ret_std > 0 else 0.0

    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr  = equity.iloc[-1] ** (1 / years) - 1 if years > 0 and equity.iloc[-1] > 0 else 0.0

    return {
        "총거래수":   len(returns),
        "승률":       win_rate,
        "평균수익":   avg_win,
        "평균손실":   avg_loss,
        "손익비":     profit_factor,
        "Sharpe":     sharpe,
        "CAGR":       cagr,
        "MDD":        mdd,
        "총수익률":   equity.iloc[-1] - 1,
    }


# ══════════════════════════════════════════════════════════════
# 단일 시나리오 실행
# ══════════════════════════════════════════════════════════════
def run_scenario(name: str, p: dict, all_data_raw: dict) -> dict:
    start_ts = pd.Timestamp(START)
    all_trades: list[dict] = []

    for ticker, raw_df in all_data_raw.items():
        df = add_signals(raw_df, p)
        if df is None:
            continue
        df_slice = df[df.index >= start_ts]
        if len(df_slice) < ATR_PERIOD + 5:
            continue
        trades = extract_trades(ticker, df_slice, p)
        all_trades.extend(trades)

    selected = select_with_capacity(all_trades)
    equity   = build_equity_curve(selected)
    metrics  = calc_metrics(selected, equity)
    metrics["시나리오"] = name
    metrics["equity"]   = equity
    metrics["trades"]   = selected
    return metrics


# ══════════════════════════════════════════════════════════════
# 비교 테이블 출력
# ══════════════════════════════════════════════════════════════
def print_comparison(results: list[dict]):
    print("\n" + "═" * 100)
    print("  시나리오 비교 결과")
    print("═" * 100)
    header = f"  {'시나리오':<22} {'거래수':>6} {'승률':>8} {'평균수익':>9} {'평균손실':>9} {'손익비':>7} {'Sharpe':>7} {'CAGR':>8} {'MDD':>8} {'총수익':>8}"
    print(header)
    print("  " + "─" * 96)

    for r in results:
        n    = r.get("총거래수") or 0
        wr   = r.get("승률")     or 0
        aw   = r.get("평균수익") or 0
        al   = r.get("평균손실") or 0
        pf   = r.get("손익비")   or 0
        sh   = r.get("Sharpe")   or 0
        cagr = r.get("CAGR")     or 0
        mdd  = r.get("MDD")      or 0
        tot  = r.get("총수익률") or 0

        # 조건 충족 여부 마킹
        ok = "✓" if (n >= 20 and pf >= 1.0) else " "
        print(
            f"  {ok} {r['시나리오']:<20} {n:>6} {wr:>+8.1%} "
            f"{aw:>+9.2%} {al:>+9.2%} {pf:>7.2f} "
            f"{sh:>7.2f} {cagr:>+8.1%} {mdd:>+8.1%} {tot:>+8.1%}"
        )

    print("═" * 100)
    print("  ✓ = 거래수 ≥20 AND 손익비 ≥1.0 조건 충족")


# ══════════════════════════════════════════════════════════════
# 비교 차트
# ══════════════════════════════════════════════════════════════
def plot_comparison(results: list[dict], spy_df: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(18, 7))
    fig.suptitle(
        f"숏스퀴즈 파라미터 튜닝 — 7개 시나리오 비교  ({START}~{datetime.today():%Y-%m})",
        fontsize=13, fontweight="bold",
    )

    colors = ["#1F77B4","#FF7F0E","#2CA02C","#D62728","#9467BD","#8C564B","#E377C2"]

    # ─ Equity 곡선 ──────────────────────────────────────────
    ax1 = axes[0]
    if spy_df is not None and not spy_df.empty:
        spy_close = spy_df["Close"].squeeze()
        spy_close = spy_close[spy_close.index >= pd.Timestamp(START)]
        if len(spy_close) > 0:
            spy_norm = spy_close / spy_close.iloc[0]
            ax1.plot(spy_norm.index, spy_norm.values,
                     color="gray", lw=1.2, ls="--", alpha=0.6, label="SPY")

    for i, r in enumerate(results):
        eq = r.get("equity")
        if eq is None or len(eq) == 0:
            continue
        label = f"{r['시나리오']} (n={r.get('총거래수',0)}, wr={r.get('승률',0):.0%})"
        ax1.plot(eq.index, eq.values, lw=1.8, color=colors[i % len(colors)], label=label)

    ax1.set_title("누적 Equity 곡선")
    ax1.set_ylabel("자산 (배)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.2f}x"))
    ax1.legend(fontsize=8, loc="upper left")
    ax1.grid(alpha=0.25)

    # ─ 승률 vs 손익비 산점도 ─────────────────────────────
    ax2 = axes[1]
    for i, r in enumerate(results):
        wr = r.get("승률") or 0
        pf = r.get("손익비") or 0
        n  = r.get("총거래수") or 0
        name = r["시나리오"]
        marker = "★" if (n >= 20 and pf >= 1.0) else "○"
        ax2.scatter(wr, pf, s=120, color=colors[i % len(colors)], zorder=5)
        ax2.annotate(
            f"{name}\n(n={n})",
            xy=(wr, pf), xytext=(5, 5), textcoords="offset points",
            fontsize=8, color=colors[i % len(colors)],
        )

    ax2.axhline(1.0, color="red", lw=1.2, ls="--", alpha=0.6, label="손익비=1.0 기준선")
    ax2.axvline(0.5, color="blue", lw=1.2, ls="--", alpha=0.6, label="승률=50% 기준선")
    ax2.set_title("승률 vs 손익비 (버블=거래수)")
    ax2.set_xlabel("승률")
    ax2.set_ylabel("손익비 (Profit Factor)")
    ax2.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.25)

    plt.tight_layout()
    path = RESULTS_DIR / "short_squeeze_tuning.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"\n  비교 차트 저장: {path}")


# ══════════════════════════════════════════════════════════════
# 최적 시나리오 선택
# ══════════════════════════════════════════════════════════════
def find_best(results: list[dict]) -> dict | None:
    """
    거래수 ≥20, 손익비 ≥1.0 조건 충족 중 승률 최대 시나리오 반환.
    """
    candidates = [
        r for r in results
        if (r.get("총거래수") or 0) >= 20
        and (r.get("손익비") or 0) >= 1.0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r.get("승률") or 0)


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 70)
    print("  숏스퀴즈 파라미터 튜닝 — 7개 시나리오 비교")
    print(f"  기간: {START} ~ {datetime.today():%Y-%m-%d}")
    print(f"  수수료: 편도 {COMMISSION*100:.1f}%")
    print("=" * 70)

    # ─ 데이터 1회 로드 ──────────────────────────────────
    print("\n[0] 데이터 로드...")
    all_data_raw, spy_df, _etf, _umap = load_full_universe(START)
    print(f"  → {len(all_data_raw)}개 종목 로드 완료\n")

    # ─ 7개 시나리오 순차 실행 ────────────────────────────
    all_results = []
    for sc_name, sc_params in SCENARIOS.items():
        print(f"[시나리오 {sc_name}] 실행 중...", end=" ", flush=True)
        r = run_scenario(sc_name, sc_params, all_data_raw)
        all_results.append(r)
        n  = r.get("총거래수") or 0
        wr = r.get("승률") or 0
        pf = r.get("손익비") or 0
        print(f"완료 → 거래수:{n}  승률:{wr:.1%}  손익비:{pf:.2f}")

    # ─ 비교 테이블 출력 ──────────────────────────────────
    print_comparison(all_results)

    # ─ 최적 시나리오 ─────────────────────────────────────
    best = find_best(all_results)
    print("\n" + "─" * 70)
    if best:
        print(f"  ★ 최적 시나리오: {best['시나리오']}")
        print(f"    거래수: {best['총거래수']}건  승률: {best['승률']:.1%}  "
              f"손익비: {best['손익비']:.2f}  MDD: {best['MDD']:.1%}  CAGR: {best['CAGR']:.1%}")

        # 최적 파라미터 상세 출력
        sc_key = best["시나리오"]
        bp = SCENARIOS[sc_key]
        print(f"\n  [최적 파라미터]")
        print(f"    VOL_SPIKE_MULT : {bp['VOL_SPIKE_MULT']}")
        print(f"    RECENT_DECLINE : {bp['RECENT_DECLINE']:.0%}")
        print(f"    REVERSAL_MIN   : {bp['REVERSAL_MIN']:.1%}")
        print(f"    ATR_SURGE_MULT : {bp['ATR_SURGE_MULT']}")
        print(f"    ATR_STOP_MULT  : {bp['ATR_STOP_MULT']}")
        print(f"    MAX_HOLD_DAYS  : {bp['MAX_HOLD_DAYS']}")
        print(f"    USE_MA_FILTER  : {bp['USE_MA_FILTER']}")
    else:
        print("  ⚠ 조건(거래수≥20, 손익비≥1.0)을 충족하는 시나리오가 없습니다.")
    print("─" * 70)

    # ─ 비교 차트 저장 ─────────────────────────────────────
    plot_comparison(all_results, spy_df)

    # ─ 결과 CSV 저장 ─────────────────────────────────────
    rows = []
    for r in all_results:
        sc_key = r["시나리오"]
        p  = SCENARIOS[sc_key]
        rows.append({
            "시나리오":       r["시나리오"],
            "VOL_SPIKE_MULT": p["VOL_SPIKE_MULT"],
            "RECENT_DECLINE": p["RECENT_DECLINE"],
            "REVERSAL_MIN":   p["REVERSAL_MIN"],
            "ATR_SURGE_MULT": p["ATR_SURGE_MULT"],
            "ATR_STOP_MULT":  p["ATR_STOP_MULT"],
            "MAX_HOLD_DAYS":  p["MAX_HOLD_DAYS"],
            "USE_MA_FILTER":  p["USE_MA_FILTER"],
            "총거래수":       r.get("총거래수"),
            "승률":           f"{r.get('승률',0):.4f}",
            "평균수익":       f"{r.get('평균수익',0):.4f}",
            "평균손실":       f"{r.get('평균손실',0):.4f}",
            "손익비":         f"{r.get('손익비',0):.4f}",
            "Sharpe":         f"{r.get('Sharpe',0):.4f}",
            "CAGR":           f"{r.get('CAGR',0):.4f}",
            "MDD":            f"{r.get('MDD',0):.4f}",
            "총수익률":       f"{r.get('총수익률',0):.4f}",
        })

    df_results = pd.DataFrame(rows)
    csv_path   = RESULTS_DIR / "short_squeeze_tuning.csv"
    df_results.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n  결과 CSV: {csv_path}")

    print("\n" + "=" * 70)
    print("  튜닝 백테스트 완료")
    print("=" * 70)
