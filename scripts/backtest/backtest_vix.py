"""
VIX 매매 전략 백테스트 (2020-01-01 ~ 현재)
══════════════════════════════════════════════════════════════
전략: VIX 임계값 돌파 시 SVXY/SVIX 지정가 매수 → VIX 회복 또는 보유기간 초과 시 매도
이론가: SVXY = 전일종가 × (1 - 0.5 × VIX_일간변동률)
        SVIX = 전일종가 × (1 - VIX_일간변동률)
지정가 = 이론가 × (1 + 할인율)  ← 할인율 음수이므로 이론가 대비 할인
══════════════════════════════════════════════════════════════
파라미터 5종:
  1. 기본:      VIX임계값 [25,30,35,40,50], 할인율 -5%, 매도VIX<20
  2. 공격적:    VIX임계값 [20,25,30], 할인율 -3%, 매도VIX<18
  3. 보수적:    VIX임계값 [35,40,50,60], 할인율 -10%, 매도VIX<22
  4. 빠른매도:  VIX임계값 [25,30,35,40], 할인율 -5%, 보유최대10일
  5. 계단식할인: VIX25→-3%, VIX30→-7%, VIX40→-12%, VIX50→-18%
══════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import sys
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime

START = "2020-01-01"
END = datetime.today().strftime("%Y-%m-%d")
INITIAL_CAPITAL = 10_000.0
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

PARAM_SETS = [
    {
        "name": "기본",
        "thresholds": [25, 30, 35, 40, 50],
        "discount": -0.05,
        "sell_vix": 20,
        "max_hold": 999,
        "tiered": None,
    },
    {
        "name": "공격적",
        "thresholds": [20, 25, 30],
        "discount": -0.03,
        "sell_vix": 18,
        "max_hold": 999,
        "tiered": None,
    },
    {
        "name": "보수적",
        "thresholds": [35, 40, 50, 60],
        "discount": -0.10,
        "sell_vix": 22,
        "max_hold": 999,
        "tiered": None,
    },
    {
        "name": "빠른매도",
        "thresholds": [25, 30, 35, 40],
        "discount": -0.05,
        "sell_vix": 999,  # VIX 조건 비활성 (보유기간으로만)
        "max_hold": 10,
        "tiered": None,
    },
    {
        "name": "계단식할인",
        "thresholds": [25, 30, 40, 50],
        "discount": -0.05,  # 기본값 (미매칭 시)
        "sell_vix": 20,
        "max_hold": 999,
        "tiered": {25: -0.03, 30: -0.07, 40: -0.12, 50: -0.18},
    },
]


def flatten_columns(df):
    """MultiIndex 컬럼 → 단일 레벨로"""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] if col[1] == "" else col[0] for col in df.columns]
    return df


def download_data():
    """SVXY, SVIX, ^VIX 데이터 다운로드"""
    print(f"데이터 다운로드: {START} ~ {END}")
    result = {}
    for name, ticker in [("SVXY", "SVXY"), ("SVIX", "SVIX"), ("VIX", "^VIX")]:
        try:
            df = yf.download(ticker, start=START, end=END, progress=False, auto_adjust=True)
            if df.empty:
                print(f"  {name}: 데이터 없음")
                continue
            # MultiIndex 처리
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            df.index = pd.to_datetime(df.index)
            result[name] = df[["Open", "High", "Low", "Close"]].dropna()
            print(f"  {name}: {len(result[name])}일 ({result[name].index[0].date()} ~ {result[name].index[-1].date()})")
        except Exception as e:
            print(f"  {name} 다운로드 실패: {e}")
    return result


def calc_metrics(equity: pd.Series, trades: list) -> dict:
    """성과 지표 계산"""
    if len(equity) < 2 or equity.iloc[0] == 0:
        return {"CAGR": 0, "MDD": 0, "Sharpe": 0, "WinRate": 0,
                "Trades": 0, "AvgReturn": 0, "AvgHoldDays": 0}

    rets = equity.pct_change().dropna()
    years = len(equity) / 252
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / max(years, 0.01)) - 1

    rolling_max = equity.expanding().max()
    dd = (equity - rolling_max) / rolling_max
    mdd = dd.min()

    sharpe = 0.0
    if rets.std() > 0:
        sharpe = rets.mean() / rets.std() * np.sqrt(252)

    if trades:
        trs = [t["return"] for t in trades]
        win_rate = sum(1 for r in trs if r > 0) / len(trs)
        avg_ret = float(np.mean(trs))
        avg_hold = float(np.mean([t["hold_days"] for t in trades]))
        n = len(trades)
    else:
        win_rate = avg_ret = avg_hold = 0.0
        n = 0

    return {
        "CAGR": cagr,
        "MDD": mdd,
        "Sharpe": sharpe,
        "WinRate": win_rate,
        "Trades": n,
        "AvgReturn": avg_ret,
        "AvgHoldDays": avg_hold,
    }


def run_backtest(price_df: pd.DataFrame, vix_df: pd.DataFrame,
                 params: dict, asset_type: str) -> tuple:
    """
    단일 파라미터 조합 + 자산별 백테스트
    asset_type: 'SVXY' 또는 'SVIX' (이론가 계산에 사용)
    반환: (metrics, equity_series, trades_list)
    """
    thresholds = sorted(params["thresholds"])
    discount = params["discount"]
    sell_vix = params["sell_vix"]
    max_hold = params["max_hold"]
    tiered = params["tiered"]

    idx = price_df.index.intersection(vix_df.index).sort_values()
    if len(idx) < 10:
        return {}, pd.Series(dtype=float), []

    prices = price_df.loc[idx]
    vix = vix_df.loc[idx]

    capital = INITIAL_CAPITAL
    position = 0.0      # 보유 주수
    entry_price = 0.0
    entry_date = None

    equity_vals = []
    trades = []

    idx_list = list(idx)
    n = len(idx_list)

    for i, date in enumerate(idx_list):
        vix_today = float(vix.loc[date, "Close"])
        p_open = float(prices.loc[date, "Open"])
        p_close = float(prices.loc[date, "Close"])
        p_low = float(prices.loc[date, "Low"])

        # ── 매도 체크 ──────────────────────────────────────────────────────
        if position > 0 and entry_date is not None:
            hold_days = (date - entry_date).days
            sell_flag = False

            if vix_today <= sell_vix:
                sell_flag = True
            if hold_days >= max_hold:
                sell_flag = True

            if sell_flag:
                # 시가에 매도
                sell_px = p_open
                trade_ret = (sell_px - entry_price) / entry_price if entry_price > 0 else 0
                capital = position * sell_px
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": date,
                    "entry_price": entry_price,
                    "exit_price": sell_px,
                    "return": trade_ret,
                    "hold_days": hold_days,
                })
                position = 0.0
                entry_price = 0.0
                entry_date = None

        # ── 매수 체크 ──────────────────────────────────────────────────────
        if position == 0 and i > 0:
            prev_date = idx_list[i - 1]
            vix_prev = float(vix.loc[prev_date, "Close"])
            price_prev = float(prices.loc[prev_date, "Close"])

            # VIX 임계값 최초 돌파 확인 (가장 낮은 돌파 레벨 우선)
            triggered = None
            for thresh in thresholds:
                if vix_today >= thresh > vix_prev:
                    triggered = thresh
                    break  # 최저 레벨 돌파부터 처리

            if triggered is not None:
                # 이론가 계산
                vix_ret = (vix_today - vix_prev) / vix_prev if vix_prev > 0 else 0
                if asset_type == "SVXY":
                    theoretical = price_prev * (1 - 0.5 * vix_ret)
                else:  # SVIX
                    theoretical = price_prev * (1 - vix_ret)

                # 할인율 결정
                if tiered is not None:
                    disc = tiered.get(triggered, discount)
                else:
                    disc = discount

                limit_px = theoretical * (1 + disc)  # disc 음수 → 이론가 아래

                # 당일 저가가 지정가 이하이면 지정가에 체결
                if p_low <= limit_px and limit_px > 0:
                    entry_price = limit_px
                    position = capital / entry_price
                    entry_date = date

        # ── 자산 가치 ──────────────────────────────────────────────────────
        cur_val = position * p_close if position > 0 else capital
        equity_vals.append(cur_val)

    # 미청산 포지션 → 마지막 날 종가로 청산
    if position > 0:
        last_date = idx_list[-1]
        last_px = float(prices.loc[last_date, "Close"])
        hold_days = (last_date - entry_date).days
        trade_ret = (last_px - entry_price) / entry_price if entry_price > 0 else 0
        trades.append({
            "entry_date": entry_date,
            "exit_date": last_date,
            "entry_price": entry_price,
            "exit_price": last_px,
            "return": trade_ret,
            "hold_days": hold_days,
        })
        equity_vals[-1] = position * last_px

    equity = pd.Series(equity_vals, index=idx, name=asset_type)
    metrics = calc_metrics(equity, trades)
    return metrics, equity, trades


def blend_equity(eq_svxy: pd.Series, eq_svix: pd.Series, w=0.6) -> pd.Series:
    """SVXY 60% + SVIX 40% 혼합 자산곡선"""
    idx = eq_svxy.index.intersection(eq_svix.index)
    if len(idx) == 0:
        return pd.Series(dtype=float)
    a = eq_svxy.loc[idx] / eq_svxy.loc[idx[0]]
    b = eq_svix.loc[idx] / eq_svix.loc[idx[0]]
    blend = w * a + (1 - w) * b
    return blend * INITIAL_CAPITAL


def fmt_pct(v):
    return f"{v*100:.1f}%"

def fmt_f(v, d=2):
    return f"{v:.{d}f}"


def main():
    data = download_data()

    if "VIX" not in data:
        print("VIX 데이터 없음 — 종료")
        sys.exit(1)

    vix_df = data["VIX"]
    assets = {}
    if "SVXY" in data:
        assets["SVXY"] = data["SVXY"]
    if "SVIX" in data:
        assets["SVIX"] = data["SVIX"]

    if not assets:
        print("SVXY/SVIX 데이터 없음 — 종료")
        sys.exit(1)

    all_results = []  # [{param_name, asset, metrics}]

    print("\n백테스트 실행 중...")
    for pset in PARAM_SETS:
        pname = pset["name"]
        row = {"파라미터": pname}
        eq_map = {}

        for asset_name, price_df in assets.items():
            m, eq, trd = run_backtest(price_df, vix_df, pset, asset_name)
            eq_map[asset_name] = eq
            tag = f"{pname}_{asset_name}"
            row[f"{asset_name}_CAGR"] = fmt_pct(m.get("CAGR", 0))
            row[f"{asset_name}_MDD"] = fmt_pct(m.get("MDD", 0))
            row[f"{asset_name}_Sharpe"] = fmt_f(m.get("Sharpe", 0))
            row[f"{asset_name}_WinRate"] = fmt_pct(m.get("WinRate", 0))
            row[f"{asset_name}_Trades"] = m.get("Trades", 0)
            row[f"{asset_name}_AvgRet"] = fmt_pct(m.get("AvgReturn", 0))
            row[f"{asset_name}_AvgHold"] = fmt_f(m.get("AvgHoldDays", 0), 1)
            print(f"  [{pname}] {asset_name}: CAGR={fmt_pct(m.get('CAGR',0))} MDD={fmt_pct(m.get('MDD',0))} Sharpe={fmt_f(m.get('Sharpe',0))} 거래={m.get('Trades',0)}건")

            all_results.append({
                "param": pname,
                "asset": asset_name,
                **m,
            })

        # 60/40 혼합 (SVXY+SVIX 둘 다 있을 때)
        if "SVXY" in eq_map and "SVIX" in eq_map and len(eq_map["SVXY"]) > 0 and len(eq_map["SVIX"]) > 0:
            blend_eq = blend_equity(eq_map["SVXY"], eq_map["SVIX"])
            m_blend = calc_metrics(blend_eq, [])  # 거래 목록 없이 곡선만으로 계산
            row["BLEND_CAGR"] = fmt_pct(m_blend.get("CAGR", 0))
            row["BLEND_MDD"] = fmt_pct(m_blend.get("MDD", 0))
            row["BLEND_Sharpe"] = fmt_f(m_blend.get("Sharpe", 0))
            print(f"  [{pname}] 60/40혼합: CAGR={fmt_pct(m_blend.get('CAGR',0))} MDD={fmt_pct(m_blend.get('MDD',0))} Sharpe={fmt_f(m_blend.get('Sharpe',0))}")
            all_results.append({
                "param": pname,
                "asset": "SVXY60+SVIX40",
                **m_blend,
            })

    # ── 결과 DataFrame ─────────────────────────────────────────────────────
    results_df = pd.DataFrame(all_results)
    csv_path = RESULTS_DIR / "backtest_vix_results.csv"
    results_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n결과 CSV 저장: {csv_path}")

    # ── Markdown 보고서 생성 ───────────────────────────────────────────────
    md_lines = []
    md_lines.append("# VIX 매매 전략 백테스트 결과\n")
    md_lines.append(f"- **기간**: {START} ~ {END}")
    md_lines.append(f"- **초기 자본**: ${INITIAL_CAPITAL:,.0f}")
    md_lines.append(f"- **전략**: VIX 임계값 돌파 시 SVXY/SVIX 지정가 매수 (이론가 대비 할인)")
    md_lines.append(f"- **데이터 소스**: yfinance (SVXY, SVIX, ^VIX)")
    md_lines.append(f"- **이론가**: SVXY = 전일종가×(1−0.5×VIX변동률), SVIX = 전일종가×(1−VIX변동률)")
    md_lines.append(f"- **지정가 체결**: 당일 저가 ≤ 지정가 시 체결\n")

    md_lines.append("## 파라미터 설정\n")
    md_lines.append("| # | 파라미터 | VIX 임계값 | 할인율 | 매도 VIX | 최대 보유 |")
    md_lines.append("|---|----------|-----------|--------|---------|---------|")
    for i, p in enumerate(PARAM_SETS, 1):
        td = f"계단식({p['tiered']})" if p["tiered"] else fmt_pct(p["discount"])
        sv = f"VIX<{p['sell_vix']}" if p["sell_vix"] < 900 else "없음"
        mh = f"{p['max_hold']}일" if p["max_hold"] < 999 else "없음"
        md_lines.append(f"| {i} | {p['name']} | {p['thresholds']} | {td} | {sv} | {mh} |")

    # SVXY 결과표
    md_lines.append("\n## SVXY 백테스트 결과\n")
    md_lines.append("| 파라미터 | CAGR | MDD | Sharpe | 승률 | 거래 | 평균수익 | 평균보유 |")
    md_lines.append("|---------|------|-----|--------|------|------|---------|---------|")
    for r in all_results:
        if r["asset"] == "SVXY":
            md_lines.append(
                f"| {r['param']} "
                f"| {fmt_pct(r.get('CAGR',0))} "
                f"| {fmt_pct(r.get('MDD',0))} "
                f"| {fmt_f(r.get('Sharpe',0))} "
                f"| {fmt_pct(r.get('WinRate',0))} "
                f"| {r.get('Trades',0)} "
                f"| {fmt_pct(r.get('AvgReturn',0))} "
                f"| {fmt_f(r.get('AvgHoldDays',0),1)}일 |"
            )

    # SVIX 결과표
    svix_rows = [r for r in all_results if r["asset"] == "SVIX"]
    if svix_rows:
        md_lines.append("\n## SVIX 백테스트 결과\n")
        md_lines.append("| 파라미터 | CAGR | MDD | Sharpe | 승률 | 거래 | 평균수익 | 평균보유 |")
        md_lines.append("|---------|------|-----|--------|------|------|---------|---------|")
        for r in svix_rows:
            md_lines.append(
                f"| {r['param']} "
                f"| {fmt_pct(r.get('CAGR',0))} "
                f"| {fmt_pct(r.get('MDD',0))} "
                f"| {fmt_f(r.get('Sharpe',0))} "
                f"| {fmt_pct(r.get('WinRate',0))} "
                f"| {r.get('Trades',0)} "
                f"| {fmt_pct(r.get('AvgReturn',0))} "
                f"| {fmt_f(r.get('AvgHoldDays',0),1)}일 |"
            )

    # 혼합 결과표
    blend_rows = [r for r in all_results if r["asset"] == "SVXY60+SVIX40"]
    if blend_rows:
        md_lines.append("\n## SVXY 60% + SVIX 40% 혼합 결과\n")
        md_lines.append("| 파라미터 | CAGR | MDD | Sharpe |")
        md_lines.append("|---------|------|-----|--------|")
        for r in blend_rows:
            md_lines.append(
                f"| {r['param']} "
                f"| {fmt_pct(r.get('CAGR',0))} "
                f"| {fmt_pct(r.get('MDD',0))} "
                f"| {fmt_f(r.get('Sharpe',0))} |"
            )

    md_lines.append("\n## 주의사항\n")
    md_lines.append("- SVIX는 2022년 3월 상장 이후 데이터만 존재")
    md_lines.append("- VIX spot을 선물 지수(SPVXSP) 대리로 사용")
    md_lines.append("- 이론가는 레버리지 ETF 특성 기반 근사치 (실제 추적 오차 존재)")
    md_lines.append("- 지정가 미체결 시 거래 스킵 (당일 저가 > 지정가)")
    md_lines.append("- 슬리피지/거래비용 미반영")
    md_lines.append(f"- 백테스트 실행일: {datetime.today().strftime('%Y-%m-%d')}")

    md_content = "\n".join(md_lines)
    print("\n" + "="*60)
    print(md_content)
    print("="*60)

    return md_content


if __name__ == "__main__":
    md = main()
    # docs 경로에 저장
    docs_dir = Path(__file__).parent.parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)
    out_path = docs_dir / "backtest_results_vix.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"\nMarkdown 보고서 저장: {out_path}")
