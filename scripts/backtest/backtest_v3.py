"""
백테스트 v3 — ATR 스톱로스 + 점수 비례 포지션 사이징 검증
══════════════════════════════════════════════════════════════
비교 대상:
  A) v2 베이스  : 고정 스톱(-10%) + 동일비중
  B) ATR 스톱   : ATR×2.5 스톱    + 동일비중
  C) 점수 비중  : 고정 스톱(-10%) + 점수비례(상한 20%)
  D) v3 최종    : ATR×2.5 스톱    + 점수비례(상한 20%)
  E) SPY 벤치마크
══════════════════════════════════════════════════════════════
"""
import logging
import sys
import warnings
warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

import numpy as np
import pandas as pd
import yfinance as yf
import pandas_ta as ta
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.constants import US_UNIVERSE, KR_UNIVERSE, ALL_UNIVERSE, SECTOR_ETF

START  = "2019-01-01"
END    = "2024-12-31"
TOP_N  = 10

ATR_PERIOD  = 14
ATR_MULT    = 2.5
FIXED_STOP  = -0.10
MAX_WEIGHT  = 0.20

WEIGHTS = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)


# ── 공통 유틸 ─────────────────────────────────────────────────
def download_all(tickers, start, end):
    data = {}
    for i in range(0, len(tickers), 40):
        chunk = tickers[i:i+40]
        try:
            raw = yf.download(chunk, start=start, end=end,
                              auto_adjust=True, progress=False, threads=True)
            if raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                for t in chunk:
                    try:
                        df = raw.xs(t, axis=1, level=1).dropna(how="all")
                        if len(df) >= 220:
                            data[t] = df
                    except KeyError:
                        pass
            else:
                if len(raw) >= 220:
                    data[chunk[0]] = raw
        except Exception as e:
            logging.debug("backtest_v3 download_all: 배치(offset=%d) 다운로드 실패 — %s", i, e)
    return data

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

    # ATR 스톱 계산
    atr_val  = float(hist["ATR"].dropna().iloc[-1]) \
               if "ATR" in hist.columns and len(hist["ATR"].dropna())>0 else np.nan
    peak20   = float(hist["High"].tail(20).max())
    atr_stop = peak20 - atr_val * ATR_MULT if not pd.isna(atr_val) else np.nan

    # 현재가가 이미 ATR 스톱 이하인 종목은 제외 (스톱 트리거 상태)
    if not pd.isna(atr_stop) and float(hist["Close"].iloc[-1]) <= atr_stop:
        return False, {}

    return True, {
        "ADX": float(adx), "RSI": float(rsi),
        "ret3m": ret3m, "vol_stab": vol_stab,
        "price": float(hist["Close"].iloc[-1]),
        "atr_stop": atr_stop,
        "atr": atr_val,
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
def position_weights(scores, equal=False, max_w=MAX_WEIGHT):
    n = len(scores)
    if equal or n == 0:
        return pd.Series([1.0/n]*n, index=scores.index)
    total = scores.sum()
    if total == 0 or pd.isna(total):
        return pd.Series([1.0/n]*n, index=scores.index)
    # 점수가 0인 종목에 최소 비중 부여 (NaN 방지)
    adj_scores = scores.copy()
    adj_scores[adj_scores <= 0] = 1e-6
    w = adj_scores / adj_scores.sum()
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
def check_stops(holdings, all_data, prev_dt, rd, use_atr_stop):
    """
    월중 일별 스톱 체크.
    holdings: {ticker: {"w": float, "entry": float, "peak": float, "atr_stop": float}}
    """
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
            new_peak = max(info["peak"], cur_px)
            info["peak"] = new_peak

            if use_atr_stop:
                # ATR 스톱: 진입 시점에 계산된 atr_stop 유지
                stop = info.get("atr_stop", np.nan)
                if not pd.isna(stop) and cur_px <= stop:
                    to_remove.append(ticker)
            else:
                # 고정 트레일링 스톱
                if cur_px <= new_peak * (1 + FIXED_STOP):
                    to_remove.append(ticker)

        for t in to_remove:
            del holdings[t]
    return holdings


# ── 백테스트 루프 ─────────────────────────────────────────────
def run_backtest(all_data, etf_data, label,
                 use_atr_stop=False, equal_weight=True):
    rebal_dates = pd.date_range(start=START, end=END, freq="BME")
    nav      = [1.0]
    holdings = {}   # {ticker: {w, entry, peak, atr_stop}}
    prev_dt  = None

    for rd in rebal_dates:
        # 월중 스톱 체크
        if prev_dt and holdings:
            holdings = check_stops(holdings, all_data, prev_dt, rd, use_atr_stop)

        # 월 수익 반영
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
            nav.append(nav[-1] * (1 + ret))
        elif prev_dt:
            nav.append(nav[-1])

        # 스크리닝
        passed = {}
        for ticker, df_t in all_data.items():
            ok, metrics = screen(df_t, rd)
            if ok:
                passed[ticker] = metrics

        # 랭킹
        ranked = rank_stocks(passed, etf_data, rd)
        top    = ranked.head(TOP_N)
        n      = len(top)

        # 포지션 구성
        holdings = {}
        if n > 0:
            ws = position_weights(top["score"], equal=equal_weight)
            for ticker in top.index:
                df_t   = all_data.get(ticker)
                entry  = float(df_t[df_t.index<=rd]["Close"].iloc[-1]) \
                         if df_t is not None else 1.0
                atr_s  = float(top.loc[ticker, "atr_stop"]) \
                         if "atr_stop" in top.columns else np.nan
                holdings[ticker] = {
                    "w": float(ws[ticker]),
                    "entry": entry,
                    "peak": entry,
                    "atr_stop": atr_s,
                }
        prev_dt = rd

    return nav


# ── 성과 지표 ─────────────────────────────────────────────────
def metrics(nav_list, label):
    s   = pd.Series(nav_list, dtype=float)
    ret = s.pct_change().dropna()
    n   = len(ret)
    return {
        "label"  : label,
        "총수익률": s.iloc[-1]-1,
        "CAGR"   : (s.iloc[-1]**(12/max(n,1)))-1,
        "MDD"    : ((s-s.cummax())/s.cummax()).min(),
        "샤프"   : (ret.mean()/(ret.std()+1e-9))*np.sqrt(12),
        "월승률" : (ret>0).mean(),
        "nav"    : nav_list,
    }

def print_m(m):
    print(f"  {'─'*52}")
    print(f"  {m['label']}")
    print(f"  총수익률 {m['총수익률']:>+8.1%}  CAGR {m['CAGR']:>+8.1%}")
    print(f"  MDD      {m['MDD']:>+8.1%}  샤프 {m['샤프']:>8.2f}  월승률 {m['월승률']:.1%}")


# ── 차트 ──────────────────────────────────────────────────────
def plot(results, spy_nav):
    colors = ["#AAAAAA","#2E75B6","#70AD47","#ED7D31","black"]
    dates  = [pd.Timestamp(START)] + list(pd.date_range(START, END, freq="BME"))
    fig    = plt.figure(figsize=(13, 9))
    gs     = gridspec.GridSpec(2,2, hspace=0.4, wspace=0.35)
    ax1    = fig.add_subplot(gs[0,:])
    ax2    = fig.add_subplot(gs[1,0])
    ax3    = fig.add_subplot(gs[1,1])

    fig.suptitle("v3 개선 검증 — ATR 스톱 + 점수 비례 포지션 (2019–2024)",
                 fontsize=12, fontweight="bold")

    for i, (label, nav) in enumerate(results):
        n = min(len(nav), len(dates))
        ax1.plot(dates[:n], nav[:n], label=label,
                 color=colors[i % len(colors)], lw=2.0)
    n = min(len(spy_nav), len(dates))
    ax1.plot(dates[:n], spy_nav[:n], label="SPY",
             color="black", lw=1.2, ls=":", alpha=0.6)
    ax1.set_ylabel("누적 자산 (배)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x,_: f"{x:.1f}x"))
    ax1.legend(fontsize=8); ax1.grid(alpha=0.25)

    # MDD 막대
    labels = [r[0] for r in results]
    mdds   = [abs(metrics(r[1],r[0])["MDD"])*100 for r in results]
    sharps = [metrics(r[1],r[0])["샤프"] for r in results]

    ax2.bar(labels, mdds, color=colors[:len(results)], alpha=0.8)
    ax2.set_ylabel("MDD (%)"); ax2.set_title("최대 낙폭 비교")
    for i,(v) in enumerate(mdds):
        ax2.text(i, v+0.2, f"{v:.1f}%", ha="center", fontsize=8)
    ax2.grid(axis="y", alpha=0.25); plt.sca(ax2); plt.xticks(rotation=20, fontsize=7)

    ax3.bar(labels, sharps, color=colors[:len(results)], alpha=0.8)
    ax3.set_ylabel("샤프지수"); ax3.set_title("샤프지수 비교")
    for i,(v) in enumerate(sharps):
        ax3.text(i, v+0.01, f"{v:.2f}", ha="center", fontsize=8)
    ax3.grid(axis="y", alpha=0.25); plt.sca(ax3); plt.xticks(rotation=20, fontsize=7)

    plt.savefig(RESULTS_DIR / "backtest_v3_result.png", dpi=150, bbox_inches="tight")
    print("\n  차트 저장: backtest_v3_result.png")
    plt.show()


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true", help="상세 출력 활성화")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    logger.debug("=" * 60)
    logger.debug("  v3 개선 백테스트: ATR 스톱 + 점수 비례 포지션")
    logger.debug(f"  기간: {START} ~ {END}")
    logger.debug("=" * 60)

    # 데이터
    logger.debug("\n[데이터 다운로드]")
    all_tickers = list(ALL_UNIVERSE.keys())
    logger.debug(f"  종목 {len(all_tickers)}개...")
    all_data = download_all(all_tickers, START, END)
    logger.debug(f"  → {len(all_data)}개 완료")

    etf_tickers = list(set(SECTOR_ETF.values()))
    logger.debug(f"  섹터 ETF {len(etf_tickers)}개...")
    etf_raw = download_all(etf_tickers, START, END)
    etf_data = {t: add_indicators(df) for t, df in etf_raw.items()}
    logger.debug(f"  → {len(etf_data)}개 완료")

    logger.debug("  SPY 벤치마크...")
    spy_raw     = yf.download("SPY", start=START, end=END,
                               auto_adjust=True, progress=False)
    spy_close   = spy_raw["Close"].squeeze()
    spy_monthly = spy_close.resample("BME").last().pct_change().fillna(0)
    spy_nav     = [1.0] + list((1+spy_monthly).cumprod().values.flatten())

    # 지표 계산
    logger.debug(f"\n  지표 계산 ({len(all_data)}개)...")
    for t in list(all_data.keys()):
        all_data[t] = add_indicators(all_data[t])

    results = []

    # A) v2 베이스: 고정 스톱 + 동일비중
    logger.debug("\n" + "═"*60)
    logger.debug("  [A] v2 베이스: 고정 스톱(-10%) + 동일비중")
    nav_a = run_backtest(all_data, etf_data,
                         "A", use_atr_stop=False, equal_weight=True)
    m_a = metrics(nav_a, "A: 고정스톱 + 동일비중")
    print_m(m_a)
    results.append(("A: 고정스톱+동일비중", nav_a))

    # B) ATR 스톱 + 동일비중
    logger.debug("\n" + "═"*60)
    logger.debug("  [B] ATR 스톱(×2.5) + 동일비중")
    nav_b = run_backtest(all_data, etf_data,
                         "B", use_atr_stop=True, equal_weight=True)
    m_b = metrics(nav_b, "B: ATR스톱 + 동일비중")
    print_m(m_b)
    dc = m_b["CAGR"] - m_a["CAGR"]
    dm = m_b["MDD"]  - m_a["MDD"]
    print(f"\n  A 대비 → CAGR {dc:+.1%}  MDD {dm:+.1%}")
    results.append(("B: ATR스톱+동일비중", nav_b))

    # C) 고정 스톱 + 점수비례
    logger.debug("\n" + "═"*60)
    logger.debug("  [C] 고정 스톱(-10%) + 점수비례 배분(상한 20%)")
    nav_c = run_backtest(all_data, etf_data,
                         "C", use_atr_stop=False, equal_weight=False)
    m_c = metrics(nav_c, "C: 고정스톱 + 점수비례")
    print_m(m_c)
    dc = m_c["CAGR"] - m_a["CAGR"]
    dm = m_c["MDD"]  - m_a["MDD"]
    print(f"\n  A 대비 → CAGR {dc:+.1%}  MDD {dm:+.1%}")
    results.append(("C: 고정스톱+점수비례", nav_c))

    # D) v3 최종: ATR 스톱 + 점수비례
    logger.debug("\n" + "═"*60)
    logger.debug("  [D] v3 최종: ATR 스톱(×2.5) + 점수비례(상한 20%)")
    nav_d = run_backtest(all_data, etf_data,
                         "D", use_atr_stop=True, equal_weight=False)
    m_d = metrics(nav_d, "D: v3 최종")
    print_m(m_d)
    dc = m_d["CAGR"] - m_a["CAGR"]
    dm = m_d["MDD"]  - m_a["MDD"]
    ds = m_d["샤프"] - m_a["샤프"]
    print(f"\n  A 대비 → CAGR {dc:+.1%}  MDD {dm:+.1%}  샤프 {ds:+.2f}")
    results.append(("D: v3(ATR+점수비례)", nav_d))

    # 종합 비교
    print("\n" + "═"*60)
    print("  종합 비교")
    print("═"*60)
    all_m = [m_a, m_b, m_c, m_d, metrics(spy_nav,"SPY")]
    print(f"  {'전략':<26} {'총수익률':>8} {'CAGR':>8} "
          f"{'MDD':>8} {'샤프':>7} {'월승률':>7}")
    print("  " + "─"*66)
    for m in all_m:
        mark = " ◀ 최종" if "v3" in m["label"] else ""
        print(f"  {m['label']:<26} {m['총수익률']:>+8.1%} {m['CAGR']:>+8.1%} "
              f"{m['MDD']:>+8.1%} {m['샤프']:>7.2f} {m['월승률']:>7.1%}{mark}")

    # CSV 저장
    rows = [{"전략":m["label"], "총수익률":f"{m['총수익률']:+.1%}",
             "CAGR":f"{m['CAGR']:+.1%}", "MDD":f"{m['MDD']:+.1%}",
             "샤프지수":f"{m['샤프']:.2f}", "월간승률":f"{m['월승률']:.1%}"}
            for m in all_m]
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "backtest_v3_comparison.csv",
                               index=False, encoding="utf-8-sig")
    print("\n  결과 저장: backtest_v3_comparison.csv")

    plot(results, spy_nav)
