#!/usr/bin/env python3
"""
BTC V10 신호를 계산하고 screening JSON 파일의 btc_signal 필드를 업데이트한다.

screening_latest.json, screening_strategies.json의 btc_signal 필드를 최신 신호로 교체한다.
btc_daytrading_4h.py의 strategy_v10을 직접 사용하므로 screener 의존성 없음.

실행:
    python scripts/crypto/update_btc_signal.py --output frontend/web/data/
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# btc_daytrading_4h.py가 같은 디렉토리에 있음
sys.path.insert(0, str(Path(__file__).parent))

_ETYPE_LABEL = {
    "sq":       "Squeeze Release — 스퀴즈 해제 + 모멘텀 상승",
    "sqm":      "Squeeze 조기진입 — Squeeze ON + 강한 모멘텀",
    "ema":      "EMA 골든크로스 — EMA20 > EMA50 돌파",
    "pullback": "RSI 눌림목 매수",
    "vwap":     "VWAP 이탈 회귀",
    "bb":       "BB 상단 돌파 — 볼린저 밴드 브레이크아웃",
    "range":    "레인지 하단 매수",
}


def _infer_reason(df: pd.DataFrame, entry_idx: int) -> str:
    """진입 시점의 신호 종류를 지표로부터 추정한다."""
    if entry_idx < 1:
        return "V10 진입 조건 충족"

    row  = df.iloc[entry_idx]
    prev = df.iloc[entry_idx - 1]

    ma50   = float(row.get("ma50", float("nan")))
    ma200  = float(row.get("ma200", float("nan")))
    adx    = float(row.get("adx", 0.0))
    rsi    = float(row.get("rsi14", float("nan")))
    mom    = float(row.get("sq_mom", float("nan")))
    dm     = float(row.get("sq_mom_delta", float("nan")))
    rel    = bool(row.get("sq_release", False))
    sq_on  = bool(row.get("sq_on", False))
    vd     = float(row.get("vwap_dev", float("nan")))
    bb_up  = float(row.get("bb_upper", float("nan")))
    ema20  = float(row.get("ema20", float("nan")))
    ema50v = float(row.get("ema50", float("nan")))
    wslope = float(row.get("weekly_slope", 0.0))
    rpos   = float(row.get("range_pos", float("nan")))
    close  = float(row.get("close", float("nan")))

    mom_series = df["sq_mom"].fillna(0)
    mom_std = float(mom_series.iloc[max(0, entry_idx - 60):entry_idx].std())

    ema_cross = (
        ema20 > ema50v
        and float(prev.get("ema20", float("nan"))) <= float(prev.get("ema50", float("nan")))
    )
    w_up = wslope > 0.001

    if ma50 > ma200 and close > ma50 and adx > 13:
        regime = "bull"
    elif adx < 13:
        regime = "sideways"
    else:
        regime = "neutral"

    if regime == "bull":
        if rel and mom > 0 and dm > 0:
            return _ETYPE_LABEL["sq"]
        if sq_on and mom_std > 0 and mom > 0.38 * mom_std and dm > 0 and rsi < 70:
            return _ETYPE_LABEL["sqm"]
        if ema_cross and adx > 13:
            return _ETYPE_LABEL["ema"]
        if rsi < 49 and w_up and adx > 13:
            return f"RSI 눌림목 — RSI {rsi:.0f}, 상승추세 포착"
        if not np.isnan(vd) and vd < -0.016:
            return f"VWAP 이탈 회귀 — VWAP 대비 {vd * 100:.1f}% 하락"
        if (
            not np.isnan(bb_up)
            and float(prev.get("close", bb_up)) <= float(prev.get("bb_upper", bb_up))
            and close > bb_up
        ):
            return _ETYPE_LABEL["bb"]
    elif regime == "sideways":
        if not np.isnan(rpos) and rpos < 0.30 and rsi < 50:
            return f"레인지 하단 매수 — 레인지 포지션 {rpos * 100:.0f}%"
    elif regime == "neutral":
        if ema_cross and adx > 13:
            return "Neutral EMA 크로스 — 추세 전환 감지"

    return "V10 진입 조건 충족"


def calculate_btc_signal() -> dict:
    """BTC V10 4시간봉 현재 시그널 계산.

    btc_daytrading_4h.py의 get_btc_data_4h, add_indicators, strategy_v10을 사용한다.
    screener 의존성 없음.
    """
    try:
        from btc_daytrading_4h import get_btc_data_4h, add_indicators, strategy_v10
    except ImportError as e:
        return {
            "signal": "hold",
            "price": None,
            "reason": f"모듈 로드 실패: {e}",
            "strategy": "V10",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    try:
        df = get_btc_data_4h("2024-01-01")
        df = add_indicators(df)
        df = strategy_v10(df.copy())

        last_pos   = int(df["position"].iloc[-1])
        last_close = float(df["close"].iloc[-1])
        last_time  = df.index[-1].isoformat()

        row   = df.iloc[-1]
        ma50  = float(row.get("ma50", float("nan")))
        ma200 = float(row.get("ma200", float("nan")))
        adx   = float(row.get("adx", 0.0))

        if ma50 > ma200 and last_close > ma50 and adx > 13:
            regime = "bull"
        elif adx < 13:
            regime = "sideways"
        else:
            regime = "neutral"

        if last_pos == 1:
            pos_series = df["position"]
            entry_idx = None
            for i in range(len(pos_series) - 1, 0, -1):
                if pos_series.iloc[i] == 1 and pos_series.iloc[i - 1] == 0:
                    entry_idx = i
                    break
            reason = _infer_reason(df, entry_idx) if entry_idx is not None else "포지션 보유 중"
            return {
                "signal": "buy",
                "price": round(last_close, 2),
                "reason": reason,
                "regime": regime,
                "strategy": "V10",
                "timestamp": last_time,
            }
        else:
            return {
                "signal": "hold",
                "price": round(last_close, 2),
                "reason": "매수 조건 미충족 — 현금 보유",
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


def _patch_json(path: Path, btc_signal: dict) -> bool:
    """JSON 파일의 btc_signal 필드를 업데이트. 파일 없으면 False 반환."""
    if not path.exists():
        return False
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["btc_signal"] = btc_signal
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="BTC V10 신호 계산 및 JSON 업데이트")
    parser.add_argument(
        "--output", type=str, default="frontend/web/data/",
        help="JSON 출력 디렉토리 (기본: frontend/web/data/)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    btc_signal = calculate_btc_signal()

    targets = [
        output_dir / "screening_latest.json",
        output_dir / "screening_strategies.json",
    ]
    updated = [p.name for p in targets if _patch_json(p, btc_signal)]

    signal    = btc_signal.get("signal", "N/A")
    price     = btc_signal.get("price")
    ts        = str(btc_signal.get("timestamp", ""))[:19]
    regime    = btc_signal.get("regime", "")
    price_str = f"${price:,.2f}" if isinstance(price, (int, float)) else "N/A"
    print(f"BTC V10: {signal} | {price_str} | regime={regime} | {ts} | 업데이트 파일: {updated}")


if __name__ == "__main__":
    main()
