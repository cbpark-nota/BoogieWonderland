"""
일별 시가총액 + 가격 데이터 수집기
──────────────────────────────────────
KST 23:00 — 한국 종목 (KOSPI/KOSDAQ)
KST 07:00 — 미국 종목 (S&P500)

데이터를 월별 parquet 파일로 저장.
"""
import argparse
import io
import os
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests
import yfinance as yf

KST = timezone(timedelta(hours=9))
DATA_DIR = os.environ.get("COLLECT_DATA_DIR", "/data/daily")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


# ── 종목 리스트 ──────────────────────────────────────────────

def fetch_sp500_tickers():
    """S&P500 구성 종목."""
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
    df = pd.read_csv(url)
    tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
    sectors = dict(zip(
        df["Symbol"].str.replace(".", "-", regex=False),
        df["GICS Sector"]
    ))
    return tickers, sectors


def fetch_kr_tickers():
    """KRX에서 KOSPI/KOSDAQ 종목 가져오기."""
    url = "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    krx = pd.read_html(io.StringIO(r.text))[0]

    kospi = krx[(krx["시장구분"] == "유가") & (krx["종목코드"].str.match(r"^\d{6}$"))].copy()
    kosdaq = krx[(krx["시장구분"] == "코스닥") & (krx["종목코드"].str.match(r"^\d{6}$"))].copy()

    kospi_tickers = [f"{c}.KS" for c in kospi["종목코드"].tolist()]
    kosdaq_tickers = [f"{c}.KQ" for c in kosdaq["종목코드"].tolist()]

    return kospi_tickers, kosdaq_tickers


# ── 데이터 수집 ──────────────────────────────────────────────

def collect_market_data(tickers, market_label, date_str):
    """종목 리스트의 당일 가격 + 시가총액 수집."""
    rows = []
    batch_size = 50
    total = len(tickers)

    for i in range(0, total, batch_size):
        batch = tickers[i:i + batch_size]
        print(f"\r  [{market_label}] {i}/{total}", end="", flush=True)

        try:
            # 최근 5일 데이터 받아서 마지막 행 사용 (당일 데이터 보장)
            raw = yf.download(batch, period="5d", auto_adjust=True,
                              progress=False, threads=True)

            if isinstance(raw.columns, pd.MultiIndex):
                for t in batch:
                    try:
                        df = raw.xs(t, axis=1, level=1).dropna(how="all")
                        if len(df) == 0:
                            continue
                        last = df.iloc[-1]
                        trade_date = df.index[-1].strftime("%Y-%m-%d")

                        # 발행주식수 가져오기
                        try:
                            info = yf.Ticker(t).fast_info
                            shares = info.get("shares", None)
                            market_cap = info.get("marketCap", None)
                        except Exception:
                            shares = None
                            market_cap = None

                        rows.append({
                            "date": trade_date,
                            "ticker": t,
                            "open": float(last.get("Open", 0)),
                            "high": float(last.get("High", 0)),
                            "low": float(last.get("Low", 0)),
                            "close": float(last.get("Close", 0)),
                            "volume": int(last.get("Volume", 0)),
                            "shares_outstanding": int(shares) if shares else None,
                            "market_cap": int(market_cap) if market_cap else None,
                        })
                    except Exception:
                        pass
            elif len(batch) == 1 and len(raw) > 0:
                last = raw.iloc[-1]
                trade_date = raw.index[-1].strftime("%Y-%m-%d")
                try:
                    info = yf.Ticker(batch[0]).fast_info
                    shares = info.get("shares", None)
                    market_cap = info.get("marketCap", None)
                except Exception:
                    shares = None
                    market_cap = None

                rows.append({
                    "date": trade_date,
                    "ticker": batch[0],
                    "open": float(last.get("Open", 0)),
                    "high": float(last.get("High", 0)),
                    "low": float(last.get("Low", 0)),
                    "close": float(last.get("Close", 0)),
                    "volume": int(last.get("Volume", 0)),
                    "shares_outstanding": int(shares) if shares else None,
                    "market_cap": int(market_cap) if market_cap else None,
                })
        except Exception as e:
            print(f"\n  배치 실패: {e}")

    print(f"\r  [{market_label}] {total}/{total} → {len(rows)}개 수집 완료")
    return rows


def save_to_monthly_parquet(rows, market_label):
    """월별 parquet 파일에 append."""
    if not rows:
        print(f"  [{market_label}] 저장할 데이터 없음")
        return

    df = pd.DataFrame(rows)
    date_str = df["date"].iloc[0]
    month_str = date_str[:7].replace("-", "")  # "202603"

    dir_path = os.path.join(DATA_DIR, market_label)
    ensure_dir(dir_path)

    fpath = os.path.join(dir_path, f"{market_label}_{month_str}.parquet")

    if os.path.exists(fpath):
        existing = pd.read_parquet(fpath)
        # 같은 날짜 데이터 제거 후 append (중복 방지)
        existing = existing[existing["date"] != date_str]
        df = pd.concat([existing, df], ignore_index=True)

    df.to_parquet(fpath, index=False)

    # 시가총액 순위 계산 및 저장
    df_with_cap = df[df["market_cap"].notna()].copy()
    if len(df_with_cap) > 0:
        df_with_cap = df_with_cap.sort_values("market_cap", ascending=False)
        df_with_cap["market_cap_rank"] = range(1, len(df_with_cap) + 1)

        rank_path = os.path.join(dir_path, f"{market_label}_rank_{month_str}.parquet")
        if os.path.exists(rank_path):
            existing_rank = pd.read_parquet(rank_path)
            existing_rank = existing_rank[existing_rank["date"] != date_str]
            rank_df = df_with_cap[["date", "ticker", "market_cap", "market_cap_rank"]]
            rank_df = pd.concat([existing_rank, rank_df], ignore_index=True)
        else:
            rank_df = df_with_cap[["date", "ticker", "market_cap", "market_cap_rank"]]

        rank_df.to_parquet(rank_path, index=False)

    print(f"  [{market_label}] 저장: {fpath} ({len(df)}행)")


# ── 메인 ──────────────────────────────────────────────────────

def collect_kr():
    """한국 시장 데이터 수집 (KST 23:00 실행)."""
    now = datetime.now(KST)
    print(f"{'='*60}")
    print(f"  한국 시장 데이터 수집")
    print(f"  시각: {now.strftime('%Y-%m-%d %H:%M KST')}")
    print(f"{'='*60}")

    t0 = time.time()

    print("\n  종목 리스트 가져오기...")
    kospi_tickers, kosdaq_tickers = fetch_kr_tickers()
    print(f"    KOSPI: {len(kospi_tickers)}개, KOSDAQ: {len(kosdaq_tickers)}개")

    print("\n  KOSPI 데이터 수집...")
    kospi_rows = collect_market_data(kospi_tickers, "kospi", now.strftime("%Y-%m-%d"))
    save_to_monthly_parquet(kospi_rows, "kospi")

    print("\n  KOSDAQ 데이터 수집...")
    kosdaq_rows = collect_market_data(kosdaq_tickers, "kosdaq", now.strftime("%Y-%m-%d"))
    save_to_monthly_parquet(kosdaq_rows, "kosdaq")

    elapsed = time.time() - t0
    print(f"\n  완료: {elapsed:.0f}초 ({elapsed/60:.1f}분)")


def collect_us():
    """미국 시장 데이터 수집 (KST 07:00 실행)."""
    now = datetime.now(KST)
    print(f"{'='*60}")
    print(f"  미국 시장 데이터 수집")
    print(f"  시각: {now.strftime('%Y-%m-%d %H:%M KST')}")
    print(f"{'='*60}")

    t0 = time.time()

    print("\n  S&P500 종목 리스트 가져오기...")
    us_tickers, sectors = fetch_sp500_tickers()
    print(f"    {len(us_tickers)}개")

    print("\n  데이터 수집...")
    us_rows = collect_market_data(us_tickers, "sp500", now.strftime("%Y-%m-%d"))

    # 섹터 정보 추가
    for row in us_rows:
        row["sector"] = sectors.get(row["ticker"], "Unknown")

    save_to_monthly_parquet(us_rows, "sp500")

    # SPY 벤치마크
    print("\n  SPY 벤치마크...")
    spy_rows = collect_market_data(["SPY"], "spy", now.strftime("%Y-%m-%d"))
    save_to_monthly_parquet(spy_rows, "spy")

    elapsed = time.time() - t0
    print(f"\n  완료: {elapsed:.0f}초 ({elapsed/60:.1f}분)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="일별 시장 데이터 수집")
    parser.add_argument("market", choices=["kr", "us", "all"],
                        help="수집 대상 시장")
    args = parser.parse_args()

    if args.market in ("kr", "all"):
        collect_kr()
    if args.market in ("us", "all"):
        collect_us()
