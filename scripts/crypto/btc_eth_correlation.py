#!/usr/bin/env python3
"""
BTC ↔ ETH 상관관계 분석 (4시간봉)
==================================
1) Cross-correlation function (CCF): BTC ret → ETH ret, lag -24~+24봉
2) Granger causality: BTC→ETH, ETH→BTC, lag 1~12봉
3) 상승기/하락기 분리 분석: BTC 50일 MA 기준
4) Rolling correlation: 30일/90일/365일
5) 변동성 spillover: BTC vol → ETH vol

결과:
  docs/research/analysis_btc_eth_correlation.md
  docs/figures/btc_eth_*.png
  scripts/backtest/results/btc_eth_correlation.json (B안 전략 자동결정용)
"""

import json
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import grangercausalitytests

warnings.filterwarnings("ignore")

# ── 경로 ─────────────────────────────────────────────────
BTC_CACHE  = Path("scripts/crypto/data/btc_4h.csv")
ETH_CACHE  = Path("scripts/crypto/data/eth_4h.csv")
DOCS_DIR   = Path("docs/research")
FIG_DIR    = Path("docs/figures")
JSON_OUT   = Path("scripts/backtest/results/btc_eth_correlation.json")

BARS_PER_DAY = 6  # 4h봉
MAX_LAG_BARS = 24  # ±4일


# ══════════════════════════════════════════════════════════════════════
# 1. 데이터 로드 & 정렬
# ══════════════════════════════════════════════════════════════════════

def load_aligned() -> pd.DataFrame:
    btc = pd.read_csv(BTC_CACHE, index_col=0, parse_dates=True)
    eth = pd.read_csv(ETH_CACHE, index_col=0, parse_dates=True)
    btc.index = pd.to_datetime(btc.index, utc=True)
    eth.index = pd.to_datetime(eth.index, utc=True)
    df = pd.DataFrame({
        "btc_close": btc["close"],
        "eth_close": eth["close"],
    }).dropna()
    df["btc_ret"] = df["btc_close"].pct_change()
    df["eth_ret"] = df["eth_close"].pct_change()
    df["btc_logret"] = np.log(df["btc_close"]).diff()
    df["eth_logret"] = np.log(df["eth_close"]).diff()
    return df.dropna()


# ══════════════════════════════════════════════════════════════════════
# 2. CCF (Cross-correlation function)
# ══════════════════════════════════════════════════════════════════════

def cross_corr(x: pd.Series, y: pd.Series, max_lag: int) -> dict:
    """
    lag>0 : x leads y by `lag` bars  (i.e., corr(x[t], y[t+lag]))
    lag<0 : y leads x by |lag| bars
    """
    out = {}
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            c = x.corr(y.shift(-lag))
        else:
            c = x.corr(y.shift(-lag))
        out[lag] = c
    return out


def plot_ccf(ccf: dict, title: str, path: Path) -> None:
    lags = sorted(ccf.keys())
    vals = [ccf[l] for l in lags]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(lags, vals, color=["#1f77b4" if l != 0 else "#d62728" for l in lags])
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xlabel("lag (4h bars)  >0: BTC leads ETH")
    ax.set_ylabel("correlation")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════
# 3. Granger causality
# ══════════════════════════════════════════════════════════════════════

def granger(df: pd.DataFrame, cause: str, effect: str, max_lag: int = 12) -> pd.DataFrame:
    """
    H0: cause does NOT Granger-cause effect.
    p<0.05 → reject H0 → cause Granger-causes effect.
    """
    data = df[[effect, cause]].dropna()
    res  = grangercausalitytests(data, maxlag=max_lag, verbose=False)
    rows = []
    for lag, r in res.items():
        f_p = r[0]["ssr_ftest"][1]
        rows.append(dict(lag=lag, p_value=f_p))
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════
# 4. 상승기 / 하락기 분리 (BTC 50일 MA 기준)
# ══════════════════════════════════════════════════════════════════════

def regime_split(df: pd.DataFrame) -> pd.DataFrame:
    ma_period = 50 * BARS_PER_DAY  # 50일 = 300봉
    df = df.copy()
    df["btc_ma50d"] = df["btc_close"].rolling(ma_period).mean()
    df["regime"] = np.where(df["btc_close"] > df["btc_ma50d"], "bull", "bear")
    return df


# ══════════════════════════════════════════════════════════════════════
# 5. Rolling correlation
# ══════════════════════════════════════════════════════════════════════

def rolling_corr(df: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for d in windows:
        win = d * BARS_PER_DAY
        out[f"corr_{d}d"] = df["btc_logret"].rolling(win).corr(df["eth_logret"])
    return out


def plot_rolling_corr(rc: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 4))
    for col in rc.columns:
        ax.plot(rc.index, rc[col], label=col, lw=0.9)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("rolling correlation (logret)")
    ax.set_title("BTC ↔ ETH rolling correlation")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════
# 6. 변동성 spillover (BTC vol(20d) → ETH ret 다음봉)
# ══════════════════════════════════════════════════════════════════════

def vol_spillover(df: pd.DataFrame) -> dict:
    win = 20 * BARS_PER_DAY  # 20일 = 120봉
    btc_vol = df["btc_logret"].rolling(win).std()
    eth_vol = df["eth_logret"].rolling(win).std()
    out = {
        "corr_vol_levels":     btc_vol.corr(eth_vol),
        "corr_btc_vol_lead_1": btc_vol.shift(1).corr(eth_vol),
        "corr_btc_vol_lead_6": btc_vol.shift(6).corr(eth_vol),  # 1일
    }
    return out


# ══════════════════════════════════════════════════════════════════════
# 7. 메인: 분석 실행
# ══════════════════════════════════════════════════════════════════════

def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)

    df = load_aligned()
    df = regime_split(df)

    # ── 1. CCF (전체 / Bull / Bear) ─────────────────────────
    ccf_all  = cross_corr(df["btc_logret"], df["eth_logret"], MAX_LAG_BARS)
    ccf_bull = cross_corr(
        df.loc[df["regime"] == "bull", "btc_logret"],
        df.loc[df["regime"] == "bull", "eth_logret"], MAX_LAG_BARS)
    ccf_bear = cross_corr(
        df.loc[df["regime"] == "bear", "btc_logret"],
        df.loc[df["regime"] == "bear", "eth_logret"], MAX_LAG_BARS)

    plot_ccf(ccf_all,  "CCF: BTC → ETH (logret, all)",   FIG_DIR / "btc_eth_ccf_all.png")
    plot_ccf(ccf_bull, "CCF: BTC → ETH (BTC bull MA50d)", FIG_DIR / "btc_eth_ccf_bull.png")
    plot_ccf(ccf_bear, "CCF: BTC → ETH (BTC bear MA50d)", FIG_DIR / "btc_eth_ccf_bear.png")

    def best_pos_lag(ccf: dict) -> tuple[int, float]:
        pos = {l: v for l, v in ccf.items() if l >= 0 and not pd.isna(v)}
        if not pos:
            return 0, 0.0
        best = max(pos, key=pos.get)
        return best, pos[best]

    best_all  = best_pos_lag(ccf_all)
    best_bull = best_pos_lag(ccf_bull)
    best_bear = best_pos_lag(ccf_bear)

    # ── 2. Granger ──────────────────────────────────────────
    g_btc_eth = granger(df, cause="btc_logret", effect="eth_logret", max_lag=12)
    g_eth_btc = granger(df, cause="eth_logret", effect="btc_logret", max_lag=12)

    # ── 3. Rolling correlation ──────────────────────────────
    rc = rolling_corr(df, [30, 90, 365])
    plot_rolling_corr(rc, FIG_DIR / "btc_eth_rolling_corr.png")

    rc_summary = {
        "corr_30d_mean":  rc["corr_30d"].mean(),
        "corr_30d_min":   rc["corr_30d"].min(),
        "corr_30d_max":   rc["corr_30d"].max(),
        "corr_90d_mean":  rc["corr_90d"].mean(),
        "corr_365d_mean": rc["corr_365d"].mean(),
    }

    # ── 4. 변동성 spillover ─────────────────────────────────
    vsp = vol_spillover(df)

    # ── 5. 동시 상관 (전체 + 시기별) ─────────────────────
    contemp = {
        "all":     df["btc_logret"].corr(df["eth_logret"]),
        "2021_22": df.loc["2021":"2022", "btc_logret"].corr(df.loc["2021":"2022", "eth_logret"]),
        "2023_24": df.loc["2023":"2024", "btc_logret"].corr(df.loc["2023":"2024", "eth_logret"]),
        "2025_now": df.loc["2025":, "btc_logret"].corr(df.loc["2025":, "eth_logret"]),
        "bull":    df.loc[df["regime"] == "bull", "btc_logret"].corr(df.loc[df["regime"] == "bull", "eth_logret"]),
        "bear":    df.loc[df["regime"] == "bear", "btc_logret"].corr(df.loc[df["regime"] == "bear", "eth_logret"]),
    }

    # ══════════════════════════════════════════════════════════════════
    # 결과 직렬화 (B안 전략에서 사용)
    # ══════════════════════════════════════════════════════════════════
    result = {
        "period": {
            "start": str(df.index[0].date()),
            "end":   str(df.index[-1].date()),
            "bars":  len(df),
        },
        "contemporaneous_corr": {k: float(v) for k, v in contemp.items()},
        "ccf_best_positive_lag": {
            "all":  {"lag": int(best_all[0]),  "corr": float(best_all[1])},
            "bull": {"lag": int(best_bull[0]), "corr": float(best_bull[1])},
            "bear": {"lag": int(best_bear[0]), "corr": float(best_bear[1])},
        },
        "ccf_full": {
            "all":  {str(k): float(v) for k, v in ccf_all.items()},
            "bull": {str(k): float(v) for k, v in ccf_bull.items()},
            "bear": {str(k): float(v) for k, v in ccf_bear.items()},
        },
        "granger_btc_to_eth": g_btc_eth.to_dict(orient="records"),
        "granger_eth_to_btc": g_eth_btc.to_dict(orient="records"),
        "rolling_corr_summary": {k: float(v) for k, v in rc_summary.items()},
        "vol_spillover": {k: float(v) for k, v in vsp.items()},
    }
    JSON_OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    # ══════════════════════════════════════════════════════════════════
    # Markdown 보고서
    # ══════════════════════════════════════════════════════════════════
    md = []
    md.append("# BTC ↔ ETH 상관관계 분석 (4시간봉)\n")
    md.append(f"> 기간: {df.index[0].date()} ~ {df.index[-1].date()}  ")
    md.append(f"> 봉 수: {len(df):,} (4h)  ")
    md.append(f"> 거래소: Binance USDT 페어  \n")
    md.append("---\n")

    md.append("## 1. 동시(contemporaneous) 상관계수\n")
    md.append("| 구간 | 상관계수 |")
    md.append("|------|---------:|")
    md.append(f"| 전체 ({df.index[0].date()}~{df.index[-1].date()}) | {contemp['all']:.4f} |")
    md.append(f"| 2021–2022 (불장→폭락) | {contemp['2021_22']:.4f} |")
    md.append(f"| 2023–2024 (회복·신고가) | {contemp['2023_24']:.4f} |")
    md.append(f"| 2025–현재 (OOS) | {contemp['2025_now']:.4f} |")
    md.append(f"| BTC Bull(>50d MA) | {contemp['bull']:.4f} |")
    md.append(f"| BTC Bear(<50d MA) | {contemp['bear']:.4f} |")
    md.append("")

    md.append("## 2. CCF (cross-correlation function): BTC → ETH\n")
    md.append("lag = +N: BTC 수익률이 N봉(4h × N) 앞서 발생할 때 ETH 수익률과의 상관.\n")
    md.append("| 구간 | 최적(+) lag | 해당 lag corr | lag=0 corr |")
    md.append("|------|-----------:|--------------:|-----------:|")
    md.append(f"| 전체 | {best_all[0]} 봉 ({best_all[0]*4}h) | {best_all[1]:.4f} | {ccf_all[0]:.4f} |")
    md.append(f"| Bull | {best_bull[0]} 봉 ({best_bull[0]*4}h) | {best_bull[1]:.4f} | {ccf_bull[0]:.4f} |")
    md.append(f"| Bear | {best_bear[0]} 봉 ({best_bear[0]*4}h) | {best_bear[1]:.4f} | {ccf_bear[0]:.4f} |")
    md.append("")
    md.append("**그래프**: `figures/btc_eth_ccf_all.png`, `_bull.png`, `_bear.png`\n")

    md.append("### 상위 lag (전체 구간) — 상위 6개 양수 lag\n")
    pos_sorted = sorted(
        [(l, v) for l, v in ccf_all.items() if l >= 0 and not pd.isna(v)],
        key=lambda x: -x[1])[:6]
    md.append("| lag (봉) | lag (시간) | corr |")
    md.append("|---------:|-----------:|-----:|")
    for lag, v in pos_sorted:
        md.append(f"| {lag} | {lag*4}h | {v:.4f} |")
    md.append("")

    md.append("## 3. Granger causality (lag 1~12봉)\n")
    md.append("H0: 원인변수가 결과변수를 Granger-cause 하지 않는다. p<0.05 → 인과성 인정.\n")
    md.append("### BTC → ETH\n")
    md.append("| lag (봉) | p-value | 유의 |")
    md.append("|---------:|--------:|:----:|")
    for r in g_btc_eth.itertuples(index=False):
        md.append(f"| {r.lag} | {r.p_value:.4g} | {'✓' if r.p_value < 0.05 else '·'} |")
    md.append("")
    md.append("### ETH → BTC\n")
    md.append("| lag (봉) | p-value | 유의 |")
    md.append("|---------:|--------:|:----:|")
    for r in g_eth_btc.itertuples(index=False):
        md.append(f"| {r.lag} | {r.p_value:.4g} | {'✓' if r.p_value < 0.05 else '·'} |")
    md.append("")

    md.append("## 4. Rolling correlation\n")
    md.append("| window | mean | min | max |")
    md.append("|--------|-----:|----:|----:|")
    md.append(f"| 30일 ({30*BARS_PER_DAY}봉)   | {rc_summary['corr_30d_mean']:.4f} | {rc_summary['corr_30d_min']:.4f} | {rc_summary['corr_30d_max']:.4f} |")
    md.append(f"| 90일 ({90*BARS_PER_DAY}봉)   | {rc_summary['corr_90d_mean']:.4f} | – | – |")
    md.append(f"| 365일 ({365*BARS_PER_DAY}봉) | {rc_summary['corr_365d_mean']:.4f} | – | – |")
    md.append("")
    md.append("**그래프**: `figures/btc_eth_rolling_corr.png`\n")

    md.append("## 5. 변동성 spillover (20일 logret std)\n")
    md.append("| 측정 | 상관계수 |")
    md.append("|------|--------:|")
    md.append(f"| BTC vol vs ETH vol (동시)     | {vsp['corr_vol_levels']:.4f} |")
    md.append(f"| BTC vol(t-1) vs ETH vol(t)    | {vsp['corr_btc_vol_lead_1']:.4f} |")
    md.append(f"| BTC vol(t-6=1일) vs ETH vol(t)| {vsp['corr_btc_vol_lead_6']:.4f} |")
    md.append("")

    md.append("## 6. 핵심 답변\n")
    g_min_p_btc_eth = g_btc_eth["p_value"].min()
    g_min_p_eth_btc = g_eth_btc["p_value"].min()
    md.append(f"- **상승기 ETH lag**: BTC가 약 **{best_bull[0]}봉({best_bull[0]*4}h)** 앞섬, 해당 lag corr={best_bull[1]:.3f}, lag=0 corr={ccf_bull[0]:.3f}. "
              "→ lag=0 상관이 양수 lag 최댓값과 거의 같으면 ETH가 동시에 따라가는 것으로 해석.")
    md.append(f"- **하락기 ETH lag**: BTC가 약 **{best_bear[0]}봉({best_bear[0]*4}h)** 앞섬, 해당 lag corr={best_bear[1]:.3f}, lag=0 corr={ccf_bear[0]:.3f}.")
    md.append(f"- **Granger 인과성**: BTC→ETH 최소 p-value={g_min_p_btc_eth:.4g}, ETH→BTC 최소 p-value={g_min_p_eth_btc:.4g}. "
              f"{'BTC가 ETH를 통계적으로 예측한다고 볼 수 있음 (p<0.05)' if g_min_p_btc_eth < 0.05 else '유의하지 않음'}.")
    md.append(f"- **시간 변동**: rolling 30d corr {rc_summary['corr_30d_min']:.3f}~{rc_summary['corr_30d_max']:.3f} 범위, "
              f"평균 {rc_summary['corr_30d_mean']:.3f}. 365d 평균 {rc_summary['corr_365d_mean']:.3f}로 장기적으로 매우 강한 양의 상관 유지.")
    md.append("")

    md.append("## 7. B안 전략 결정 근거\n")
    md.append("4h 단위에서 BTC ↔ ETH 동시 상관이 매우 강하고(전체 ≈ "
              f"{contemp['all']:.2f}) 양수 lag로 갈수록 corr가 단조 감소하는 패턴이라면, "
              "ETH는 BTC와 거의 동시에 움직이며 'BTC 시그널 발생 후 N봉 lag 진입' 같은 단순 lag 트레이딩은 의미가 약함. "
              "오히려 BTC 추세/레짐 필터를 ETH 자체 신호와 결합하는 것이 합리적.\n")
    if best_bull[0] >= 1 and best_bull[1] - ccf_bull[0] > 0.02:
        md.append("- 단, 상승기에서 lag>0 corr이 lag=0 보다 의미 있게 크다면 lag-N 진입을 보조 시그널로 사용.")
    md.append("")
    md.append("**B안 v1~v10 알고리즘 골격**:")
    md.append("1. BTC 4h 데이터에 대해 BTC vN 전략의 진입 신호를 계산.")
    md.append("2. ETH 4h 데이터에 동일 진입 신호를 계산 (자체 신호).")
    md.append("3. **BTC 신호 + ETH 자체 신호** 모두 만족할 때만 ETH 매수/매도 — 즉 BTC 추세를 게이트로 사용.")
    md.append(f"4. 최적 lag(전체={best_all[0]}봉, bull={best_bull[0]}봉, bear={best_bear[0]}봉)가 0이면 동시 진입, >0이면 lag봉 후 진입.")
    md.append("5. BTC 레짐(50d MA 기준)이 bear일 때 ETH 진입 차단 (롱 전용 게이트).")
    md.append("6. 매도 조건은 A안과 동일 (각 vN의 SL/TP/MH 그대로).")
    md.append("")

    out_md = DOCS_DIR / "analysis_btc_eth_correlation.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"correlation analysis → {out_md}")
    print(f"  contemp corr (all)  = {contemp['all']:.4f}")
    print(f"  best lag (bull)     = {best_bull[0]} bars (corr {best_bull[1]:.4f})")
    print(f"  best lag (bear)     = {best_bear[0]} bars (corr {best_bear[1]:.4f})")
    print(f"  granger BTC→ETH min p = {g_min_p_btc_eth:.4g}")
    print(f"  granger ETH→BTC min p = {g_min_p_eth_btc:.4g}")


if __name__ == "__main__":
    main()
