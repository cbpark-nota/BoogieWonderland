"""
추세 전환 스크리너 — 일봉 기준 5MA / 120MA 골든크로스
══════════════════════════════════════════════════════════════
백테스트(`backtest_5w_120w_cross.py`)의 5W/120W 전략을 일봉으로 적용:
  - MA_SHORT = 25일 (5주 × 5거래일)
  - MA_LONG  = 600일 (120주 × 5거래일)
  - 매수 후보: 현재 MA25 > MA600 인 종목 (골든크로스 유지 중)
  - 스코어  : MA gap ratio = (MA25 - MA600) / MA600 (추세 강도)
  - Top N    : 시장별 25개 (gap ratio 내림차순)
  - 스톱가  : 최근 20일 고점 - ATR(14) × 2.5  (v3.3 트레일링 진입가 동일)

매수 방식은 v3.3 모멘텀과 동일하게 격주 리밸런싱 + 트레일링 스톱.
이 스크립트는 후보 리스트만 산출한다.

출력: trend_reversal_us.json, trend_reversal_kr.json
══════════════════════════════════════════════════════════════
"""
import argparse
import json
import logging
import sys
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*yfinance.*")

import numpy as np
import pandas as pd
import pandas_ta as ta
import yfinance as yf

logger = logging.getLogger(__name__)

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent))

from data_cache import (  # noqa: E402
    fetch_sp500_tickers,
    fetch_nasdaq100_tickers,
    fetch_kr_tickers,
    CACHE_DIR,
)

MA_SHORT     = 25      # 5주 × 5거래일
MA_LONG      = 600     # 120주 × 5거래일
ATR_PERIOD   = 14
ATR_MULT     = 2.5
TOP_N        = 25
DOWNLOAD_DAYS = 800    # MA600 워밍업 + 버퍼
MIN_ROWS     = MA_LONG + ATR_PERIOD


# ── 지표 계산 ────────────────────────────────────────────────

def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c = d["Close"].squeeze()
    h = d["High"].squeeze()
    l = d["Low"].squeeze()

    d["MA_S"] = c.rolling(MA_SHORT, min_periods=MA_SHORT).mean()
    d["MA_L"] = c.rolling(MA_LONG, min_periods=MA_LONG).mean()
    atr = ta.atr(h, l, c, length=ATR_PERIOD)
    d["ATR"] = atr if atr is not None else np.nan
    return d


def _peak_20(df: pd.DataFrame) -> float:
    return float(df["High"].tail(20).max())


# ── 데이터 다운로드 ──────────────────────────────────────────

def _download_market(tickers: list[str], label: str) -> dict:
    """yfinance 배치 다운로드. period로 충분한 일봉 확보."""
    if not tickers:
        return {}
    out: dict[str, pd.DataFrame] = {}
    end = datetime.today()
    start = end - pd.Timedelta(days=DOWNLOAD_DAYS * 1.5)
    for i in range(0, len(tickers), 50):
        batch = tickers[i:i + 50]
        try:
            raw = yf.download(
                batch,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                for t in batch:
                    try:
                        df = raw.xs(t, axis=1, level=1).dropna(how="all")
                        if len(df) >= MIN_ROWS:
                            out[t] = df
                    except Exception:
                        pass
            elif len(batch) == 1:
                if len(raw) >= MIN_ROWS:
                    out[batch[0]] = raw
        except Exception as e:
            logger.warning("  %s 배치 다운로드 실패 (offset=%d): %s", label, i, e)
    logger.info("  %s 데이터 확보: %d/%d종목", label, len(out), len(tickers))
    return out


def _try_cache(tickers: list[str]) -> dict:
    """data_cache가 있으면 거기서 읽음 (백테스트 캐시 재사용)."""
    candidate_dirs = [
        CACHE_DIR,
        _THIS_DIR.parents[3] / "data" / "full_universe",
    ]
    actual_dir = next(
        (d for d in candidate_dirs if (d / "manifest.json").exists()),
        None,
    )
    if actual_dir is None:
        return {}
    try:
        with open(actual_dir / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception:
        return {}

    out: dict[str, pd.DataFrame] = {}
    stocks = manifest.get("stocks", {})
    for t in tickers:
        if t not in stocks:
            continue
        path = actual_dir / stocks[t]
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
            if len(df) >= MIN_ROWS:
                out[t] = df
        except Exception:
            pass
    return out


# ── 스크리닝 ─────────────────────────────────────────────────

def _screen(all_data: dict, market: str) -> list[dict]:
    """현재 MA25 > MA600 인 종목 → gap 내림차순 Top 25."""
    rows: list[dict] = []
    for ticker, df in all_data.items():
        d = _add_indicators(df)
        last = d.iloc[-1]
        ma_s = last.get("MA_S", np.nan)
        ma_l = last.get("MA_L", np.nan)
        atr_v = last.get("ATR", np.nan)
        close = last.get("Close", np.nan)

        if pd.isna(ma_s) or pd.isna(ma_l) or ma_l <= 0:
            continue
        if ma_s <= ma_l:
            continue
        if pd.isna(close):
            continue

        gap = float((ma_s - ma_l) / ma_l)
        peak = _peak_20(d)
        if pd.isna(atr_v) or atr_v <= 0:
            stop_price = None
            stop_dist = None
        else:
            stop_price = round(peak - float(atr_v) * ATR_MULT, 2)
            stop_dist = round((stop_price - float(close)) / float(close), 4)

        rows.append({
            "ticker": ticker,
            "market": market,
            "score": round(gap, 4),
            "ma_short": round(float(ma_s), 4),
            "ma_long": round(float(ma_l), 4),
            "price": round(float(close), 2),
            "stop_price": stop_price,
            "stop_dist_pct": stop_dist,
            "atr": round(float(atr_v), 4) if not pd.isna(atr_v) else None,
        })

    rows.sort(key=lambda r: r["score"], reverse=True)
    top = rows[:TOP_N]
    for i, r in enumerate(top, 1):
        r["rank"] = i
        r["weight_pct"] = round(100.0 / max(len(top), 1), 2)
        r["sector"] = ""
    return top


# ── 메인 ──────────────────────────────────────────────────────

def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    run_dt = now.strftime("%Y-%m-%dT%H:%M:%S")
    run_id = int(now.strftime("%Y%m%d"))

    # US
    sp500_tickers, _ = fetch_sp500_tickers()
    ndx_tickers, _ = fetch_nasdaq100_tickers()
    sp500_set = set(sp500_tickers)
    us_tickers = sp500_tickers + [t for t in ndx_tickers if t not in sp500_set]

    us_data = _try_cache(us_tickers) or _download_market(us_tickers, "US")
    # 캐시 항목은 충분하나 일부 종목만 있으면 부족분은 다운로드
    if len(us_data) < len(us_tickers) * 0.5:
        us_data = _download_market(us_tickers, "US")
    us_results = _screen(us_data, "US")
    us_payload = {
        "run_id": run_id,
        "run_date": run_dt,
        "total_screened": len(us_data),
        "total_passed": len(us_results),
        "results": us_results,
    }
    (output_dir / "trend_reversal_us.json").write_text(
        json.dumps(us_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("US 추세전환 후보: %d종목", len(us_results))

    # KR
    kr_tickers = fetch_kr_tickers(kospi_n=200, kosdaq_n=150)
    kr_data = _try_cache(kr_tickers) or _download_market(kr_tickers, "KR")
    if len(kr_data) < len(kr_tickers) * 0.5:
        kr_data = _download_market(kr_tickers, "KR")
    kr_results = _screen(kr_data, "KR")
    kr_payload = {
        "run_id": run_id,
        "run_date": run_dt,
        "total_screened": len(kr_data),
        "total_passed": len(kr_results),
        "results": kr_results,
    }
    (output_dir / "trend_reversal_kr.json").write_text(
        json.dumps(kr_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("KR 추세전환 후보: %d종목", len(kr_results))

    return {"us": us_payload, "kr": kr_payload}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="추세 전환(5MA/120MA) 스크리너")
    parser.add_argument(
        "--output",
        type=str,
        default="frontend/web/data/",
        help="JSON 출력 디렉토리",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(message)s",
    )
    run(Path(args.output))
