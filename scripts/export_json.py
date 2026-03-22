"""
4전략 스크리닝 결과를 JSON으로 내보내기 (서버리스 배포용)
─────────────────────────────────────────────────────────
전략별 ATR 승수를 변경하여 screener_v3 실행 → JSON 생성.
시장 관망 여부와 무관하게 모든 전략의 결과를 제공한다.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "screener"))

import screener_v3 as sc

# 4가지 전략 프리셋
STRATEGIES = {
    "aggressive":   {"atr_mult": 2.0, "label": "공격적", "rebal_freq": "주간"},
    "balanced":     {"atr_mult": 2.5, "label": "균형형", "rebal_freq": "격주"},
    "conservative": {"atr_mult": 3.5, "label": "보수적", "rebal_freq": "월간"},
    "adaptive":     {"atr_mult": None, "label": "적응형", "rebal_freq": "동적"},
}


def safe_float(val, ndigits=2):
    try:
        if pd.isna(val) or np.isnan(float(val)):
            return None
    except (TypeError, ValueError):
        return None
    return round(float(val), ndigits)


def detect_adaptive_regime(mkt):
    """시장 상태에서 적응형 국면 판별 (간이 버전)."""
    if mkt is None:
        return "balanced", 2.5
    gap = mkt["gap_pct"]
    if gap > 5:
        return "aggressive", 2.0
    elif gap > 0:
        return "balanced", 2.5
    else:
        return "conservative", 3.5


def run_screening_with_atr(all_data_ind, etf_data, atr_mult):
    """특정 ATR 승수로 스크리닝 실행."""
    # ATR_MULT를 임시 변경
    orig_mult = sc.ATR_MULT
    sc.ATR_MULT = atr_mult

    passed = {}
    for t, df_ind in all_data_ind.items():
        ok, metrics = sc.screen(df_ind)
        if ok:
            passed[t] = metrics

    sc.ATR_MULT = orig_mult
    return passed


def build_results(passed, etf_data):
    """통과 종목을 랭킹하고 결과 리스트 생성."""
    if not passed:
        return []

    ranked = sc.rank_stocks(passed, etf_data)
    top = ranked.head(sc.TOP_N).copy()
    weights = sc.calc_position_weights(top["score"], sc.SIZING_MODE, sc.MAX_WEIGHT)
    top["weight"] = weights

    results = []
    for rank, (ticker, row) in enumerate(top.iterrows(), 1):
        market = "KR" if ticker.endswith(".KS") else "US"
        sector = sc.ALL_UNIVERSE.get(ticker, "Unknown")
        results.append({
            "rank": rank,
            "ticker": ticker,
            "market": market,
            "sector": sector,
            "score": safe_float(row["score"], 4),
            "weight_pct": safe_float(row["weight"] * 100, 1),
            "price": safe_float(row["price"]),
            "adx": safe_float(row["ADX"], 1),
            "rsi": safe_float(row["RSI"], 1),
            "ret_3m": safe_float(row["ret3m"], 4),
            "stop_price": safe_float(row["stop_price"]),
            "stop_dist_pct": safe_float(row["stop_dist"], 4),
            "atr": safe_float(row["atr"], 2),
        })
    return results


def export_all_strategies(output_dir: Path):
    """4전략 스크리닝 실행 후 단일 JSON으로 저장."""
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    # 시장 상태
    mkt = sc.check_market()
    market_status = None
    if mkt:
        market_status = {
            "spy_price": round(mkt["price"], 2),
            "is_golden_cross": mkt["is_golden"],
            "ma50": round(mkt["ma50"], 2),
            "ma200": round(mkt["ma200"], 2),
            "gap_pct": round(mkt["gap_pct"], 2),
        }

    # 데이터 다운로드 (1회)
    print("데이터 다운로드 중...")
    us_data, kr_data, etf_data = {}, {}, {}
    for i in range(0, len(sc.US_UNIVERSE), 30):
        us_data.update(sc.download(list(sc.US_UNIVERSE.keys())[i:i + 30]))
    for i in range(0, len(sc.KR_UNIVERSE), 30):
        kr_data.update(sc.download(list(sc.KR_UNIVERSE.keys())[i:i + 30]))
    etf_raw = sc.download(list(set(sc.SECTOR_ETF.values())))
    for t, df in etf_raw.items():
        etf_data[t] = sc.calc_indicators(df)

    all_data = {**us_data, **kr_data}

    # 지표 계산 (1회)
    print(f"지표 계산 중 ({len(all_data)}개 종목)...")
    all_data_ind = {}
    for t, df in all_data.items():
        all_data_ind[t] = sc.calc_indicators(df)

    # 적응형 국면 판별
    adaptive_regime, adaptive_atr = detect_adaptive_regime(mkt)

    # 4전략 스크리닝
    strategies_output = {}
    for key, preset in STRATEGIES.items():
        atr_mult = preset["atr_mult"] if preset["atr_mult"] is not None else adaptive_atr
        print(f"  {preset['label']} (ATR={atr_mult}) 스크리닝 중...")
        passed = run_screening_with_atr(all_data_ind, etf_data, atr_mult)
        results = build_results(passed, etf_data)

        strategy_info = {
            "key": key,
            "label": preset["label"],
            "atr_mult": atr_mult,
            "rebal_freq": preset["rebal_freq"],
            "total_screened": len(all_data),
            "total_passed": len(passed),
            "results": results,
        }

        # 적응형 전략에는 현재 국면 정보 추가
        if key == "adaptive":
            strategy_info["current_regime"] = adaptive_regime
            strategy_info["regime_label"] = STRATEGIES[adaptive_regime]["label"]

        strategies_output[key] = strategy_info

    output = {
        "run_id": int(now.strftime("%Y%m%d")),
        "run_date": now.isoformat(timespec="seconds"),
        "market_status": market_status,
        "strategies": strategies_output,
    }

    # screening_latest.json (하위 호환: 균형형을 기본으로)
    balanced = strategies_output["balanced"]
    compat_output = {
        "run_id": output["run_id"],
        "run_date": output["run_date"],
        "market_status": market_status,
        "total_screened": balanced["total_screened"],
        "total_passed": balanced["total_passed"],
        "results": balanced["results"],
    }
    compat_path = output_dir / "screening_latest.json"
    with open(compat_path, "w", encoding="utf-8") as f:
        json.dump(compat_output, f, ensure_ascii=False, indent=2)

    # screening_strategies.json (4전략 전체)
    full_path = output_dir / "screening_strategies.json"
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_passed = sum(s["total_passed"] for s in strategies_output.values())
    print(f"\n완료: {full_path}")
    print(f"  공격적: {strategies_output['aggressive']['total_passed']}개 통과")
    print(f"  균형형: {strategies_output['balanced']['total_passed']}개 통과")
    print(f"  보수적: {strategies_output['conservative']['total_passed']}개 통과")
    print(f"  적응형: {strategies_output['adaptive']['total_passed']}개 통과 "
          f"(현재 국면: {STRATEGIES[adaptive_regime]['label']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="4전략 스크리닝 결과 JSON 내보내기")
    parser.add_argument("--output", type=str, default="frontend/web/data/",
                        help="JSON 출력 디렉토리")
    args = parser.parse_args()
    export_all_strategies(Path(args.output))
