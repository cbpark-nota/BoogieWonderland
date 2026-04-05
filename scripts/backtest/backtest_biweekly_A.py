"""
격주(2W) 리밸런싱 × 4전략 × A진입방식(MA정배열) 백테스트
══════════════════════════════════════════════════════════════
파라미터:
  공격적: ATR 1.5, TOP 15, 격주(2W-FRI)
  균형형: ATR 2.0, TOP 10, 격주(2W-FRI)
  보수적: ATR 2.5, TOP  7, 격주(2W-FRI)
  적응형: ATR 2.0, TOP 10, 격주(2W-FRI) + 국면별 동적 파라미터

진입방식: A — MA20>MA50>MA200 정배열, 시장 상태 무관하게 항상 스크리닝
유니버스: S&P500 + NASDAQ-100 + KOSPI200 + KOSDAQ150 (동적 수집)
수수료  : 편도 0.2% (왕복 0.4%)
기간    : 2015-01-01 ~ 현재
══════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import logging
import sys
import importlib.util
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

# ── 경로 설정 ──────────────────────────────────────────────
_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent))

# 공용 캐시 모듈
from data_cache import load_full_universe, SECTOR_ETF as CACHE_SECTOR_ETF

# backtest_hybrid_entry 모듈 동적 로드 (함수 재사용)
_spec = importlib.util.spec_from_file_location(
    "backtest_hybrid_entry", _THIS_DIR / "backtest_hybrid_entry.py"
)
bhe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bhe)

RESULTS_DIR = _THIS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

START      = "2015-01-01"
END        = datetime.today().strftime("%Y-%m-%d")
REBAL_FREQ = "2W-FRI"        # 격주 금요일 리밸런싱
PERIODS_PY = 26              # 연간 기간 수 (격주: 52/2=26)

# (전략명, ATR 승수, TOP_N, adaptive)
STRATEGY_CONFIGS = [
    ("공격적", 1.5, 15, False),
    ("균형형", 2.0, 10, False),
    ("보수적", 2.5,  7, False),
    ("적응형", 2.0, 10, True),   # adaptive=True → 국면별 ATR/TOP_N 동적 전환
]


# ══════════════════════════════════════════════════════════════
# 격주 기준 성과 지표 계산
# ══════════════════════════════════════════════════════════════
def calc_metrics_biweekly(nav_list: list, label: str) -> dict:
    """
    격주(2W) 리밸런싱 기준 성과 지표.
    periods_per_year=26 으로 CAGR·샤프를 올바르게 계산.
    """
    s    = pd.Series(nav_list, dtype=float)
    ret  = s.pct_change().dropna()
    n    = len(ret)
    years = n / PERIODS_PY
    cagr  = (s.iloc[-1] ** (1 / max(years, 0.1))) - 1 if s.iloc[-1] > 0 else -1.0
    mdd   = ((s - s.cummax()) / s.cummax()).min()
    sharp = (ret.mean() / (ret.std() + 1e-9)) * np.sqrt(PERIODS_PY)
    return {
        "label":   label,
        "총수익률": s.iloc[-1] - 1,
        "CAGR":    cagr,
        "MDD":     mdd,
        "샤프":    sharp,
        "기간승률": (ret > 0).mean(),   # 격주 기간 기준 승률
        "nav":     nav_list,
    }


def print_metrics(m: dict):
    logger.info(f"  {'─'*60}")
    logger.info(f"  {m['label']}")
    logger.info(f"  총수익률 {m['총수익률']:>+8.1%}   CAGR {m['CAGR']:>+8.1%}")
    logger.info(f"  MDD      {m['MDD']:>+8.1%}   샤프 {m['샤프']:>8.2f}   기간승률 {m['기간승률']:.1%}")


# ══════════════════════════════════════════════════════════════
# 차트 저장
# ══════════════════════════════════════════════════════════════
def plot_results(results: list, spy_nav: list):
    colors = ["#2E75B6", "#ED7D31", "#70AD47", "#A020F0"]
    dates  = [pd.Timestamp(START)] + list(pd.date_range(START, END, freq=REBAL_FREQ))

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle(
        f"격주(2W) 리밸런싱 × 4전략 × A진입방식  "
        f"(수수료 0.2%RT, {START}~{END[:7]})",
        fontsize=13, fontweight="bold",
    )

    ax1 = axes[0]
    for i, (label, nav) in enumerate(results):
        n = min(len(nav), len(dates))
        ax1.plot(dates[:n], nav[:n], label=label, color=colors[i], lw=2.0)
    n_spy = min(len(spy_nav), len(dates))
    ax1.plot(dates[:n_spy], spy_nav[:n_spy], label="SPY",
             color="gray", lw=1.2, ls="--", alpha=0.7)
    ax1.set_ylabel("누적 자산 (배)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.1f}x"))
    ax1.set_title("누적 NAV 곡선")
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.25)

    ax2 = axes[1]
    labels_bar = [r[0] for r in results]
    metrics    = [calc_metrics_biweekly(r[1], r[0]) for r in results]
    mdds   = [abs(m["MDD"]) * 100 for m in metrics]
    sharps = [m["샤프"] for m in metrics]
    cagrs  = [m["CAGR"] * 100 for m in metrics]

    x   = np.arange(len(labels_bar))
    w   = 0.25
    ax2.bar(x - w,  cagrs,  width=w, label="CAGR(%)",  color="#2E75B6", alpha=0.8)
    ax2.bar(x,      mdds,   width=w, label="MDD(%)",   color="#FF4444", alpha=0.8)
    ax2.bar(x + w,  sharps, width=w, label="샤프",     color="#70AD47", alpha=0.8)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels_bar, rotation=15, fontsize=9)
    ax2.set_title("CAGR / MDD / 샤프 비교")
    ax2.legend(fontsize=9)
    ax2.grid(axis="y", alpha=0.25)

    path = RESULTS_DIR / "biweekly_A_all_strategies.png"
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    logger.info(f"\n  차트 저장: {path}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true", help="상세 출력 활성화")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    if args.verbose:
        print("=" * 70)
        print("  격주(2W) 리밸런싱 × 4전략 × A진입방식(MA정배열) 백테스트")
        print(f"  기간     : {START} ~ {END}")
        print(f"  리밸런싱 : 격주 ({REBAL_FREQ})")
        print(f"  수수료   : 편도 {bhe.COMMISSION*100:.1f}% (왕복 {bhe.COMMISSION*2*100:.1f}%)")
        print(f"  유니버스 : 풀 유니버스 (S&P500 + NASDAQ-100 + KOSPI200 + KOSDAQ150)")
        print("=" * 70)
        print()
        print("  [전략 파라미터]")
        print("  공격적: ATR1.5, TOP15, 격주")
        print("  균형형: ATR2.0, TOP10, 격주")
        print("  보수적: ATR2.5, TOP7,  격주")
        print("  적응형: ATR2.0, TOP10, 격주 + 국면별 동적 전환")
        print()

    # ── [1] 데이터 로드 ──────────────────────────────────────
    if args.verbose:
        print("[1] 데이터 로드 (캐시 또는 yfinance 다운로드)...")
    all_data_raw, spy_df, etf_raw, universe_map = load_full_universe(START)

    # 모듈 전역 유니버스/섹터 업데이트 (rank_stocks 에서 참조)
    bhe.ALL_UNIVERSE.update(universe_map)
    bhe.SECTOR_ETF.update(CACHE_SECTOR_ETF)

    if args.verbose:
        print(f"  → 종목 {len(all_data_raw)}개 로드 완료 (유니버스: {len(universe_map)}개)")

    # ── [2] 지표 계산 ─────────────────────────────────────────
    if args.verbose:
        print(f"\n[2] 종목 지표 계산 ({len(all_data_raw)}종목)...")
    all_data = {t: bhe.add_indicators(df) for t, df in all_data_raw.items()}
    etf_data = {t: bhe.add_indicators(df) for t, df in etf_raw.items()}
    spy_data = bhe.add_indicators(spy_df)
    if args.verbose:
        print("  완료")

    # SPY 벤치마크 NAV (격주 기준)
    spy_close    = spy_df["Close"].squeeze()
    spy_biweekly = spy_close.resample(REBAL_FREQ).last().pct_change().fillna(0)
    spy_nav      = [1.0] + list((1 + spy_biweekly).cumprod().values.flatten())

    # ── [3] 백테스트 실행 ─────────────────────────────────────
    if args.verbose:
        print(f"\n[3] 백테스트 실행 (진입방식: A, 리밸런싱: {REBAL_FREQ})")

    all_metrics      = []
    results_for_chart = []

    for strat_name, atr_m, tn, is_adaptive in STRATEGY_CONFIGS:
        label = f"{strat_name}-A(격주)"
        if args.verbose:
            print(f"\n  ▶ {label}  ATR={atr_m}, TOP={tn}"
                  + (" [adaptive]" if is_adaptive else ""))

        nav = bhe.run_backtest(
            all_data, etf_data, spy_data,
            strategy="A",
            atr_mult=atr_m,
            top_n=tn,
            rebal_freq=REBAL_FREQ,
            adaptive=is_adaptive,
        )
        m = calc_metrics_biweekly(nav, label)
        print_metrics(m)
        all_metrics.append(m)
        results_for_chart.append((label, nav))

    # SPY 벤치마크
    m_spy = calc_metrics_biweekly(spy_nav, "SPY 벤치마크")
    all_metrics.append(m_spy)

    # ── [4] 종합 비교 표 ──────────────────────────────────────
    if args.verbose:
        print("\n" + "═" * 70)
        print("  종합 성과 비교 (4전략 × A진입방식 + SPY, 격주 리밸런싱)")
        print("═" * 70)
        print(f"  {'전략':<32} {'CAGR':>8} {'MDD':>8} {'샤프':>7} {'기간승률':>8}")
        print("  " + "─" * 65)
        for m in all_metrics:
            print(f"  {m['label']:<32} {m['CAGR']:>+8.1%} "
                  f"{m['MDD']:>+8.1%} {m['샤프']:>7.2f} {m['기간승률']:>8.1%}")

    # ── [5] CSV 저장 ──────────────────────────────────────────
    rows = [{
        "전략":     m["label"],
        "총수익률": f"{m['총수익률']:+.1%}",
        "CAGR":     f"{m['CAGR']:+.1%}",
        "MDD":      f"{m['MDD']:+.1%}",
        "샤프지수": f"{m['샤프']:.2f}",
        "기간승률": f"{m['기간승률']:.1%}",
    } for m in all_metrics]
    csv_path = RESULTS_DIR / "biweekly_A_all_strategies.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    if args.verbose:
        print(f"\n  결과 CSV: {csv_path}")

    # ── [6] 차트 ─────────────────────────────────────────────
    plot_results(results_for_chart, spy_nav)

    if args.verbose:
        print("\n" + "=" * 70)
        print("  백테스트 완료")
        print("=" * 70)
