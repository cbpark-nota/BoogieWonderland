"""
VIX 급등 시 SVXY/SVIX 지정가 매수 전략 백테스트
════════════════════════════════════════════════════════════
전략:
  VIX가 특정 임계값을 돌파할 때 SVXY/SVIX 매수 (60/40 배분)
  - 이론가 계산: 전일 종가 기준 VIX 변동에 따른 이론가
  - 지정가: 이론가 × (1 - 할인율)
  - 매도: VIX < 회복 임계값 또는 최대 보유기간 도달

파라미터 튜닝 (5가지 조합):
  1. 기본: VIX [25,30,35,40,50], 할인 -5%, 매도 VIX<20
  2. 공격적: VIX [20,25,30], 할인 -3%, 매도 VIX<18
  3. 보수적: VIX [35,40,50,60], 할인 -10%, 매도 VIX<22
  4. 빠른매도: VIX [25,30,35,40], 할인 -5%, 최대 10일 보유
  5. 계단식: VIX 25→-3%, 30→-7%, 40→-12%, 50→-18%

측정 지표:
  CAGR, MDD, Sharpe, 승률, 평균 보유기간, 거래 횟수, 손익비
════════════════════════════════════════════════════════════
"""
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

_THIS_DIR = Path(__file__).parent
RESULTS_DIR = _THIS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

DOCS_DIR = _THIS_DIR.parent.parent / "docs" / "backtest"
DOCS_DIR.mkdir(exist_ok=True)

# ── 백테스트 기간 ─────────────────────────────────────────
START_SVXY = "2011-10-04"   # SVXY 출시일 (2011-10-04)
START_SVIX  = "2022-03-22"  # SVIX 출시일 (2022-03-22)
END         = datetime.today().strftime("%Y-%m-%d")

SVXY_WEIGHT = 0.6  # 포트폴리오 내 SVXY 비중
SVIX_WEIGHT = 0.4  # 포트폴리오 내 SVIX 비중
INITIAL_CAPITAL = 100_000  # 초기 자본 (달러)

# ── 파라미터 세트 정의 ────────────────────────────────────
PARAM_SETS = [
    {
        "name": "기본 설정",
        "vix_thresholds": [25, 30, 35, 40, 50],
        "discount_rates": {25: 0.05, 30: 0.05, 35: 0.05, 40: 0.05, 50: 0.05},
        "vix_exit": 20,
        "max_hold_days": 60,
        "desc": "VIX [25,30,35,40,50], 할인 -5%, 매도 VIX<20",
    },
    {
        "name": "공격적 매수",
        "vix_thresholds": [20, 25, 30],
        "discount_rates": {20: 0.03, 25: 0.03, 30: 0.03},
        "vix_exit": 18,
        "max_hold_days": 60,
        "desc": "VIX [20,25,30], 할인 -3%, 매도 VIX<18",
    },
    {
        "name": "보수적 매수",
        "vix_thresholds": [35, 40, 50, 60],
        "discount_rates": {35: 0.10, 40: 0.10, 50: 0.10, 60: 0.10},
        "vix_exit": 22,
        "max_hold_days": 60,
        "desc": "VIX [35,40,50,60], 할인 -10%, 매도 VIX<22",
    },
    {
        "name": "빠른 매도",
        "vix_thresholds": [25, 30, 35, 40],
        "discount_rates": {25: 0.05, 30: 0.05, 35: 0.05, 40: 0.05},
        "vix_exit": 20,
        "max_hold_days": 10,
        "desc": "VIX [25,30,35,40], 할인 -5%, 최대 10일 보유",
    },
    {
        "name": "계단식 할인",
        "vix_thresholds": [25, 30, 40, 50],
        "discount_rates": {25: 0.03, 30: 0.07, 40: 0.12, 50: 0.18},
        "vix_exit": 20,
        "max_hold_days": 60,
        "desc": "VIX 25→-3%, 30→-7%, 40→-12%, 50→-18%",
    },
]


# ── 데이터 다운로드 ──────────────────────────────────────
def download_data(start: str, end: str) -> dict:
    print(f"  데이터 다운로드: SVXY, SVIX, ^VIX ({start} ~ {end})")
    tickers = ["SVXY", "SVIX", "^VIX"]
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    close = raw["Close"].copy()
    close.columns = [c.replace("^", "") for c in close.columns]

    # SVIX는 2022-03-22 이후만 유효
    if "SVIX" in close.columns:
        close["SVIX"] = close["SVIX"].where(close.index >= "2022-03-22")

    print(f"  다운로드 완료: {len(close)} 거래일")
    return close


# ── 이론가 계산 (VIX spot 기반 근사) ─────────────────────
def calc_theoretical_price(prev_price: float, vix_prev: float, vix_curr: float, leverage: float) -> float:
    """
    VIX 현물 변동률로 ETF 이론가 근사 계산.
    실제는 VIX 선물 지수(SPVXSP/SHORTVOL) 사용해야 하나,
    yfinance에서 ^SPVXSP 데이터가 제한적이므로 VIX spot으로 근사.
    VIX spot 변동률 × 0.7 = VIX 선물 지수 변동률 근사 (경험적 조정).
    """
    if vix_prev <= 0:
        return prev_price
    vix_chg = (vix_curr - vix_prev) / vix_prev
    futures_chg = vix_chg * 0.7  # VIX spot → VIX 선물 지수 변동 근사
    theo = prev_price * (1 + leverage * futures_chg)
    return max(theo, 0.01)


# ── 단일 파라미터 백테스트 ────────────────────────────────
def run_backtest(df: pd.DataFrame, params: dict) -> dict:
    thresholds = sorted(params["vix_thresholds"])
    discount_rates = params["discount_rates"]
    vix_exit = params["vix_exit"]
    max_hold_days = params["max_hold_days"]

    # SVXY/SVIX 각각 독립 시뮬레이션 후 60/40 합산
    results_combined = []

    for ticker, leverage, weight in [("SVXY", -0.5, SVXY_WEIGHT), ("SVIX", -1.0, SVIX_WEIGHT)]:
        if ticker not in df.columns:
            continue
        sub = df[[ticker, "VIX"]].dropna()
        if len(sub) < 20:
            continue

        capital = INITIAL_CAPITAL * weight
        cash = capital
        position = 0.0   # 보유 주식 수
        entry_price = 0.0
        entry_date = None
        entry_vix_thresh = None
        trades = []

        prices = sub[ticker].values
        vix_vals = sub["VIX"].values
        dates = sub.index

        for i in range(1, len(sub)):
            price = prices[i]
            vix = vix_vals[i]
            prev_price = prices[i - 1]
            prev_vix = vix_vals[i - 1]
            today = dates[i]

            # 포지션 보유 중 → 매도 조건 체크
            if position > 0:
                hold_days = (today - entry_date).days
                exit_now = (vix < vix_exit) or (hold_days >= max_hold_days)
                if exit_now:
                    sell_value = position * price
                    ret = (price - entry_price) / entry_price
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": today,
                        "entry_price": entry_price,
                        "exit_price": price,
                        "return": ret,
                        "hold_days": hold_days,
                        "vix_thresh": entry_vix_thresh,
                    })
                    cash += sell_value
                    position = 0.0
                    entry_price = 0.0
                    entry_date = None
                    entry_vix_thresh = None
                continue

            # 포지션 없음 → 매수 조건 체크
            # VIX가 임계값 중 하나를 돌파했는지 확인
            triggered_thresh = None
            for thresh in thresholds:
                if prev_vix < thresh <= vix:
                    triggered_thresh = thresh
                    break

            if triggered_thresh is None:
                continue

            # 이론가 계산 및 지정가 설정
            theo = calc_theoretical_price(prev_price, prev_vix, vix, leverage)
            discount = discount_rates.get(triggered_thresh, 0.05)
            limit_price = theo * (1 - discount)

            # 당일 실제 가격이 지정가 이하면 체결 (종가 기준 근사)
            if price <= limit_price:
                buy_price = limit_price
                shares = cash / buy_price
                position = shares
                entry_price = buy_price
                entry_date = today
                entry_vix_thresh = triggered_thresh
                cash = 0.0

        # 미청산 포지션은 마지막 가격으로 청산
        if position > 0:
            last_price = prices[-1]
            ret = (last_price - entry_price) / entry_price
            trades.append({
                "entry_date": entry_date,
                "exit_date": dates[-1],
                "entry_price": entry_price,
                "exit_price": last_price,
                "return": ret,
                "hold_days": (dates[-1] - entry_date).days,
                "vix_thresh": entry_vix_thresh,
            })
            cash += position * last_price

        results_combined.append({
            "ticker": ticker,
            "weight": weight,
            "final_cash": cash,
            "initial_capital": capital,
            "trades": trades,
        })

    # 전체 통계 집계
    all_trades = []
    total_final = 0.0
    total_initial = 0.0
    for r in results_combined:
        all_trades.extend(r["trades"])
        total_final += r["final_cash"]
        total_initial += r["initial_capital"]

    # CAGR
    if len(df) < 2:
        return {}
    days_total = (df.index[-1] - df.index[0]).days
    years = days_total / 365.25
    cagr = (total_final / total_initial) ** (1 / years) - 1 if years > 0 else 0

    # 거래 통계
    if not all_trades:
        return {
            "name": params["name"],
            "desc": params["desc"],
            "n_trades": 0,
            "win_rate": 0,
            "avg_return": 0,
            "max_return": 0,
            "min_return": 0,
            "avg_hold_days": 0,
            "cagr": cagr,
            "mdd": 0,
            "sharpe": 0,
            "profit_factor": 0,
        }

    trade_df = pd.DataFrame(all_trades)
    wins = trade_df[trade_df["return"] > 0]
    losses = trade_df[trade_df["return"] <= 0]
    win_rate = len(wins) / len(trade_df) if len(trade_df) > 0 else 0
    avg_ret = trade_df["return"].mean()
    max_ret = trade_df["return"].max()
    min_ret = trade_df["return"].min()
    avg_hold = trade_df["hold_days"].mean()

    gross_profit = wins["return"].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses["return"].sum()) if len(losses) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # 포트폴리오 곡선으로 MDD, Sharpe 계산
    equity_curve = _build_equity_curve(df, results_combined)
    mdd = _calc_mdd(equity_curve)
    sharpe = _calc_sharpe(equity_curve)

    return {
        "name": params["name"],
        "desc": params["desc"],
        "n_trades": len(trade_df),
        "win_rate": win_rate,
        "avg_return": avg_ret,
        "max_return": max_ret,
        "min_return": min_ret,
        "avg_hold_days": avg_hold,
        "cagr": cagr,
        "mdd": mdd,
        "sharpe": sharpe,
        "profit_factor": profit_factor,
        "trade_df": trade_df,
        "equity_curve": equity_curve,
    }


def _build_equity_curve(df: pd.DataFrame, results: list) -> pd.Series:
    """간단한 일별 자산 곡선 재구성"""
    if not results:
        return pd.Series(dtype=float)

    # 각 포지션의 날별 가치를 합산
    total_capital = sum(r["initial_capital"] for r in results)
    equity = pd.Series(total_capital, index=df.index, dtype=float)

    for r in results:
        ticker = r["ticker"]
        if ticker not in df.columns:
            continue
        for trade in r["trades"]:
            entry = trade["entry_date"]
            exit_ = trade["exit_date"]
            entry_price = trade["entry_price"]
            shares = r["initial_capital"] / entry_price  # 근사
            mask = (df.index >= entry) & (df.index <= exit_)
            prices_in_period = df.loc[mask, ticker]
            if prices_in_period.empty:
                continue
            pnl = (prices_in_period - entry_price) * shares
            equity.loc[mask] += pnl.values[: mask.sum()]

    return equity


def _calc_mdd(equity: pd.Series) -> float:
    if equity.empty or equity.isna().all():
        return 0.0
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max
    return drawdown.min()


def _calc_sharpe(equity: pd.Series, rf: float = 0.04) -> float:
    if equity.empty or len(equity) < 2:
        return 0.0
    daily_ret = equity.pct_change().dropna()
    if daily_ret.std() == 0:
        return 0.0
    excess = daily_ret - rf / 252
    return (excess.mean() / daily_ret.std()) * np.sqrt(252)


# ── 임계값별 매수 기회 분석 ───────────────────────────────
def analyze_opportunities(vix: pd.Series, thresholds: list) -> pd.DataFrame:
    rows = []
    for thresh in thresholds:
        crossings = ((vix.shift(1) < thresh) & (vix >= thresh))
        n = crossings.sum()
        vix_at_cross = vix[crossings]
        rows.append({
            "VIX 임계값": thresh,
            "돌파 횟수": n,
            "평균 VIX (돌파 시)": vix_at_cross.mean() if n > 0 else 0,
            "최대 VIX (돌파 시)": vix_at_cross.max() if n > 0 else 0,
        })
    return pd.DataFrame(rows)


# ── 결과 출력 ─────────────────────────────────────────────
def print_summary(results: list, df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("VIX/SVXY/SVIX 전략 백테스트 결과 요약")
    print(f"데이터 기간: {df.index[0].date()} ~ {df.index[-1].date()}")
    print("=" * 70)

    print(f"\n{'전략명':<12} {'CAGR':>7} {'MDD':>8} {'Sharpe':>8} {'승률':>7} {'거래수':>7} {'손익비':>8} {'평균보유':>8}")
    print("-" * 70)
    for r in results:
        if not r:
            continue
        print(
            f"{r['name']:<12} "
            f"{r['cagr']*100:>6.1f}% "
            f"{r['mdd']*100:>7.1f}% "
            f"{r['sharpe']:>8.2f} "
            f"{r['win_rate']*100:>6.1f}% "
            f"{r['n_trades']:>7d} "
            f"{r['profit_factor']:>8.2f} "
            f"{r['avg_hold_days']:>7.1f}일"
        )


# ── 마크다운 보고서 생성 ──────────────────────────────────
def save_markdown_report(results: list, df: pd.DataFrame, vix: pd.Series, out_path: Path):
    lines = []
    lines.append("# VIX/SVXY/SVIX 매매 전략 백테스트 결과")
    lines.append("")
    lines.append(f"**실행일:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**데이터 기간:** {df.index[0].date()} ~ {df.index[-1].date()}")
    lines.append(f"**초기 자본:** ${INITIAL_CAPITAL:,}")
    lines.append(f"**배분:** SVXY {SVXY_WEIGHT*100:.0f}% / SVIX {SVIX_WEIGHT*100:.0f}%")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 데이터 가용성 메모
    lines.append("## 데이터 가용성")
    lines.append("")
    lines.append("| 티커 | 데이터 시작 | 비고 |")
    lines.append("|------|------------|------|")
    lines.append("| SVXY | 2011-10-04 | 2018-02-27 이전 -1x → 이후 -0.5x |")
    lines.append("| SVIX | 2022-03-22 | Volatility Shares 출시 |")
    lines.append("| ^VIX | 1990-01-02 | CBOE VIX 현물 |")
    lines.append("| ^SPVXSP | 제한적 | yfinance 미지원 → VIX spot 근사 (×0.7) |")
    lines.append("")
    lines.append("> **주의:** SPVXSP(VIX 선물 지수) 데이터가 yfinance에서 제공되지 않아")
    lines.append("> VIX 현물 변동률 × 0.7로 근사했습니다. 실제 이론가와 편차가 있을 수 있습니다.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # VIX 임계값별 기회 분석 (기본 파라미터 기준)
    lines.append("## VIX 임계값별 돌파 빈도 분석")
    lines.append("")
    all_thresholds = sorted(set(
        t for p in PARAM_SETS for t in p["vix_thresholds"]
    ))
    opp_df = analyze_opportunities(vix, all_thresholds)
    lines.append("| VIX 임계값 | 돌파 횟수 | 평균 VIX (돌파 시) | 최대 VIX (돌파 시) |")
    lines.append("|-----------|---------|-----------------|-----------------|")
    for _, row in opp_df.iterrows():
        lines.append(
            f"| {row['VIX 임계값']} | {int(row['돌파 횟수'])} "
            f"| {row['평균 VIX (돌파 시)']:.1f} "
            f"| {row['최대 VIX (돌파 시)']:.1f} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")

    # 파라미터 조합별 결과 비교표
    lines.append("## 파라미터 조합별 백테스트 결과")
    lines.append("")
    lines.append("| 전략명 | CAGR | MDD | Sharpe | 승률 | 거래수 | 손익비 | 평균보유 |")
    lines.append("|--------|------|-----|--------|------|--------|--------|--------|")
    for r in results:
        if not r:
            continue
        pf_str = f"{r['profit_factor']:.2f}" if r["profit_factor"] != float("inf") else "∞"
        lines.append(
            f"| {r['name']} "
            f"| {r['cagr']*100:.1f}% "
            f"| {r['mdd']*100:.1f}% "
            f"| {r['sharpe']:.2f} "
            f"| {r['win_rate']*100:.1f}% "
            f"| {r['n_trades']} "
            f"| {pf_str} "
            f"| {r['avg_hold_days']:.1f}일 |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")

    # 각 전략별 상세
    lines.append("## 전략별 상세 결과")
    lines.append("")
    for r in results:
        if not r:
            continue
        lines.append(f"### {r['name']}")
        lines.append(f"**설정:** {r['desc']}")
        lines.append("")
        lines.append(f"- CAGR: **{r['cagr']*100:.1f}%**")
        lines.append(f"- MDD: {r['mdd']*100:.1f}%")
        lines.append(f"- Sharpe Ratio: {r['sharpe']:.2f}")
        lines.append(f"- 승률: {r['win_rate']*100:.1f}%")
        lines.append(f"- 총 거래 수: {r['n_trades']}회")
        lines.append(f"- 평균 수익률: {r['avg_return']*100:.1f}%")
        lines.append(f"- 최대 수익률: {r['max_return']*100:.1f}%")
        lines.append(f"- 최대 손실률: {r['min_return']*100:.1f}%")
        lines.append(f"- 평균 보유기간: {r['avg_hold_days']:.1f}일")
        pf_str = f"{r['profit_factor']:.2f}" if r["profit_factor"] != float("inf") else "∞"
        lines.append(f"- 손익비: {pf_str}")
        lines.append("")

        # VIX 임계값별 거래 분포
        if "trade_df" in r and len(r["trade_df"]) > 0:
            td = r["trade_df"]
            lines.append("**VIX 임계값별 거래 분포:**")
            lines.append("")
            lines.append("| VIX 임계값 | 거래 수 | 평균 수익률 | 승률 |")
            lines.append("|-----------|--------|-----------|------|")
            for thresh, grp in td.groupby("vix_thresh"):
                w = (grp["return"] > 0).mean()
                lines.append(
                    f"| {thresh} | {len(grp)} "
                    f"| {grp['return'].mean()*100:.1f}% "
                    f"| {w*100:.1f}% |"
                )
            lines.append("")

    # 역사적 VIX 급등 사례 매핑
    lines.append("---")
    lines.append("")
    lines.append("## 역사적 VIX 급등 사례 vs 전략 트리거")
    lines.append("")
    lines.append("| 사건 | 날짜 | VIX 고점 | 전략 트리거 여부 |")
    lines.append("|------|------|---------|----------------|")
    events = [
        ("COVID-19 급등", "2020-02-24", 82.69),
        ("Volmageddon", "2018-02-05", 37.32),
        ("2024.08 엔캐리", "2024-08-05", 65.73),
        ("2022 우크라이나", "2022-02-24", 36.45),
        ("2015.08 차이나쇼크", "2015-08-24", 40.74),
        ("2011.08 미국 신용등급 강등", "2011-08-08", 48.00),
    ]
    for name, date_, vix_peak in events:
        triggered = [
            p["name"]
            for p in PARAM_SETS
            if any(t <= vix_peak for t in p["vix_thresholds"])
        ]
        trig_str = ", ".join(triggered) if triggered else "없음"
        lines.append(f"| {name} | {date_} | {vix_peak} | {trig_str} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 결론 및 시사점")
    lines.append("")
    lines.append("1. **SPVXSP 데이터 부재**: yfinance에서 SPVXSP(VIX 선물 지수) 히스토리가 제공되지 않아")
    lines.append("   VIX spot × 0.7 근사를 사용했습니다. 정확한 이론가 계산을 위해서는")
    lines.append("   CBOE 또는 S&P Global에서 SPVXSP 일별 데이터를 별도 수집 필요.")
    lines.append("")
    lines.append("2. **SVIX 데이터 한계**: SVIX는 2022년 출시로 데이터가 부족.")
    lines.append("   특히 대형 VIX 이벤트(COVID, Volmageddon)가 없어 극단적 리스크 검증 불가.")
    lines.append("")
    lines.append("3. **전략 선택 가이드**:")
    lines.append("   - 고빈도 트레이딩 원하면 → 공격적 매수 (낮은 임계값)")
    lines.append("   - 안정성 우선이면 → 보수적 매수 (높은 임계값 + 높은 할인율)")
    lines.append("   - 회전율 최소화 원하면 → 빠른 매도 (짧은 보유기간)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*면책: 이 백테스트는 연구 목적이며 투자 조언이 아닙니다.*")
    lines.append("*레버리지/인버스 ETF는 원금 전액 손실 가능성이 있는 고위험 상품입니다.*")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  마크다운 보고서 저장: {out_path}")


# ── 차트 저장 ─────────────────────────────────────────────
def save_charts(results: list, df: pd.DataFrame):
    valid = [r for r in results if r and "equity_curve" in r]
    if not valid:
        return

    fig, axes = plt.subplots(2, 1, figsize=(14, 10))

    # 자산 곡선
    ax1 = axes[0]
    for r in valid:
        eq = r["equity_curve"]
        if not eq.empty:
            ax1.plot(eq.index, eq / INITIAL_CAPITAL, label=r["name"], linewidth=1.5)
    ax1.set_title("VIX 전략 자산 곡선 (정규화)", fontsize=13)
    ax1.set_ylabel("자산 배수 (초기=1)")
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.3)

    # VIX 차트
    ax2 = axes[1]
    vix = df["VIX"].dropna()
    ax2.plot(vix.index, vix.values, color="red", linewidth=1, alpha=0.7, label="VIX")
    for lvl in [20, 25, 30, 35, 40, 50]:
        ax2.axhline(lvl, color="gray", linestyle="--", linewidth=0.5, alpha=0.5)
        ax2.text(vix.index[-1], lvl, f" {lvl}", fontsize=7, va="center", color="gray")
    ax2.set_title("VIX 지수", fontsize=13)
    ax2.set_ylabel("VIX")
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    chart_path = RESULTS_DIR / "backtest_vix_results.png"
    plt.savefig(chart_path, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"  차트 저장: {chart_path}")


# ── 메인 ─────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("VIX/SVXY/SVIX 백테스트 시작")
    print("=" * 70)

    # 데이터 다운로드 (SVXY 기준 최대 기간)
    print("\n[1/3] 데이터 다운로드")
    df = download_data(START_SVXY, END)

    if "VIX" not in df.columns or df["VIX"].dropna().empty:
        print("  오류: VIX 데이터 없음")
        sys.exit(1)
    if "SVXY" not in df.columns or df["SVXY"].dropna().empty:
        print("  오류: SVXY 데이터 없음")
        sys.exit(1)

    vix = df["VIX"].dropna()
    print(f"  VIX 통계: 평균={vix.mean():.1f}, 최소={vix.min():.1f}, 최대={vix.max():.1f}")

    # VIX 임계값별 기회 분석
    print("\n[2/3] VIX 임계값별 돌파 빈도 분석")
    all_thresholds = sorted(set(t for p in PARAM_SETS for t in p["vix_thresholds"]))
    opp_df = analyze_opportunities(vix, all_thresholds)
    print(opp_df.to_string(index=False))

    # 5가지 파라미터 조합 백테스트
    print("\n[3/3] 파라미터 조합 백테스트 실행")
    all_results = []
    for i, params in enumerate(PARAM_SETS, 1):
        print(f"\n  [{i}/5] {params['name']}: {params['desc']}")
        result = run_backtest(df, params)
        all_results.append(result)
        if result:
            pf_str = f"{result['profit_factor']:.2f}" if result["profit_factor"] != float("inf") else "∞"
            print(
                f"        CAGR={result['cagr']*100:.1f}% | "
                f"MDD={result['mdd']*100:.1f}% | "
                f"Sharpe={result['sharpe']:.2f} | "
                f"승률={result['win_rate']*100:.1f}% | "
                f"거래수={result['n_trades']} | "
                f"손익비={pf_str}"
            )

    # 요약 출력
    print_summary(all_results, df)

    # 마크다운 보고서
    report_path = DOCS_DIR / "backtest_results_vix.md"
    save_markdown_report(all_results, df, vix, report_path)

    # 차트
    save_charts(all_results, df)

    print("\n백테스트 완료!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
