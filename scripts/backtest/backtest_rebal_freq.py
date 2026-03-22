"""
리밸런싱 주기별 백테스트 비교 (로컬 데이터 사용)
══════════════════════════════════════════════════════════════
사전 조건: python download_data.py 로 data/ 디렉토리에 데이터 캐시 필요
비교 대상 (모두 v3 최종: ATR×2.5 스톱 + 점수비례 상한20%):
  W) 주간 리밸런싱   (매주 금요일)
  B) 격주 리밸런싱   (2주마다)
  M) 월간 리밸런싱   (월말)
  + SPY 벤치마크
══════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import json
import os
import sys

import numpy as np
import pandas as pd
import pandas_ta as ta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

START  = "2010-01-01"
END    = "2024-12-31"
TOP_N  = 10

ATR_PERIOD  = 14
ATR_MULT    = 2.5
MAX_WEIGHT  = 0.20

WEIGHTS = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)

DATA_DIR  = "data"
STOCK_DIR = os.path.join(DATA_DIR, "stocks")
ETF_DIR   = os.path.join(DATA_DIR, "etfs")
SPY_PATH  = os.path.join(DATA_DIR, "spy.parquet")
MANIFEST  = os.path.join(DATA_DIR, "manifest.json")

SECTOR_ETF = {
    "Technology":"XLK","Health Care":"XLV","Financials":"XLF",
    "Consumer Disc":"XLY","Industrials":"XLI","Energy":"XLE",
    "Materials":"XLB","Communication":"XLC",
}
US_UNIVERSE = {
    "NVDA":"Technology","AAPL":"Technology","MSFT":"Technology","AVGO":"Technology",
    "AMD":"Technology","QCOM":"Technology","AMAT":"Technology","LRCX":"Technology",
    "MU":"Technology","KLAC":"Technology","ORCL":"Technology","ADBE":"Technology",
    "CRM":"Technology","NOW":"Technology","PANW":"Technology","SNPS":"Technology",
    "META":"Communication","GOOGL":"Communication","NFLX":"Communication","TMUS":"Communication",
    "AMZN":"Consumer Disc","TSLA":"Consumer Disc","HD":"Consumer Disc","LULU":"Consumer Disc",
    "LLY":"Health Care","UNH":"Health Care","ABBV":"Health Care","ISRG":"Health Care","VRTX":"Health Care",
    "V":"Financials","MA":"Financials","JPM":"Financials","GS":"Financials",
    "XOM":"Energy","CVX":"Energy","SLB":"Energy",
    "CAT":"Industrials","GE":"Industrials","ETN":"Industrials","LMT":"Industrials",
    "FCX":"Materials","NEM":"Materials",
}
KR_UNIVERSE = {
    "005930.KS":"Technology","000660.KS":"Technology","009150.KS":"Technology",
    "006400.KS":"Technology","373220.KS":"Technology",
    "207940.KS":"Health Care","068270.KS":"Health Care",
    "051910.KS":"Materials","247540.KS":"Materials",
    "005380.KS":"Consumer Disc","000270.KS":"Consumer Disc",
    "035420.KS":"Communication","035720.KS":"Communication",
    "105560.KS":"Financials","055550.KS":"Financials",
    "096770.KS":"Energy","011200.KS":"Industrials",
}
ALL_UNIVERSE = {**US_UNIVERSE, **KR_UNIVERSE}


# ── 로컬 데이터 로드 ──────────────────────────────────────────
def load_local_data():
    """data/ 디렉토리에서 parquet 파일 로드. (all_data, etf_data, spy_close) 반환."""
    if not os.path.exists(MANIFEST):
        print(f"  ✗ {MANIFEST} 없음. 먼저 python download_data.py 를 실행하세요.")
        sys.exit(1)

    with open(MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # 종목 로드
    all_data = {}
    for ticker, info in manifest["stocks"].items():
        path = os.path.join(DATA_DIR, info["file"])
        if os.path.exists(path):
            df = pd.read_parquet(path, engine="pyarrow")
            if len(df) >= 220:
                all_data[ticker] = df

    # ETF 로드
    etf_data = {}
    for ticker, info in manifest["etfs"].items():
        path = os.path.join(DATA_DIR, info["file"])
        if os.path.exists(path):
            etf_data[ticker] = pd.read_parquet(path, engine="pyarrow")

    # SPY 로드
    spy_close = None
    if os.path.exists(SPY_PATH):
        spy_df = pd.read_parquet(SPY_PATH, engine="pyarrow")
        spy_close = spy_df["Close"].squeeze()

    return all_data, etf_data, spy_close


# ── 공통 유틸 ─────────────────────────────────────────────────
def add_indicators(df):
    d = df.copy()
    c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
    d["MA20"]  = ta.sma(c, 20)
    d["MA50"]  = ta.sma(c, 50)
    d["MA200"] = ta.sma(c, 200)
    d["RSI"]   = ta.rsi(c, 14)
    adx = ta.adx(h, l, c, 14)
    d["ADX"]   = adx["ADX_14"] if adx is not None and "ADX_14" in adx.columns else np.nan
    d["VolMA20"] = v.rolling(20).mean()
    d["VolMA60"] = v.rolling(60).mean()
    d["High52w"] = h.rolling(252).max()
    atr = ta.atr(h, l, c, length=ATR_PERIOD)
    d["ATR"]   = atr if atr is not None else np.nan
    return d

def swing_hh_hl(df_win, n=3):
    highs = df_win["High"].values
    lows  = df_win["Low"].values
    sh = [highs[i] for i in range(n, len(highs)-n) if highs[i]==max(highs[i-n:i+n+1])]
    sl = [lows[i]  for i in range(n, len(lows)-n)  if lows[i] ==min(lows[i-n:i+n+1])]
    return min(sum(sh[i]>sh[i-1] for i in range(1,len(sh))),
               sum(sl[i]>sl[i-1] for i in range(1,len(sl))))

def minmax(s):
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)


# ── 스크리닝 ──────────────────────────────────────────────────
def screen(df, as_of):
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
    atr_stop = peak20 - atr_val * ATR_MULT if not pd.isna(atr_val) else np.nan

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
            cur_px   = float(day_close.iloc[-1])
            info["peak"] = max(info["peak"], cur_px)
            stop = info.get("atr_stop", np.nan)
            if not pd.isna(stop) and cur_px <= stop:
                to_remove.append(ticker)
        for t in to_remove:
            del holdings[t]
    return holdings


# ── 리밸런싱 일자 생성 ────────────────────────────────────────
def make_rebal_dates(freq):
    if freq == "W":
        return pd.date_range(start=START, end=END, freq="W-FRI")
    elif freq == "2W":
        weekly = pd.date_range(start=START, end=END, freq="W-FRI")
        return weekly[::2]
    else:
        return pd.date_range(start=START, end=END, freq="BME")


# ── 백테스트 루프 ─────────────────────────────────────────────
def run_backtest(all_data, etf_data, freq):
    rebal_dates = make_rebal_dates(freq)
    nav_series  = pd.Series(dtype=float)
    nav         = 1.0
    holdings    = {}
    prev_dt     = None
    trade_count = 0

    total = len(rebal_dates)
    for i, rd in enumerate(rebal_dates):
        if (i+1) % 50 == 0 or i == total - 1:
            print(f"\r    진행: {i+1}/{total} ({(i+1)/total:.0%})", end="", flush=True)

        if prev_dt and holdings:
            holdings = check_stops(holdings, all_data, prev_dt, rd)

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
            nav *= (1 + ret)
        nav_series[rd] = nav

        passed = {}
        for ticker, df_t in all_data.items():
            ok, met = screen(df_t, rd)
            if ok:
                passed[ticker] = met

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

        old_set = set(holdings.keys())
        new_set = set(new_holdings.keys())
        trade_count += len(old_set ^ new_set)

        holdings = new_holdings
        prev_dt  = rd

    print()  # 줄바꿈
    return nav_series, trade_count


# ── 성과 지표 ─────────────────────────────────────────────────
def calc_metrics(nav_series, label, freq, trade_count):
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

    dd     = (nav_series - nav_series.cummax()) / nav_series.cummax()
    mdd    = dd.min()
    sharpe = (ret.mean() / (ret.std() + 1e-9)) * annualize
    win    = (ret > 0).mean()

    trades_per_year = trade_count / years if years > 0 else 0

    return {
        "label"    : label,
        "총수익률" : total_ret,
        "CAGR"     : cagr,
        "MDD"      : mdd,
        "샤프"     : sharpe,
        "승률"     : win,
        "거래횟수" : trade_count,
        "연평균거래": trades_per_year,
        "nav"      : nav_series,
    }


def print_m(m):
    print(f"  {'─'*56}")
    print(f"  {m['label']}")
    print(f"  총수익률 {m['총수익률']:>+10.1%}  CAGR {m['CAGR']:>+8.1%}")
    print(f"  MDD      {m['MDD']:>+10.1%}  샤프 {m['샤프']:>8.2f}  승률 {m['승률']:.1%}")
    print(f"  총 거래 {m['거래횟수']:>5d}회  (연평균 {m['연평균거래']:.0f}회)")


# ── 차트 ──────────────────────────────────────────────────────
def plot(all_metrics, spy_close):
    colors = {"W": "#ED7D31", "2W": "#2E75B6", "M": "#70AD47"}
    fig = plt.figure(figsize=(14, 10))
    gs  = gridspec.GridSpec(2, 3, hspace=0.45, wspace=0.35)
    ax1 = fig.add_subplot(gs[0, :])
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[1, 1])
    ax4 = fig.add_subplot(gs[1, 2])

    fig.suptitle(f"Rebalancing Frequency Comparison (v3, {START}~{END})",
                 fontsize=12, fontweight="bold")

    spy_nav = spy_close / float(spy_close.iloc[0])
    for m in all_metrics:
        freq = m["label"].split("(")[1].rstrip(")")
        ax1.plot(m["nav"].index, m["nav"].values,
                 label=m["label"], color=colors.get(freq, "gray"), lw=2.0)
    ax1.plot(spy_nav.index, spy_nav.values,
             label="SPY", color="black", lw=1.2, ls=":", alpha=0.6)
    ax1.set_ylabel("NAV (x)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.1f}x"))
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.25)

    labels = [m["label"] for m in all_metrics]

    mdds = [abs(m["MDD"])*100 for m in all_metrics]
    ax2.bar(labels, mdds,
            color=[colors.get(m["label"].split("(")[1].rstrip(")"), "gray")
                   for m in all_metrics], alpha=0.8)
    ax2.set_ylabel("MDD (%)")
    ax2.set_title("MDD")
    for i, v in enumerate(mdds):
        ax2.text(i, v+0.2, f"{v:.1f}%", ha="center", fontsize=8)
    ax2.grid(axis="y", alpha=0.25)
    plt.sca(ax2); plt.xticks(rotation=15, fontsize=8)

    sharps = [m["샤프"] for m in all_metrics]
    ax3.bar(labels, sharps,
            color=[colors.get(m["label"].split("(")[1].rstrip(")"), "gray")
                   for m in all_metrics], alpha=0.8)
    ax3.set_ylabel("Sharpe")
    ax3.set_title("Sharpe Ratio")
    for i, v in enumerate(sharps):
        ax3.text(i, v+0.01, f"{v:.2f}", ha="center", fontsize=8)
    ax3.grid(axis="y", alpha=0.25)
    plt.sca(ax3); plt.xticks(rotation=15, fontsize=8)

    trades = [m["연평균거래"] for m in all_metrics]
    ax4.bar(labels, trades,
            color=[colors.get(m["label"].split("(")[1].rstrip(")"), "gray")
                   for m in all_metrics], alpha=0.8)
    ax4.set_ylabel("Trades/Year")
    ax4.set_title("Annual Trades")
    for i, v in enumerate(trades):
        ax4.text(i, v+1, f"{v:.0f}", ha="center", fontsize=8)
    ax4.grid(axis="y", alpha=0.25)
    plt.sca(ax4); plt.xticks(rotation=15, fontsize=8)

    plt.savefig(RESULTS_DIR / "backtest_rebal_freq.png", dpi=150, bbox_inches="tight")
    print("\n  차트 저장: backtest_rebal_freq.png")
    plt.close()


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 62)
    print("  리밸런싱 주기별 백테스트 비교 (로컬 데이터)")
    print(f"  전략: v3 최종 (ATR×{ATR_MULT} 스톱 + 점수비례 상한{MAX_WEIGHT:.0%})")
    print(f"  기간: {START} ~ {END}")
    print("=" * 62)

    # ── 로컬 데이터 로드 ──
    print("\n[데이터 로드]")
    all_data, etf_raw, spy_close = load_local_data()
    print(f"  종목 {len(all_data)}개, ETF {len(etf_raw)}개, SPY {'✓' if spy_close is not None else '✗'}")

    if spy_close is None:
        print("  ✗ SPY 데이터 없음. download_data.py를 실행하세요.")
        sys.exit(1)

    # ── 지표 계산 ──
    print(f"  지표 계산 ({len(all_data)}개)...")
    for t in list(all_data.keys()):
        all_data[t] = add_indicators(all_data[t])
    etf_data = {t: add_indicators(df) for t, df in etf_raw.items()}

    # ── 백테스트 실행 ──
    configs = [
        ("W",  "주간(W)"),
        ("2W", "격주(2W)"),
        ("M",  "월간(M)"),
    ]

    all_metrics = []
    for freq, label in configs:
        print(f"\n{'═'*62}")
        print(f"  [{label}] 리밸런싱 주기: {label}")
        nav_s, trades = run_backtest(all_data, etf_data, freq)
        m = calc_metrics(nav_s, label, freq, trades)
        print_m(m)
        all_metrics.append(m)

    # ── 종합 비교 ──
    print(f"\n{'═'*62}")
    print("  종합 비교")
    print("═" * 62)
    header = (f"  {'주기':<12} {'총수익률':>10} {'CAGR':>8} "
              f"{'MDD':>8} {'샤프':>7} {'승률':>7} {'연거래':>7}")
    print(header)
    print("  " + "─" * 60)

    for m in all_metrics:
        print(f"  {m['label']:<12} {m['총수익률']:>+10.1%} {m['CAGR']:>+8.1%} "
              f"{m['MDD']:>+8.1%} {m['샤프']:>7.2f} {m['승률']:>7.1%} "
              f"{m['연평균거래']:>5.0f}회")

    spy_total = float(spy_close.iloc[-1] / spy_close.iloc[0]) - 1
    spy_years = (spy_close.index[-1] - spy_close.index[0]).days / 365.25
    spy_cagr  = ((1 + spy_total) ** (1/spy_years)) - 1
    spy_dd    = ((spy_close - spy_close.cummax()) / spy_close.cummax()).min()
    print(f"  {'SPY':<12} {spy_total:>+10.1%} {spy_cagr:>+8.1%} "
          f"{spy_dd:>+8.1%}       -       -       -")

    # ── CSV 저장 ──
    rows = []
    for m in all_metrics:
        rows.append({
            "주기": m["label"],
            "총수익률": f"{m['총수익률']:+.1%}",
            "CAGR": f"{m['CAGR']:+.1%}",
            "MDD": f"{m['MDD']:+.1%}",
            "샤프지수": f"{m['샤프']:.2f}",
            "승률": f"{m['승률']:.1%}",
            "총거래횟수": m["거래횟수"],
            "연평균거래": f"{m['연평균거래']:.0f}",
        })
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "backtest_rebal_freq.csv",
                               index=False, encoding="utf-8-sig")
    print(f"\n  결과 저장: backtest_rebal_freq.csv")

    plot(all_metrics, spy_close)
