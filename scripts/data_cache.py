"""
공용 풀 유니버스 데이터 캐시 모듈
══════════════════════════════════════════════════════════════
모든 백테스트 스크립트에서 공통으로 사용하는 데이터 로더.
yfinance에서 867종목을 매번 다운로드하지 않고, 당일 캐시를 재사용.

캐시 구조:
  data/full_universe/
    {TICKER}.parquet        — 종목별 OHLCV (안전한 파일명으로 변환)
    etf_{TICKER}.parquet    — 섹터 ETF OHLCV
    spy.parquet             — SPY 벤치마크
    manifest.json           — 다운로드 날짜, 종목 수 등 메타 정보

사용 예:
    from scripts.data_cache import load_full_universe

    all_data, spy_df, etf_data, universe_map = load_full_universe("2015-01-01")
    # all_data: dict[ticker] -> DataFrame (OHLCV)
    # spy_df  : DataFrame (SPY OHLCV)
    # etf_data: dict[ticker] -> DataFrame (OHLCV)
    # universe_map: dict[ticker] -> sector
══════════════════════════════════════════════════════════════
"""
import io
import json
import sys
import warnings
from datetime import date, datetime
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd
import requests
import yfinance as yf

# ── 경로 설정 ──────────────────────────────────────────────
_SCRIPTS_DIR = Path(__file__).parent
_REPO_ROOT   = _SCRIPTS_DIR.parent
CACHE_DIR    = _REPO_ROOT / "data" / "full_universe"

# ── 섹터 ETF 매핑 (GICS 섹터명 + 구형 섹터명 모두 지원) ────
SECTOR_ETF = {
    # GICS 표준
    "Information Technology":  "XLK",
    "Health Care":             "XLV",
    "Financials":              "XLF",
    "Consumer Discretionary":  "XLY",
    "Industrials":             "XLI",
    "Energy":                  "XLE",
    "Materials":               "XLB",
    "Communication Services":  "XLC",
    "Consumer Staples":        "XLP",
    "Utilities":               "XLU",
    "Real Estate":             "XLRE",
    # 구형 섹터명 (기존 백테스트 스크립트 호환)
    "Technology":              "XLK",
    "Consumer Disc":           "XLY",
    "Communication":           "XLC",
    "Health":                  "XLV",
}

# ICB Industry (Wikipedia NASDAQ-100) → GICS 섹터 매핑
_ICB_TO_GICS = {
    "Technology":             "Information Technology",
    "Consumer Discretionary": "Consumer Discretionary",
    "Health Care":            "Health Care",
    "Utilities":              "Utilities",
    "Industrials":            "Industrials",
    "Energy":                 "Energy",
    "Telecommunications":     "Communication Services",
    "Consumer Staples":       "Consumer Staples",
    "Real Estate":            "Real Estate",
    "Basic Materials":        "Materials",
    "Financials":             "Financials",
}


# ══════════════════════════════════════════════════════════════
# 유니버스 수집 함수
# ══════════════════════════════════════════════════════════════

def fetch_sp500_tickers():
    """S&P500 구성 종목 및 GICS 섹터 가져오기."""
    try:
        url = ("https://raw.githubusercontent.com/datasets/"
               "s-and-p-500-companies/main/data/constituents.csv")
        df = pd.read_csv(url)
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        sectors = dict(zip(
            df["Symbol"].str.replace(".", "-", regex=False),
            df["GICS Sector"],
        ))
        print(f"  S&P500 {len(tickers)}개 종목 수집 완료")
        return tickers, sectors
    except Exception as e:
        print(f"  S&P500 수집 실패 ({e})")
        return [], {}


def fetch_nasdaq100_tickers():
    """NASDAQ-100 구성 종목 및 섹터 가져오기 (Wikipedia)."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            )
        }
        r = requests.get(
            "https://en.wikipedia.org/wiki/Nasdaq-100",
            headers=headers,
            timeout=15,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        ndx = tables[4]
        tickers = ndx["Ticker"].str.replace(".", "-", regex=False).tolist()
        sectors = {
            row["Ticker"].replace(".", "-"): _ICB_TO_GICS.get(
                row["ICB Industry[14]"], row["ICB Industry[14]"]
            )
            for _, row in ndx.iterrows()
        }
        print(f"  NASDAQ-100 {len(tickers)}개 종목 수집 완료")
        return tickers, sectors
    except Exception as e:
        print(f"  NASDAQ-100 수집 실패 ({e})")
        return [], {}


def fetch_kr_tickers(kospi_n=200, kosdaq_n=150):
    """KRX에서 KOSPI/KOSDAQ 상위 종목 가져오기.

    1차: kind.krx.co.kr 상장법인 목록 (EUC-KR 명시 디코딩)
    2차 fallback: 네이버 금융 시가총액 페이지
    """
    try:
        url = ("http://kind.krx.co.kr/corpgeneral/corpList.do"
               "?method=download&searchType=13")
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        r.raise_for_status()
        krx = pd.read_html(io.StringIO(r.content.decode("euc-kr")))[0]

        kospi = krx[
            (krx["시장구분"] == "유가") &
            (krx["종목코드"].astype(str).str.match(r"^\d{6}$"))
        ].copy()
        kosdaq = krx[
            (krx["시장구분"] == "코스닥") &
            (krx["종목코드"].astype(str).str.match(r"^\d{6}$"))
        ].copy()

        kospi_tickers  = [f"{str(c).zfill(6)}.KS" for c in kospi["종목코드"].tolist()][:kospi_n]
        kosdaq_tickers = [f"{str(c).zfill(6)}.KQ" for c in kosdaq["종목코드"].tolist()][:kosdaq_n]

        all_kr = kospi_tickers + kosdaq_tickers
        print(f"  KR KOSPI {len(kospi_tickers)}개 + KOSDAQ {len(kosdaq_tickers)}개 수집 완료")
        return all_kr
    except Exception as e:
        print(f"  KRX 수집 실패 ({e}), 네이버 금융으로 재시도...")
        return _fetch_kr_naver_fallback(kospi_n, kosdaq_n)


def _fetch_kr_naver_fallback(kospi_n=200, kosdaq_n=150):
    """네이버 금융 시가총액 페이지에서 KR 종목 수집 (fallback)."""
    import re
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("  bs4 미설치, KR 종목 수집 불가")
        return []

    def _scrape(sosok, n, suffix):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        tickers = []
        page = 1
        while len(tickers) < n:
            url = (f"https://finance.naver.com/sise/sise_market_sum.nhn"
                   f"?sosok={sosok}&page={page}")
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-kr")
                links = soup.select("table.type_2 a[href*=code]")
                if not links:
                    break
                for link in links:
                    code = link["href"].split("code=")[-1]
                    ticker = f"{code}{suffix}"
                    if re.match(r"^\d{6}$", code) and ticker not in tickers:
                        tickers.append(ticker)
                page += 1
            except Exception:
                break
        return tickers[:n]

    try:
        kospi  = _scrape(0, kospi_n, ".KS")
        kosdaq = _scrape(1, kosdaq_n, ".KQ")
        all_kr = kospi + kosdaq
        print(f"  KR (네이버) KOSPI {len(kospi)}개 + KOSDAQ {len(kosdaq)}개 수집 완료")
        return all_kr
    except Exception as e:
        print(f"  KR 종목 수집 최종 실패 ({e})")
        return []


# ══════════════════════════════════════════════════════════════
# 다운로드 유틸리티
# ══════════════════════════════════════════════════════════════

def _download_batch(tickers, start, end, batch_size=50, label="종목"):
    """yfinance 배치 다운로드 → dict[ticker, DataFrame(OHLCV)]."""
    all_data = {}
    total = len(tickers)

    for i in range(0, total, batch_size):
        batch = tickers[i:i + batch_size]
        done  = min(i + batch_size, total)
        print(f"\r  {label} 다운로드: {done}/{total}", end="", flush=True)
        try:
            raw = yf.download(
                batch, start=start, end=end,
                auto_adjust=True, progress=False, threads=True,
            )
            if raw.empty:
                continue

            if isinstance(raw.columns, pd.MultiIndex):
                for t in batch:
                    try:
                        df = raw.xs(t, axis=1, level=1).dropna(how="all")
                        df = _clean_ohlcv(df)
                        if df is not None:
                            all_data[t] = df
                    except KeyError:
                        pass
            elif len(batch) == 1:
                df = _clean_ohlcv(raw)
                if df is not None:
                    all_data[batch[0]] = df
        except Exception as e:
            print(f"\n  배치 다운로드 오류 (offset={i}): {e}")

    print(f"\r  {label} 다운로드 완료: {len(all_data)}/{total}개", flush=True)
    print()
    return all_data


def _clean_ohlcv(df: pd.DataFrame, min_rows: int = 50) -> pd.DataFrame | None:
    """OHLCV DataFrame 정규화. 최소 행 수 미달 시 None 반환."""
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(df.columns):
        return None
    df = df[list(required)].copy()
    df.index = pd.to_datetime(df.index)
    df.index.name = "Date"
    for col in ("Open", "High", "Low", "Close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0).astype("int64")
    df = df.dropna(subset=["Close"])
    if len(df) < min_rows:
        return None
    return df


# ══════════════════════════════════════════════════════════════
# 캐시 저장 / 로드
# ══════════════════════════════════════════════════════════════

def _safe_fname(ticker: str) -> str:
    return ticker.replace(".", "_").replace("/", "_")


def _save_cache(all_data: dict, spy_df: pd.DataFrame, etf_data: dict,
                universe_map: dict, start: str):
    """데이터를 parquet + manifest.json으로 캐시 저장."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {
        "downloaded_at": date.today().isoformat(),
        "start":         start,
        "ticker_count":  len(all_data),
        "etf_count":     len(etf_data),
        "universe_map":  universe_map,
        "stocks":        {},
        "etfs":          {},
    }

    # 종목
    for ticker, df in all_data.items():
        fname = f"{_safe_fname(ticker)}.parquet"
        df.to_parquet(CACHE_DIR / fname)
        manifest["stocks"][ticker] = fname

    # ETF
    for ticker, df in etf_data.items():
        fname = f"etf_{_safe_fname(ticker)}.parquet"
        df.to_parquet(CACHE_DIR / fname)
        manifest["etfs"][ticker] = fname

    # SPY
    spy_df.to_parquet(CACHE_DIR / "spy.parquet")

    with open(CACHE_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"  캐시 저장 완료: {CACHE_DIR} ({len(all_data)}종목, ETF {len(etf_data)}개)")


def _load_cache(start: str):
    """캐시에서 데이터 로드. 캐시가 없거나 만료/불일치 시 None 반환."""
    manifest_path = CACHE_DIR / "manifest.json"
    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"  manifest 읽기 실패 ({e})")
        return None

    # 날짜 유효성 확인
    cached_date = manifest.get("downloaded_at", "")
    today = date.today().isoformat()
    if cached_date != today:
        print(f"  캐시 만료 (저장일: {cached_date} ≠ 오늘: {today})")
        return None

    # 시작일 일치 확인
    cached_start = manifest.get("start", "")
    if cached_start != start:
        print(f"  캐시 시작일 불일치 (캐시: {cached_start}, 요청: {start})")
        return None

    # 종목 로드
    all_data = {}
    for ticker, fname in manifest.get("stocks", {}).items():
        path = CACHE_DIR / fname
        if path.exists():
            all_data[ticker] = pd.read_parquet(path)

    # ETF 로드
    etf_data = {}
    for ticker, fname in manifest.get("etfs", {}).items():
        path = CACHE_DIR / fname
        if path.exists():
            etf_data[ticker] = pd.read_parquet(path)

    # SPY 로드
    spy_path = CACHE_DIR / "spy.parquet"
    if not spy_path.exists():
        print("  SPY 캐시 파일 없음, 재다운로드 필요")
        return None
    spy_df = pd.read_parquet(spy_path)

    universe_map = manifest.get("universe_map", {})

    print(f"  캐시 로드 완료: {len(all_data)}종목, ETF {len(etf_data)}개 (저장일: {cached_date})")
    return all_data, spy_df, etf_data, universe_map


# ══════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════

def load_full_universe(start: str = "2015-01-01", force_refresh: bool = False):
    """
    풀 유니버스 데이터를 로드.
    당일 캐시가 있으면 재사용, 없으면 yfinance에서 다운로드 후 캐시 저장.

    Parameters
    ----------
    start : str
        데이터 시작일 (기본값: "2015-01-01")
    force_refresh : bool
        True이면 캐시를 무시하고 재다운로드

    Returns
    -------
    all_data : dict[str, pd.DataFrame]
        종목별 OHLCV 데이터 (Open, High, Low, Close, Volume)
    spy_df : pd.DataFrame
        SPY 벤치마크 OHLCV 데이터
    etf_data : dict[str, pd.DataFrame]
        섹터 ETF OHLCV 데이터
    universe_map : dict[str, str]
        ticker → GICS 섹터명 매핑

    Examples
    --------
    >>> from scripts.data_cache import load_full_universe
    >>> all_data, spy_df, etf_data, universe_map = load_full_universe("2015-01-01")
    >>> print(f"{len(all_data)}종목 로드됨")
    """
    end = datetime.today().strftime("%Y-%m-%d")

    # ── 캐시 확인 ──
    if not force_refresh:
        cached = _load_cache(start)
        if cached is not None:
            return cached

    # ── 유니버스 수집 ──
    print("\n풀 유니버스 다운로드 시작...")
    print("유니버스 수집 중...")

    us_tickers, us_sectors = fetch_sp500_tickers()
    ndx_tickers, ndx_sectors = fetch_nasdaq100_tickers()

    # S&P500 중복 제거 후 NASDAQ-100 신규 종목 추가
    sp500_set  = set(us_tickers)
    ndx_new    = [t for t in ndx_tickers if t not in sp500_set]
    ndx_new_sec = {t: s for t, s in ndx_sectors.items() if t not in sp500_set}
    print(f"  NASDAQ-100 신규 추가: {len(ndx_new)}개 (S&P500 중복 {len(ndx_tickers) - len(ndx_new)}개 제거)")

    us_tickers = us_tickers + ndx_new
    us_sectors = {**us_sectors, **ndx_new_sec}

    kr_tickers = fetch_kr_tickers()
    kr_sectors = {t: "Unknown" for t in kr_tickers}

    all_tickers  = us_tickers + kr_tickers
    universe_map = {**us_sectors, **kr_sectors}

    print(f"  유니버스 합계: US {len(us_tickers)}종목 + KR {len(kr_tickers)}종목 = {len(all_tickers)}종목")

    # ── 종목 다운로드 ──
    all_data = _download_batch(all_tickers, start, end, batch_size=50, label="종목")

    # ── ETF 다운로드 ──
    etf_tickers = sorted(set(SECTOR_ETF.values()))
    etf_data = _download_batch(etf_tickers, start, end,
                               batch_size=len(etf_tickers), label="ETF")

    # ── SPY 다운로드 ──
    print("  SPY 다운로드 중...", end="", flush=True)
    spy_raw = yf.download("SPY", start=start, end=end,
                          auto_adjust=True, progress=False)
    if isinstance(spy_raw.columns, pd.MultiIndex):
        spy_raw = spy_raw.droplevel(level=1, axis=1)
    spy_df = _clean_ohlcv(spy_raw, min_rows=1)
    if spy_df is None:
        spy_df = spy_raw.copy()
    print(f" {len(spy_df)}행")

    # ── 캐시 저장 ──
    _save_cache(all_data, spy_df, etf_data, universe_map, start)

    return all_data, spy_df, etf_data, universe_map


# ══════════════════════════════════════════════════════════════
# CLI: 캐시 강제 갱신 / 상태 확인
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="풀 유니버스 데이터 캐시 관리")
    parser.add_argument("--refresh", action="store_true",
                        help="캐시 강제 갱신 (재다운로드)")
    parser.add_argument("--start", default="2015-01-01",
                        help="데이터 시작일 (기본값: 2015-01-01)")
    parser.add_argument("--status", action="store_true",
                        help="캐시 상태만 확인")
    args = parser.parse_args()

    if args.status:
        manifest_path = CACHE_DIR / "manifest.json"
        if not manifest_path.exists():
            print("캐시 없음")
        else:
            with open(manifest_path, encoding="utf-8") as f:
                m = json.load(f)
            print(f"캐시 상태:")
            print(f"  저장일   : {m.get('downloaded_at', 'N/A')}")
            print(f"  시작일   : {m.get('start', 'N/A')}")
            print(f"  종목 수  : {m.get('ticker_count', 'N/A')}")
            print(f"  ETF 수   : {m.get('etf_count', 'N/A')}")
            print(f"  캐시경로 : {CACHE_DIR}")
    else:
        all_data, spy_df, etf_data, universe_map = load_full_universe(
            start=args.start,
            force_refresh=args.refresh,
        )
        print(f"\n완료: {len(all_data)}종목, SPY {len(spy_df)}행, ETF {len(etf_data)}개")
