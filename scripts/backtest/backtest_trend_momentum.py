"""
트렌드+모멘텀 파라미터 튜닝 백테스트
══════════════════════════════════════════════════════════════
비교:
  기존 모멘텀   : screener_v3 기준 (A전략, ATR2.0, TOP10, 격주)
  튜닝 트렌드+모멘텀 : 3가지 튜닝 적용
    1. 활성 섹터: 신규 진입 종목의 섹터만 (1기간 lag)
    2. 상관관계 임계값: 0.8 (높은 상관 종목 중복 제외)
    3. Top N: 10 (동일)

유니버스: 풀 유니버스 (S&P500 + NASDAQ-100 + KOSPI200 + KOSDAQ150)
수수료  : 편도 0.2% (왕복 0.4%)
기간    : 2015-01-01 ~ 현재
리밸런싱: 격주 금요일 (2W-FRI)
══════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import sys
import importlib.util
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── 경로 설정 ──────────────────────────────────────────────
_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent))

from data_cache import load_full_universe, SECTOR_ETF as CACHE_SECTOR_ETF

# backtest_hybrid_entry 동적 로드 (기존 모멘텀 run_backtest 재사용)
_spec = importlib.util.spec_from_file_location(
    "backtest_hybrid_entry", _THIS_DIR / "backtest_hybrid_entry.py"
)
bhe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bhe)

RESULTS_DIR = _THIS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── 파라미터 ───────────────────────────────────────────────
START      = "2015-01-01"
END        = datetime.today().strftime("%Y-%m-%d")
REBAL_FREQ = "2W-FRI"
PERIODS_PY = 26          # 연간 기간 수 (격주: 52/2=26)

COMMISSION = bhe.COMMISSION  # 0.002 (편도 0.2%)
ATR_MULT   = 2.0
TOP_N      = 10

# 튜닝 파라미터
CORR_THRESH = 0.8        # 튜닝 2: 0.6 → 0.8
CORR_WINDOW = 60         # 상관관계 계산 기간 (영업일)

WEIGHTS = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)
SECTOR_ETF = CACHE_SECTOR_ETF


# ══════════════════════════════════════════════════════════════
# 성과 지표 (격주 기준)
# ══════════════════════════════════════════════════════════════
def calc_metrics(nav_list: list, label: str) -> dict:
    s    = pd.Series(nav_list, dtype=float)
    ret  = s.pct_change().dropna()
    n    = len(ret)
    years = n / PERIODS_PY
    cagr  = (s.iloc[-1] ** (1 / max(years, 0.1))) - 1 if s.iloc[-1] > 0 else -1.0
    mdd   = ((s - s.cummax()) / s.cummax()).min()
    sharp = (ret.mean() / (ret.std() + 1e-9)) * np.sqrt(PERIODS_PY)
    return {
        "label":    label,
        "총수익률": s.iloc[-1] - 1,
        "CAGR":     cagr,
        "MDD":      mdd,
        "샤프":     sharp,
        "기간승률": (ret > 0).mean(),
        "nav":      nav_list,
    }


def print_metrics(m: dict):
    print(f"  {'─'*60}")
    print(f"  {m['label']}")
    print(f"  총수익률 {m['총수익률']:>+8.1%}   CAGR {m['CAGR']:>+8.1%}")
    print(f"  MDD      {m['MDD']:>+8.1%}   샤프 {m['샤프']:>8.2f}   기간승률 {m['기간승률']:.1%}")


# ══════════════════════════════════════════════════════════════
# 유틸
# ══════════════════════════════════════════════════════════════
def minmax(s: pd.Series) -> pd.Series:
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)


# ══════════════════════════════════════════════════════════════
# 상관관계 필터 (튜닝 2: 임계값 0.8)
# ══════════════════════════════════════════════════════════════
def apply_correlation_filter(
    ranked: pd.DataFrame,
    all_data: dict,
    as_of,
    corr_thresh: float = CORR_THRESH,
    window: int = CORR_WINDOW,
    top_n: int = TOP_N,
) -> pd.DataFrame:
    """
    그리디: 점수 높은 순서대로 추가, 기존 선택 종목과 corr > corr_thresh이면 제외.
    """
    if ranked.empty:
        return ranked

    ret_series: dict = {}
    for t in ranked.index:
        df_t = all_data.get(t)
        if df_t is None:
            continue
        hist = df_t[df_t.index <= as_of]
        if len(hist) < window + 1:
            continue
        ret = hist["Close"].tail(window + 1).pct_change().dropna()
        if len(ret) >= window // 2:
            ret_series[t] = ret

    selected = []
    for ticker in ranked.index:
        if len(selected) >= top_n:
            break
        if ticker not in ret_series:
            selected.append(ticker)
            continue
        too_corr = False
        for prev in selected:
            if prev not in ret_series:
                continue
            r1 = ret_series[ticker]
            r2 = ret_series[prev]
            common = r1.index.intersection(r2.index)
            if len(common) < 20:
                continue
            corr = float(r1.loc[common].corr(r2.loc[common]))
            if corr > corr_thresh:
                too_corr = True
                break
        if not too_corr:
            selected.append(ticker)

    return ranked.loc[selected] if selected else ranked.head(0)


# ══════════════════════════════════════════════════════════════
# 랭킹 (섹터 강도 포함)
# ══════════════════════════════════════════════════════════════
def rank_stocks_tm(passed: dict, etf_data: dict, as_of, universe_map: dict) -> pd.DataFrame:
    if not passed:
        return pd.DataFrame()
    df = pd.DataFrame(passed).T
    df["sector"]  = [universe_map.get(t, "Unknown") for t in df.index]
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
        minmax(df["ADX"])              * WEIGHTS["adx"] +
        minmax(df["ret3m"].fillna(0))  * WEIGHTS["ret3m"] +
        minmax(df["sec_n"])            * WEIGHTS["sector"] +
        minmax(df["vol_stab"])         * WEIGHTS["vol_stab"]
    )
    return df.sort_values("score", ascending=False)


# ══════════════════════════════════════════════════════════════
# 포지션 사이징
# ══════════════════════════════════════════════════════════════
def position_weights(scores: pd.Series, max_w: float = 0.10) -> pd.Series:
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
# 튜닝된 트렌드+모멘텀 백테스트
# ══════════════════════════════════════════════════════════════
def run_trend_momentum_backtest(
    all_data: dict,
    etf_data: dict,
    spy_data: pd.DataFrame,
    universe_map: dict,
    atr_mult: float = ATR_MULT,
    top_n: int = TOP_N,
    rebal_freq: str = REBAL_FREQ,
    corr_thresh: float = CORR_THRESH,
) -> list:
    """
    튜닝된 트렌드+모멘텀 전략 백테스트:
      - 기존 A 전략 스크리닝 (ADX, MA정배열, RSI, ATR스톱 등)
      - 활성 섹터 필터: 이전 기간 신규 진입 종목의 섹터만 (1기간 lag)
        ※ 첫 기간: 전체 섹터 허용
      - 상관관계 0.8 필터 (그리디 선택)
    """
    rebal_dates = pd.date_range(start=START, end=END, freq=rebal_freq)

    nav          = [1.0]
    holdings     = {}
    prev_dt      = None
    active_sectors = None  # None = 전체 허용 (초기)

    for rd in rebal_dates:
        # ── 구간 스톱 체크
        if prev_dt and holdings:
            holdings = bhe.check_stops(holdings, all_data, prev_dt, rd)

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

        # ── 스크리닝 (기존 A 전략 기준)
        passed_all = {}
        for ticker, df_t in all_data.items():
            ok, m = bhe.screen_A(df_t, rd, atr_mult)
            if ok:
                passed_all[ticker] = m

        # 튜닝 1: 활성 섹터 필터 (신규 진입 후보에만 적용)
        # - 기존 보유 종목: 섹터 필터 미적용 (ATR 스톱만)
        # - 신규 진입 후보: active_sectors에 속한 종목만 허용
        prev_tickers = set(holdings.keys())
        if active_sectors is None:
            # 첫 기간: 전체 허용
            passed = passed_all
        else:
            passed = {}
            for t, m in passed_all.items():
                sec = universe_map.get(t, "Unknown")
                if t in prev_tickers or sec in active_sectors:
                    passed[t] = m

        # ── 랭킹
        ranked = rank_stocks_tm(passed, etf_data, rd, universe_map)

        # 튜닝 2: 상관관계 0.8 필터 (튜닝 3: top_n=10)
        top = apply_correlation_filter(ranked, all_data, rd, corr_thresh, CORR_WINDOW, top_n)

        # ── 수수료 (턴오버 기반)
        if prev_dt and len(top) > 0:
            new_set   = set(top.index)
            old_set   = set(holdings.keys())
            sold_w    = sum(holdings[t]["w"] for t in old_set - new_set)
            ws_tmp    = position_weights(top["score"])
            bought_w  = sum(float(ws_tmp.get(t, 0)) for t in new_set - old_set)
            rebal_w   = sum(
                abs(float(ws_tmp.get(t, 0)) - holdings[t]["w"])
                for t in old_set & new_set
            )
            total_comm = (sold_w + bought_w + rebal_w) * COMMISSION
            nav[-1] *= (1 - total_comm)

        # ── 포지션 구성
        holdings = {}
        if len(top) > 0:
            ws = position_weights(top["score"])
            for ticker in top.index:
                df_t  = all_data.get(ticker)
                entry = float(df_t[df_t.index <= rd]["Close"].iloc[-1]) \
                        if df_t is not None else 1.0
                atr_s = float(top.loc[ticker, "atr_stop"]) \
                        if "atr_stop" in top.columns and \
                           not pd.isna(top.loc[ticker, "atr_stop"]) else np.nan
                holdings[ticker] = {
                    "w":        float(ws.get(ticker, 0)),
                    "entry":    entry,
                    "peak":     entry,
                    "atr_stop": atr_s,
                }

        # 튜닝 1: 다음 기간 활성 섹터 = 신규 진입 종목의 섹터
        new_entrants = [t for t in top.index if t not in prev_tickers]
        if new_entrants:
            active_sectors = {universe_map.get(t, "Unknown") for t in new_entrants}
        elif active_sectors is not None:
            pass  # 신규 진입 없으면 이전 활성 섹터 유지

        prev_dt = rd

    return nav


# ══════════════════════════════════════════════════════════════
# 차트 저장
# ══════════════════════════════════════════════════════════════
def plot_results(results: list, spy_nav: list):
    colors = ["#2E75B6", "#ED7D31", "#70AD47"]
    dates  = [pd.Timestamp(START)] + list(pd.date_range(START, END, freq=REBAL_FREQ))

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle(
        f"모멘텀 vs 트렌드+모멘텀 (튜닝)  —  격주 리밸런싱  {START}~{END[:7]}\n"
        f"튜닝: 활성섹터(신규진입만) + 상관관계임계값0.8 + TOP10",
        fontsize=12, fontweight="bold",
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
    metrics    = [calc_metrics(r[1], r[0]) for r in results]
    mdds   = [abs(m["MDD"]) * 100 for m in metrics]
    sharps = [m["샤프"] for m in metrics]
    cagrs  = [m["CAGR"] * 100 for m in metrics]

    x = np.arange(len(labels_bar))
    w = 0.25
    ax2.bar(x - w, cagrs,  width=w, label="CAGR(%)",  color="#2E75B6", alpha=0.8)
    ax2.bar(x,     mdds,   width=w, label="MDD(%)",   color="#FF4444", alpha=0.8)
    ax2.bar(x + w, sharps, width=w, label="샤프",     color="#70AD47", alpha=0.8)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels_bar, rotation=15, fontsize=9)
    ax2.set_title("CAGR / MDD / 샤프 비교")
    ax2.legend(fontsize=9)
    ax2.grid(axis="y", alpha=0.25)

    path = RESULTS_DIR / "trend_momentum_comparison.png"
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"\n  차트 저장: {path}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 70)
    print("  모멘텀 vs 튜닝된 트렌드+모멘텀 백테스트")
    print(f"  기간     : {START} ~ {END}")
    print(f"  리밸런싱 : 격주 ({REBAL_FREQ})")
    print(f"  수수료   : 편도 {COMMISSION*100:.1f}% (왕복 {COMMISSION*2*100:.1f}%)")
    print(f"  유니버스 : 풀 유니버스 (S&P500+NASDAQ100+KOSPI200+KOSDAQ150)")
    print("=" * 70)
    print()
    print("  [비교 전략]")
    print(f"  기존 모멘텀     : ATR{ATR_MULT}, TOP{TOP_N}, 격주 (A전략, 섹터필터 없음)")
    print(f"  튜닝 트렌드+모멘텀: ATR{ATR_MULT}, TOP{TOP_N}, 격주 + 3가지 튜닝")
    print(f"    1. 활성 섹터: 신규 진입 종목의 섹터만 (1기간 lag)")
    print(f"    2. 상관관계 임계값: {CORR_THRESH}")
    print(f"    3. Top N: {TOP_N}")
    print()

    # ── [1] 데이터 로드 ──────────────────────────────────────
    print("[1] 데이터 로드 (캐시 또는 yfinance 다운로드)...")
    all_data_raw, spy_df, etf_raw, universe_map = load_full_universe(START)

    bhe.ALL_UNIVERSE.update(universe_map)
    bhe.SECTOR_ETF.update(CACHE_SECTOR_ETF)

    print(f"  → 종목 {len(all_data_raw)}개 로드 완료 (유니버스: {len(universe_map)}개)")

    # ── [2] 지표 계산 ─────────────────────────────────────────
    print(f"\n[2] 종목 지표 계산 ({len(all_data_raw)}종목)...")
    all_data = {t: bhe.add_indicators(df) for t, df in all_data_raw.items()}
    etf_data = {t: bhe.add_indicators(df) for t, df in etf_raw.items()}
    spy_data = bhe.add_indicators(spy_df)
    print("  완료")

    # SPY 벤치마크 NAV
    spy_close    = spy_df["Close"].squeeze()
    spy_biweekly = spy_close.resample(REBAL_FREQ).last().pct_change().fillna(0)
    spy_nav      = [1.0] + list((1 + spy_biweekly).cumprod().values.flatten())

    # ── [3] 기존 모멘텀 백테스트 ──────────────────────────────
    print(f"\n[3] 기존 모멘텀 백테스트 (A전략, ATR={ATR_MULT}, TOP={TOP_N})...")
    nav_baseline = bhe.run_backtest(
        all_data, etf_data, spy_data,
        strategy="A",
        atr_mult=ATR_MULT,
        top_n=TOP_N,
        rebal_freq=REBAL_FREQ,
        adaptive=False,
    )
    m_baseline = calc_metrics(nav_baseline, f"기존 모멘텀(A, TOP{TOP_N})")
    print_metrics(m_baseline)

    # ── [4] 튜닝 트렌드+모멘텀 백테스트 ───────────────────────
    print(f"\n[4] 튜닝 트렌드+모멘텀 백테스트 "
          f"(활성섹터+corr{CORR_THRESH}+TOP{TOP_N})...")
    nav_tuned = run_trend_momentum_backtest(
        all_data, etf_data, spy_data, universe_map,
        atr_mult=ATR_MULT,
        top_n=TOP_N,
        rebal_freq=REBAL_FREQ,
        corr_thresh=CORR_THRESH,
    )
    m_tuned = calc_metrics(nav_tuned, f"튜닝 트렌드+모멘텀(corr{CORR_THRESH})")
    print_metrics(m_tuned)

    # SPY 벤치마크
    m_spy = calc_metrics(spy_nav, "SPY 벤치마크")

    # ── [5] 종합 비교 표 ──────────────────────────────────────
    all_metrics = [m_baseline, m_tuned, m_spy]
    print("\n" + "═" * 70)
    print("  종합 성과 비교")
    print("═" * 70)
    print(f"  {'전략':<36} {'CAGR':>8} {'MDD':>8} {'샤프':>7} {'기간승률':>8}")
    print("  " + "─" * 65)
    for m in all_metrics:
        print(f"  {m['label']:<36} {m['CAGR']:>+8.1%} "
              f"{m['MDD']:>+8.1%} {m['샤프']:>7.2f} {m['기간승률']:>8.1%}")

    # 개선 여부 출력
    print()
    delta_cagr  = m_tuned["CAGR"]  - m_baseline["CAGR"]
    delta_mdd   = m_tuned["MDD"]   - m_baseline["MDD"]
    delta_sharp = m_tuned["샤프"]  - m_baseline["샤프"]
    print(f"  [튜닝 효과]")
    print(f"  CAGR  변화: {delta_cagr:>+.1%}  "
          f"({'개선' if delta_cagr > 0 else '저하'})")
    print(f"  MDD   변화: {delta_mdd:>+.1%}  "
          f"({'개선(낙폭감소)' if delta_mdd > 0 else '악화(낙폭증가)'})")
    print(f"  샤프  변화: {delta_sharp:>+.2f}  "
          f"({'개선' if delta_sharp > 0 else '저하'})")

    # ── [6] CSV 저장 ──────────────────────────────────────────
    rows = [{
        "전략":     m["label"],
        "총수익률": f"{m['총수익률']:+.1%}",
        "CAGR":     f"{m['CAGR']:+.1%}",
        "MDD":      f"{m['MDD']:+.1%}",
        "샤프지수": f"{m['샤프']:.2f}",
        "기간승률": f"{m['기간승률']:.1%}",
    } for m in all_metrics]
    csv_path = RESULTS_DIR / "trend_momentum_comparison.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n  결과 CSV: {csv_path}")

    # ── [7] 차트 ─────────────────────────────────────────────
    results_for_chart = [
        (m_baseline["label"], nav_baseline),
        (m_tuned["label"],    nav_tuned),
    ]
    plot_results(results_for_chart, spy_nav)

    print("\n" + "=" * 70)
    print("  백테스트 완료")
    print("=" * 70)
