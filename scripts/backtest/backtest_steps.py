"""
단계별 알고리즘 개선 백테스트 비교 엔진
══════════════════════════════════════════════════════════════
베이스라인  : 원본 알고리즘
Step 1      : 스톱로스 추가          (트레일링 스톱 -10%)
Step 2      : RSI 상한선 조정        (70 → 75)
Step 3      : HH-HL 스윙 포인트 교체 (일봉 → 스윙 기준)
Step 4      : 섹터 강도 ETF 기준     (유니버스 내 비교 → ETF 초과수익률)
Step 5      : 52주 신고가 필터 추가  (신고가 20% 이내)

실행 방법:
    pip install yfinance pandas-ta pandas numpy matplotlib
    python backtest_steps.py
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
from copy import deepcopy
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent.parent))

# ═══════════════════════════════════════════════════════════════
# 0. 공통 설정
# ═══════════════════════════════════════════════════════════════
START   = "2019-01-01"
END     = "2024-12-31"
TOP_N   = 10
WEIGHTS = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)

from core.constants import US_UNIVERSE, KR_UNIVERSE, ALL_UNIVERSE, SECTOR_ETF


# ═══════════════════════════════════════════════════════════════
# 1. 데이터 다운로드
# ═══════════════════════════════════════════════════════════════
def download_all(tickers, start, end):
    data = {}
    batch = 40
    for i in range(0, len(tickers), batch):
        chunk = tickers[i:i+batch]
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
            logging.debug("backtest_steps download_all: 배치(offset=%d) 다운로드 실패 — %s", i, e)
    return data


# ═══════════════════════════════════════════════════════════════
# 2. 지표 계산
# ═══════════════════════════════════════════════════════════════
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
    return d


# ═══════════════════════════════════════════════════════════════
# 3. 스윙 포인트 계산 (Step 3용)
# ═══════════════════════════════════════════════════════════════
def find_swing_highs(highs, n=3):
    pts = []
    for i in range(n, len(highs) - n):
        if highs[i] == max(highs[i-n:i+n+1]):
            pts.append((i, highs[i]))
    return pts

def find_swing_lows(lows, n=3):
    pts = []
    for i in range(n, len(lows) - n):
        if lows[i] == min(lows[i-n:i+n+1]):
            pts.append((i, lows[i]))
    return pts

def count_hh_hl_swing(df_window, n=3):
    """스윙 포인트 기준 HH-HL 패턴 카운트"""
    highs = df_window["High"].values
    lows  = df_window["Low"].values
    sh = find_swing_highs(highs, n)
    sl = find_swing_lows(lows, n)
    hh = sum(sh[i][1] > sh[i-1][1] for i in range(1, len(sh)))
    hl = sum(sl[i][1] > sl[i-1][1] for i in range(1, len(sl)))
    return min(hh, hl)


# ═══════════════════════════════════════════════════════════════
# 4. 스크리닝 함수 (cfg 딕셔너리로 단계별 조건 제어)
# ═══════════════════════════════════════════════════════════════
def screen(df, as_of, cfg, sector_etf_data=None):
    """
    cfg 키:
      rsi_max       : RSI 상한 (Step2: 70→75)
      swing_hh_hl   : True면 스윙 기준 HH-HL (Step3)
      use_etf_sector: True면 ETF 초과수익률 (Step4)
      use_52w_filter: True면 52주 신고가 필터 (Step5)
    """
    hist = df[df.index <= as_of]
    if len(hist) < 220:
        return False, {}

    row   = hist.iloc[-1]
    r5    = hist.tail(6)
    r20   = hist.tail(20)
    r60   = hist.tail(60)
    r63   = hist.tail(63)

    # ① ADX ≥ 25
    adx = row.get("ADX", np.nan)
    if pd.isna(adx) or adx < 25:
        return False, {}

    # ② 이평선 정배열
    ma20, ma50, ma200 = row.get("MA20"), row.get("MA50"), row.get("MA200")
    if any(pd.isna(v) for v in [ma20, ma50, ma200]):
        return False, {}
    if not (ma20 > ma50 > ma200):
        return False, {}

    # ③ RSI (Step2에서 상한 조정)
    rsi = row.get("RSI", np.nan)
    rsi_max = cfg.get("rsi_max", 70)
    if pd.isna(rsi) or not (50 <= rsi <= rsi_max):
        return False, {}

    # ④ 거래량 급등 필터
    vol60 = row.get("VolMA60", np.nan)
    if pd.isna(vol60) or vol60 == 0:
        return False, {}
    if (r20["Volume"] > vol60 * 3.0).any():
        return False, {}

    # ⑤ 단기 급등 필터
    if (r5["Close"].pct_change().abs() > 0.10).any():
        return False, {}

    # ⑥ HH-HL 패턴 (Step3: 스윙 기준)
    if cfg.get("swing_hh_hl", False):
        hh_hl = count_hh_hl_swing(r60)
    else:
        highs = r60["High"].values
        lows  = r60["Low"].values
        hh_hl = sum(highs[i] > highs[i-1] and lows[i] > lows[i-1]
                    for i in range(1, len(highs)))
    if hh_hl < 3:
        return False, {}

    # ⑦ 52주 신고가 20% 이내 (Step5)
    if cfg.get("use_52w_filter", False):
        high52 = row.get("High52w", np.nan)
        if not pd.isna(high52) and high52 > 0:
            if row["Close"] < high52 * 0.80:
                return False, {}

    # 복합점수 원재료
    ret3m    = float(hist["Close"].iloc[-1] / r63["Close"].iloc[0]) - 1 if len(r63) >= 60 else np.nan
    vol_cv   = r20["Volume"].std() / (vol60 + 1e-9)
    vol_stab = float(1 / (vol_cv + 1e-6))

    # 섹터 ETF 초과수익률 (Step4)
    etf_ret = np.nan
    if cfg.get("use_etf_sector", False) and sector_etf_data:
        pass  # 아래 rank 단계에서 처리

    return True, {
        "ADX": float(adx), "RSI": float(rsi),
        "ret3m": ret3m, "vol_stab": vol_stab,
        "price": float(hist["Close"].iloc[-1]),
    }


# ═══════════════════════════════════════════════════════════════
# 5. 복합점수 및 랭킹
# ═══════════════════════════════════════════════════════════════
def minmax(s):
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)

def rank_stocks(passed, sector_map, cfg, etf_data=None, as_of=None):
    if not passed:
        return pd.DataFrame()
    df = pd.DataFrame(passed).T
    df["sector"] = [sector_map.get(t, "Unknown") for t in df.index]

    # 섹터 강도 계산
    if cfg.get("use_etf_sector", False) and etf_data and as_of:
        # ETF 초과수익률 기준
        df["sec_str"] = 0.0
        for idx, row in df.iterrows():
            sec = row["sector"]
            etf_sym = SECTOR_ETF.get(sec)
            if etf_sym and etf_sym in etf_data:
                etf_hist = etf_data[etf_sym]
                etf_hist = etf_hist[etf_hist.index <= as_of]
                if len(etf_hist) >= 63:
                    etf_ret = float(etf_hist["Close"].iloc[-1] /
                                    etf_hist["Close"].iloc[-63]) - 1
                    df.loc[idx, "sec_str"] = row["ret3m"] - etf_ret \
                        if not pd.isna(row["ret3m"]) else 0.0
        df["sec_str"] = minmax(df["sec_str"])
    else:
        # 유니버스 내 비교
        df["sec_str"] = 0.5
        for sec in df["sector"].unique():
            mask = df["sector"] == sec
            if mask.sum() > 1:
                df.loc[mask, "sec_str"] = minmax(
                    df.loc[mask, "ret3m"].fillna(0))

    df["score"] = (
        minmax(df["ADX"])                * WEIGHTS["adx"]      +
        minmax(df["ret3m"].fillna(0))    * WEIGHTS["ret3m"]    +
        minmax(df["sec_str"])            * WEIGHTS["sector"]   +
        minmax(df["vol_stab"])           * WEIGHTS["vol_stab"]
    )
    return df.sort_values("score", ascending=False)


# ═══════════════════════════════════════════════════════════════
# 6. 백테스트 루프
# ═══════════════════════════════════════════════════════════════
def run_backtest(all_data, sector_map, cfg, label,
                 etf_data=None, stop_pct=None):
    """
    stop_pct: None = 스톱로스 없음, -0.10 = -10% 트레일링 스톱
    """
    rebal_dates = pd.date_range(start=START, end=END, freq="BME")

    nav       = [1.0]
    holdings  = {}   # {ticker: (weight, entry_price, peak_price)}
    prev_dt   = None

    for rd in rebal_dates:
        # ── 월중 스톱로스 체크 (Step1) ──
        if stop_pct and prev_dt and holdings:
            monthly_days = pd.date_range(prev_dt, rd, freq="B")[1:]
            for day in monthly_days:
                if not holdings:
                    break
                to_remove = []
                for ticker, (w, entry_px, peak_px) in holdings.items():
                    df_t = all_data.get(ticker)
                    if df_t is None:
                        continue
                    day_data = df_t[df_t.index <= day]["Close"]
                    if len(day_data) == 0:
                        continue
                    cur_px = float(day_data.iloc[-1])
                    new_peak = max(peak_px, cur_px)
                    holdings[ticker] = (w, entry_px, new_peak)
                    # 트레일링 스톱: 고점 대비 stop_pct 하락
                    if cur_px <= new_peak * (1 + stop_pct):
                        to_remove.append(ticker)
                for ticker in to_remove:
                    del holdings[ticker]

        # ── 월 수익 반영 ──
        if prev_dt and holdings:
            monthly_ret = 0.0
            for ticker, (w, entry_px, peak_px) in holdings.items():
                df_t = all_data.get(ticker)
                if df_t is None:
                    continue
                p0 = df_t[df_t.index <= prev_dt]["Close"]
                p1 = df_t[df_t.index <= rd]["Close"]
                if len(p0) and len(p1) and float(p0.iloc[-1]) > 0:
                    monthly_ret += w * (float(p1.iloc[-1]) / float(p0.iloc[-1]) - 1)
            nav.append(nav[-1] * (1 + monthly_ret))
        elif prev_dt:
            nav.append(nav[-1])

        # ── 스크리닝 ──
        passed = {}
        for ticker, df_t in all_data.items():
            ok, metrics = screen(df_t, rd, cfg,
                                  sector_etf_data=etf_data)
            if ok:
                passed[ticker] = metrics

        # ── 랭킹 및 종목 선택 ──
        ranked = rank_stocks(passed, sector_map, cfg,
                             etf_data=etf_data, as_of=rd)
        top    = ranked.head(TOP_N)
        n      = len(top)

        # 새 홀딩 구성 (entry_price, peak_price 초기화)
        new_holdings = {}
        if n > 0:
            w_each = 1.0 / n
            for ticker in top.index:
                df_t = all_data.get(ticker)
                entry_px = float(df_t[df_t.index <= rd]["Close"].iloc[-1]) \
                    if df_t is not None else 1.0
                new_holdings[ticker] = (w_each, entry_px, entry_px)
        holdings = new_holdings
        prev_dt  = rd

    return nav


# ═══════════════════════════════════════════════════════════════
# 7. 성과 지표
# ═══════════════════════════════════════════════════════════════
def calc_metrics(nav_list, label):
    s   = pd.Series(nav_list, dtype=float)
    ret = s.pct_change().dropna()
    n   = len(ret)
    return {
        "label"   : label,
        "총수익률": s.iloc[-1] - 1,
        "CAGR"    : (s.iloc[-1] ** (12 / max(n, 1))) - 1,
        "MDD"     : ((s - s.cummax()) / s.cummax()).min(),
        "샤프"    : (ret.mean() / (ret.std() + 1e-9)) * np.sqrt(12),
        "월승률"  : (ret > 0).mean(),
        "nav"     : nav_list,
    }

def print_metrics(m):
    print(f"  {'─'*52}")
    print(f"  {m['label']}")
    print(f"  {'─'*52}")
    print(f"  총수익률  {m['총수익률']:>+8.1%}   "
          f"CAGR      {m['CAGR']:>+8.1%}")
    print(f"  MDD       {m['MDD']:>+8.1%}   "
          f"샤프지수  {m['샤프']:>8.2f}")
    print(f"  월간승률  {m['월승률']:>8.1%}")


# ═══════════════════════════════════════════════════════════════
# 8. 결과 차트
# ═══════════════════════════════════════════════════════════════
def plot_all(results, spy_nav):
    colors = ["#AAAAAA", "#2E75B6", "#70AD47", "#ED7D31", "#7030A0", "#C00000"]
    dates  = pd.date_range(start=START, end=END, freq="BME")
    dates  = [pd.Timestamp(START)] + list(dates)

    fig = plt.figure(figsize=(14, 10))
    gs  = gridspec.GridSpec(2, 1, height_ratios=[3, 1], hspace=0.35)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])

    fig.suptitle("단계별 알고리즘 개선 — 백테스트 비교 (2019–2024)",
                 fontsize=13, fontweight="bold")

    # NAV 곡선
    for i, (label, nav) in enumerate(results):
        n   = min(len(nav), len(dates))
        lw  = 2.2 if i > 0 else 1.4
        ls  = "-" if i > 0 else "--"
        ax1.plot(dates[:n], nav[:n], label=label,
                 color=colors[i % len(colors)], lw=lw, ls=ls)

    # SPY 벤치마크
    n = min(len(spy_nav), len(dates))
    ax1.plot(dates[:n], spy_nav[:n], label="S&P500 (SPY)",
             color="black", lw=1.2, ls=":", alpha=0.7)

    ax1.set_ylabel("누적 자산 (배)", fontsize=10)
    ax1.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _: f"{x:.1f}x"))
    ax1.legend(fontsize=8, loc="upper left")
    ax1.grid(alpha=0.25)

    # MDD 비교 막대
    labels = [r[0] for r in results]
    mdds   = [abs(calc_metrics(r[1], r[0])["MDD"]) * 100 for r in results]
    bar_colors = colors[:len(results)]
    bars = ax2.bar(labels, mdds, color=bar_colors, alpha=0.8, width=0.6)
    ax2.set_ylabel("최대 낙폭 MDD (%)", fontsize=10)
    ax2.set_title("단계별 MDD 비교", fontsize=10)
    for bar, val in zip(bars, mdds):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                 f"{val:.1f}%", ha="center", va="bottom", fontsize=8)
    ax2.grid(axis="y", alpha=0.25)
    plt.xticks(rotation=15, fontsize=8)

    plt.savefig(RESULTS_DIR / "backtest_steps_result.png", dpi=150, bbox_inches="tight")
    print("\n  차트 저장: backtest_steps_result.png")
    plt.show()


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true", help="상세 출력 활성화")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    logger.debug("=" * 60)
    logger.debug("  단계별 알고리즘 개선 백테스트")
    logger.debug(f"  기간: {START} ~ {END} | 리밸런싱: 매월 말")
    logger.debug("=" * 60)

    # ── 데이터 다운로드 ──────────────────────────────────────
    logger.debug("\n[데이터 다운로드]")
    all_tickers = list(ALL_UNIVERSE.keys())
    logger.debug(f"  종목 데이터 ({len(all_tickers)}개) 다운로드 중...")
    all_data = download_all(all_tickers, START, END)
    logger.debug(f"  → {len(all_data)}개 수신 완료")

    # 섹터 ETF 데이터 (Step4용)
    etf_tickers = list(set(SECTOR_ETF.values()))
    logger.debug(f"  섹터 ETF ({len(etf_tickers)}개) 다운로드 중...")
    etf_data = download_all(etf_tickers, START, END)
    logger.debug(f"  → {len(etf_data)}개 수신 완료")

    # SPY 벤치마크
    logger.debug("  SPY 벤치마크 다운로드 중...")
    spy_raw = yf.download("SPY", start=START, end=END,
                          auto_adjust=True, progress=False)
    spy_monthly = spy_raw["Close"].resample("BME").last().pct_change().fillna(0)
    spy_nav = [1.0] + list((1 + spy_monthly).cumprod().values)

    # 지표 계산
    logger.debug(f"\n  지표 계산 중 ({len(all_data)}개)...")
    for t in list(all_data.keys()):
        all_data[t] = add_indicators(all_data[t])
    for t in list(etf_data.keys()):
        etf_data[t] = add_indicators(etf_data[t])
    logger.debug("  완료")

    results = []

    # ── 베이스라인 ───────────────────────────────────────────
    logger.debug("\n" + "═"*60)
    logger.debug("  [베이스라인] 원본 알고리즘")
    logger.debug("═"*60)
    cfg_base = dict(rsi_max=70, swing_hh_hl=False,
                    use_etf_sector=False, use_52w_filter=False)
    nav_base = run_backtest(all_data, ALL_UNIVERSE, cfg_base,
                             "베이스라인", stop_pct=None)
    m_base = calc_metrics(nav_base, "베이스라인 (원본)")
    print_metrics(m_base)
    results.append(("베이스라인", nav_base))

    # ── Step 1: 스톱로스 ─────────────────────────────────────
    logger.debug("\n" + "═"*60)
    logger.debug("  [Step 1] 트레일링 스톱로스 추가 (-10%)")
    logger.debug("═"*60)
    nav_s1 = run_backtest(all_data, ALL_UNIVERSE, cfg_base,
                          "Step1", stop_pct=-0.10)
    m_s1 = calc_metrics(nav_s1, "Step1: 스톱로스 (-10%)")
    print_metrics(m_s1)
    d_cagr = m_s1["CAGR"] - m_base["CAGR"]
    d_mdd  = m_s1["MDD"]  - m_base["MDD"]
    print(f"\n  베이스 대비 → CAGR {d_cagr:+.1%}  MDD {d_mdd:+.1%}")
    results.append(("Step1: 스톱로스", nav_s1))

    # ── Step 2: RSI 상한 조정 ─────────────────────────────────
    logger.debug("\n" + "═"*60)
    logger.debug("  [Step 2] RSI 상한 70 → 75 (+ Step1 포함)")
    logger.debug("═"*60)
    cfg_s2 = dict(rsi_max=75, swing_hh_hl=False,
                  use_etf_sector=False, use_52w_filter=False)
    nav_s2 = run_backtest(all_data, ALL_UNIVERSE, cfg_s2,
                          "Step2", stop_pct=-0.10)
    m_s2 = calc_metrics(nav_s2, "Step2: RSI 상한 75")
    print_metrics(m_s2)
    d_cagr = m_s2["CAGR"] - m_s1["CAGR"]
    d_mdd  = m_s2["MDD"]  - m_s1["MDD"]
    print(f"\n  Step1 대비 → CAGR {d_cagr:+.1%}  MDD {d_mdd:+.1%}")
    results.append(("Step2: RSI 75", nav_s2))

    # ── Step 3: HH-HL 스윙 포인트 ────────────────────────────
    logger.debug("\n" + "═"*60)
    logger.debug("  [Step 3] HH-HL 일봉 → 스윙 포인트 기준 (+ Step1,2 포함)")
    logger.debug("═"*60)
    cfg_s3 = dict(rsi_max=75, swing_hh_hl=True,
                  use_etf_sector=False, use_52w_filter=False)
    nav_s3 = run_backtest(all_data, ALL_UNIVERSE, cfg_s3,
                          "Step3", stop_pct=-0.10)
    m_s3 = calc_metrics(nav_s3, "Step3: HH-HL 스윙 기준")
    print_metrics(m_s3)
    d_cagr = m_s3["CAGR"] - m_s2["CAGR"]
    d_mdd  = m_s3["MDD"]  - m_s2["MDD"]
    print(f"\n  Step2 대비 → CAGR {d_cagr:+.1%}  MDD {d_mdd:+.1%}")
    results.append(("Step3: HH-HL 스윙", nav_s3))

    # ── Step 4: 섹터 ETF 기준 ────────────────────────────────
    logger.debug("\n" + "═"*60)
    logger.debug("  [Step 4] 섹터 강도 → ETF 초과수익률 기준 (+ Step1,2,3 포함)")
    logger.debug("═"*60)
    cfg_s4 = dict(rsi_max=75, swing_hh_hl=True,
                  use_etf_sector=True, use_52w_filter=False)
    nav_s4 = run_backtest(all_data, ALL_UNIVERSE, cfg_s4,
                          "Step4", etf_data=etf_data, stop_pct=-0.10)
    m_s4 = calc_metrics(nav_s4, "Step4: 섹터 ETF 기준")
    print_metrics(m_s4)
    d_cagr = m_s4["CAGR"] - m_s3["CAGR"]
    d_mdd  = m_s4["MDD"]  - m_s3["MDD"]
    print(f"\n  Step3 대비 → CAGR {d_cagr:+.1%}  MDD {d_mdd:+.1%}")
    results.append(("Step4: 섹터 ETF", nav_s4))

    # ── Step 5: 52주 신고가 필터 ──────────────────────────────
    logger.debug("\n" + "═"*60)
    logger.debug("  [Step 5] 52주 신고가 20% 이내 필터 (전체 누적)")
    logger.debug("═"*60)
    cfg_s5 = dict(rsi_max=75, swing_hh_hl=True,
                  use_etf_sector=True, use_52w_filter=True)
    nav_s5 = run_backtest(all_data, ALL_UNIVERSE, cfg_s5,
                          "Step5", etf_data=etf_data, stop_pct=-0.10)
    m_s5 = calc_metrics(nav_s5, "Step5: 52주 신고가 필터")
    print_metrics(m_s5)
    d_cagr = m_s5["CAGR"] - m_s4["CAGR"]
    d_mdd  = m_s5["MDD"]  - m_s4["MDD"]
    print(f"\n  Step4 대비 → CAGR {d_cagr:+.1%}  MDD {d_mdd:+.1%}")
    results.append(("Step5: 최종", nav_s5))

    # ── 종합 비교표 ──────────────────────────────────────────
    print("\n" + "═"*60)
    print("  종합 비교")
    print("═"*60)
    all_metrics = [m_base, m_s1, m_s2, m_s3, m_s4, m_s5]
    spy_m = calc_metrics(spy_nav, "S&P500 (SPY)")
    all_metrics.append(spy_m)

    header = f"  {'전략':<22} {'총수익률':>8} {'CAGR':>8} {'MDD':>8} {'샤프':>7} {'월승률':>7}"
    print(header)
    print("  " + "─" * 62)
    for m in all_metrics:
        mark = " ◀ 최종" if "Step5" in m["label"] else ""
        print(
            f"  {m['label']:<22} "
            f"{m['총수익률']:>+8.1%} "
            f"{m['CAGR']:>+8.1%} "
            f"{m['MDD']:>+8.1%} "
            f"{m['샤프']:>7.2f} "
            f"{m['월승률']:>7.1%}"
            f"{mark}"
        )

    # ── 결과 저장 ────────────────────────────────────────────
    rows = []
    for m in all_metrics:
        rows.append({
            "전략"    : m["label"],
            "총수익률": f"{m['총수익률']:+.1%}",
            "CAGR"    : f"{m['CAGR']:+.1%}",
            "MDD"     : f"{m['MDD']:+.1%}",
            "샤프지수": f"{m['샤프']:.2f}",
            "월간승률": f"{m['월승률']:.1%}",
        })
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "step_comparison.csv",
                               index=False, encoding="utf-8-sig")
    print("\n  비교 결과 저장: step_comparison.csv")

    # ── 차트 출력 ────────────────────────────────────────────
    plot_all(results, spy_nav)
