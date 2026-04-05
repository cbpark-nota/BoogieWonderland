"""
ATR 승수 튜닝 + 거래비용 반영 백테스트
══════════════════════════════════════════════════════════════
변수:
  ATR 승수  : 1.5, 2.0, 2.5, 3.0, 3.5, 4.0
  리밸런싱  : 주간(W), 격주(2W), 월간(M)
  거래비용  : 편도 0.1% (매수+매도 = 0.2% round-trip)
══════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import json
import logging
import os
import sys
import itertools

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

START  = "2010-01-01"
END    = "2024-12-31"
TOP_N  = 10

ATR_PERIOD   = 14
ATR_MULTS    = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
MAX_WEIGHT   = 0.20
COST_PER_SIDE = 0.001   # 편도 0.1%

WEIGHTS = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)

DATA_DIR  = "data"
MANIFEST  = os.path.join(DATA_DIR, "manifest.json")

from core.constants import US_UNIVERSE, KR_UNIVERSE, ALL_UNIVERSE, SECTOR_ETF


# ── 로컬 데이터 로드 ──────────────────────────────────────────
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


# ── 지표 ──────────────────────────────────────────────────────
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
    d["ATR"]     = atr if atr is not None else np.nan
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


# ── 스크리닝 (ATR 승수를 파라미터로) ─────────────────────────
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


# ── 포지션 사이징 ─────────────────────────────────────────────
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


# ── 스톱 체크 ─────────────────────────────────────────────────
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


# ── 리밸런싱 일자 ─────────────────────────────────────────────
def make_rebal_dates(freq):
    if freq == "W":
        return pd.date_range(start=START, end=END, freq="W-FRI")
    elif freq == "2W":
        weekly = pd.date_range(start=START, end=END, freq="W-FRI")
        return weekly[::2]
    else:
        return pd.date_range(start=START, end=END, freq="BME")


# ── 거래비용 계산 ─────────────────────────────────────────────
def calc_turnover_cost(old_holdings, new_holdings, cost_per_side):
    """
    이전 포트폴리오 → 새 포트폴리오 전환 시 발생하는 거래비용.
    변경된 비중의 절대값 합 × 편도 수수료.
    """
    all_tickers = set(list(old_holdings.keys()) + list(new_holdings.keys()))
    turnover = 0.0
    for t in all_tickers:
        old_w = old_holdings.get(t, {}).get("w", 0.0)
        new_w = new_holdings.get(t, {}).get("w", 0.0)
        turnover += abs(new_w - old_w)
    # turnover은 매수+매도의 합이므로, 각 변경분에 편도 수수료 적용
    return turnover * cost_per_side


# ── 백테스트 루프 ─────────────────────────────────────────────
def run_backtest(all_data, etf_data, freq, atr_mult, cost_per_side):
    rebal_dates = make_rebal_dates(freq)
    nav_gross   = 1.0   # 거래비용 미반영
    nav_net     = 1.0   # 거래비용 반영
    holdings    = {}
    prev_dt     = None
    trade_count = 0
    total_cost  = 0.0

    nav_gross_series = pd.Series(dtype=float)
    nav_net_series   = pd.Series(dtype=float)

    total = len(rebal_dates)
    for i, rd in enumerate(rebal_dates):
        if (i+1) % 100 == 0 or i == total - 1:
            logger.info(f"    진행: {i+1}/{total} ({(i+1)/total:.0%})")

        # 스톱 체크
        if prev_dt and holdings:
            holdings = check_stops(holdings, all_data, prev_dt, rd)

        # 구간 수익 반영
        if prev_dt and holdings:
            ret = 0.0
            for ticker, info in holdings.items():
                df_t = all_data.get(ticker)
                if df_t is None:
                    continue
                p0 = df_t[df_t.index <= prev_dt]["Close"]
                p1 = df_t[df_t.index <= rd]["Close"]
                if len(p0) and len(p1) and float(p0.iloc[-1]) > 0:
                    ret += info["w"] * (float(p1.iloc[-1])/float(p0.iloc[-1]) - 1)
            nav_gross *= (1 + ret)
            nav_net   *= (1 + ret)

        # 스크리닝
        passed = {}
        for ticker, df_t in all_data.items():
            ok, met = screen(df_t, rd, atr_mult)
            if ok:
                passed[ticker] = met

        # 랭킹 + 포지션 구성
        ranked = rank_stocks(passed, etf_data, rd)
        top    = ranked.head(TOP_N)
        n      = len(top)

        new_holdings = {}
        if n > 0:
            ws = position_weights(top["score"])
            for ticker in top.index:
                df_t  = all_data.get(ticker)
                entry = float(df_t[df_t.index<=rd]["Close"].iloc[-1]) \
                        if df_t is not None else 1.0
                atr_s = float(top.loc[ticker, "atr_stop"]) \
                        if "atr_stop" in top.columns else np.nan
                new_holdings[ticker] = {
                    "w": float(ws[ticker]),
                    "entry": entry,
                    "peak": entry,
                    "atr_stop": atr_s,
                }

        # 거래비용 차감
        period_cost = calc_turnover_cost(holdings, new_holdings, cost_per_side)
        nav_net *= (1 - period_cost)
        total_cost += period_cost

        # 거래 횟수
        old_set = set(holdings.keys())
        new_set = set(new_holdings.keys())
        trade_count += len(old_set ^ new_set)

        holdings = new_holdings
        prev_dt  = rd

        nav_gross_series[rd] = nav_gross
        nav_net_series[rd]   = nav_net

    logger.info("")
    return nav_gross_series, nav_net_series, trade_count, total_cost


# ── 성과 지표 ─────────────────────────────────────────────────
def calc_metrics(nav_series, label, freq):
    ret = nav_series.pct_change().dropna()
    total_ret = nav_series.iloc[-1] - 1

    if freq == "W":
        annualize = np.sqrt(52)
    elif freq == "2W":
        annualize = np.sqrt(26)
    else:
        annualize = np.sqrt(12)

    years = (nav_series.index[-1] - nav_series.index[0]).days / 365.25
    cagr  = (nav_series.iloc[-1] ** (1/years)) - 1 if years > 0 else 0
    dd    = (nav_series - nav_series.cummax()) / nav_series.cummax()
    mdd   = dd.min()
    sharpe = (ret.mean() / (ret.std() + 1e-9)) * annualize
    win    = (ret > 0).mean()

    return {
        "label": label, "총수익률": total_ret, "CAGR": cagr,
        "MDD": mdd, "샤프": sharpe, "승률": win, "nav": nav_series,
    }


# ── 차트 ──────────────────────────────────────────────────────
def plot_heatmaps(results_df):
    """ATR × 주기 히트맵: CAGR(순), 샤프(순), MDD"""
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle(f"ATR Multiplier Tuning with Transaction Cost ({COST_PER_SIDE*100:.1f}% per side), {START}~{END}",
                 fontsize=12, fontweight="bold")

    for ax, col, title, fmt, cmap in [
        (axes[0], "CAGR(순)", "CAGR (Net)",       "{:.1%}", "YlGn"),
        (axes[1], "샤프(순)", "Sharpe (Net)",      "{:.2f}", "YlGn"),
        (axes[2], "MDD(순)",  "MDD (Net)",         "{:.1%}", "YlOrRd_r"),
    ]:
        pivot = results_df.pivot(index="ATR", columns="주기", values=col)
        pivot = pivot[["W", "2W", "M"]]  # 열 순서 고정

        im = ax.imshow(pivot.values, cmap=cmap, aspect="auto")
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels(pivot.columns)
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels([f"{v:.1f}" for v in pivot.index])
        ax.set_xlabel("리밸런싱 주기")
        ax.set_ylabel("ATR 승수")
        ax.set_title(title)

        for i in range(len(pivot.index)):
            for j in range(len(pivot.columns)):
                val = pivot.values[i, j]
                text = fmt.format(val)
                ax.text(j, i, text, ha="center", va="center", fontsize=9,
                        color="white" if abs(val) > 0.3 else "black")

        fig.colorbar(im, ax=ax, shrink=0.8)

    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "backtest_atr_tuning.png", dpi=150, bbox_inches="tight")
    logger.info("  차트 저장: backtest_atr_tuning.png")
    plt.close()


def plot_nav_curves(best_results, spy_close):
    """상위 조합의 NAV 곡선"""
    fig, ax = plt.subplots(figsize=(13, 6))
    fig.suptitle(f"Top Combinations NAV (Net of Cost), {START}~{END}",
                 fontsize=12, fontweight="bold")

    colors = plt.cm.tab10.colors
    for i, row in enumerate(best_results):
        ax.plot(row["nav_net"].index, row["nav_net"].values,
                label=row["label"], color=colors[i % len(colors)], lw=1.8)

    spy_nav = spy_close / float(spy_close.iloc[0])
    ax.plot(spy_nav.index, spy_nav.values,
            label="SPY", color="black", lw=1.2, ls=":", alpha=0.6)
    ax.set_ylabel("NAV (x)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}x"))
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "backtest_atr_tuning_nav.png", dpi=150, bbox_inches="tight")
    logger.info("  차트 저장: backtest_atr_tuning_nav.png")
    plt.close()


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

    freqs = ["W", "2W", "M"]
    freq_labels = {"W": "주간", "2W": "격주", "M": "월간"}
    combos = list(itertools.product(ATR_MULTS, freqs))

    if args.verbose:
        print("=" * 66)
        print("  ATR 승수 튜닝 + 거래비용 반영 백테스트")
        print(f"  ATR 승수: {ATR_MULTS}")
        print(f"  리밸런싱: {[freq_labels[f] for f in freqs]}")
        print(f"  거래비용: 편도 {COST_PER_SIDE*100:.1f}%")
        print(f"  기간: {START} ~ {END}")
        print(f"  총 {len(combos)}개 조합")
        print("=" * 66)

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

    # ── 백테스트 실행 ──
    all_results = []
    for idx, (atr_m, freq) in enumerate(combos, 1):
        label = f"ATR={atr_m:.1f} {freq_labels[freq]}({freq})"
        if args.verbose:
            print(f"\n[{idx}/{len(combos)}] {label}")

        nav_g, nav_n, trades, cost = run_backtest(
            all_data, etf_data, freq, atr_m, COST_PER_SIDE)

        m_gross = calc_metrics(nav_g, label + " (Gross)", freq)
        m_net   = calc_metrics(nav_n, label + " (Net)", freq)

        years = (nav_n.index[-1] - nav_n.index[0]).days / 365.25

        result = {
            "ATR": atr_m, "주기": freq,
            "label": label,
            "CAGR(총)": m_gross["CAGR"], "CAGR(순)": m_net["CAGR"],
            "MDD(총)": m_gross["MDD"], "MDD(순)": m_net["MDD"],
            "샤프(총)": m_gross["샤프"], "샤프(순)": m_net["샤프"],
            "승률(순)": m_net["승률"],
            "총수익(총)": m_gross["총수익률"], "총수익(순)": m_net["총수익률"],
            "거래횟수": trades,
            "연거래": trades / years if years > 0 else 0,
            "누적비용": cost,
            "nav_gross": nav_g, "nav_net": nav_n,
        }

        if args.verbose:
            print(f"    Gross → CAGR {m_gross['CAGR']:>+7.1%}  MDD {m_gross['MDD']:>+6.1%}  샤프 {m_gross['샤프']:.2f}")
            print(f"    Net   → CAGR {m_net['CAGR']:>+7.1%}  MDD {m_net['MDD']:>+6.1%}  샤프 {m_net['샤프']:.2f}  "
                  f"연거래 {result['연거래']:.0f}회")

        all_results.append(result)

    # ── 종합 비교 테이블 ──
    # 순수익 CAGR 기준 정렬
    sorted_results = sorted(all_results, key=lambda x: x["CAGR(순)"], reverse=True)

    if args.verbose:
        print(f"\n{'═'*80}")
        print("  종합 비교 (거래비용 반영 후 순수익 기준)")
        print("═" * 80)
        print(f"  {'ATR':>4} {'주기':<5}  {'CAGR총':>7} {'CAGR순':>7} {'비용차':>6}  "
              f"{'MDD순':>7} {'샤프순':>6} {'승률':>5} {'연거래':>5}")
        print("  " + "─" * 72)

        for r in sorted_results:
            cost_drag = r["CAGR(총)"] - r["CAGR(순)"]
            print(f"  {r['ATR']:>4.1f} {freq_labels[r['주기']]:<4}({r['주기']:<2})"
                  f" {r['CAGR(총)']:>+7.1%} {r['CAGR(순)']:>+7.1%} {cost_drag:>+6.1%}"
                  f"  {r['MDD(순)']:>+7.1%} {r['샤프(순)']:>6.2f} {r['승률(순)']:>5.1%}"
                  f" {r['연거래']:>5.0f}")

        # SPY 참고
        spy_total = float(spy_close.iloc[-1] / spy_close.iloc[0]) - 1
        spy_years = (spy_close.index[-1] - spy_close.index[0]).days / 365.25
        spy_cagr  = ((1 + spy_total) ** (1/spy_years)) - 1
        spy_dd    = ((spy_close - spy_close.cummax()) / spy_close.cummax()).min()
        print("  " + "─" * 72)
        print(f"  SPY  {'':>10} {spy_cagr:>+7.1%} {'':>6}  {spy_dd:>+7.1%}")

        # ── 최적 조합 ──
        best = sorted_results[0]
        print(f"\n  ★ 최적 조합: ATR={best['ATR']:.1f} × {freq_labels[best['주기']]}({best['주기']})")
        print(f"    순 CAGR {best['CAGR(순)']:+.1%}  MDD {best['MDD(순)']:+.1%}  "
              f"샤프 {best['샤프(순)']:.2f}  승률 {best['승률(순)']:.1%}")

        # 주기별 최적
        print(f"\n  [주기별 최적 ATR 승수]")
        for freq in freqs:
            freq_results = [r for r in sorted_results if r["주기"] == freq]
            if freq_results:
                b = freq_results[0]
                print(f"    {freq_labels[freq]}({freq}): ATR={b['ATR']:.1f} → "
                      f"CAGR(순) {b['CAGR(순)']:+.1%}  MDD {b['MDD(순)']:+.1%}  "
                      f"샤프 {b['샤프(순)']:.2f}")

    # ── CSV 저장 ──
    rows = []
    for r in sorted_results:
        rows.append({
            "ATR승수": r["ATR"], "주기": r["주기"],
            "CAGR(총)": f"{r['CAGR(총)']:+.1%}",
            "CAGR(순)": f"{r['CAGR(순)']:+.1%}",
            "비용차": f"{r['CAGR(총)']-r['CAGR(순)']:+.1%}",
            "MDD(순)": f"{r['MDD(순)']:+.1%}",
            "샤프(순)": f"{r['샤프(순)']:.2f}",
            "승률": f"{r['승률(순)']:.1%}",
            "연거래횟수": f"{r['연거래']:.0f}",
            "총수익(총)": f"{r['총수익(총)']:+.1%}",
            "총수익(순)": f"{r['총수익(순)']:+.1%}",
        })
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "backtest_atr_tuning.csv",
                               index=False, encoding="utf-8-sig")
    if args.verbose:
        print(f"\n  결과 저장: backtest_atr_tuning.csv")

    # ── 히트맵 ──
    results_df = pd.DataFrame([{
        "ATR": r["ATR"], "주기": r["주기"],
        "CAGR(순)": r["CAGR(순)"], "샤프(순)": r["샤프(순)"], "MDD(순)": r["MDD(순)"],
    } for r in all_results])
    plot_heatmaps(results_df)

    # ── 상위 5개 NAV 곡선 ──
    plot_nav_curves(sorted_results[:5], spy_close)
