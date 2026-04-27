#!/usr/bin/env python3
"""
ETH 4h B안 — BTC 신호 기반 ETH 매매
======================================
btc_eth_correlation 분석 결과를 기반으로 자동 결정된 알고리즘:

* CCF 분석에서 모든 구간(전체/Bull/Bear) 최적 양수 lag = 0봉
  → "BTC 시그널 발생 → N봉 후 ETH 진입" 같은 lag 트레이딩은 효과 없음.
* Granger BTC→ETH는 ETH→BTC보다 훨씬 유의 (lag 5~12봉 모두 p<0.001).
* 동시(t=0) 상관 ≈ 0.84 (전체) — 강한 동조성.

따라서 B안 = "BTC strategy_vN의 position 시퀀스를 ETH 가격에 그대로 카피".
즉 BTC 4h 데이터로 strategy_v1~v10을 실행해 BTC 진입/청산 신호를 얻고,
같은 봉(t=0)의 ETH 가격에 동일 포지션을 적용한다.
* 매도 조건(SL/TP/MH): 각 BTC strategy 내부의 BTC 가격/ATR 기준 그대로 작동.
  ETH의 P&L은 ETH 가격 시계열로 계산 (수수료 RT 0.1%).

결과:
  scripts/backtest/results/eth_4h_btc_driven/v{1..10}.json
  docs/eth_4h_btc_driven_backtest_{YYYYMMDD}.md
"""

import argparse
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from btc_daytrading_4h import (
    STRATEGIES,
    add_indicators,
    calc_metrics,
    calc_period,
    get_btc_data_4h,
    _serialize_metrics,
)
from eth_daytrading_4h import get_eth_data_4h

warnings.filterwarnings("ignore")

RESULTS_DIR = Path("scripts/backtest/results/eth_4h_btc_driven")
DOCS_DIR    = Path("docs")
FEE         = 0.001  # RT 0.1%
LAG_BARS    = 0      # CCF 분석 결과 (모든 구간에서 최적 양수 lag = 0)


# ══════════════════════════════════════════════════════════════════════
# 1. BTC position → ETH P&L 백테스트 엔진
# ══════════════════════════════════════════════════════════════════════

def run_backtest_eth_from_btc(
    btc_positions: np.ndarray,
    eth_close: np.ndarray,
    eth_dates: pd.DatetimeIndex,
    fee_rate: float = FEE,
    lag_bars: int = 0,
) -> tuple[np.ndarray, pd.DataFrame]:
    """
    BTC strategy의 position 시퀀스를 ETH 가격에 적용해 P&L 산출.

    lag_bars > 0: BTC pos[t] → ETH pos[t + lag_bars]
    lag_bars = 0: 동시 진입
    """
    n        = len(eth_close)
    half_fee = fee_rate / 2.0
    equity   = np.ones(n, dtype=float)

    pos = np.zeros(n, dtype=int)
    if lag_bars == 0:
        pos[:] = btc_positions[:n]
    else:
        pos[lag_bars:] = btc_positions[:n - lag_bars]

    trade_log   = []
    entry_price = np.nan
    entry_pos   = 0
    entry_idx   = 0

    for i in range(1, n):
        prev_p = pos[i - 1]
        curr_p = pos[i]
        ret    = eth_close[i] / eth_close[i - 1]
        if prev_p == 1:
            equity[i] = equity[i - 1] * ret
        elif prev_p == -1:
            equity[i] = equity[i - 1] * (2.0 - ret)
        else:
            equity[i] = equity[i - 1]

        if prev_p != curr_p:
            if prev_p != 0:
                equity[i] *= (1.0 - half_fee)
                if not np.isnan(entry_price):
                    if entry_pos == 1:
                        trade_ret = eth_close[i] / entry_price - 1
                    else:
                        trade_ret = entry_price / eth_close[i] - 1
                    trade_log.append(dict(
                        entry_date=eth_dates[entry_idx],
                        exit_date=eth_dates[i],
                        direction="long" if entry_pos == 1 else "short",
                        entry_price=entry_price,
                        exit_price=eth_close[i],
                        gross_return=trade_ret,
                        hold_bars=i - entry_idx,
                        hold_days=(i - entry_idx) / 6.0,
                    ))
            if curr_p != 0:
                equity[i] *= (1.0 - half_fee)
                entry_price = eth_close[i]
                entry_pos   = curr_p
                entry_idx   = i
            else:
                entry_price = np.nan
                entry_pos   = 0

    return equity, pd.DataFrame(trade_log)


# ══════════════════════════════════════════════════════════════════════
# 2. 데이터 정렬: BTC와 ETH 인덱스 교집합으로 정렬
# ══════════════════════════════════════════════════════════════════════

def load_aligned(refresh_cache=False, cache_only=False) -> tuple[pd.DataFrame, pd.DataFrame]:
    btc = get_btc_data_4h("2021-01-01", refresh_cache=refresh_cache, cache_only=cache_only)
    eth = get_eth_data_4h("2021-01-01", refresh_cache=refresh_cache, cache_only=cache_only)
    common = btc.index.intersection(eth.index)
    return btc.loc[common], eth.loc[common]


# ══════════════════════════════════════════════════════════════════════
# 3. JSON 저장 / 집계
# ══════════════════════════════════════════════════════════════════════

def save_result(version: str, name: str, equity: np.ndarray,
                trades_df: pd.DataFrame, metrics: dict, period_metrics: dict,
                df_dates: pd.DatetimeIndex, fee_rate: float = FEE) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{version}.json"
    result = {
        "version":   version,
        "name":      name,
        "asset":     "ETH",
        "mode":      "btc_driven",
        "lag_bars":  LAG_BARS,
        "run_at":    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fee_rate":  fee_rate,
        "period": {
            "start": str(df_dates[0].date()),
            "end":   str(df_dates[-1].date()),
            "bars":  len(df_dates),
        },
        "metrics": _serialize_metrics(metrics),
        "period_breakdown": {
            k: {"cagr": float(v["cagr"]), "mdd": float(v["mdd"])}
            for k, v in period_metrics.items()
        },
        "trades_count": int(metrics.get("n_trades", len(trades_df))),
    }
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))


def aggregate_results() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    records = {}
    for v in [f"v{i}" for i in range(1, 11)]:
        p = RESULTS_DIR / f"{v}.json"
        if p.exists():
            records[v] = json.loads(p.read_text())

    if not records:
        print("집계할 결과 없음.")
        return

    today   = datetime.now().strftime("%Y%m%d")
    md_path = DOCS_DIR / f"eth_4h_btc_driven_backtest_{today}.md"
    lines = [
        "# ETH 4시간봉 백테스트 — B안 (BTC 신호 기반) V1~V10",
        "",
        f"> 생성일: {datetime.now().strftime('%Y-%m-%d')}  ",
        f"> 수수료: 매수 0.05% + 매도 0.05% (RT 0.1%)  ",
        f"> 알고리즘: BTC vN strategy의 position을 ETH 가격에 lag={LAG_BARS}봉 적용  ",
        "",
        "## 전략별 성과",
        "",
        "| 버전 | 전략명 | CAGR | MDD | 샤프 | 거래/년 | 승률 | 주간≥1% |",
        "|------|--------|-----:|----:|-----:|-------:|----:|--------:|",
    ]
    for v, r in records.items():
        m = r.get("metrics", {})
        lines.append(
            f"| {v} | {r.get('name','')} | "
            f"{m.get('cagr',0)*100:.1f}% | {m.get('mdd',0)*100:.1f}% | "
            f"{m.get('sharpe',0):.2f} | {m.get('trades_per_yr',0):.0f} | "
            f"{m.get('win_rate',0)*100:.1f}% | {m.get('weekly_1pct',0)*100:.1f}% |"
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ETH B안 보고서 저장: {md_path}")


# ══════════════════════════════════════════════════════════════════════
# 4. CLI
# ══════════════════════════════════════════════════════════════════════

def run_single_version(version: str, refresh_cache=False, cache_only=False) -> None:
    if version not in STRATEGIES:
        raise ValueError(f"unknown: {version}  ({list(STRATEGIES)})")
    name, func = STRATEGIES[version]

    btc, eth = load_aligned(refresh_cache, cache_only)
    btc_ind  = add_indicators(btc)
    btc_sig  = func(btc_ind.copy())
    btc_pos  = btc_sig["position"].values

    eq, tr = run_backtest_eth_from_btc(
        btc_pos, eth["close"].values, eth.index, fee_rate=FEE, lag_bars=LAG_BARS,
    )
    m  = calc_metrics(eq, eth.index, tr)
    pm = calc_period(eq, eth.index)
    save_result(version, name, eq, tr, m, pm, eth.index, fee_rate=FEE)
    print(
        f"[ETH-B {version}] {name}  "
        f"CAGR={m.get('cagr',0)*100:.1f}%  "
        f"MDD={m.get('mdd',0)*100:.1f}%  "
        f"샤프={m.get('sharpe',0):.2f}  "
        f"거래={m.get('trades_per_yr',0):.0f}회/년"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="ETH 4h B안 백테스트 (BTC 신호 기반)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--version", metavar="vN", help="개별 버전 (v1~v10)")
    g.add_argument("--aggregate", action="store_true", help="vN.json 집계")
    p.add_argument("--refresh-cache", action="store_true")
    p.add_argument("--cache-only",    action="store_true")
    a = p.parse_args()

    if a.version:
        run_single_version(a.version, a.refresh_cache, a.cache_only)
        return
    if a.aggregate:
        aggregate_results()
        return

    for v in [f"v{i}" for i in range(1, 11)]:
        run_single_version(v, a.refresh_cache, a.cache_only)
    aggregate_results()


if __name__ == "__main__":
    main()
