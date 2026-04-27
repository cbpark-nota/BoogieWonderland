#!/usr/bin/env python3
"""
ETH V10 시그널을 계산하고 screening JSON 파일의 eth_signal 필드를 업데이트한다.

ETH V10 = B안 V10: BTC strategy_v10의 position 시퀀스를 ETH 가격에 그대로 적용한다.
근거: docs/backtest_eth_strategies_comparison.md
  · CCF 분석 — 모든 구간 최적 양수 lag = 0봉
  · Granger BTC→ETH 강한 예측력 (p < 0.001)
  · B안 V10 CAGR +45.0%, MDD -33.2%, 샤프 1.03 (1순위 추천)

따라서 BTC V10 신호(buy/hold)와 동일한 시그널을 사용하되,
가격은 같은 봉(t=0)의 ETH 가격을 표시한다.

실행:
    python scripts/crypto/update_eth_signal.py --output frontend/web/data/
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

# update_btc_signal.py의 _infer_reason 재사용 (ETH V10도 동일한 BTC 진입 조건 기반)
from update_btc_signal import _infer_reason  # noqa: E402


def calculate_eth_signal() -> dict:
    """ETH V10 (B안) 4시간봉 현재 시그널 계산.

    BTC strategy_v10의 신호를 ETH 가격에 동시 적용한다 (lag=0).
    """
    try:
        from btc_daytrading_4h import (
            get_btc_data_4h,
            add_indicators,
            strategy_v10,
        )
        from eth_daytrading_4h import get_eth_data_4h
    except ImportError as e:
        return {
            "signal": "hold",
            "price": None,
            "reason": f"모듈 로드 실패: {e}",
            "strategy": "V10",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    try:
        btc = get_btc_data_4h("2024-01-01")
        eth = get_eth_data_4h("2024-01-01")
        # BTC와 ETH 인덱스 교집합으로 정렬 (B안 backtest와 동일한 방식)
        common = btc.index.intersection(eth.index)
        btc = btc.loc[common]
        eth = eth.loc[common]

        btc_ind = add_indicators(btc)
        btc_sig = strategy_v10(btc_ind.copy())

        last_pos       = int(btc_sig["position"].iloc[-1])
        last_eth_close = float(eth["close"].iloc[-1])
        last_time      = eth.index[-1].isoformat()

        row   = btc_sig.iloc[-1]
        ma50  = float(row.get("ma50", float("nan")))
        ma200 = float(row.get("ma200", float("nan")))
        adx   = float(row.get("adx", 0.0))
        last_btc_close = float(btc["close"].iloc[-1])

        if ma50 > ma200 and last_btc_close > ma50 and adx > 13:
            regime = "bull"
        elif adx < 13:
            regime = "sideways"
        else:
            regime = "neutral"

        if last_pos == 1:
            pos_series = btc_sig["position"]
            entry_idx = None
            for i in range(len(pos_series) - 1, 0, -1):
                if pos_series.iloc[i] == 1 and pos_series.iloc[i - 1] == 0:
                    entry_idx = i
                    break
            reason = _infer_reason(btc_sig, entry_idx) if entry_idx is not None else "포지션 보유 중"
            return {
                "signal": "buy",
                "price": round(last_eth_close, 2),
                "reason": reason,
                "regime": regime,
                "strategy": "V10",
                "timestamp": last_time,
            }
        else:
            return {
                "signal": "hold",
                "price": round(last_eth_close, 2),
                "reason": "BTC V10 매수 조건 미충족 — 현금 보유",
                "regime": regime,
                "strategy": "V10",
                "timestamp": last_time,
            }

    except Exception as e:
        return {
            "signal": "hold",
            "price": None,
            "reason": f"시그널 계산 실패: {e}",
            "strategy": "V10",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }


def _patch_json(path: Path, eth_signal: dict) -> bool:
    if not path.exists():
        return False
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["eth_signal"] = eth_signal
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="ETH V10 신호 계산 및 JSON 업데이트")
    parser.add_argument(
        "--output", type=str, default="frontend/web/data/",
        help="JSON 출력 디렉토리 (기본: frontend/web/data/)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    eth_signal = calculate_eth_signal()

    targets = [
        output_dir / "screening_latest.json",
        output_dir / "screening_strategies.json",
    ]
    updated = [p.name for p in targets if _patch_json(p, eth_signal)]

    signal    = eth_signal.get("signal", "N/A")
    price     = eth_signal.get("price")
    ts        = str(eth_signal.get("timestamp", ""))[:19]
    regime    = eth_signal.get("regime", "")
    price_str = f"${price:,.2f}" if isinstance(price, (int, float)) else "N/A"
    print(f"ETH V10: {signal} | {price_str} | regime={regime} | {ts} | 업데이트 파일: {updated}")


if __name__ == "__main__":
    main()
