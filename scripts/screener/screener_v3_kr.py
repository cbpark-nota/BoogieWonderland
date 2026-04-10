"""
모멘텀 종목 스크리너 v3.2 — 한국 시장
══════════════════════════════════════════════════════════
screener_v3 와 동일한 모멘텀 알고리즘을 한국 시장에 적용.
데이터 소스: pykrx (yfinance 대신 KRX 직접 조회)

사용법 (독립 실행):
    source .venv/bin/activate
    python scripts/screener/screener_v3_kr.py [--verbose]
══════════════════════════════════════════════════════════
"""
import logging
import sys
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# screener_v3 알고리즘 재사용
sys.path.insert(0, str(Path(__file__).parent))
import screener_v3 as sc

logger = logging.getLogger(__name__)

# ── KR 전용 상수 ──────────────────────────────────────────────
KR_TOP_N = 10


def _safe_float(val, ndigits=2):
    import math
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, ndigits)
    except (TypeError, ValueError):
        return None


# ── pykrx 기반 KR 데이터 다운로드 ────────────────────────────
def download_kr_pykrx(
    tickers: list[str],
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """pykrx로 KR 종목 OHLCV 수집 후 screener_v3 형식(컬럼명 영문)으로 반환.

    Args:
        tickers: ['005930.KS', '000660.KS', ...] 형식
        start: 'YYYY-MM-DD' (기본: 오늘 기준 400일 전)
        end: 'YYYY-MM-DD' (기본: 오늘)
    Returns:
        {ticker: pd.DataFrame(Open/High/Low/Close/Volume)}
    """
    try:
        from pykrx import stock as pkstock  # type: ignore
    except ImportError as e:
        logger.error("pykrx 설치 필요: uv add pykrx (%s)", e)
        return {}

    today = datetime.now()
    _end = end or today.strftime("%Y-%m-%d")
    _start = start or (today - timedelta(days=400)).strftime("%Y-%m-%d")

    # pykrx 날짜 형식: YYYYMMDD
    start_fmt = _start.replace("-", "")
    end_fmt = _end.replace("-", "")

    result: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            code = ticker.split(".")[0]  # '005930.KS' → '005930'
            df = pkstock.get_market_ohlcv_by_date(start_fmt, end_fmt, code)
            if df is None or df.empty or len(df) < 60:
                continue
            # pykrx 컬럼명 → 영문 (screener_v3 형식)
            rename_map = {
                "시가": "Open",
                "고가": "High",
                "저가": "Low",
                "종가": "Close",
                "거래량": "Volume",
            }
            df = df.rename(columns=rename_map)
            keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            if len(keep) < 4:
                continue
            df = df[keep].copy()
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            df = df[~df.index.duplicated(keep="last")]
            result[ticker] = df
        except Exception as ex:
            logger.debug("screener_v3_kr download: %s 실패 — %s", ticker, ex)

    return result


# ── KR 유니버스 수집 ──────────────────────────────────────────
def fetch_kr_universe(kospi_n: int = 200, kosdaq_n: int = 150) -> tuple[list[str], dict[str, str]]:
    """KOSPI 상위 kospi_n + KOSDAQ 상위 kosdaq_n 종목을 pykrx로 수집.

    Returns:
        (tickers, sectors): tickers=['005930.KS',...], sectors={ticker: 'Unknown'}
    """
    try:
        from pykrx import stock as pkstock  # type: ignore
        today_str = datetime.now().strftime("%Y%m%d")

        # KOSPI 시가총액 기준 상위 종목
        kospi_df = pkstock.get_market_cap_by_ticker(today_str, market="KOSPI")
        kospi_df = kospi_df.sort_values("시가총액", ascending=False).head(kospi_n)
        kospi_tickers = [f"{code}.KS" for code in kospi_df.index.tolist()]

        # KOSDAQ 시가총액 기준 상위 종목
        kosdaq_df = pkstock.get_market_cap_by_ticker(today_str, market="KOSDAQ")
        kosdaq_df = kosdaq_df.sort_values("시가총액", ascending=False).head(kosdaq_n)
        kosdaq_tickers = [f"{code}.KQ" for code in kosdaq_df.index.tolist()]

        all_tickers = kospi_tickers + kosdaq_tickers
        sectors = {t: "Unknown" for t in all_tickers}
        logger.info("  KR 유니버스 (pykrx): KOSPI %d + KOSDAQ %d = %d종목",
                    len(kospi_tickers), len(kosdaq_tickers), len(all_tickers))
        return all_tickers, sectors

    except Exception as e:
        logger.warning("  pykrx 유니버스 수집 실패 (%s), 빈 목록 반환", e)
        return [], {}


# ── KR 종목명 수집 ────────────────────────────────────────────
def fetch_kr_names(tickers: list[str]) -> dict[str, str]:
    """pykrx로 KR 종목명 수집."""
    try:
        from pykrx import stock as pkstock  # type: ignore
        names: dict[str, str] = {}
        for ticker in tickers:
            code = ticker.split(".")[0]
            name = pkstock.get_market_ticker_name(code)
            if name:
                names[ticker] = name
        return names
    except Exception as e:
        logger.warning("  pykrx 종목명 수집 실패 (%s)", e)
        return {}


# ── KR 스크리닝 실행 (export_json.py 에서 호출) ──────────────
def run_kr_screening(
    tickers: list[str],
    sectors: dict[str, str],
    atr_mult: float = 2.5,
    kr_data: dict | None = None,
) -> tuple[dict, int]:
    """KR 데이터로 스크리닝 실행. passed 딕셔너리 반환 (rank_stocks는 호출자가 담당).

    Args:
        tickers: KR 티커 목록
        sectors: {ticker: sector}
        atr_mult: ATR 승수
        kr_data: 미리 다운로드된 {ticker: df_indicators} (없으면 내부에서 다운로드)
    Returns:
        (passed_dict, total_downloaded)
    """
    if kr_data is None:
        raw = download_kr_pykrx(tickers)
        kr_data_ind = {}
        for t, df in raw.items():
            kr_data_ind[t] = sc.calc_indicators(df)
    else:
        kr_data_ind = kr_data

    orig_atr = sc.ATR_MULT
    sc.ATR_MULT = atr_mult

    passed: dict[str, dict] = {}
    for ticker, df_ind in kr_data_ind.items():
        ok, metrics = sc.screen(df_ind)
        if ok:
            passed[ticker] = metrics

    sc.ATR_MULT = orig_atr
    return passed, len(kr_data_ind)


# ── 독립 실행 ─────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="모멘텀 종목 스크리너 v3.2 — 한국 시장")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--top-n", type=int, default=KR_TOP_N)
    parser.add_argument("--atr-mult", type=float, default=2.5)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")

    print(f"모멘텀 스크리너 v3.2 KR — 기준일: {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 60)

    kr_tickers, kr_sectors = fetch_kr_universe()
    if not kr_tickers:
        print("  KR 유니버스 수집 실패")
        exit(1)
    print(f"  유니버스: {len(kr_tickers)}종목")

    # 스크리닝
    orig_all = dict(sc.ALL_UNIVERSE)
    sc.ALL_UNIVERSE.clear()
    sc.ALL_UNIVERSE.update(kr_sectors)

    passed, total_dl = run_kr_screening(kr_tickers, kr_sectors, atr_mult=args.atr_mult)
    print(f"  다운로드: {total_dl} | 통과: {len(passed)}")

    if passed:
        ranked = sc.rank_stocks(passed, {})
        kr_names = fetch_kr_names(list(passed.keys()))
        top = ranked.head(args.top_n)
        weights = sc.calc_position_weights(top["score"], sc.SIZING_MODE, sc.MAX_WEIGHT)
        top = top.copy()
        top["weight"] = weights

        print(f"\n  TOP {len(top)} 결과:")
        for rank, (ticker, row) in enumerate(top.iterrows(), 1):
            name = kr_names.get(ticker, ticker)
            print(f"  {rank:2d}. {ticker:<15} {name:<20} "
                  f"ADX={float(row['ADX']):.1f}  RSI={float(row['RSI']):.1f}  "
                  f"비중={float(row['weight']) * 100:.1f}%")

    sc.ALL_UNIVERSE.clear()
    sc.ALL_UNIVERSE.update(orig_all)
