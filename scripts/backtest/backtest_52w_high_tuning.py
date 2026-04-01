"""
52주 신고가 돌파 전략 — 파라미터 튜닝 (시나리오 A~G 비교)
══════════════════════════════════════════════════════════════

시나리오:
  A (베이스라인): HIGH_52W_THRESHOLD=0.98, VOLUME_SPIKE=1.5, ATR_MULT=2.0, MAX_HOLD=40
  B (첫 돌파만): 최근 20일 내 신고가 기록 종목 제외
  C (스톱 넓히기): ATR_MULT=3.0, MAX_HOLD=60
  D (거래량 강화 + 눌림목): VOLUME_SPIKE=2.0, 돌파 후 3일 내 52주 고점 -2% 이내 진입
  E (B+C): 첫 돌파 + 넓은 스톱
  F (B+D): 첫 돌파 + 눌림목
  G (전부 조합): B+C+D

결과: CAGR 최고이면서 MDD <= SPY(-33.7%) 인 최적 조합 선별
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
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent))
from data_cache import load_full_universe

RESULTS_DIR = _THIS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

START = "2015-01-01"
END   = datetime.today().strftime("%Y-%m-%d")
TRADING_DAYS_PER_YEAR = 252

SPY_MDD_BENCHMARK = -0.337   # SPY MDD 기준 (-33.7%)


# ══════════════════════════════════════════════════════════════
# 시나리오 정의
# ══════════════════════════════════════════════════════════════

@dataclass
class ScenarioConfig:
    name: str
    label: str
    # 기본 파라미터
    high_52w_threshold: float = 0.98
    volume_spike: float       = 1.5
    atr_mult: float           = 2.0
    max_hold_days: int        = 40
    # 시나리오 플래그
    first_breakout_only: bool = False   # B: 최근 20일 내 신고가 이미 있는 종목 제외
    pullback_entry: bool      = False   # D: 돌파 후 3일 내 눌림목 진입
    # 공통 고정값
    max_positions: int  = 10
    commission: float   = 0.002
    surge_exclude: float = 0.10
    adx_min: float      = 20
    rsi_max: float      = 80
    # 첫 돌파 확인 윈도우
    first_breakout_lookback: int = 20
    # 눌림목 진입 파라미터
    pullback_window: int   = 3     # 돌파 후 며칠 이내
    pullback_pct: float    = 0.02  # 52주 고점 -2% 이내


SCENARIOS = [
    ScenarioConfig("A", "베이스라인"),
    ScenarioConfig("B", "첫 돌파만",      first_breakout_only=True),
    ScenarioConfig("C", "스톱 넓히기",    atr_mult=3.0, max_hold_days=60),
    ScenarioConfig("D", "눌림목 진입",    volume_spike=2.0, pullback_entry=True),
    ScenarioConfig("E", "B+C (첫돌파+넓은스톱)",
                   first_breakout_only=True, atr_mult=3.0, max_hold_days=60),
    ScenarioConfig("F", "B+D (첫돌파+눌림목)",
                   first_breakout_only=True, volume_spike=2.0, pullback_entry=True),
    ScenarioConfig("G", "전부 조합 (B+C+D)",
                   first_breakout_only=True, volume_spike=2.0, pullback_entry=True,
                   atr_mult=3.0, max_hold_days=60),
]


# ══════════════════════════════════════════════════════════════
# 지표 계산
# ══════════════════════════════════════════════════════════════

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """52주 신고가 전략에 필요한 지표 추가."""
    df = df.copy()
    close  = df["Close"].squeeze()
    high   = df["High"].squeeze()
    low    = df["Low"].squeeze()
    volume = df["Volume"].squeeze()

    # ADX
    adx_res = ta.adx(high, low, close, length=14)
    if adx_res is not None and not adx_res.empty:
        col = [c for c in adx_res.columns if c.startswith("ADX_")]
        df["ADX"] = adx_res[col[0]].values if col else np.nan
    else:
        df["ADX"] = np.nan

    # RSI
    rsi_res = ta.rsi(close, length=14)
    df["RSI"] = rsi_res.values if rsi_res is not None else np.nan

    # ATR
    atr_res = ta.atr(high, low, close, length=14)
    df["ATR"] = atr_res.values if atr_res is not None else np.nan

    # 52주 고점
    df["High52W"] = high.rolling(252, min_periods=50).max()

    # 20일 평균 거래량
    df["VolMA20"] = volume.rolling(20, min_periods=10).mean()

    # 5일 수익률
    df["Ret5D"] = close.pct_change(5)

    # 52주 신고가 터치 플래그 (1 = 터치, 0 = 아님)
    # High52W * 0.98 이상이면 터치로 간주 (베이스 0.98 기준)
    df["Is52WHigh"] = (close >= df["High52W"] * 0.98).astype(int)

    return df


# ══════════════════════════════════════════════════════════════
# 진입 신호 판단
# ══════════════════════════════════════════════════════════════

def is_base_entry_signal(row: pd.Series, cfg: ScenarioConfig) -> bool:
    """기본 진입 조건 체크 (눌림목 여부 미포함)."""
    try:
        if pd.isna(row["High52W"]) or row["High52W"] <= 0:
            return False
        if row["Close"] < row["High52W"] * cfg.high_52w_threshold:
            return False
        if pd.isna(row["VolMA20"]) or row["VolMA20"] <= 0:
            return False
        if row["Volume"] < row["VolMA20"] * cfg.volume_spike:
            return False
        if not pd.isna(row["Ret5D"]) and row["Ret5D"] >= cfg.surge_exclude:
            return False
        if pd.isna(row["ADX"]) or row["ADX"] < cfg.adx_min:
            return False
        if pd.isna(row["RSI"]) or row["RSI"] > cfg.rsi_max:
            return False
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════
# 백테스트 엔진
# ══════════════════════════════════════════════════════════════

def run_backtest(all_data: dict, cfg: ScenarioConfig) -> tuple[list, list, list]:
    """
    시나리오 설정에 따라 52주 신고가 전략 백테스트 실행.
    """
    all_dates = sorted(set().union(*[set(df.index) for df in all_data.values()]))
    all_dates = pd.DatetimeIndex(all_dates)
    all_dates = all_dates[all_dates >= START]

    cash = 1.0
    positions: dict[str, dict] = {}
    nav_list   = [1.0]
    trade_log  = []

    # 눌림목 진입용: 종목별 마지막 돌파일 기록
    # {ticker: last_breakout_date}
    last_breakout: dict[str, pd.Timestamp] = {}

    for today in all_dates:
        # ── [A] 청산 체크 ─────────────────────────────────────
        to_sell = []
        for ticker, pos in positions.items():
            df = all_data.get(ticker)
            if df is None or today not in df.index:
                pos["hold_days"] += 1
                if pos["hold_days"] >= cfg.max_hold_days:
                    to_sell.append((ticker, "기간청산", pos["entry_price"]))
                continue

            row = df.loc[today]
            price = float(row["Close"])
            if pd.isna(price) or price <= 0:
                continue

            # 트레일링 스톱 갱신
            if price > pos.get("peak", pos["entry_price"]):
                pos["peak"] = price
                if not pd.isna(row["ATR"]) and row["ATR"] > 0:
                    pos["stop"] = price - row["ATR"] * cfg.atr_mult

            pos["hold_days"] += 1

            if price <= pos["stop"]:
                to_sell.append((ticker, "스톱청산", price))
            elif pos["hold_days"] >= cfg.max_hold_days:
                to_sell.append((ticker, "기간청산", price))

        for ticker, reason, sell_price in to_sell:
            pos = positions.pop(ticker)
            proceeds = pos["shares"] * sell_price * (1 - cfg.commission)
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

        # ── [B] 신규 진입 후보 스캔 ───────────────────────────
        slots_available = cfg.max_positions - len(positions)
        if slots_available > 0:
            candidates = []
            existing_tickers = set(positions.keys())

            for ticker, df in all_data.items():
                if ticker in existing_tickers:
                    continue
                if today not in df.index:
                    continue

                row = df.loc[today]

                # ── 눌림목 진입 모드 ──────────────────────────
                if cfg.pullback_entry:
                    close = float(row["Close"])
                    high52w = float(row["High52W"]) if not pd.isna(row["High52W"]) else 0.0
                    vol    = float(row["Volume"])
                    volma  = float(row["VolMA20"]) if not pd.isna(row["VolMA20"]) else 0.0

                    # 오늘 돌파 신호 발생 여부 (거래량 동반 돌파)
                    is_breakout_today = (
                        high52w > 0
                        and close >= high52w * cfg.high_52w_threshold
                        and volma > 0
                        and vol >= volma * cfg.volume_spike
                    )
                    if is_breakout_today:
                        last_breakout[ticker] = today

                    # 진입 조건: 최근 breakout 발생 후 N일 이내 + 가격 조건
                    lb = last_breakout.get(ticker)
                    if lb is None:
                        continue

                    days_since = (today - lb).days
                    # 영업일 기준이 아닌 달력일 기준으로 체크 (간단히 5일 이내)
                    if days_since > cfg.pullback_window * 2 or days_since < 1:
                        # 오늘 돌파 당일(0)은 건너뜀 (눌림목 대기), 너무 오래된 것도 제외
                        if days_since != 0:
                            continue
                        else:
                            continue

                    # 현재가가 52주 고점 -pullback_pct 이내
                    if high52w <= 0 or close < high52w * (1 - cfg.pullback_pct):
                        continue

                    # 나머지 기본 필터 (거래량 조건은 돌파일에 이미 체크했으므로 여기선 제외)
                    if pd.isna(row["ADX"]) or float(row["ADX"]) < cfg.adx_min:
                        continue
                    if pd.isna(row["RSI"]) or float(row["RSI"]) > cfg.rsi_max:
                        continue
                    if not pd.isna(row["Ret5D"]) and float(row["Ret5D"]) >= cfg.surge_exclude:
                        continue

                    signal = True

                else:
                    # ── 일반 진입 모드 ────────────────────────
                    signal = is_base_entry_signal(row, cfg)

                if not signal:
                    continue

                # ── 첫 돌파만 필터 ────────────────────────────
                if cfg.first_breakout_only:
                    # 최근 20일(영업일) 내 이미 52주 신고가였던 날 있으면 제외
                    if "Is52WHigh" in df.columns:
                        idx_pos = df.index.get_loc(today)
                        lookback_start = max(0, idx_pos - cfg.first_breakout_lookback)
                        # 오늘 제외, 이전 기간 체크
                        recent_highs = df["Is52WHigh"].iloc[lookback_start:idx_pos].sum()
                        if recent_highs > 0:
                            continue

                adx_val = float(row.get("ADX", 0) or 0)
                candidates.append((ticker, float(row["Close"]), adx_val))

            # ADX 높은 순 정렬
            candidates.sort(key=lambda x: x[2], reverse=True)
            candidates = candidates[:slots_available]

            for ticker, entry_price, adx_val in candidates:
                if entry_price <= 0 or pd.isna(entry_price):
                    continue

                total_portfolio = cash + sum(
                    p["shares"] * entry_price for p in positions.values()
                )
                alloc = total_portfolio / cfg.max_positions
                if alloc > cash:
                    alloc = cash * 0.99

                shares = alloc * (1 - cfg.commission) / entry_price
                cost   = shares * entry_price * (1 + cfg.commission)

                if cost > cash or shares <= 0:
                    continue

                df = all_data[ticker]
                row = df.loc[today]
                atr_val = float(row.get("ATR", 0) or 0)
                stop = entry_price - atr_val * cfg.atr_mult if atr_val > 0 else entry_price * 0.90

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

        # ── [C] 일별 NAV 계산 ────────────────────────────────
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
    s     = pd.Series(nav_list, dtype=float)
    ret   = s.pct_change().dropna()
    n     = len(ret)
    years = n / TRADING_DAYS_PER_YEAR

    cagr   = (s.iloc[-1] ** (1 / max(years, 0.1))) - 1 if s.iloc[-1] > 0 else -1.0
    mdd    = ((s - s.cummax()) / s.cummax()).min()
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
    close = spy_df["Close"].squeeze()
    close = close[close.index >= START]
    if close.empty:
        return [1.0]
    nav = (close / close.iloc[0]).tolist()
    return [1.0] + nav[1:]


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("  52주 신고가 돌파 전략 — 파라미터 튜닝 (시나리오 A~G)")
    print(f"  기간: {START} ~ {END}")
    print("=" * 70)

    # ── [1] 데이터 로드 ──────────────────────────────────────
    print("\n[1] 데이터 로드...")
    all_data_raw, spy_df, etf_raw, universe_map = load_full_universe(START)
    print(f"  → {len(all_data_raw)}개 종목 로드 완료")

    # ── [2] 지표 계산 (1회만) ─────────────────────────────────
    print(f"\n[2] 지표 계산 ({len(all_data_raw)}종목)...")
    all_data = {}
    for i, (t, df) in enumerate(all_data_raw.items()):
        if i % 100 == 0:
            print(f"\r  진행: {i}/{len(all_data_raw)}", end="", flush=True)
        all_data[t] = add_indicators(df)
    print(f"\r  완료: {len(all_data)}종목", flush=True)

    # SPY 벤치마크
    spy_nav = calc_spy_nav(spy_df)
    spy_met = calc_metrics(spy_nav)

    # ── [3] 시나리오별 백테스트 ───────────────────────────────
    results = []
    for cfg in SCENARIOS:
        print(f"\n[3-{cfg.name}] {cfg.name}: {cfg.label} 실행 중...")
        nav_list, trade_log, dates = run_backtest(all_data, cfg)
        met = calc_metrics(nav_list)
        sells = [t for t in trade_log if t["action"] == "SELL"]
        trade_count = len(trade_log)
        win_trades  = sum(1 for t in sells if t["pnl_pct"] > 0) if sells else 0
        avg_pnl     = np.mean([t["pnl_pct"] for t in sells]) if sells else 0.0

        row = {
            "시나리오":    cfg.name,
            "설명":        cfg.label,
            "파라미터":    f"ATR×{cfg.atr_mult}, VOL×{cfg.volume_spike}, HOLD={cfg.max_hold_days}d",
            "총수익률":    met["총수익률"],
            "CAGR":        met["CAGR"],
            "MDD":         met["MDD"],
            "샤프":        met["샤프"],
            "승률(NAV)":   met["승률"],
            "거래건수":    trade_count,
            "첫돌파필터":  "O" if cfg.first_breakout_only else "-",
            "눌림목진입":  "O" if cfg.pullback_entry else "-",
            "MDD기준충족": "O" if met["MDD"] >= SPY_MDD_BENCHMARK else "X",
        }
        results.append(row)
        print(f"  완료: CAGR {met['CAGR']:+.1%} | MDD {met['MDD']:.1%} | 샤프 {met['샤프']:.2f} | 거래 {trade_count}건")

    # ── [4] 결과 비교 테이블 ──────────────────────────────────
    df_results = pd.DataFrame(results)

    print("\n" + "═" * 100)
    print("  시나리오별 성과 비교")
    print("═" * 100)
    print(f"  {'시나리오':<5} {'설명':<28} {'CAGR':>8} {'MDD':>8} {'샤프':>7} {'승률':>7} "
          f"{'거래건':>7} {'첫돌파':>6} {'눌림목':>6} {'MDD기준':>7}")
    print("  " + "─" * 95)
    for _, r in df_results.iterrows():
        marker = " ◀ 최적후보" if r["MDD기준충족"] == "O" else ""
        print(f"  {r['시나리오']:<5} {r['설명']:<28} {r['CAGR']:>+8.1%} {r['MDD']:>+8.1%} "
              f"{r['샤프']:>7.2f} {r['승률(NAV)']:>7.1%} {r['거래건수']:>7} "
              f"{r['첫돌파필터']:>6} {r['눌림목진입']:>6} {r['MDD기준충족']:>7}{marker}")

    # SPY 벤치마크 출력
    print("  " + "─" * 95)
    print(f"  {'SPY':<5} {'Buy&Hold':<28} {spy_met['CAGR']:>+8.1%} {spy_met['MDD']:>+8.1%} "
          f"{spy_met['샤프']:>7.2f} {spy_met['승률']:>7.1%}")

    # ── [5] 최적 시나리오 선정 ────────────────────────────────
    # 기준: MDD >= SPY_MDD_BENCHMARK (-33.7%) 이면서 CAGR 최고
    candidates_df = df_results[df_results["MDD기준충족"] == "O"].copy()
    if not candidates_df.empty:
        best = candidates_df.loc[candidates_df["CAGR"].idxmax()]
        print(f"\n  ★ 최적 시나리오: {best['시나리오']} ({best['설명']})")
        print(f"    CAGR  : {best['CAGR']:+.1%}")
        print(f"    MDD   : {best['MDD']:.1%}")
        print(f"    샤프   : {best['샤프']:.2f}")
        print(f"    파라미터: {best['파라미터']}")
        best_name = best["시나리오"]
    else:
        # MDD 기준 미충족 시 MDD가 가장 낮은 것 선택
        best = df_results.loc[df_results["MDD"].idxmax()]
        print(f"\n  ※ MDD 기준({SPY_MDD_BENCHMARK:.1%}) 충족 시나리오 없음 — MDD 최소 선택")
        print(f"  ★ 최적 시나리오: {best['시나리오']} ({best['설명']})")
        best_name = best["시나리오"]

    # ── [6] CSV 저장 ──────────────────────────────────────────
    csv_path = RESULTS_DIR / "backtest_52w_high_tuning.csv"
    df_results.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n  결과 CSV: {csv_path}")

    # ── [7] 비교 차트 ─────────────────────────────────────────
    # 시나리오별 CAGR vs MDD 산점도
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle("52주 신고가 전략 파라미터 튜닝 — 시나리오 A~G 비교", fontsize=14, fontweight="bold")

    ax1 = axes[0]
    colors = plt.cm.tab10(np.linspace(0, 1, len(SCENARIOS)))
    for i, r in df_results.iterrows():
        ax1.scatter(abs(r["MDD"]) * 100, r["CAGR"] * 100,
                    color=colors[i], s=120, zorder=5,
                    marker="*" if r["MDD기준충족"] == "O" else "o")
        ax1.annotate(r["시나리오"], (abs(r["MDD"]) * 100, r["CAGR"] * 100),
                     textcoords="offset points", xytext=(5, 3), fontsize=9)

    # SPY 기준선
    ax1.axvline(abs(SPY_MDD_BENCHMARK) * 100, color="gray", ls="--", lw=1.2,
                label=f"SPY MDD 기준 ({SPY_MDD_BENCHMARK:.1%})")
    ax1.scatter(abs(spy_met["MDD"]) * 100, spy_met["CAGR"] * 100,
                color="gray", s=80, marker="D", label="SPY", zorder=5)
    ax1.set_xlabel("|MDD| (%)")
    ax1.set_ylabel("CAGR (%)")
    ax1.set_title("CAGR vs |MDD| (★=MDD 기준 충족)")
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.25)

    ax2 = axes[1]
    x = np.arange(len(SCENARIOS))
    cagr_vals = [r["CAGR"] * 100 for _, r in df_results.iterrows()]
    mdd_vals  = [abs(r["MDD"]) * 100 for _, r in df_results.iterrows()]
    bar_colors = ["#2E75B6" if r["MDD기준충족"] == "O" else "#AAAAAA"
                  for _, r in df_results.iterrows()]

    bars = ax2.bar(x - 0.2, cagr_vals, 0.4, label="CAGR (%)", color=bar_colors, alpha=0.85)
    bars2 = ax2.bar(x + 0.2, mdd_vals, 0.4, label="|MDD| (%)", color="#FF6B6B", alpha=0.6)
    ax2.axhline(abs(SPY_MDD_BENCHMARK) * 100, color="gray", ls="--", lw=1.2,
                label=f"SPY |MDD| = {abs(SPY_MDD_BENCHMARK)*100:.1f}%")
    ax2.set_xticks(x)
    ax2.set_xticklabels([r["시나리오"] for _, r in df_results.iterrows()])
    ax2.set_ylabel("(%)")
    ax2.set_title("시나리오별 CAGR / |MDD| (파란색=MDD 기준 충족)")
    ax2.legend(fontsize=9)
    ax2.grid(axis="y", alpha=0.25)

    chart_path = RESULTS_DIR / "backtest_52w_high_tuning.png"
    plt.tight_layout()
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    print(f"  비교 차트: {chart_path}")

    print("\n" + "=" * 70)
    print("  튜닝 완료")
    print("=" * 70)
