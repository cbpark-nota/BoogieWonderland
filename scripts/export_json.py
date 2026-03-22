"""
스크리닝 결과를 JSON으로 내보내기 (서버리스 배포용)
─────────────────────────────────────────────────
screener_v3.py의 핵심 함수를 import하여 실행하고,
Flutter 앱의 ScreeningRun.fromJson 포맷과 동일한 JSON을 생성한다.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# screener_v3.py를 import할 수 있도록 경로 추가
sys.path.insert(0, str(Path(__file__).parent / "screener"))

from screener_v3 import (
    US_UNIVERSE, KR_UNIVERSE, ALL_UNIVERSE, SECTOR_ETF,
    ATR_PERIOD, ATR_MULT, SIZING_MODE, MAX_WEIGHT, TOP_N,
    download, calc_indicators, screen, rank_stocks,
    calc_position_weights, check_market,
)


def export_screening(output_dir: Path):
    """스크리닝 실행 후 JSON으로 저장."""
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    # 시장 상태
    mkt = check_market()
    market_status = None
    if mkt:
        market_status = {
            "spy_price": round(mkt["price"], 2),
            "is_golden_cross": mkt["is_golden"],
            "ma50": round(mkt["ma50"], 2),
            "ma200": round(mkt["ma200"], 2),
            "gap_pct": round(mkt["gap_pct"], 2),
        }

    # 데이터 다운로드
    us_data, kr_data, etf_data = {}, {}, {}
    for i in range(0, len(US_UNIVERSE), 30):
        us_data.update(download(list(US_UNIVERSE.keys())[i:i + 30]))
    for i in range(0, len(KR_UNIVERSE), 30):
        kr_data.update(download(list(KR_UNIVERSE.keys())[i:i + 30]))
    etf_raw = download(list(set(SECTOR_ETF.values())))
    for t, df in etf_raw.items():
        etf_data[t] = calc_indicators(df)

    all_data = {**us_data, **kr_data}

    # 지표 계산 + 스크리닝
    passed = {}
    for t, df in all_data.items():
        df_ind = calc_indicators(df)
        ok, metrics = screen(df_ind)
        if ok:
            passed[t] = metrics

    # 결과 생성
    results = []
    if passed:
        ranked = rank_stocks(passed, etf_data)
        top = ranked.head(TOP_N).copy()
        weights = calc_position_weights(top["score"], SIZING_MODE, MAX_WEIGHT)
        top["weight"] = weights

        for rank, (ticker, row) in enumerate(top.iterrows(), 1):
            market = "KR" if ticker.endswith(".KS") else "US"
            sector = ALL_UNIVERSE.get(ticker, "Unknown")

            def safe_float(val, ndigits=2):
                try:
                    import pandas as pd
                    import numpy as np
                    if pd.isna(val) or np.isnan(float(val)):
                        return None
                except (TypeError, ValueError):
                    return None
                return round(float(val), ndigits)

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

    output = {
        "run_id": int(now.strftime("%Y%m%d")),
        "run_date": now.isoformat(timespec="seconds"),
        "market_status": market_status,
        "total_screened": len(all_data),
        "total_passed": len(passed),
        "results": results,
    }

    out_path = output_dir / "screening_latest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"스크리닝 완료: {len(passed)}/{len(all_data)} 통과 → {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="스크리닝 결과 JSON 내보내기")
    parser.add_argument("--output", type=str, default="frontend/web/data/",
                        help="JSON 출력 디렉토리")
    args = parser.parse_args()
    export_screening(Path(args.output))
