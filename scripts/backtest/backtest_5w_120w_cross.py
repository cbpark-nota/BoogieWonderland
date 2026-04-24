"""
5W/120W 이평선 골든크로스 전략 백테스트
══════════════════════════════════════════════════════════════
매수: 5주(25일) 이평선이 120주(600일) 이평선을 상향 돌파한 종목을 후보로 선정.
     격주 금요일 리밸런싱 시 MA gap ratio 상위 Top 25 유지.

매도:
  1. 트레일링 ATR 스톱 (매일 체크, 즉시 청산)
     peak = max(누적 peak, 오늘 High)
     stop = max(기존 stop, peak - ATR(14) × 2.5)  ← 스톱만 상향
     Close ≤ stop → 즉시 청산

  2. Top 25 이탈 (격주 금요일 리밸런싱)
     스코어 기준: MA gap ratio = (MA25 - MA600) / MA600
       → 5주 이평이 120주 이평 위에 얼마나 떠 있는지 = 골든크로스 이후 추세 강도
     Top 25 밖 종목은 리밸런싱 시 청산

포지션: 동일 비중 (1/TOP_N), 수수료 편도 0.1%
유니버스: US (S&P 500 + NASDAQ 100) + KR (KOSPI 200 + KOSDAQ 150)
기간    : 2015-01-01 ~ 최신 캐시 데이터
══════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import logging
import sys
import json
import numpy as np
import pandas as pd
import pandas_ta as ta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent))

from data_cache import CACHE_DIR

RESULTS_DIR = _THIS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── 전략 파라미터 ──────────────────────────────────────────────
MA_SHORT   = 25     # 5주 × 5거래일
MA_LONG    = 600    # 120주 × 5거래일
ATR_PERIOD = 14
ATR_MULT   = 2.5    # v3.3 동일
TOP_N      = 25
COMMISSION = 0.001  # 편도 0.1%

START      = "2015-01-01"
END        = datetime.today().strftime("%Y-%m-%d")
REBAL_FREQ = "2W-FRI"  # 격주 금요일
PERIODS_PY = 26         # 연간 격주 기간 수


# ══════════════════════════════════════════════════════════════
# 데이터 로드 (날짜 체크 없이 기존 캐시 직접 로드)
# ══════════════════════════════════════════════════════════════

def load_cache_direct() -> tuple:
    """기존 캐시에서 날짜 체크 없이 데이터 로드.
    worktree 환경에서는 main 레포 캐시 경로도 탐색."""
    # worktree → main repo 경로 탐색
    candidate_dirs = [
        CACHE_DIR,
        _THIS_DIR.parents[4] / "data" / "full_universe",  # _s_test 메인 레포 (worktree 상위)
    ]
    actual_dir = next((d for d in candidate_dirs if (d / "manifest.json").exists()), None)
    if actual_dir is None:
        raise FileNotFoundError(f"캐시 manifest 없음 (탐색: {candidate_dirs})")
    manifest_path = actual_dir / "manifest.json"

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    all_data = {}
    for ticker, fname in manifest.get("stocks", {}).items():
        path = actual_dir / fname
        if path.exists():
            try:
                all_data[ticker] = pd.read_parquet(path)
            except Exception:
                pass

    spy_path = actual_dir / "spy.parquet"
    spy_df = pd.read_parquet(spy_path) if spy_path.exists() else pd.DataFrame()

    universe_map = manifest.get("universe_map", {})
    cached_date  = manifest.get("downloaded_at", "N/A")
    return all_data, spy_df, universe_map, cached_date


# ══════════════════════════════════════════════════════════════
# 지표 계산
# ══════════════════════════════════════════════════════════════

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c = d["Close"].squeeze()
    h = d["High"].squeeze()
    l = d["Low"].squeeze()

    d["MA_S"] = c.rolling(MA_SHORT, min_periods=MA_SHORT).mean()
    d["MA_L"] = c.rolling(MA_LONG,  min_periods=MA_LONG).mean()

    atr = ta.atr(h, l, c, length=ATR_PERIOD)
    d["ATR"] = atr if atr is not None else np.nan

    return d


def is_kr(ticker: str) -> bool:
    return ticker.endswith(".KS") or ticker.endswith(".KQ")


# ══════════════════════════════════════════════════════════════
# 백테스트 엔진
# ══════════════════════════════════════════════════════════════

def run_backtest(all_data: dict) -> tuple:
    """
    Parameters
    ----------
    all_data : dict[ticker, DataFrame with MA_S, MA_L, ATR columns]

    Returns
    -------
    nav       : list[float]  — 격주 NAV (시작 1.0, 길이 = rebal 기간 수 + 1)
    trades    : list[dict]   — 완결 거래 목록 (ATR_STOP / TOP_N_EXIT)
    rebal_dts : DatetimeIndex
    """
    rebal_dts = pd.date_range(start=START, end=END, freq=REBAL_FREQ)

    nav      = [1.0]
    holdings = {}  # {ticker: {w, entry_price, peak, stop, entry_date}}
    trades   = []
    prev_dt  = None

    for rd in rebal_dts:

        # ── [A] 구간 내 일별 ATR 스톱 체크 ───────────────────
        if prev_dt and holdings:
            check_range = pd.bdate_range(
                prev_dt + pd.Timedelta(days=1),
                rd - pd.Timedelta(days=1),
            )
            for day in check_range:
                to_stop = []
                for ticker, pos in list(holdings.items()):
                    df_t = all_data.get(ticker)
                    if df_t is None or day not in df_t.index:
                        continue
                    row   = df_t.loc[day]
                    price = float(row["Close"])
                    high  = float(row["High"])
                    atr_v = float(row["ATR"]) if not pd.isna(row["ATR"]) else None

                    # peak 갱신 (누적 최고가)
                    new_peak = max(pos["peak"], high)
                    pos["peak"] = new_peak

                    # 스톱 갱신 (상향만)
                    if atr_v and atr_v > 0:
                        cand_stop = new_peak - atr_v * ATR_MULT
                        pos["stop"] = max(pos["stop"], cand_stop)

                    if price <= pos["stop"]:
                        to_stop.append((ticker, price, day))

                for ticker, sell_px, sell_dt in to_stop:
                    pos = holdings.pop(ticker)
                    pnl = sell_px / pos["entry_price"] - 1
                    trades.append({
                        "exit_date":   sell_dt,
                        "ticker":      ticker,
                        "entry_date":  pos["entry_date"],
                        "entry_price": pos["entry_price"],
                        "exit_price":  sell_px,
                        "pnl_pct":     round(pnl * 100, 4),
                        "hold_days":   (sell_dt - pos["entry_date"]).days,
                        "reason":      "ATR_STOP",
                    })

        # ── [B] 구간 수익 계산 (prev_dt → rd) ────────────────
        if prev_dt:
            period_ret = 0.0
            for ticker, pos in holdings.items():
                df_t = all_data.get(ticker)
                if df_t is None:
                    continue
                p0s = df_t[df_t.index <= prev_dt]["Close"]
                p1s = df_t[df_t.index <= rd]["Close"]
                if len(p0s) and len(p1s):
                    p0 = float(p0s.iloc[-1])
                    p1 = float(p1s.iloc[-1])
                    if p0 > 0:
                        period_ret += pos["w"] * (p1 / p0 - 1)
            nav.append(nav[-1] * (1 + period_ret))

        # ── [C] Top N 후보 선정 (MA_S > MA_L 중 gap ratio 상위) ──
        cands = {}
        for ticker, df_t in all_data.items():
            hist = df_t[df_t.index <= rd]
            if len(hist) < MA_LONG + ATR_PERIOD + 5:
                continue
            row  = hist.iloc[-1]
            ma_s = row.get("MA_S", np.nan)
            ma_l = row.get("MA_L", np.nan)
            if pd.isna(ma_s) or pd.isna(ma_l) or ma_l <= 0:
                continue
            if ma_s <= ma_l:
                continue  # 골든크로스 상태 아님

            gap   = (ma_s - ma_l) / ma_l
            atr_v = float(row["ATR"]) if not pd.isna(row["ATR"]) else None
            cands[ticker] = {
                "gap":   gap,
                "price": float(row["Close"]),
                "high":  float(row["High"]),
                "atr":   atr_v,
            }

        ranked      = sorted(cands.items(), key=lambda x: x[1]["gap"], reverse=True)
        top_tickers = {t for t, _ in ranked[:TOP_N]}

        # ── [D] Top N 이탈 종목 청산 ─────────────────────────
        to_exit = set(holdings.keys()) - top_tickers
        for ticker in to_exit:
            pos  = holdings.pop(ticker)
            df_t = all_data.get(ticker)
            sell_px = float(df_t[df_t.index <= rd]["Close"].iloc[-1]) \
                      if df_t is not None else pos["entry_price"]
            pnl = sell_px / pos["entry_price"] - 1
            trades.append({
                "exit_date":   rd,
                "ticker":      ticker,
                "entry_date":  pos["entry_date"],
                "entry_price": pos["entry_price"],
                "exit_price":  sell_px,
                "pnl_pct":     round(pnl * 100, 4),
                "hold_days":   (rd - pos["entry_date"]).days,
                "reason":      "TOP_N_EXIT",
            })

        # ── [E] 수수료 계산 (턴오버 기반) ────────────────────
        if prev_dt and top_tickers:
            n_new    = len(top_tickers)
            eq_w     = 1.0 / n_new
            old_ws   = {t: pos["w"] for t, pos in holdings.items()}
            sold_w   = sum(old_ws.get(t, 0) for t in set(old_ws) - top_tickers)
            bought_w = sum(eq_w for t in top_tickers - set(old_ws))
            rebal_w  = sum(
                abs(eq_w - old_ws.get(t, 0))
                for t in top_tickers & set(old_ws)
            )
            nav[-1] *= (1 - (sold_w + bought_w + rebal_w) * COMMISSION)

        # ── [F] 포지션 재구성 ─────────────────────────────────
        eq_w = 1.0 / len(top_tickers) if top_tickers else 0.0
        new_holdings = {}
        for ticker in top_tickers:
            info = cands[ticker]
            if ticker in holdings:
                pos = holdings[ticker]
                new_holdings[ticker] = {
                    "w":           eq_w,
                    "entry_price": pos["entry_price"],
                    "peak":        max(pos["peak"], info["high"]),
                    "stop":        pos["stop"],
                    "entry_date":  pos["entry_date"],
                }
            else:
                entry_px = info["price"]
                atr_v    = info["atr"]
                peak     = info["high"]
                stop     = (peak - atr_v * ATR_MULT) if atr_v and atr_v > 0 else entry_px * 0.85
                new_holdings[ticker] = {
                    "w":           eq_w,
                    "entry_price": entry_px,
                    "peak":        peak,
                    "stop":        stop,
                    "entry_date":  rd,
                }

        holdings = new_holdings
        prev_dt  = rd

    return nav, trades, rebal_dts


# ══════════════════════════════════════════════════════════════
# 성과 지표
# ══════════════════════════════════════════════════════════════

def calc_metrics(nav: list) -> dict:
    s      = pd.Series(nav, dtype=float)
    ret    = s.pct_change().dropna()
    n      = len(ret)
    years  = n / PERIODS_PY
    cagr   = (s.iloc[-1] ** (1 / max(years, 0.1))) - 1 if s.iloc[-1] > 0 else -1.0
    mdd    = ((s - s.cummax()) / s.cummax()).min()
    sharpe = (ret.mean() / (ret.std() + 1e-9)) * np.sqrt(PERIODS_PY)
    wr     = (ret > 0).mean()
    return {
        "총수익률": s.iloc[-1] - 1,
        "CAGR":    cagr,
        "MDD":     mdd,
        "샤프":    sharpe,
        "기간승률": wr,
        "기간(년)": round(years, 2),
        "기간수":   n,
    }


def calc_trade_stats(trades: list) -> dict:
    if not trades:
        return {"총거래": 0, "승률": 0.0, "평균수익(%)": 0.0, "평균보유(일)": 0.0}
    n   = len(trades)
    win = sum(1 for t in trades if t["pnl_pct"] > 0)
    return {
        "총거래":      n,
        "승률":        win / n,
        "평균수익(%)":  sum(t["pnl_pct"] for t in trades) / n,
        "평균보유(일)": sum(t["hold_days"] for t in trades) / n,
    }


def spy_biweekly_nav(spy_df: pd.DataFrame) -> list:
    c   = spy_df["Close"].squeeze()
    c   = c[c.index >= START]
    biw = c.resample(REBAL_FREQ).last().pct_change().fillna(0)
    return [1.0] + list((1 + biw).cumprod().values.flatten())


# ══════════════════════════════════════════════════════════════
# 차트 저장
# ══════════════════════════════════════════════════════════════

def plot_results(results: list, spy_nav: list, rebal_dts):
    """
    results: [(label, nav_list), ...]
    """
    colors = ["#2E75B6", "#ED7D31", "#70AD47", "#A020F0"]
    dates  = [pd.Timestamp(START)] + list(rebal_dts)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle(
        f"5W/120W 골든크로스 전략  (ATR×{ATR_MULT} 트레일링 스톱, Top {TOP_N}, 격주 리밸런싱)\n"
        f"수수료 {COMMISSION*100:.1f}%  {START}~{END[:7]}",
        fontsize=12, fontweight="bold",
    )

    ax1 = axes[0]
    for i, (label, nav) in enumerate(results):
        n = min(len(nav), len(dates))
        ax1.plot(dates[:n], nav[:n], label=label, color=colors[i % len(colors)], lw=2.0)
    n_spy = min(len(spy_nav), len(dates))
    ax1.plot(dates[:n_spy], spy_nav[:n_spy], label="SPY B&H",
             color="gray", lw=1.2, ls="--", alpha=0.7)
    ax1.set_ylabel("누적 자산 (배)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.1f}x"))
    ax1.set_title("누적 NAV 곡선")
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.25)

    ax2 = axes[1]
    labels_bar = [r[0] for r in results]
    metrics    = [calc_metrics(r[1]) for r in results]
    cagrs  = [m["CAGR"] * 100 for m in metrics]
    mdds   = [abs(m["MDD"]) * 100 for m in metrics]
    sharps = [m["샤프"] for m in metrics]

    x = np.arange(len(labels_bar))
    w = 0.25
    ax2.bar(x - w, cagrs,  width=w, label="CAGR(%)",  color="#2E75B6", alpha=0.8)
    ax2.bar(x,     mdds,   width=w, label="|MDD|(%)", color="#FF4444", alpha=0.8)
    ax2.bar(x + w, sharps, width=w, label="샤프",     color="#70AD47", alpha=0.8)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels_bar, rotation=15, fontsize=9)
    ax2.set_title("CAGR / MDD / 샤프 비교")
    ax2.legend(fontsize=9)
    ax2.grid(axis="y", alpha=0.25)

    path = RESULTS_DIR / "backtest_5w_120w_cross.png"
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  차트 저장: {path}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    print("=" * 70)
    print("  5W/120W 골든크로스 전략 백테스트")
    print(f"  기간       : {START} ~ (캐시 최신)")
    print(f"  리밸런싱   : 격주 금요일 ({REBAL_FREQ})")
    print(f"  매수신호   : MA{MA_SHORT} > MA{MA_LONG} (5주/120주 이평 골든크로스)")
    print(f"  스코어기준 : MA gap ratio = (MA{MA_SHORT} - MA{MA_LONG}) / MA{MA_LONG}")
    print(f"  ATR 스톱   : peak - ATR({ATR_PERIOD}) × {ATR_MULT}  (매일 체크)")
    print(f"  Top N      : {TOP_N}")
    print(f"  수수료     : 편도 {COMMISSION*100:.1f}%")
    print("=" * 70)

    # ── [1] 데이터 로드 ──────────────────────────────────────
    print("\n[1] 캐시 데이터 로드 중...")
    all_data_raw, spy_df, universe_map, cached_date = load_cache_direct()
    print(f"  캐시 날짜: {cached_date}, 종목 수: {len(all_data_raw)}")

    us_raw = {t: df for t, df in all_data_raw.items() if not is_kr(t)}
    kr_raw = {t: df for t, df in all_data_raw.items() if is_kr(t)}
    print(f"  US: {len(us_raw)}종목, KR: {len(kr_raw)}종목")

    # ── [2] 지표 계산 ─────────────────────────────────────────
    print(f"\n[2] 지표 계산 (MA{MA_SHORT}, MA{MA_LONG}, ATR{ATR_PERIOD})...")
    us_data  = {t: add_indicators(df) for t, df in us_raw.items()}
    kr_data  = {t: add_indicators(df) for t, df in kr_raw.items()}
    all_data = {**us_data, **kr_data}
    print(f"  완료: US {len(us_data)} + KR {len(kr_data)} = {len(all_data)}종목")

    # SPY NAV
    spy_nav = spy_biweekly_nav(spy_df)
    spy_met = calc_metrics(spy_nav)

    # ── [3] 백테스트 실행 ─────────────────────────────────────
    print("\n[3] 백테스트 실행 중...")

    print("  [3-1] US 유니버스...")
    nav_us, trades_us, rebal_dts = run_backtest(us_data)
    met_us = calc_metrics(nav_us)
    ts_us  = calc_trade_stats(trades_us)
    print(f"    완료 → CAGR {met_us['CAGR']:+.1%}, MDD {met_us['MDD']:.1%}, 샤프 {met_us['샤프']:.2f}")

    print("  [3-2] KR 유니버스...")
    nav_kr, trades_kr, _ = run_backtest(kr_data)
    met_kr = calc_metrics(nav_kr)
    ts_kr  = calc_trade_stats(trades_kr)
    print(f"    완료 → CAGR {met_kr['CAGR']:+.1%}, MDD {met_kr['MDD']:.1%}, 샤프 {met_kr['샤프']:.2f}")

    print("  [3-3] 통합 유니버스 (US + KR)...")
    nav_all, trades_all, _ = run_backtest(all_data)
    met_all = calc_metrics(nav_all)
    ts_all  = calc_trade_stats(trades_all)
    print(f"    완료 → CAGR {met_all['CAGR']:+.1%}, MDD {met_all['MDD']:.1%}, 샤프 {met_all['샤프']:.2f}")

    # ── [4] 종합 결과 출력 ────────────────────────────────────
    print("\n" + "═" * 70)
    print("  성과 비교 (격주 기간 기준)")
    print("═" * 70)
    print(f"  {'전략':<18} {'CAGR':>8} {'MDD':>8} {'샤프':>7} {'기간승률':>8} {'총수익률':>9}")
    print("  " + "─" * 60)

    rows = [
        ("5W/120W [통합]",   met_all, nav_all),
        ("5W/120W [US]",     met_us,  nav_us),
        ("5W/120W [KR]",     met_kr,  nav_kr),
        ("SPY Buy&Hold",      spy_met, spy_nav),
    ]
    for label, m, _ in rows:
        print(f"  {label:<18} {m['CAGR']:>+8.1%} {m['MDD']:>+8.1%} "
              f"{m['샤프']:>7.2f} {m['기간승률']:>8.1%} {m['총수익률']:>+9.1%}")

    print("\n  [거래 통계]")
    print(f"  {'전략':<18} {'총거래':>7} {'승률':>7} {'평균수익(%)':>11} {'평균보유(일)':>12}")
    print("  " + "─" * 60)
    for label, ts in [("통합", ts_all), ("US", ts_us), ("KR", ts_kr)]:
        print(f"  {label:<18} {ts['총거래']:>7} {ts['승률']:>7.1%} "
              f"{ts['평균수익(%)']:>11.2f} {ts['평균보유(일)']:>12.1f}")

    print(f"\n  기간: {met_all['기간(년)']}년 ({met_all['기간수']} 격주 기간)")

    # ── [5] 거래 내역 CSV 저장 ────────────────────────────────
    for label, tlist in [("us", trades_us), ("kr", trades_kr), ("all", trades_all)]:
        if tlist:
            pd.DataFrame(tlist).to_csv(
                RESULTS_DIR / f"5w120w_trades_{label}.csv",
                index=False, encoding="utf-8-sig",
            )

    # NAV CSV (통합) — nav 길이는 len(rebal_dts) (초기 1.0 + N-1 기간)
    n_nav = min(len(nav_all), len(nav_us), len(nav_kr))
    all_dates = [START] + [str(d.date()) for d in rebal_dts]
    nav_df = pd.DataFrame({
        "date":    all_dates[:n_nav],
        "nav_all": nav_all[:n_nav],
        "nav_us":  nav_us[:n_nav],
        "nav_kr":  nav_kr[:n_nav],
    })
    nav_csv = RESULTS_DIR / "5w120w_nav.csv"
    nav_df.to_csv(nav_csv, index=False, encoding="utf-8-sig")
    print(f"\n  NAV CSV: {nav_csv}")

    # ── [6] 차트 ─────────────────────────────────────────────
    plot_results(
        [("통합(US+KR)", nav_all), ("US", nav_us), ("KR", nav_kr)],
        spy_nav,
        rebal_dts,
    )

    print("\n" + "=" * 70)
    print("  백테스트 완료")
    print("=" * 70)
