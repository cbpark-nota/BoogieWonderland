"""
숏스퀴즈 스크리너
══════════════════════════════════════════════════════════
숏스퀴즈 발생 가능성이 높은 종목을 스크리닝합니다.

스코어링 지표 (각 0~1 정규화 후 가중 합산):
  ① SI % of Float      — 유동주식 대비 공매도 잔량 비율
  ② Days to Cover      — 커버에 필요한 일수 (공매도잔량 ÷ 일평균거래량)
  ③ Cost to Borrow     — 대차 비용 (높을수록 squeeze 압력 ↑)
  ④ Volume Surge       — 거래량 급증 (평균 대비 비율)
  ⑤ FTD Trend          — Failure to Deliver 증가 추세 (보조)

파라미터는 모두 상수로 정의하여 나중에 튜닝 가능.
══════════════════════════════════════════════════════════
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from short_squeeze_data import (
    fetch_us_yfinance_short,
    fetch_iborrowdesk_ctb,
    fetch_us_volume_ratio,
    fetch_finra_short_volume,
    fetch_sec_ftd,
    fetch_kr_short_data,
    fetch_kr_volume_ratio,
)

# ═══════════════════════════════════════════════════════════════
# 파라미터 상수 — 나중에 튜닝 가능한 값들
# ═══════════════════════════════════════════════════════════════

# ── US 필터링 임계값 ─────────────────────────────────────────
US_SI_FLOAT_MIN  = 0.15   # Short Interest >= 15% of Float
US_DTC_MIN       = 5.0    # Days to Cover >= 5일
US_CTB_MIN       = 0.5    # Cost to Borrow >= 0.5% (연간)
US_VOL_RATIO_MIN = 1.5    # 5일 평균 거래량 >= 1.5 × 20일 평균
US_PRICE_MIN     = 1.0    # 최소 주가 (페니스톡 제외)
US_MARKET_CAP_MIN = 50_000_000  # 최소 시가총액 5천만 달러

# ── KR 필터링 임계값 ─────────────────────────────────────────
KR_SI_PCT_MIN    = 1.0    # 공매도 잔고 비율 >= 1.0%
KR_VOL_RATIO_MIN = 1.5    # 5일 공매도거래량 >= 1.5 × 20일 평균

# ── 스코어링 가중치 ──────────────────────────────────────────
# US 지표별 가중치 (합계 = 1.0)
US_WEIGHTS = {
    "si_pct_float":         0.35,  # 가장 핵심 지표
    "days_to_cover":        0.25,  # 커버 압력
    "ctb_rate":             0.20,  # 대차 비용 (높을수록 압력 ↑)
    "vol_ratio":            0.15,  # 거래량 급증
    "ftd_trend":            0.05,  # FTD 보조 지표
}

# KR 지표별 가중치 (합계 = 1.0)
KR_WEIGHTS = {
    "si_pct":               0.50,  # 공매도 잔고 비율
    "vol_ratio":            0.35,  # 거래량 급증
    "si_balance_change":    0.15,  # 잔고 변화 추세 (보조)
}

# ── 출력 설정 ────────────────────────────────────────────────
US_TOP_N   = 20   # US 상위 N개 출력
KR_TOP_N   = 15   # KR 상위 N개 출력
BATCH_SIZE = 50   # 배치 다운로드 크기


# ═══════════════════════════════════════════════════════════════
# 유틸리티
# ═══════════════════════════════════════════════════════════════

def safe_float(v, ndigits: int = 4) -> Optional[float]:
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return round(f, ndigits)
    except (TypeError, ValueError):
        return None


def minmax_normalize(series: pd.Series) -> pd.Series:
    """0~1 min-max 정규화."""
    mn, mx = series.min(), series.max()
    if mx - mn < 1e-9:
        return pd.Series(0.5, index=series.index)
    return (series - mn) / (mx - mn)


# ═══════════════════════════════════════════════════════════════
# US 스크리닝
# ═══════════════════════════════════════════════════════════════

def screen_us_ticker(ticker: str, enable_finra: bool = False,
                     enable_ftd: bool = False) -> Optional[dict]:
    """
    단일 US 티커의 공매도 데이터를 수집하고 필터링 조건을 검사합니다.
    통과하면 지표 dict 반환, 실패하면 None 반환.
    """
    # 1) yfinance 기본 공매도 데이터
    yf_data = fetch_us_yfinance_short(ticker)
    si_pct   = yf_data.get("si_pct_float")   # 0~1
    dtc      = yf_data.get("days_to_cover")

    # 필터링: SI % of Float
    if si_pct is None or si_pct < US_SI_FLOAT_MIN:
        return None
    # 필터링: Days to Cover
    if dtc is None or dtc < US_DTC_MIN:
        return None

    # 2) 거래량 비율
    vol_data = fetch_us_volume_ratio(ticker)
    vol_r5   = vol_data.get("vol_ratio_5d")
    vol_r1   = vol_data.get("vol_ratio_1d")

    # 3) iBorrowDesk CTB
    ctb_data = fetch_iborrowdesk_ctb(ticker)
    ctb_rate = ctb_data.get("ctb_rate")

    # 4) 현재가 + 시총 확인
    try:
        info = yf.Ticker(ticker).info
        price    = safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
        mkt_cap  = safe_float(info.get("marketCap"))
        name     = info.get("shortName") or info.get("longName")
        sector   = info.get("sector", "Unknown")
        if price is not None and price < US_PRICE_MIN:
            return None
        if mkt_cap is not None and mkt_cap < US_MARKET_CAP_MIN:
            return None
    except Exception:
        price = None
        mkt_cap = None
        name = None
        sector = "Unknown"

    # 5) 선택적: FINRA short volume
    finra_data = {}
    if enable_finra:
        finra_data = fetch_finra_short_volume(ticker)

    # 6) 선택적: SEC FTD
    ftd_data = {}
    if enable_ftd:
        ftd_data = fetch_sec_ftd(ticker)

    return {
        "ticker":               ticker,
        "market":               "US",
        "name":                 name,
        "sector":               sector,
        "price":                price,
        "market_cap":           mkt_cap,
        # SI 지표
        "si_pct_float":         safe_float(si_pct * 100, 2),   # % 단위로 변환
        "days_to_cover":        safe_float(dtc, 2),
        "shares_short":         yf_data.get("shares_short"),
        "float_shares":         yf_data.get("float_shares"),
        # CTB
        "ctb_rate":             safe_float(ctb_rate, 2),
        "ctb_available":        ctb_data.get("available"),
        # 거래량
        "vol_ratio_5d":         safe_float(vol_r5, 2),
        "vol_ratio_1d":         safe_float(vol_r1, 2),
        # FINRA short volume
        "short_vol_pct_avg":    safe_float(finra_data.get("short_vol_pct_avg"), 2),
        "short_vol_pct_last":   safe_float(finra_data.get("short_vol_pct_last"), 2),
        "short_vol_trend":      safe_float(finra_data.get("short_vol_ratio_trend"), 4),
        # FTD
        "ftd_total":            ftd_data.get("ftd_total"),
        "ftd_trend":            safe_float(ftd_data.get("ftd_trend"), 0),
    }


def score_us(records: list[dict]) -> pd.DataFrame:
    """
    US 스크리닝 통과 종목에 숏스퀴즈 점수를 부여합니다.
    각 지표를 min-max 정규화한 뒤 가중 합산.
    """
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df.set_index("ticker", inplace=True)

    # 정규화할 컬럼 매핑 (높을수록 squeeze 가능성 ↑)
    col_map = {
        "si_pct_float":  "si_pct_float",
        "days_to_cover": "days_to_cover",
        "ctb_rate":      "ctb_rate",
        "vol_ratio":     "vol_ratio_5d",
        "ftd_trend":     "ftd_trend",
    }

    score = pd.Series(0.0, index=df.index)
    for key, col in col_map.items():
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce").fillna(0)
        norm = minmax_normalize(s)
        score += norm * US_WEIGHTS.get(key, 0)

    df["squeeze_score"] = (score * 100).round(2)
    df.reset_index(inplace=True)
    return df.sort_values("squeeze_score", ascending=False)


# ═══════════════════════════════════════════════════════════════
# KR 스크리닝
# ═══════════════════════════════════════════════════════════════

def screen_kr_ticker(ticker: str) -> Optional[dict]:
    """
    단일 KR 티커의 공매도 데이터를 수집하고 필터링 조건을 검사합니다.
    """
    # pykrx 공매도 데이터
    kr_data = fetch_kr_short_data(ticker)
    si_pct  = kr_data.get("si_pct")
    vol_r5  = kr_data.get("vol_ratio_5d")

    # 필터링: 공매도 잔고 비율
    if si_pct is None or si_pct < KR_SI_PCT_MIN:
        return None

    # 거래량 비율 (전체 거래량 기준)
    vol_data = fetch_kr_volume_ratio(ticker)
    total_vol_r5 = vol_data.get("vol_ratio_5d")

    # 현재가
    try:
        info  = yf.Ticker(ticker).info
        price = safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
        name  = info.get("shortName") or info.get("longName")
    except Exception:
        price = None
        name  = None

    return {
        "ticker":           ticker,
        "market":           "KR",
        "name":             name,
        "sector":           "Unknown",   # pykrx에서 섹터 별도 수집 필요
        "price":            price,
        # SI 지표
        "si_balance":       kr_data.get("si_balance"),
        "si_balance_value": kr_data.get("si_balance_value"),
        "si_pct":           safe_float(si_pct, 2),
        "short_vol_avg":    kr_data.get("short_vol_avg"),
        # 거래량
        "vol_ratio_5d_short": safe_float(vol_r5, 2),   # 공매도 거래량 비율
        "vol_ratio_5d":       safe_float(total_vol_r5, 2),  # 전체 거래량 비율
    }


def score_kr(records: list[dict]) -> pd.DataFrame:
    """KR 종목 숏스퀴즈 점수 부여."""
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df.set_index("ticker", inplace=True)

    col_map = {
        "si_pct":            "si_pct",
        "vol_ratio":         "vol_ratio_5d",
        "si_balance_change": "vol_ratio_5d_short",
    }

    score = pd.Series(0.0, index=df.index)
    for key, col in col_map.items():
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce").fillna(0)
        norm = minmax_normalize(s)
        score += norm * KR_WEIGHTS.get(key, 0)

    df["squeeze_score"] = (score * 100).round(2)
    df.reset_index(inplace=True)
    return df.sort_values("squeeze_score", ascending=False)


# ═══════════════════════════════════════════════════════════════
# 메인 스크리닝 실행
# ═══════════════════════════════════════════════════════════════

def run_us_screening(
    us_tickers: list[str],
    enable_finra: bool = False,
    enable_ftd: bool = False,
    top_n: int = US_TOP_N,
) -> pd.DataFrame:
    """US 전체 유니버스 숏스퀴즈 스크리닝."""
    passed: list[dict] = []
    total = len(us_tickers)

    print(f"  US 종목 {total}개 스크리닝 중...")
    for i, ticker in enumerate(us_tickers, 1):
        if i % 50 == 0:
            print(f"    {i}/{total}...")
        result = screen_us_ticker(ticker, enable_finra=enable_finra,
                                  enable_ftd=enable_ftd)
        if result is not None:
            passed.append(result)

    print(f"  US 필터 통과: {len(passed)}개 / {total}개")
    if not passed:
        return pd.DataFrame()

    df = score_us(passed)
    return df.head(top_n)


def run_kr_screening(
    kr_tickers: list[str],
    top_n: int = KR_TOP_N,
) -> pd.DataFrame:
    """KR 전체 유니버스 숏스퀴즈 스크리닝."""
    passed: list[dict] = []
    total = len(kr_tickers)

    print(f"  KR 종목 {total}개 스크리닝 중...")
    for i, ticker in enumerate(kr_tickers, 1):
        if i % 20 == 0:
            print(f"    {i}/{total}...")
        result = screen_kr_ticker(ticker)
        if result is not None:
            passed.append(result)

    print(f"  KR 필터 통과: {len(passed)}개 / {total}개")
    if not passed:
        return pd.DataFrame()

    df = score_kr(passed)
    return df.head(top_n)


def build_output_records(df: pd.DataFrame, rank_offset: int = 1) -> list[dict]:
    """DataFrame → JSON 직렬화 가능한 dict 리스트로 변환."""
    records = []
    for rank, (_, row) in enumerate(df.iterrows(), rank_offset):
        record: dict = {"rank": rank}
        for col in df.columns:
            val = row[col]
            if isinstance(val, (np.integer,)):
                val = int(val)
            elif isinstance(val, (np.floating,)):
                val = None if np.isnan(val) else float(val)
            elif isinstance(val, float) and val != val:  # NaN
                val = None
            record[col] = val
        records.append(record)
    return records


# ═══════════════════════════════════════════════════════════════
# CLI 실행
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="숏스퀴즈 스크리너")
    parser.add_argument("--finra", action="store_true", help="FINRA short volume 데이터 포함")
    parser.add_argument("--ftd",   action="store_true", help="SEC FTD 데이터 포함")
    parser.add_argument("--kr-only", action="store_true", help="KR 시장만 실행")
    parser.add_argument("--us-only", action="store_true", help="US 시장만 실행")
    parser.add_argument("--sample", action="store_true", help="샘플 티커로 빠른 테스트")
    args = parser.parse_args()

    today = datetime.now().strftime("%Y-%m-%d")
    print("=" * 64)
    print(f"  숏스퀴즈 스크리너   기준일: {today}")
    print(f"  파라미터: SI>={US_SI_FLOAT_MIN*100:.0f}% | DTC>={US_DTC_MIN} | "
          f"Vol>={US_VOL_RATIO_MIN}x")
    print("=" * 64)

    # 유니버스 로드
    if args.sample:
        # 빠른 테스트용 샘플 티커
        us_tickers = ["GME", "AMC", "BBBY", "SPCE", "RIVN", "LCID",
                      "BYND", "CLOV", "WISH", "WKHS"]
        kr_tickers = ["005930.KS", "000660.KS", "035420.KS",
                      "373220.KS", "247540.KS"]
    else:
        # 실 유니버스 (export_json.py에서 동적 수집)
        sys.path.insert(0, str(Path(__file__).parent.parent))
        try:
            import export_json as ej
            print("\n[유니버스 수집 중]")
            us_sp500, us_sp500_sectors   = ej.fetch_sp500_tickers()
            us_ndx, us_ndx_sectors       = ej.fetch_nasdaq100_tickers()
            us_tickers = list(dict.fromkeys(us_sp500 + us_ndx))
            kr_tickers = ej.fetch_kr_tickers()
        except Exception as e:
            print(f"  유니버스 수집 실패 ({e}), 기본 유니버스 사용")
            import screener_v3 as sc
            us_tickers = list(sc.US_UNIVERSE.keys())
            kr_tickers = list(sc.KR_UNIVERSE.keys())

    print(f"  유니버스: US {len(us_tickers)}개, KR {len(kr_tickers)}개\n")

    us_df = pd.DataFrame()
    kr_df = pd.DataFrame()

    if not args.kr_only:
        print("[US 스크리닝]")
        us_df = run_us_screening(us_tickers,
                                 enable_finra=args.finra,
                                 enable_ftd=args.ftd)

    if not args.us_only:
        print("\n[KR 스크리닝]")
        kr_df = run_kr_screening(kr_tickers)

    # 결과 출력
    print("\n" + "=" * 64)
    if not us_df.empty:
        print(f"\n  ★ US 숏스퀴즈 상위 {len(us_df)}개")
        print(f"  {'순위':>3} {'티커':<10} {'점수':>6} {'SI%Float':>9} "
              f"{'DTC':>6} {'CTB%':>6} {'Vol5x':>6} {'가격':>8}")
        print("  " + "─" * 58)
        for _, r in us_df.iterrows():
            print(
                f"  {int(r.get('rank',0)):>3}위 "
                f"{str(r.get('ticker','')):<10} "
                f"{r.get('squeeze_score', 0):>6.1f} "
                f"{r.get('si_pct_float') or 0:>9.1f}% "
                f"{r.get('days_to_cover') or 0:>6.1f} "
                f"{r.get('ctb_rate') or 0:>6.1f} "
                f"{r.get('vol_ratio_5d') or 0:>6.2f}x "
                f"${r.get('price') or 0:>7.2f}"
            )

    if not kr_df.empty:
        print(f"\n  ★ KR 숏스퀴즈 상위 {len(kr_df)}개")
        print(f"  {'순위':>3} {'티커':<13} {'점수':>6} {'잔고비율':>9} "
              f"{'거래량배율':>8} {'가격':>10}")
        print("  " + "─" * 55)
        for _, r in kr_df.iterrows():
            print(
                f"  {int(r.get('rank',0)):>3}위 "
                f"{str(r.get('ticker','')):<13} "
                f"{r.get('squeeze_score', 0):>6.1f} "
                f"{r.get('si_pct') or 0:>9.2f}% "
                f"{r.get('vol_ratio_5d') or 0:>8.2f}x "
                f"₩{r.get('price') or 0:>9,.0f}"
            )

    # CSV 저장
    if not us_df.empty:
        us_df.to_csv("short_squeeze_us.csv", index=False, encoding="utf-8-sig")
        print("\n  결과 저장: short_squeeze_us.csv")
    if not kr_df.empty:
        kr_df.to_csv("short_squeeze_kr.csv", index=False, encoding="utf-8-sig")
        print("  결과 저장: short_squeeze_kr.csv")

    # JSON 저장
    output = {
        "run_date": today,
        "params": {
            "us_si_float_min": US_SI_FLOAT_MIN,
            "us_dtc_min": US_DTC_MIN,
            "us_ctb_min": US_CTB_MIN,
            "us_vol_ratio_min": US_VOL_RATIO_MIN,
            "kr_si_pct_min": KR_SI_PCT_MIN,
        },
        "total_us_screened": len(us_tickers),
        "total_kr_screened": len(kr_tickers),
        "total_us_passed":   len(us_df),
        "total_kr_passed":   len(kr_df),
        "us_results": build_output_records(us_df),
        "kr_results": build_output_records(kr_df),
    }
    with open("short_squeeze_result.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("  결과 저장: short_squeeze_result.json")
