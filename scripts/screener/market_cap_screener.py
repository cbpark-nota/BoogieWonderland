"""
시가총액 Top 20 신규 진입 스크리너
════════════════════════════════════════════════════════════
전략 개요:
  매 영업일 시총 Top 20을 확인 → 새로 진입한 종목 = 시장 메타 트렌드 신호
  새로 Top 20에 올라온 종목을 다음 영업일 시가에 매수

대상 시장:
  US: S&P500 + NASDAQ-100 유니버스에서 시총 Top 20
  KR: KOSPI 200 + KOSDAQ 150 유니버스에서 시총 Top 20

시총 계산:
  현재: yfinance info['marketCap'] (현재 스냅샷)
  과거 근사: 일봉 Close × sharesOutstanding (shares는 현재값 고정 → 한계 있음)
════════════════════════════════════════════════════════════
"""
import argparse
import io
import json
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

TOP_N = 20
RESULTS_DIR = Path(__file__).parent.parent.parent / "data" / "market_cap"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

PREV_SNAPSHOT_PATH = RESULTS_DIR / "prev_top20.json"


# ── 유니버스 수집 ─────────────────────────────────────────

def fetch_sp500_tickers() -> list[str]:
    """S&P500 구성 종목 수집."""
    try:
        url = (
            "https://raw.githubusercontent.com/datasets/"
            "s-and-p-500-companies/main/data/constituents.csv"
        )
        df = pd.read_csv(url)
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        print(f"  S&P500 {len(tickers)}개 수집")
        return tickers
    except Exception as e:
        print(f"  S&P500 수집 실패 ({e})")
        return []


def fetch_nasdaq100_tickers() -> list[str]:
    """NASDAQ-100 구성 종목 수집 (Wikipedia)."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(
            "https://en.wikipedia.org/wiki/Nasdaq-100",
            headers=headers, timeout=15,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        ndx = tables[4]
        tickers = ndx["Ticker"].str.replace(".", "-", regex=False).tolist()
        print(f"  NASDAQ-100 {len(tickers)}개 수집")
        return tickers
    except Exception as e:
        print(f"  NASDAQ-100 수집 실패 ({e})")
        return []


def fetch_kr_tickers(kospi_n: int = 200, kosdaq_n: int = 150) -> list[str]:
    """KRX에서 KOSPI/KOSDAQ 종목 수집."""
    try:
        url = (
            "http://kind.krx.co.kr/corpgeneral/corpList.do"
            "?method=download&searchType=13"
        )
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

        kospi_tickers = [f"{str(c).zfill(6)}.KS" for c in kospi["종목코드"].tolist()][:kospi_n]
        kosdaq_tickers = [f"{str(c).zfill(6)}.KQ" for c in kosdaq["종목코드"].tolist()][:kosdaq_n]
        all_kr = kospi_tickers + kosdaq_tickers
        print(f"  KR KOSPI {len(kospi_tickers)}개 + KOSDAQ {len(kosdaq_tickers)}개 수집")
        return all_kr
    except Exception as e:
        print(f"  KR 수집 실패 ({e}), 네이버 금융 fallback...")
        return _fetch_kr_from_naver(kospi_n, kosdaq_n)


def _fetch_kr_from_naver(kospi_n: int, kosdaq_n: int) -> list[str]:
    """네이버 금융 시가총액 순위에서 KR 종목 수집 (fallback)."""
    import re
    from bs4 import BeautifulSoup

    def _scrape_market(sosok: int, n: int, suffix: str) -> list[str]:
        headers = {"User-Agent": "Mozilla/5.0"}
        tickers: list[str] = []
        page = 1
        while len(tickers) < n:
            url = (
                f"https://finance.naver.com/sise/sise_market_sum.nhn"
                f"?sosok={sosok}&page={page}"
            )
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
        result = _scrape_market(0, kospi_n, ".KS") + _scrape_market(1, kosdaq_n, ".KQ")
        print(f"  네이버 fallback: {len(result)}개 수집")
        return result
    except Exception as e:
        print(f"  KR 수집 최종 실패 ({e})")
        return []


# ── 시가총액 조회 ─────────────────────────────────────────

def get_market_caps_current(tickers: list[str]) -> dict[str, float]:
    """yfinance에서 현재 시가총액 가져오기."""
    caps: dict[str, float] = {}
    for i in range(0, len(tickers), 50):
        batch = tickers[i:i + 50]
        print(f"\r  시총 조회: {i}/{len(tickers)}", end="", flush=True)
        for t in batch:
            try:
                info = yf.Ticker(t).fast_info
                mc = info.get("market_cap", None)
                if mc and mc > 0:
                    caps[t] = float(mc)
            except Exception:
                pass
    print(f"\r  시총 조회 완료: {len(caps)}/{len(tickers)}개")
    return caps


def get_shares_outstanding(tickers: list[str]) -> dict[str, int]:
    """yfinance에서 발행주식수 가져오기 (과거 시총 근사용)."""
    shares: dict[str, int] = {}
    for i in range(0, len(tickers), 50):
        batch = tickers[i:i + 50]
        print(f"\r  발행주식수: {i}/{len(tickers)}", end="", flush=True)
        for t in batch:
            try:
                info = yf.Ticker(t).fast_info
                s = info.get("shares", None)
                if s and s > 0:
                    shares[t] = int(s)
            except Exception:
                pass
    print(f"\r  발행주식수 완료: {len(shares)}/{len(tickers)}개")
    return shares


# ── Top 20 계산 ───────────────────────────────────────────

def get_top20(market_caps: dict[str, float]) -> list[str]:
    """시가총액 기준 상위 TOP_N 반환."""
    if not market_caps:
        return []
    sorted_caps = sorted(market_caps.items(), key=lambda x: x[1], reverse=True)
    return [t for t, _ in sorted_caps[:TOP_N]]


def load_prev_top20() -> dict[str, list[str]]:
    """이전 Top 20 스냅샷 로드."""
    if PREV_SNAPSHOT_PATH.exists():
        with open(PREV_SNAPSHOT_PATH) as f:
            return json.load(f)
    return {"us": [], "kr": []}


def save_top20(us_top20: list[str], kr_top20: list[str],
               us_caps: dict[str, float], kr_caps: dict[str, float]) -> None:
    """현재 Top 20 스냅샷 저장."""
    snapshot = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "us": us_top20,
        "kr": kr_top20,
        "us_caps": {t: us_caps.get(t, 0) for t in us_top20},
        "kr_caps": {t: kr_caps.get(t, 0) for t in kr_top20},
    }
    with open(PREV_SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)


def detect_new_entrants(
    current_top20: list[str],
    prev_top20: list[str],
) -> list[str]:
    """이전 대비 새로 Top 20에 진입한 종목 반환."""
    prev_set = set(prev_top20)
    return [t for t in current_top20 if t not in prev_set]


def detect_exits(
    current_top20: list[str],
    prev_top20: list[str],
) -> list[str]:
    """이전 대비 Top 20에서 퇴출된 종목 반환."""
    curr_set = set(current_top20)
    return [t for t in prev_top20 if t not in curr_set]


# ── ATR 스톱로스 계산 ─────────────────────────────────────

def calc_atr_stop(ticker: str, atr_mult: float = 2.0, period: int = 14) -> dict | None:
    """yfinance에서 최근 가격 + ATR 기반 스톱로스 계산."""
    try:
        df = yf.download(ticker, period="3mo", auto_adjust=True, progress=False)
        if df.empty or len(df) < period + 2:
            return None
        close = df["Close"].squeeze()
        high = df["High"].squeeze()
        low = df["Low"].squeeze()

        # ATR 계산 (True Range)
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]

        current_price = float(close.iloc[-1])
        high_20d = float(high.tail(20).max())
        stop_price = high_20d - atr_mult * atr

        return {
            "price": round(current_price, 4),
            "atr": round(float(atr), 4),
            "stop_price": round(float(stop_price), 4),
            "stop_dist_pct": round((current_price - float(stop_price)) / current_price * 100, 2),
        }
    except Exception:
        return None


# ── 결과 출력 ─────────────────────────────────────────────

def print_results(
    market: str,
    top20: list[str],
    new_entrants: list[str],
    exits: list[str],
    caps: dict[str, float],
) -> None:
    """스크리닝 결과 출력."""
    cap_unit = "억원" if market == "KR" else "억$"
    divisor = 1e8 if market == "KR" else 1e8  # 억 단위

    print(f"\n{'═'*60}")
    print(f"  {market} 시총 Top {TOP_N}")
    print(f"{'═'*60}")

    for i, t in enumerate(top20, 1):
        cap_val = caps.get(t, 0)
        cap_str = f"{cap_val / divisor:,.0f} {cap_unit}" if cap_val else "N/A"
        new_mark = "★ NEW" if t in new_entrants else "     "
        print(f"  {new_mark} {i:2d}. {t:<15} {cap_str}")

    if new_entrants:
        print(f"\n  ▲ 신규 진입 ({len(new_entrants)}개): {', '.join(new_entrants)}")
    if exits:
        print(f"  ▼ 퇴출 ({len(exits)}개): {', '.join(exits)}")

    print()


# ── 메인 스크리닝 함수 ────────────────────────────────────

def run_market_cap_screening(
    save_result: bool = True,
    atr_mult: float = 2.0,
) -> dict:
    """시가총액 Top 20 신규 진입 스크리닝 실행.

    Returns:
        dict: 스크리닝 결과 (new_entrants, exits, top20, caps, atr_stops)
    """
    print("=" * 60)
    print("  시가총액 Top 20 신규 진입 스크리너")
    print("=" * 60)

    # 유니버스 수집
    print("\n[1] 유니버스 수집")
    sp500 = fetch_sp500_tickers()
    ndx100 = fetch_nasdaq100_tickers()
    sp500_set = set(sp500)
    ndx_new = [t for t in ndx100 if t not in sp500_set]
    us_universe = sp500 + ndx_new
    kr_universe = fetch_kr_tickers()
    print(f"  US: {len(us_universe)}개 | KR: {len(kr_universe)}개")

    # 현재 시총 조회
    print("\n[2] 현재 시가총액 조회")
    print("  US 시총 조회 중...")
    us_caps = get_market_caps_current(us_universe)
    print("  KR 시총 조회 중...")
    kr_caps = get_market_caps_current(kr_universe)

    # Top 20 계산
    us_top20 = get_top20(us_caps)
    kr_top20 = get_top20(kr_caps)

    # 이전 스냅샷 로드 및 비교
    print("\n[3] 신규 진입 감지")
    prev = load_prev_top20()
    prev_us = prev.get("us", [])
    prev_kr = prev.get("kr", [])

    us_new = detect_new_entrants(us_top20, prev_us)
    kr_new = detect_new_entrants(kr_top20, prev_kr)
    us_exits = detect_exits(us_top20, prev_us)
    kr_exits = detect_exits(kr_top20, prev_kr)

    # 결과 출력
    print_results("US", us_top20, us_new, us_exits, us_caps)
    print_results("KR", kr_top20, kr_new, kr_exits, kr_caps)

    # ATR 스톱로스 계산 (신규 진입 종목)
    all_new_entrants = us_new + kr_new
    atr_stops: dict[str, dict] = {}
    if all_new_entrants:
        print("[4] ATR 스톱로스 계산")
        for t in all_new_entrants:
            stop = calc_atr_stop(t, atr_mult)
            if stop:
                atr_stops[t] = stop
                print(f"  {t}: 현재가={stop['price']}, 스톱={stop['stop_price']} ({stop['stop_dist_pct']:.1f}%)")

    # 스냅샷 저장
    if save_result and (us_top20 or kr_top20):
        save_top20(us_top20, kr_top20, us_caps, kr_caps)
        print(f"\n  스냅샷 저장: {PREV_SNAPSHOT_PATH}")

    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "us": {
            "top20": us_top20,
            "new_entrants": us_new,
            "exits": us_exits,
            "caps": {t: us_caps.get(t, 0) for t in us_top20},
        },
        "kr": {
            "top20": kr_top20,
            "new_entrants": kr_new,
            "exits": kr_exits,
            "caps": {t: kr_caps.get(t, 0) for t in kr_top20},
        },
        "atr_stops": atr_stops,
    }

    return result


def export_to_json(result: dict, output_path: Path) -> None:
    """스크리닝 결과를 JSON으로 저장."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  JSON 저장: {output_path}")


# ── CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="시가총액 Top 20 신규 진입 스크리너")
    parser.add_argument("--atr-mult", type=float, default=2.0, help="ATR 승수 (기본: 2.0)")
    parser.add_argument("--no-save", action="store_true", help="스냅샷 저장 안 함")
    parser.add_argument("--output", type=str, default=None, help="JSON 출력 경로")
    args = parser.parse_args()

    result = run_market_cap_screening(
        save_result=not args.no_save,
        atr_mult=args.atr_mult,
    )

    if args.output:
        export_to_json(result, Path(args.output))

    # 요약
    us_new = result["us"]["new_entrants"]
    kr_new = result["kr"]["new_entrants"]
    print("\n" + "=" * 60)
    print("  스크리닝 완료")
    if us_new:
        print(f"  US 신규 진입: {', '.join(us_new)}")
    if kr_new:
        print(f"  KR 신규 진입: {', '.join(kr_new)}")
    if not us_new and not kr_new:
        print("  신규 진입 종목 없음 (Top 20 변동 없음)")
    print("=" * 60)


if __name__ == "__main__":
    main()
