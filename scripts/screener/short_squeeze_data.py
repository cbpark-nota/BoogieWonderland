"""
숏스퀴즈 데이터 수집 모듈
══════════════════════════════════════════════════════════
데이터 소스:
  [US]
  - yfinance       : Short Interest % of Float, Days to Cover (shortRatio),
                     Shares Short, Float Shares
  - iBorrowDesk    : Cost to Borrow (CTB) rate — 비공식 JSON API
  - FINRA CDN      : 일별 공매도 거래량 (Short Volume / Total Volume 비율)
  - SEC FTD        : Failure to Deliver 월별 데이터 파싱

  [KR]
  - pykrx          : 공매도 잔고, 공매도 비율, 공매도 거래량

  각 소스 실패 시 None 반환으로 graceful fallback 처리.
══════════════════════════════════════════════════════════
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf

# ── 공통 HTTP 헤더 ────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
_TIMEOUT = 15


# ═══════════════════════════════════════════════════════════════
# US 데이터 수집
# ═══════════════════════════════════════════════════════════════

def fetch_us_yfinance_short(ticker: str) -> dict:
    """
    yfinance Ticker.info에서 공매도 관련 지표를 가져옵니다.

    Returns:
        {
            "si_pct_float"  : float | None,   # 0~1 (예: 0.25 = 25%)
            "days_to_cover" : float | None,   # short ratio (Days to Cover)
            "shares_short"  : int   | None,   # 공매도 잔량 (주수)
            "float_shares"  : int   | None,   # 유통주식수
        }
    """
    try:
        info = yf.Ticker(ticker).info
        return {
            "si_pct_float":  _safe_float(info.get("shortPercentOfFloat")),
            "days_to_cover": _safe_float(info.get("shortRatio")),
            "shares_short":  _safe_int(info.get("sharesShort")),
            "float_shares":  _safe_int(info.get("floatShares")),
        }
    except Exception as e:
        _warn(f"yfinance short data 실패 [{ticker}]: {e}")
        return {"si_pct_float": None, "days_to_cover": None,
                "shares_short": None, "float_shares": None}


def fetch_iborrowdesk_ctb(ticker: str) -> dict:
    """
    iBorrowDesk 비공식 API에서 Cost to Borrow (CTB) 정보를 가져옵니다.

    Returns:
        {
            "ctb_rate"  : float | None,   # 연간 대차 비율 (%)
            "available" : int   | None,   # 가용 주식수
        }
    """
    try:
        url = f"https://iborrowdesk.com/api/ticker/{ticker}"
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if r.status_code != 200:
            return {"ctb_rate": None, "available": None}
        data = r.json()
        # 응답 형태: {"ticker": "GME", "rate": 0.5, "available": 100000, ...}
        rate = _safe_float(data.get("rate") or data.get("borrowRate") or data.get("fee"))
        avail = _safe_int(data.get("available") or data.get("availableShares"))
        return {"ctb_rate": rate, "available": avail}
    except Exception as e:
        _warn(f"iBorrowDesk CTB 실패 [{ticker}]: {e}")
        return {"ctb_rate": None, "available": None}


def fetch_finra_short_volume(ticker: str, lookback_days: int = 5) -> dict:
    """
    FINRA CDN에서 최근 N거래일 일별 공매도 거래량 데이터를 가져옵니다.
    URL: https://cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt

    Returns:
        {
            "short_vol_pct_avg" : float | None,   # 평균 공매도 거래량 비율 (%)
            "short_vol_pct_last": float | None,   # 최근일 공매도 거래량 비율 (%)
            "short_vol_ratio_trend": float | None, # 최근 5일 추세 (기울기)
        }
    """
    try:
        # 최근 N 거래일 날짜 생성 (주말 제외)
        dates = _recent_trading_dates(lookback_days + 5)[:lookback_days]
        rows: list[dict] = []

        for d in dates:
            url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt"
            try:
                r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
                if r.status_code != 200:
                    continue
                content = r.text
                # 파이프 구분자: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
                df = pd.read_csv(io.StringIO(content), sep="|",
                                 dtype=str, on_bad_lines="skip")
                df.columns = [c.strip().upper() for c in df.columns]
                col_sym = next((c for c in df.columns if "SYMBOL" in c), None)
                col_sv  = next((c for c in df.columns if "SHORTVOL" in c
                                and "EXEMPT" not in c), None)
                col_tv  = next((c for c in df.columns if "TOTALVOL" in c), None)
                if col_sym is None or col_sv is None or col_tv is None:
                    continue
                row = df[df[col_sym].str.upper() == ticker.upper()]
                if row.empty:
                    continue
                sv = float(row[col_sv].iloc[0]) if row[col_sv].iloc[0] else 0
                tv = float(row[col_tv].iloc[0]) if row[col_tv].iloc[0] else 0
                if tv > 0:
                    rows.append({"date": d, "sv_pct": sv / tv * 100})
            except Exception:
                continue

        if not rows:
            return {"short_vol_pct_avg": None, "short_vol_pct_last": None,
                    "short_vol_ratio_trend": None}

        df_rows = pd.DataFrame(rows)
        avg  = float(df_rows["sv_pct"].mean())
        last = float(df_rows["sv_pct"].iloc[-1]) if len(df_rows) > 0 else None
        trend = None
        if len(df_rows) >= 3:
            x = np.arange(len(df_rows))
            y = df_rows["sv_pct"].values
            trend = float(np.polyfit(x, y, 1)[0])  # 선형회귀 기울기

        return {
            "short_vol_pct_avg":    round(avg, 2),
            "short_vol_pct_last":   round(last, 2) if last is not None else None,
            "short_vol_ratio_trend": round(trend, 4) if trend is not None else None,
        }
    except Exception as e:
        _warn(f"FINRA short volume 실패 [{ticker}]: {e}")
        return {"short_vol_pct_avg": None, "short_vol_pct_last": None,
                "short_vol_ratio_trend": None}


def fetch_sec_ftd(ticker: str, months: int = 2) -> dict:
    """
    SEC FTD(Failure to Deliver) 월별 데이터를 파싱합니다.
    URL: https://www.sec.gov/ftp/data/failstodeliver/cnsfails{YYYYMM}{a|b}.zip

    Returns:
        {
            "ftd_total"    : int   | None,  # 최근 N개월 합계 FTD 주수
            "ftd_last_date": str   | None,  # 가장 최근 FTD 날짜
            "ftd_trend"    : float | None,  # 추세 (월별 변화량)
        }
    """
    try:
        now = datetime.now()
        monthly: list[float] = []

        for i in range(months):
            d = now - timedelta(days=30 * i)
            ym = d.strftime("%Y%m")
            for half in ("b", "a"):  # b(후반부) → a(전반부) 순서
                url = (f"https://www.sec.gov/ftp/data/failstodeliver/"
                       f"cnsfails{ym}{half}.zip")
                try:
                    r = requests.get(url, headers=_HEADERS, timeout=20)
                    if r.status_code != 200:
                        continue
                    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                        name = z.namelist()[0]
                        with z.open(name) as f:
                            df = pd.read_csv(
                                f, sep="|", dtype=str,
                                header=0, on_bad_lines="skip",
                                encoding="latin-1"
                            )
                    df.columns = [c.strip().upper() for c in df.columns]
                    col_sym = next((c for c in df.columns if "SYMBOL" in c), None)
                    col_qty = next((c for c in df.columns
                                   if "QUANTITY" in c or "FAIL" in c), None)
                    if col_sym is None or col_qty is None:
                        continue
                    sub = df[df[col_sym].str.upper() == ticker.upper()]
                    if not sub.empty:
                        qty = pd.to_numeric(sub[col_qty], errors="coerce").sum()
                        if not np.isnan(qty):
                            monthly.append(float(qty))
                except Exception:
                    continue

        if not monthly:
            return {"ftd_total": None, "ftd_last_date": None, "ftd_trend": None}

        total = sum(monthly)
        trend = None
        if len(monthly) >= 2:
            trend = monthly[0] - monthly[-1]   # 양수면 최근에 증가

        return {
            "ftd_total":    int(total),
            "ftd_last_date": now.strftime("%Y-%m"),
            "ftd_trend":     round(trend, 0) if trend is not None else None,
        }
    except Exception as e:
        _warn(f"SEC FTD 실패 [{ticker}]: {e}")
        return {"ftd_total": None, "ftd_last_date": None, "ftd_trend": None}


def fetch_us_volume_ratio(ticker: str, period: str = "60d") -> dict:
    """
    yfinance로 최근 거래량 vs 평균 거래량 비율을 계산합니다.

    Returns:
        {
            "vol_ratio_5d" : float | None,  # 5일 평균 / 20일 평균
            "vol_ratio_1d" : float | None,  # 최근 1일 / 20일 평균
        }
    """
    try:
        df = yf.download(ticker, period=period, auto_adjust=True,
                         progress=False, threads=False)
        if df.empty or len(df) < 20:
            return {"vol_ratio_5d": None, "vol_ratio_1d": None}
        vol = df["Volume"].squeeze()
        ma20 = float(vol.rolling(20).mean().iloc[-1])
        if ma20 == 0:
            return {"vol_ratio_5d": None, "vol_ratio_1d": None}
        avg5 = float(vol.tail(5).mean())
        last1 = float(vol.iloc[-1])
        return {
            "vol_ratio_5d": round(avg5 / ma20, 2),
            "vol_ratio_1d": round(last1 / ma20, 2),
        }
    except Exception as e:
        _warn(f"거래량 비율 계산 실패 [{ticker}]: {e}")
        return {"vol_ratio_5d": None, "vol_ratio_1d": None}


def fetch_us_short_data_full(ticker: str) -> dict:
    """
    US 종목 전체 공매도 관련 데이터를 수집합니다. (단일 진입점)

    Returns 통합 dict:
        si_pct_float, days_to_cover, shares_short, float_shares,
        ctb_rate, available, short_vol_pct_avg, short_vol_pct_last,
        short_vol_ratio_trend, ftd_total, ftd_last_date, ftd_trend,
        vol_ratio_5d, vol_ratio_1d
    """
    base   = fetch_us_yfinance_short(ticker)
    ctb    = fetch_iborrowdesk_ctb(ticker)
    vol    = fetch_us_volume_ratio(ticker)
    # FINRA/FTD는 개별 티커 루프보다 배치 처리 시 성능 유리 → 여기서는 선택적 호출
    return {**base, **ctb, **vol,
            "ftd_total": None, "ftd_last_date": None, "ftd_trend": None,
            "short_vol_pct_avg": None, "short_vol_pct_last": None,
            "short_vol_ratio_trend": None}


# ═══════════════════════════════════════════════════════════════
# KR 데이터 수집 (pykrx)
# ═══════════════════════════════════════════════════════════════

def fetch_kr_short_data(ticker: str, lookback_days: int = 10) -> dict:
    """
    pykrx를 이용해 KR 종목의 공매도 잔고 및 비율을 가져옵니다.
    ticker 형식: "005930.KS" 또는 "005930.KQ"

    Returns:
        {
            "si_balance"       : int   | None,  # 공매도 잔고 (주수)
            "si_balance_value" : float | None,  # 공매도 잔고 금액 (원)
            "si_pct"           : float | None,  # 공매도 잔고 비율 (%)
            "short_vol_avg"    : float | None,  # N일 평균 공매도 거래량
            "vol_ratio_5d"     : float | None,  # 5일 공매도거래량 / 20일 평균
        }
    """
    try:
        from pykrx import stock as pkstock  # type: ignore

        code = ticker.split(".")[0]
        end_dt  = datetime.now()
        start_dt = end_dt - timedelta(days=60)
        start = start_dt.strftime("%Y%m%d")
        end   = end_dt.strftime("%Y%m%d")

        # 공매도 잔고 (최근 데이터)
        df_bal = pkstock.get_shorting_balance_by_date(start, end, code)
        if df_bal is None or df_bal.empty:
            return _kr_empty()

        # 컬럼명 정규화
        df_bal.columns = [c.strip() for c in df_bal.columns]
        # pykrx 컬럼: 공매도잔고, 상장주식수, 공매도잔고비율 (버전마다 다를 수 있음)
        bal_col  = next((c for c in df_bal.columns if "잔고" in c
                         and "금액" not in c and "비율" not in c), None)
        pct_col  = next((c for c in df_bal.columns if "비율" in c), None)
        val_col  = next((c for c in df_bal.columns if "금액" in c), None)

        si_balance = None
        si_pct     = None
        si_value   = None
        if bal_col:
            si_balance = _safe_int(df_bal[bal_col].dropna().iloc[-1])
        if pct_col:
            si_pct = _safe_float(df_bal[pct_col].dropna().iloc[-1])
        if val_col:
            si_value = _safe_float(df_bal[val_col].dropna().iloc[-1])

        # 공매도 거래량 (단기 추세)
        df_vol = pkstock.get_shorting_volume_by_date(start, end, code)
        short_vol_avg = None
        vol_ratio_5d  = None
        if df_vol is not None and not df_vol.empty:
            df_vol.columns = [c.strip() for c in df_vol.columns]
            v_col = next((c for c in df_vol.columns
                          if "공매도" in c and "거래량" in c), None)
            if v_col is None:
                v_col = df_vol.columns[0]
            vol_series = pd.to_numeric(df_vol[v_col], errors="coerce").dropna()
            if len(vol_series) >= 10:
                ma20 = float(vol_series.rolling(20, min_periods=5).mean().iloc[-1])
                avg5 = float(vol_series.tail(5).mean())
                short_vol_avg = round(float(vol_series.tail(lookback_days).mean()), 0)
                if ma20 > 0:
                    vol_ratio_5d = round(avg5 / ma20, 2)

        return {
            "si_balance":       si_balance,
            "si_balance_value": si_value,
            "si_pct":           si_pct,
            "short_vol_avg":    short_vol_avg,
            "vol_ratio_5d":     vol_ratio_5d,
        }
    except Exception as e:
        _warn(f"pykrx 공매도 데이터 실패 [{ticker}]: {e}")
        return _kr_empty()


def fetch_kr_volume_ratio(ticker: str) -> dict:
    """yfinance로 KR 종목 전체 거래량 비율 계산."""
    return fetch_us_volume_ratio(ticker)


def _kr_empty() -> dict:
    return {"si_balance": None, "si_balance_value": None,
            "si_pct": None, "short_vol_avg": None, "vol_ratio_5d": None}


# ═══════════════════════════════════════════════════════════════
# 유틸리티
# ═══════════════════════════════════════════════════════════════

def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if (f != f) else f  # NaN 체크
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> Optional[int]:
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _recent_trading_dates(n: int) -> list[str]:
    """최근 n개 거래일 날짜 문자열(YYYYMMDD) 리스트 반환 (오늘부터 역순)."""
    dates = []
    d = datetime.now()
    while len(dates) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:  # 월~금
            dates.append(d.strftime("%Y%m%d"))
    return dates
