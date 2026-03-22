"""
백테스트용 시장 데이터 사전 다운로드
══════════════════════════════════════════════════════════════
저장 구조:
  data/
    stocks/{TICKER}.parquet   — 종목별 OHLCV
    etfs/{TICKER}.parquet     — 섹터 ETF OHLCV
    spy.parquet               — SPY 벤치마크
    manifest.json             — 다운로드 메타 정보
══════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import json
import os
from datetime import datetime

import pandas as pd
import yfinance as yf

START = "2010-01-01"
END   = "2024-12-31"

DATA_DIR   = "data"
STOCK_DIR  = os.path.join(DATA_DIR, "stocks")
ETF_DIR    = os.path.join(DATA_DIR, "etfs")
SPY_PATH   = os.path.join(DATA_DIR, "spy.parquet")
MANIFEST   = os.path.join(DATA_DIR, "manifest.json")

US_UNIVERSE = {
    "NVDA":"Technology","AAPL":"Technology","MSFT":"Technology","AVGO":"Technology",
    "AMD":"Technology","QCOM":"Technology","AMAT":"Technology","LRCX":"Technology",
    "MU":"Technology","KLAC":"Technology","ORCL":"Technology","ADBE":"Technology",
    "CRM":"Technology","NOW":"Technology","PANW":"Technology","SNPS":"Technology",
    "META":"Communication","GOOGL":"Communication","NFLX":"Communication","TMUS":"Communication",
    "AMZN":"Consumer Disc","TSLA":"Consumer Disc","HD":"Consumer Disc","LULU":"Consumer Disc",
    "LLY":"Health Care","UNH":"Health Care","ABBV":"Health Care","ISRG":"Health Care","VRTX":"Health Care",
    "V":"Financials","MA":"Financials","JPM":"Financials","GS":"Financials",
    "XOM":"Energy","CVX":"Energy","SLB":"Energy",
    "CAT":"Industrials","GE":"Industrials","ETN":"Industrials","LMT":"Industrials",
    "FCX":"Materials","NEM":"Materials",
}
KR_UNIVERSE = {
    "005930.KS":"Technology","000660.KS":"Technology","009150.KS":"Technology",
    "006400.KS":"Technology","373220.KS":"Technology",
    "207940.KS":"Health Care","068270.KS":"Health Care",
    "051910.KS":"Materials","247540.KS":"Materials",
    "005380.KS":"Consumer Disc","000270.KS":"Consumer Disc",
    "035420.KS":"Communication","035720.KS":"Communication",
    "105560.KS":"Financials","055550.KS":"Financials",
    "096770.KS":"Energy","011200.KS":"Industrials",
}
ALL_UNIVERSE = {**US_UNIVERSE, **KR_UNIVERSE}

SECTOR_ETF = {
    "Technology":"XLK","Health Care":"XLV","Financials":"XLF",
    "Consumer Disc":"XLY","Industrials":"XLI","Energy":"XLE",
    "Materials":"XLB","Communication":"XLC",
}


def download_and_save_single(ticker, out_dir, start, end):
    """개별 종목 다운로드 후 parquet로 저장. 성공 시 행 수 반환, 실패 시 0."""
    try:
        df = yf.download(ticker, start=start, end=end,
                         auto_adjust=True, progress=False, threads=False)
        if df.empty:
            return 0

        # yfinance가 MultiIndex 컬럼을 반환하는 경우 처리
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(level=1, axis=1)

        # 필수 컬럼 확인
        required = {"Open", "High", "Low", "Close", "Volume"}
        if not required.issubset(set(df.columns)):
            return 0

        # NaN 행 제거
        df = df.dropna(subset=["Close"])
        if len(df) < 50:
            return 0

        # 인덱스 정리: DatetimeIndex 보장
        df.index = pd.to_datetime(df.index)
        df.index.name = "Date"

        # 컬럼을 필수 컬럼만 유지 (순서 고정)
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()

        # 타입 검증: 숫자 컬럼인지 확인
        for col in ["Open", "High", "Low", "Close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0).astype("int64")
        df = df.dropna(subset=["Close"])

        # 저장
        safe_name = ticker.replace("/", "_")
        path = os.path.join(out_dir, f"{safe_name}.parquet")
        df.to_parquet(path, engine="pyarrow")
        return len(df)
    except Exception as e:
        print(f"    ⚠ {ticker} 실패: {e}")
        return 0


def verify_parquet(path):
    """저장된 parquet 파일 무결성 검증. (ok, row_count, msg) 반환."""
    try:
        df = pd.read_parquet(path, engine="pyarrow")
    except Exception as e:
        return False, 0, f"읽기 실패: {e}"

    # 인덱스 검증
    if not isinstance(df.index, pd.DatetimeIndex):
        return False, 0, "인덱스가 DatetimeIndex가 아님"

    # 컬럼 검증
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = required - set(df.columns)
    if missing:
        return False, 0, f"필수 컬럼 누락: {missing}"

    # 데이터 타입 검증
    for col in ["Open", "High", "Low", "Close"]:
        if not pd.api.types.is_numeric_dtype(df[col]):
            return False, 0, f"{col} 컬럼이 숫자 타입이 아님"

    # NaN 검증
    nan_count = df[["Open", "High", "Low", "Close"]].isna().sum().sum()
    if nan_count > 0:
        return False, len(df), f"경고: OHLC에 NaN {nan_count}건"

    # 날짜 정렬 검증
    if not df.index.is_monotonic_increasing:
        return False, len(df), "날짜가 오름차순이 아님"

    # 가격 양수 검증
    if (df["Close"] <= 0).any():
        return False, len(df), "Close에 0 이하 값 존재"

    return True, len(df), "OK"


if __name__ == "__main__":
    print("=" * 62)
    print("  백테스트용 데이터 다운로드")
    print(f"  기간: {START} ~ {END}")
    print(f"  종목: {len(ALL_UNIVERSE)}개 + ETF {len(set(SECTOR_ETF.values()))}개 + SPY")
    print("=" * 62)

    os.makedirs(STOCK_DIR, exist_ok=True)
    os.makedirs(ETF_DIR, exist_ok=True)

    manifest = {
        "start": START, "end": END,
        "downloaded_at": datetime.now().isoformat(),
        "stocks": {}, "etfs": {}, "spy": {},
    }

    # ── 종목 다운로드 ──
    print(f"\n[1/3] 종목 다운로드 ({len(ALL_UNIVERSE)}개)")
    ok_count, fail_count = 0, 0
    for i, (ticker, sector) in enumerate(ALL_UNIVERSE.items(), 1):
        rows = download_and_save_single(ticker, STOCK_DIR, START, END)
        status = "✓" if rows > 0 else "✗"
        print(f"  {status} {i:2d}/{len(ALL_UNIVERSE)} {ticker:<12} "
              f"{sector:<16} {rows:>5}행")
        if rows > 0:
            manifest["stocks"][ticker] = {
                "sector": sector, "rows": rows,
                "file": f"stocks/{ticker.replace('/', '_')}.parquet",
            }
            ok_count += 1
        else:
            fail_count += 1
    print(f"  → 성공 {ok_count}개, 실패 {fail_count}개")

    # ── ETF 다운로드 ──
    etf_list = sorted(set(SECTOR_ETF.values()))
    print(f"\n[2/3] 섹터 ETF 다운로드 ({len(etf_list)}개)")
    for i, ticker in enumerate(etf_list, 1):
        rows = download_and_save_single(ticker, ETF_DIR, START, END)
        status = "✓" if rows > 0 else "✗"
        print(f"  {status} {i}/{len(etf_list)} {ticker:<6} {rows:>5}행")
        if rows > 0:
            manifest["etfs"][ticker] = {
                "rows": rows,
                "file": f"etfs/{ticker}.parquet",
            }

    # ── SPY 다운로드 ──
    print(f"\n[3/3] SPY 벤치마크 다운로드")
    spy_rows = download_and_save_single("SPY", DATA_DIR, START, END)
    print(f"  {'✓' if spy_rows > 0 else '✗'} SPY {spy_rows}행")
    if spy_rows > 0:
        # SPY는 DATA_DIR에 저장되므로 파일명 수정
        os.rename(os.path.join(DATA_DIR, "SPY.parquet"), SPY_PATH)
        manifest["spy"] = {"rows": spy_rows, "file": "spy.parquet"}

    # ── manifest 저장 ──
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\n  매니페스트 저장: {MANIFEST}")

    # ── 저장 파일 검증 ──
    print(f"\n{'═'*62}")
    print("  저장 파일 검증")
    print("═" * 62)

    errors = []
    # 종목 검증
    for ticker, info in manifest["stocks"].items():
        path = os.path.join(DATA_DIR, info["file"])
        ok, rows, msg = verify_parquet(path)
        if not ok:
            errors.append((ticker, msg))
            print(f"  ✗ {ticker:<12} {msg}")
        elif rows != info["rows"]:
            errors.append((ticker, f"행 수 불일치: manifest={info['rows']}, 파일={rows}"))
            print(f"  ✗ {ticker:<12} 행 수 불일치")

    # ETF 검증
    for ticker, info in manifest["etfs"].items():
        path = os.path.join(DATA_DIR, info["file"])
        ok, rows, msg = verify_parquet(path)
        if not ok:
            errors.append((ticker, msg))
            print(f"  ✗ {ticker:<6} {msg}")

    # SPY 검증
    ok, rows, msg = verify_parquet(SPY_PATH)
    if not ok:
        errors.append(("SPY", msg))
        print(f"  ✗ SPY {msg}")

    if errors:
        print(f"\n  ⚠ 검증 실패: {len(errors)}건")
        for t, m in errors:
            print(f"    - {t}: {m}")
    else:
        total_files = len(manifest["stocks"]) + len(manifest["etfs"]) + 1
        print(f"  ✓ 전체 {total_files}개 파일 검증 통과")

    print(f"\n  완료!")
