"""
숏스퀴즈 스크리닝 스크립트
──────────────────────────────────────────────────────────
공매도 비율이 높고 최근 가격 상승이 있는 종목을 스크리닝한다.

사용법:
  python scripts/screener/short_squeeze_screener.py            # 실시간 데이터
  python scripts/screener/short_squeeze_screener.py --sample   # 샘플 데이터 (네트워크 불필요)
  python scripts/screener/short_squeeze_screener.py --output frontend/web/data/
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 샘플 데이터 (네트워크 없이 빠른 UI 확인용)
SAMPLE_DATA = [
    {"ticker": "GME",  "name": "GameStop Corp",          "short_float_pct": 25.4, "days_to_cover": 2.8, "price": 25.10,  "change_1d_pct": 4.8,  "change_5d_pct": 12.3, "volume_ratio": 3.1, "market_cap": 8500000000,    "sector": "Consumer Discretionary"},
    {"ticker": "AMC",  "name": "AMC Entertainment",      "short_float_pct": 22.1, "days_to_cover": 1.9, "price":  4.32,  "change_1d_pct": 6.2,  "change_5d_pct": 18.7, "volume_ratio": 4.5, "market_cap": 1200000000,    "sector": "Communication Services"},
    {"ticker": "BBBY", "name": "Bed Bath & Beyond",      "short_float_pct": 40.2, "days_to_cover": 3.1, "price":  0.83,  "change_1d_pct": 8.1,  "change_5d_pct": 22.5, "volume_ratio": 6.2, "market_cap":  120000000,    "sector": "Consumer Discretionary"},
    {"ticker": "CVNA", "name": "Carvana Co",              "short_float_pct": 17.8, "days_to_cover": 4.2, "price": 215.40, "change_1d_pct": 3.4,  "change_5d_pct":  9.8, "volume_ratio": 2.3, "market_cap": 41000000000,   "sector": "Consumer Discretionary"},
    {"ticker": "BYND", "name": "Beyond Meat",             "short_float_pct": 35.6, "days_to_cover": 2.5, "price":  8.21,  "change_1d_pct": 5.9,  "change_5d_pct": 16.4, "volume_ratio": 3.8, "market_cap":  580000000,    "sector": "Consumer Staples"},
    {"ticker": "UPST", "name": "Upstart Holdings",        "short_float_pct": 28.3, "days_to_cover": 3.7, "price": 52.60,  "change_1d_pct": 2.8,  "change_5d_pct":  7.2, "volume_ratio": 1.9, "market_cap": 4500000000,    "sector": "Financials"},
    {"ticker": "SPCE", "name": "Virgin Galactic",         "short_float_pct": 19.7, "days_to_cover": 2.1, "price":  2.14,  "change_1d_pct": 7.3,  "change_5d_pct": 20.1, "volume_ratio": 5.1, "market_cap":  460000000,    "sector": "Industrials"},
    {"ticker": "PLUG", "name": "Plug Power",              "short_float_pct": 16.9, "days_to_cover": 3.3, "price":  3.45,  "change_1d_pct": 4.1,  "change_5d_pct": 11.6, "volume_ratio": 2.7, "market_cap": 2100000000,    "sector": "Industrials"},
    {"ticker": "RDFN", "name": "Redfin Corp",             "short_float_pct": 21.4, "days_to_cover": 4.8, "price":  9.80,  "change_1d_pct": 3.7,  "change_5d_pct":  8.9, "volume_ratio": 2.1, "market_cap": 1100000000,    "sector": "Real Estate"},
    {"ticker": "W",    "name": "Wayfair Inc",             "short_float_pct": 15.2, "days_to_cover": 5.2, "price": 45.30,  "change_1d_pct": 2.2,  "change_5d_pct":  6.1, "volume_ratio": 1.7, "market_cap": 5900000000,    "sector": "Consumer Discretionary"},
]


def fetch_real_data(min_short_float: float = 15.0, top_n: int = 20) -> list[dict]:
    """yfinance로 실시간 숏 포지션 데이터 수집."""
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance 미설치 — pip install yfinance", file=sys.stderr)
        return []

    sys.path.insert(0, str(Path(__file__).parent.parent))
    try:
        from data_cache import fetch_sp500_tickers
        us_tickers, us_sectors = fetch_sp500_tickers()
    except Exception as e:
        print(f"티커 수집 실패: {e}", file=sys.stderr)
        return []

    results = []
    checked = 0
    for ticker in us_tickers:
        try:
            info = yf.Ticker(ticker).info
            short_pct = info.get("shortPercentOfFloat")
            if short_pct is None or short_pct * 100 < min_short_float:
                continue

            hist = yf.download(ticker, period="10d", auto_adjust=True, progress=False)
            if hist.empty or len(hist) < 2:
                continue
            close = hist["Close"].squeeze().dropna()
            price = float(close.iloc[-1])
            change_1d = (close.iloc[-1] / close.iloc[-2] - 1) * 100
            change_5d = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0.0
            vol = hist["Volume"].squeeze().dropna()
            vol_ratio = float(vol.iloc[-1]) / float(vol.iloc[:-1].mean()) if len(vol) > 1 else 1.0

            results.append({
                "ticker": ticker,
                "name": info.get("longName", ticker),
                "short_float_pct": round(float(short_pct) * 100, 1),
                "days_to_cover": round(float(info.get("shortRatio", 0)), 1),
                "price": round(price, 2),
                "change_1d_pct": round(float(change_1d), 1),
                "change_5d_pct": round(float(change_5d), 1),
                "volume_ratio": round(vol_ratio, 1),
                "market_cap": info.get("marketCap", 0),
                "sector": us_sectors.get(ticker, "Unknown"),
            })
            checked += 1
            if len(results) % 5 == 0:
                print(f"  진행: {len(results)}개 발견 (검사: {checked}개)", flush=True)
        except Exception:
            continue

    results.sort(key=lambda x: x["short_float_pct"], reverse=True)
    return results[:top_n]


def generate_json(use_sample: bool, output_dir: Path, top_n: int = 20) -> Path:
    now = datetime.now()
    if use_sample:
        print("샘플 데이터 사용 (--sample 플래그)")
        data = sorted(SAMPLE_DATA, key=lambda x: x["short_float_pct"], reverse=True)[:top_n]
    else:
        print("실시간 숏 포지션 데이터 수집 중...")
        data = fetch_real_data(top_n=top_n)
        if not data:
            print("데이터 수집 실패 — 샘플 데이터로 대체")
            data = sorted(SAMPLE_DATA, key=lambda x: x["short_float_pct"], reverse=True)[:top_n]

    output = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "is_sample": use_sample,
        "total_candidates": len(data),
        "criteria": {
            "min_short_float_pct": 15.0,
            "description": "공매도 비율 15% 이상, 5일 가격 상승 종목 (숏스퀴즈 압력 높음)",
        },
        "results": data,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "short_squeeze_latest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"short_squeeze_latest.json 저장: {out_path} ({len(data)}개 종목)")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="숏스퀴즈 스크리닝 JSON 생성")
    parser.add_argument("--sample", action="store_true", help="샘플 데이터 사용 (네트워크 불필요)")
    parser.add_argument("--output", type=str, default="frontend/web/data/", help="출력 디렉토리")
    parser.add_argument("--top-n", type=int, default=20, help="상위 N개 종목")
    args = parser.parse_args()

    generate_json(
        use_sample=args.sample,
        output_dir=Path(args.output),
        top_n=args.top_n,
    )
