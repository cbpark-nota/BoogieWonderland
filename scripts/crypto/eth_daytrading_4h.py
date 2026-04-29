#!/usr/bin/env python3
"""
ETH 4시간봉 데이 트레이딩 — A안 (ETH 단독 신호)
=================================================
btc_daytrading_4h.py의 strategy_v1~v10을 그대로 ETH 4h 가격에 적용.
거래비용 편도 0.05% (RT 0.1%) 통일.

데이터:
  · 캐시: scripts/crypto/data/eth_4h.csv  (Binance ETH/USDT 4h)
  · 기간: BTC 캐시와 동일 (2021-01-01 이후)

결과:
  · scripts/backtest/results/eth_4h/v{1..10}.json
  · docs/eth_4h_backtest_results_YYYYMMDD.md
"""

import argparse
import json
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

# btc_daytrading_4h의 지표/엔진/전략을 재사용
from btc_daytrading_4h import (
    STRATEGIES,
    add_indicators,
    run_backtest,
    calc_metrics,
    calc_period,
    _serialize_metrics,
)

warnings.filterwarnings("ignore")

CACHE_PATH         = Path("scripts/crypto/data/eth_4h.csv")
CACHE_MAX_AGE_HRS  = 12
RESULTS_DIR        = Path("scripts/backtest/results/eth_4h")
DOCS_DIR           = Path("docs")
FEE                = 0.001  # RT 0.1%


# ══════════════════════════════════════════════════════════════════════
# 1. ETH 데이터 수집 (BTC와 동일 패턴)
# ══════════════════════════════════════════════════════════════════════

def _fetch_binance(symbol: str, start_ms: int, end_ms: int) -> list:
    url = "https://api.binance.com/api/v3/klines"
    rows = []
    cur  = start_ms
    while cur < end_ms:
        try:
            r = requests.get(url, params={
                "symbol": symbol, "interval": "4h",
                "startTime": cur, "endTime": end_ms, "limit": 1000,
            }, timeout=15)
            r.raise_for_status()
            chunk = r.json()
        except Exception as e:
            print(f"    Binance API 오류: {e}")
            break
        if not chunk:
            break
        rows.extend(chunk)
        cur = chunk[-1][0] + 4 * 3600 * 1000
        time.sleep(0.05)
    return rows


def _rows_to_df(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "n_trades",
        "taker_base", "taker_quote", "ignore",
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time")[["open", "high", "low", "close", "volume"]].astype(float)
    return df[~df.index.duplicated(keep="first")].sort_index()


def get_eth_data_4h(
    start: str = "2021-01-01",
    refresh_cache: bool = False,
    cache_only: bool = False,
) -> pd.DataFrame:
    """Binance ETHUSDT 4h. 캐시 정책은 BTC와 동일.

    Fallback: Binance 실패 시 yfinance ETH-USD 1h → 4h 리샘플링 (캐시 저장 생략)
    """
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    now_ms = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)

    if cache_only:
        if not CACHE_PATH.exists():
            raise FileNotFoundError(f"캐시 없음: {CACHE_PATH}  (--cache-only)")
        df = pd.read_csv(CACHE_PATH, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True)
        return df

    if not refresh_cache and CACHE_PATH.exists():
        df_old = pd.read_csv(CACHE_PATH, index_col=0, parse_dates=True)
        df_old.index = pd.to_datetime(df_old.index, utc=True)
        if len(df_old) > 0:
            last_ms  = int(df_old.index[-1].timestamp() * 1000)
            age_hrs  = (now_ms - last_ms) / 3_600_000
            if age_hrs <= CACHE_MAX_AGE_HRS:
                return df_old
            inc_start = last_ms + 4 * 3600 * 1000
            try:
                rows = _fetch_binance("ETHUSDT", inc_start, now_ms)
                if rows:
                    df_new = _rows_to_df(rows)
                    df_m   = pd.concat([df_old, df_new])
                    df_m   = df_m[~df_m.index.duplicated(keep="last")].sort_index()
                    df_m.to_csv(CACHE_PATH)
                    return df_m
                return df_old
            except Exception as e:
                print(f"  ETH 증분 다운로드 실패: {e}  — 기존 캐시 사용")
                return df_old

    start_ms = int(pd.Timestamp(start).timestamp() * 1000)
    try:
        rows = _fetch_binance("ETHUSDT", start_ms, now_ms)
        if len(rows) > 200:
            df = _rows_to_df(rows)
            df.to_csv(CACHE_PATH)
            return df
    except Exception as e:
        print(f"  Binance 실패: {e}  — yfinance 1h 데이터로 대체")

    # ── Fallback: yfinance 1h → 4h 리샘플링 ──────────────────
    raw = yf.download("ETH-USD", period="730d", interval="1h",
                      progress=False, auto_adjust=True)
    raw.columns = [c[0].lower() if isinstance(c, tuple) else c.lower()
                   for c in raw.columns]
    raw = raw[["open", "high", "low", "close", "volume"]].dropna()

    df = raw.resample("4h", closed="left", label="left").agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna()

    df = df.loc[start:] if start else df
    return df


# ══════════════════════════════════════════════════════════════════════
# 2. JSON 저장 / 집계
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
        "mode":      "eth_self_signal",
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
    md_path = DOCS_DIR / f"eth_4h_backtest_results_{today}.md"
    lines = [
        "# ETH 4시간봉 백테스트 — A안 (ETH 단독 신호) V1~V10",
        "",
        f"> 생성일: {datetime.now().strftime('%Y-%m-%d')}  ",
        f"> 수수료: 매수 0.05% + 매도 0.05% (RT 0.1%)  ",
        f"> 데이터: Binance ETH/USDT 4h  ",
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
    print(f"  ETH A안 보고서 저장: {md_path}")


# ══════════════════════════════════════════════════════════════════════
# 3. CLI
# ══════════════════════════════════════════════════════════════════════

def run_single_version(version: str, refresh_cache=False, cache_only=False) -> None:
    if version not in STRATEGIES:
        raise ValueError(f"unknown: {version}  ({list(STRATEGIES)})")
    name, func = STRATEGIES[version]
    df = get_eth_data_4h("2021-01-01", refresh_cache=refresh_cache, cache_only=cache_only)
    df = add_indicators(df)
    eq, tr = run_backtest(df, func, fee_rate=FEE)
    m  = calc_metrics(eq, df.index, tr)
    pm = calc_period(eq, df.index)
    save_result(version, name, eq, tr, m, pm, df.index, fee_rate=FEE)
    print(
        f"[ETH-A {version}] {name}  "
        f"CAGR={m.get('cagr',0)*100:.1f}%  "
        f"MDD={m.get('mdd',0)*100:.1f}%  "
        f"샤프={m.get('sharpe',0):.2f}  "
        f"거래={m.get('trades_per_yr',0):.0f}회/년"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="ETH 4h A안 백테스트 (ETH 단독 신호)")
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

    # 인자 없으면 v1~v10 일괄 실행
    for v in [f"v{i}" for i in range(1, 11)]:
        run_single_version(v, a.refresh_cache, a.cache_only)
    aggregate_results()


if __name__ == "__main__":
    main()
