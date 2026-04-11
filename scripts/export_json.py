"""
4전략 스크리닝 결과를 JSON으로 내보내기 (서버리스 배포용)
─────────────────────────────────────────────────────────
전략별 ATR 승수를 변경하여 screener_v3 실행 → JSON 생성.
시장 관망 여부와 무관하게 모든 전략의 결과를 제공한다.

v3 최적 파라미터 적용:
  ATR 승수: 공격적 1.5 / 균형형 2.0 / 보수적 2.5
  유니버스: S&P500 전체 + KOSPI/KOSDAQ 상위 종목 동적 수집
"""
import argparse
import io
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# DEPLOY_ENV: "serverless" | "local" | "cloud"  (기본값: "serverless")
# export_json.py는 serverless 배포용 정적 JSON 생성 스크립트이므로 기본값을 serverless로 설정.
DEPLOY_ENV = os.environ.get("DEPLOY_ENV", "serverless")
if DEPLOY_ENV != "serverless":
    logging.warning(
        "export_json.py는 DEPLOY_ENV=serverless 환경을 위한 스크립트입니다. "
        f"현재 DEPLOY_ENV={DEPLOY_ENV}"
    )

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent / "screener"))
sys.path.insert(0, str(Path(__file__).parent / "crypto"))

import screener_v3 as sc
import screener_v3_kr as sc_kr
from data_cache import fetch_sp500_tickers, fetch_nasdaq100_tickers

# 4가지 전략 프리셋 — v3 최적 ATR 승수 + 전략별 종목 수
# top_n: 공격적(15) > 균형형(10) > 보수적(7) — 위험선호도에 따라 포트폴리오 집중도 차별화
# 적응형: ATR 2.0, TOP 10 고정 (균형형 기준, 국면 정보는 별도 표시)
# 한국 종목명 캐시 (ticker → 회사명)
KR_NAMES: dict[str, str] = {}

STRATEGIES = {
    "aggressive":   {"atr_mult": 1.5, "label": "공격적", "rebal_freq": "격주",  "top_n": 15},
    "balanced":     {"atr_mult": 2.0, "label": "균형형", "rebal_freq": "격주",  "top_n": 10},
    "conservative": {"atr_mult": 2.5, "label": "보수적", "rebal_freq": "격주",  "top_n": 7},
    "adaptive":     {"atr_mult": 2.0, "label": "적응형", "rebal_freq": "격주",  "top_n": 10},
}


def safe_float(val, ndigits=2):
    try:
        if pd.isna(val) or np.isnan(float(val)):
            return None
    except (TypeError, ValueError):
        return None
    return round(float(val), ndigits)


def detect_adaptive_regime(mkt):
    """시장 상태에서 적응형 국면 판별 (간이 버전, v3 최적 ATR 승수)."""
    if mkt is None:
        return "balanced", 2.0
    gap = mkt["gap_pct"]
    if gap > 5:
        return "aggressive", 1.5
    elif gap > 0:
        return "balanced", 2.0
    else:
        return "conservative", 2.5


# ── 동적 유니버스 수집 ────────────────────────────────────────
# fetch_sp500_tickers, fetch_nasdaq100_tickers는 data_cache 모듈에서 import

def _fetch_kr_from_naver(kospi_n: int, kosdaq_n: int) -> list[str]:
    """네이버 금융 시가총액 페이지에서 KR 종목 수집 (fallback).

    BeautifulSoup으로 HTML a[href*=code] 링크를 파싱해서 종목코드를 추출한다.
    sosok=0: KOSPI, sosok=1: KOSDAQ
    """
    import re
    from bs4 import BeautifulSoup

    def _scrape_market(sosok: int, n: int, suffix: str) -> tuple[list[str], dict[str, str]]:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        tickers: list[str] = []
        names: dict[str, str] = {}
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
                        names[ticker] = link.text.strip()
                page += 1
            except Exception:
                break
        return tickers[:n], {t: names[t] for t in tickers[:n] if t in names}

    try:
        kospi_tickers, kospi_names   = _scrape_market(0, kospi_n, ".KS")
        kosdaq_tickers, kosdaq_names = _scrape_market(1, kosdaq_n, ".KQ")
        all_kr = kospi_tickers + kosdaq_tickers
        all_names = {**kospi_names, **kosdaq_names}
        logger.info("  KR (네이버 fallback) KOSPI %d개 + KOSDAQ %d개 수집 완료", len(kospi_tickers), len(kosdaq_tickers))
        KR_NAMES.update(all_names)
        return all_kr
    except Exception as e:
        logger.warning("  KR 종목 수집 최종 실패 (%s), 기본 유니버스 사용", e)
        fallback = list(sc.KR_UNIVERSE.keys())
        _fill_kr_names_pykrx(fallback)
        return fallback


def _fill_kr_names_pykrx(tickers: list[str]) -> None:
    """pykrx로 KR 종목명 보완 (KRX/네이버 실패 시 3차 fallback)."""
    try:
        from pykrx import stock as pkstock  # type: ignore
        missing = [t for t in tickers if t not in KR_NAMES]
        for t in missing:
            code = t.split(".")[0]
            name = pkstock.get_market_ticker_name(code)
            if name:
                KR_NAMES[t] = name
        filled = sum(1 for t in missing if t in KR_NAMES)
        if filled:
            logger.info("  pykrx로 종목명 %d개 보완 완료", filled)
    except Exception as pe:
        logger.warning("  pykrx 종목명 보완 실패 (%s)", pe)


def fetch_kr_tickers(kospi_n=200, kosdaq_n=150):
    """KRX에서 KOSPI/KOSDAQ 상위 종목 가져오기.

    1차: kind.krx.co.kr 상장법인 목록 (EUC-KR 명시 디코딩)
    2차 fallback: 네이버 금융 시가총액 페이지 BeautifulSoup 파싱
    """
    try:
        url = ("http://kind.krx.co.kr/corpgeneral/corpList.do"
               "?method=download&searchType=13")
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        r.raise_for_status()
        # Content-Type: application/vnd.ms-excel; charset=EUC-KR → 명시적 디코딩
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

        # 종목명 수집
        name_col = "회사명" if "회사명" in krx.columns else krx.columns[0]
        for _, row in kospi.iterrows():
            ticker = f"{str(row['종목코드']).zfill(6)}.KS"
            KR_NAMES[ticker] = str(row[name_col])
        for _, row in kosdaq.iterrows():
            ticker = f"{str(row['종목코드']).zfill(6)}.KQ"
            KR_NAMES[ticker] = str(row[name_col])

        all_kr = kospi_tickers + kosdaq_tickers
        logger.info("  KR KOSPI %d개 + KOSDAQ %d개 수집 완료", len(kospi_tickers), len(kosdaq_tickers))
        return all_kr
    except Exception as e:
        logger.warning("  KRX (kind.krx.co.kr) 실패 (%s), 네이버 금융으로 재시도...", e)
        return _fetch_kr_from_naver(kospi_n, kosdaq_n)


def download_for_date(tickers, end_date: str | None = None):
    """특정 날짜 기준으로 주가 데이터 다운로드.

    end_date(YYYY-MM-DD)가 지정되면 그 날 종가까지의 1년치 데이터를,
    지정하지 않으면 최근 1년치 데이터를 다운로드한다.
    """
    import yfinance as yf

    try:
        if end_date:
            end_dt = pd.Timestamp(end_date) + pd.Timedelta(days=1)
            start_dt = pd.Timestamp(end_date) - pd.Timedelta(days=400)
            raw = yf.download(
                tickers,
                start=start_dt.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        else:
            raw = yf.download(tickers, period="1y", auto_adjust=True, progress=False, threads=True)

        result = {}
        if isinstance(raw.columns, pd.MultiIndex):
            for t in tickers:
                try:
                    df = raw.xs(t, axis=1, level=1).dropna(how="all")
                    if len(df) >= 60:
                        result[t] = df
                except Exception:
                    pass
        else:
            if len(raw) >= 60:
                result[tickers[0]] = raw
        return result
    except Exception:
        return {}


def run_screening_with_atr(all_data_ind, etf_data, atr_mult):
    """특정 ATR 승수로 스크리닝 실행."""
    # ATR_MULT를 임시 변경
    orig_mult = sc.ATR_MULT
    sc.ATR_MULT = atr_mult

    passed = {}
    for t, df_ind in all_data_ind.items():
        ok, metrics = sc.screen(df_ind)
        if ok:
            passed[t] = metrics

    sc.ATR_MULT = orig_mult
    return passed


def build_results(passed, etf_data, top_n=None):
    """통과 종목을 랭킹하고 결과 리스트 생성."""
    if not passed:
        return []

    ranked = sc.rank_stocks(passed, etf_data)
    n = top_n if top_n is not None else sc.TOP_N
    top = ranked.head(n).copy()
    weights = sc.calc_position_weights(top["score"], sc.SIZING_MODE, sc.MAX_WEIGHT)
    top["weight"] = weights

    results = []
    for rank, (ticker, row) in enumerate(top.iterrows(), 1):
        market = "KR" if (ticker.endswith(".KS") or ticker.endswith(".KQ")) else "US"
        sector = sc.ALL_UNIVERSE.get(ticker, "Unknown")
        name = KR_NAMES.get(ticker) if market == "KR" else None
        if name is None and market == "KR":
            _fill_kr_names_pykrx([ticker])
            name = KR_NAMES.get(ticker)
        results.append({
            "rank": rank,
            "ticker": ticker,
            "market": market,
            "name": name,
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
    return results


def _build_kr_results(
    passed: dict,
    kr_names: dict[str, str],
    kr_sectors: dict[str, str],
    top_n: int | None = None,
) -> list[dict]:
    """KR passed 딕셔너리를 랭킹하고 결과 리스트 생성."""
    if not passed:
        return []
    ranked = sc.rank_stocks(passed, {})
    n = top_n if top_n is not None else sc.TOP_N
    top = ranked.head(n).copy()
    weights = sc.calc_position_weights(top["score"], sc.SIZING_MODE, sc.MAX_WEIGHT)
    top["weight"] = weights

    results = []
    for rank, (ticker, row) in enumerate(top.iterrows(), 1):
        results.append({
            "rank": rank,
            "ticker": ticker,
            "market": "KR",
            "name": kr_names.get(ticker),
            "sector": kr_sectors.get(ticker, "Unknown"),
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
    return results


def _infer_v10_reason(df: pd.DataFrame, entry_idx: int) -> str:
    """V10 진입 시점의 신호 종류 추정"""
    if entry_idx < 1:
        return "V10 진입 조건 충족"

    row  = df.iloc[entry_idx]
    prev = df.iloc[entry_idx - 1]

    ma50   = row.get("ma50", float("nan"))
    ma200  = row.get("ma200", float("nan"))
    adx    = row.get("adx", 0.0)
    rsi    = row.get("rsi14", float("nan"))
    mom    = row.get("sq_mom", float("nan"))
    dm     = row.get("sq_mom_delta", float("nan"))
    rel    = bool(row.get("sq_release", False))
    sq_on  = bool(row.get("sq_on", False))
    vd     = row.get("vwap_dev", float("nan"))
    bb_up  = row.get("bb_upper", float("nan"))
    ema20  = row.get("ema20", float("nan"))
    ema50v = row.get("ema50", float("nan"))
    wslope = row.get("weekly_slope", 0.0)
    rpos   = row.get("range_pos", float("nan"))
    close  = row.get("close", float("nan"))

    mom_series = df["sq_mom"].fillna(0)
    mom_std = float(mom_series.iloc[max(0, entry_idx - 60):entry_idx].std())

    ema_cross = (ema20 > ema50v) and (prev.get("ema20", float("nan")) <= prev.get("ema50", float("nan")))
    w_up = wslope > 0.001

    # 레짐
    if ma50 > ma200 and close > ma50 and adx > 13:
        regime = "bull"
    elif adx < 13:
        regime = "sideways"
    else:
        regime = "neutral"

    if regime == "bull":
        if rel and mom > 0 and dm > 0:
            return "Squeeze Release — 스퀴즈 해제 + 모멘텀 상승"
        if sq_on and mom_std > 0 and mom > 0.38 * mom_std and dm > 0 and rsi < 70:
            return "Squeeze 조기진입 — Squeeze ON + 강한 모멘텀"
        if ema_cross and adx > 13:
            return "EMA 골든크로스 — EMA20 > EMA50 돌파"
        if rsi < 49 and w_up and adx > 13:
            return f"RSI 눌림목 — RSI {rsi:.0f}, 상승추세 포착"
        if not pd.isna(vd) and vd < -0.016:
            return f"VWAP 이탈 회귀 — VWAP 대비 {vd * 100:.1f}% 하락"
        if not pd.isna(bb_up) and prev.get("close", bb_up) <= prev.get("bb_upper", bb_up) and close > bb_up:
            return "BB 상단 돌파 — 볼린저 밴드 브레이크아웃"
    elif regime == "sideways":
        if not pd.isna(rpos) and rpos < 0.30 and rsi < 50:
            return f"레인지 하단 매수 — 레인지 포지션 {rpos * 100:.0f}%"
    elif regime == "neutral":
        if ema_cross and adx > 13:
            return "Neutral EMA 크로스 — 추세 전환 감지"

    return "V10 진입 조건 충족"


def calculate_btc_signal() -> dict:
    """
    BTC V10 4시간봉 현재 시그널 계산
    Binance API 또는 yfinance에서 최근 데이터를 가져와 V10 전략 실행 후 현재 포지션 반환.
    """
    try:
        from btc_daytrading_4h import get_btc_data_4h, add_indicators, strategy_v10
    except ImportError as e:
        return {
            "signal": "hold",
            "price": None,
            "reason": f"모듈 로드 실패: {e}",
            "strategy": "V10",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    try:
        logger.info("BTC V10 시그널 계산 중...")
        # MA200(200봉) + 웜업(210봉) + 여유 확보 → 최소 500봉
        # 2024-01-01 이후 데이터는 약 1100봉 이상 (충분)
        df = get_btc_data_4h("2024-01-01")
        df = add_indicators(df)
        df = strategy_v10(df.copy())

        last_pos   = int(df["position"].iloc[-1])
        last_close = float(df["close"].iloc[-1])
        last_time  = df.index[-1].isoformat()

        # 현재 레짐 계산
        row = df.iloc[-1]
        ma50  = row.get("ma50", float("nan"))
        ma200 = row.get("ma200", float("nan"))
        adx   = row.get("adx", 0.0)
        close = last_close
        if ma50 > ma200 and close > ma50 and adx > 13:
            regime = "bull"
        elif adx < 13:
            regime = "sideways"
        else:
            regime = "neutral"

        if last_pos == 1:
            # 진입 시점 역추적
            pos_series = df["position"]
            entry_idx = None
            for i in range(len(pos_series) - 1, 0, -1):
                if pos_series.iloc[i] == 1 and pos_series.iloc[i - 1] == 0:
                    entry_idx = i
                    break

            reason = _infer_v10_reason(df, entry_idx) if entry_idx is not None else "포지션 보유 중"
            logger.info("  → 매수 신호 (현재가 $%s, 레짐: %s)", f"{last_close:,.0f}", regime)
            return {
                "signal": "buy",
                "price": round(last_close, 2),
                "reason": reason,
                "regime": regime,
                "strategy": "V10",
                "timestamp": last_time,
            }
        else:
            logger.info("  → 관망 (현재가 $%s, 레짐: %s)", f"{last_close:,.0f}", regime)
            return {
                "signal": "hold",
                "price": round(last_close, 2),
                "reason": "매수 조건 미충족 — 현금 보유",
                "regime": regime,
                "strategy": "V10",
                "timestamp": last_time,
            }

    except Exception as e:
        logger.warning("  BTC 시그널 계산 실패: %s", e)
        return {
            "signal": "hold",
            "price": None,
            "reason": f"시그널 계산 실패: {e}",
            "strategy": "V10",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }


def check_kospi_market() -> dict | None:
    """KOSPI 지수(^KS11) MA20/MA60 골든/데드크로스 확인."""
    try:
        import yfinance as yf
        ks = yf.download("^KS11", period="1y", auto_adjust=True, progress=False)
        # pre-market/장 개장 직전 시각에 마지막 행이 NaN으로 반환될 수 있으므로 dropna 적용
        close = ks["Close"].squeeze().dropna()
        if close.empty:
            logger.warning("  KOSPI 데이터 없음")
            return None
        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma60 = float(close.rolling(60).mean().iloc[-1])
        price = float(close.iloc[-1])
        import math
        if any(math.isnan(v) for v in [price, ma20, ma60]):
            logger.warning("  KOSPI 데이터 NaN — 조회 건너뜀")
            return None
        gap = (ma20 - ma60) / ma60 * 100
        return {"price": price, "ma20": ma20, "ma60": ma60,
                "gap_pct": gap, "is_golden": ma20 > ma60}
    except Exception as e:
        logger.warning("  KOSPI 시장 상태 조회 실패 (%s)", e)
        return None


def fetch_market_cap_top20(
    us_tickers: list[str],
    us_sectors: dict[str, str],
    output_dir: Path | None = None,
) -> dict:
    """S&P500+NASDAQ100 종목의 시가총액 Top 20 계산 (트렌드 모니터링용).

    ThreadPoolExecutor로 병렬 조회. 실패 시 해당 종목 제외.
    이전 market_cap.json이 output_dir에 있으면 신규 진입 종목을 하이라이트한다.
    """
    import yfinance as yf
    from concurrent.futures import ThreadPoolExecutor, as_completed

    logger.info("시총 Top 20 수집 중...")

    def _get_mc(ticker: str) -> tuple[str, float | None]:
        try:
            mc = yf.Ticker(ticker).fast_info.market_cap
            return ticker, mc
        except Exception:
            return ticker, None

    market_caps: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(_get_mc, t): t for t in us_tickers}
        for fut in as_completed(futures):
            ticker, mc = fut.result()
            if mc and mc > 0:
                market_caps[ticker] = mc

    sorted_tickers = sorted(market_caps, key=lambda t: market_caps[t], reverse=True)[:20]

    # 이전 Top 20 읽기 (신규 진입 하이라이트용)
    prev_tickers: list[str] = []
    if output_dir:
        prev_path = output_dir / "market_cap.json"
        if prev_path.exists():
            try:
                with open(prev_path, encoding="utf-8") as f:
                    prev_data = json.load(f)
                prev_tickers = [r["ticker"] for r in prev_data.get("top20", [])]
            except Exception:
                pass
    prev_set = set(prev_tickers)

    now = datetime.now().isoformat(timespec="seconds")
    results = []
    for rank, ticker in enumerate(sorted_tickers, 1):
        sector = us_sectors.get(ticker, "Unknown")
        mc = market_caps[ticker]
        is_new = bool(prev_tickers) and (ticker not in prev_set)
        results.append({
            "rank": rank,
            "ticker": ticker,
            "market_cap_b": round(mc / 1e9, 1),  # 십억 달러(Billion) 단위
            "sector": sector,
            "is_new_entrant": is_new,
        })

    # 섹터 분포
    sector_count: dict[str, int] = {}
    for r in results:
        s = r["sector"]
        sector_count[s] = sector_count.get(s, 0) + 1
    sector_dist = [
        {"sector": s, "count": c}
        for s, c in sorted(sector_count.items(), key=lambda x: -x[1])
    ]

    new_entrants = [r["ticker"] for r in results if r["is_new_entrant"]]
    logger.info("  시총 Top 20 수집 완료 (%d개), 신규 진입: %s", len(results), new_entrants or "없음")
    return {
        "updated_at": now,
        "note": "매매 전략이 아닌 시장 트렌드 모니터링 참고 도구입니다.",
        "top20": results,
        "sector_distribution": sector_dist,
    }


def fetch_vix_etf_prices() -> dict:
    """VIX, SVXY, SVIX 현재가를 yfinance로 조회하여 반환.

    실패 시 빈 딕셔너리 반환.
    """
    import yfinance as yf

    result = {"run_date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
    for symbol in ("^VIX", "SVXY", "SVIX"):
        try:
            ticker = yf.Ticker(symbol)
            price = ticker.fast_info.last_price
            if price is None or price != price:  # None or NaN
                raise ValueError("가격 없음")
            key = symbol.lstrip("^").lower()
            result[key] = round(float(price), 2)
        except Exception as e:
            logger.warning("  %s 가격 조회 실패: %s", symbol, e)
    return result


def export_all_strategies(output_dir: Path, screening_date: str | None = None):
    """4전략 스크리닝 실행 후 단일 JSON으로 저장.

    screening_date(YYYY-MM-DD)가 지정되면 그 날 종가 기준 히스토리 파일만 생성하고
    screening_latest.json / screening_strategies.json은 갱신하지 않는다.
    지정하지 않으면 오늘 날짜로 모든 파일을 갱신한다.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    is_history_only = screening_date is not None
    if is_history_only:
        logger.info("히스토리 모드: %s 날짜 기준 데이터 생성", screening_date)

    # 시장 상태 (SPY)
    mkt = sc.check_market()
    market_status = None
    if mkt:
        market_status = {
            "spy_price": round(mkt["price"], 2),
            "is_golden_cross": mkt["is_golden"],
            "ma20": round(mkt["ma20"], 2),
            "ma60": round(mkt["ma60"], 2),
            "gap_pct": round(mkt["gap_pct"], 2),
        }

    # KOSPI 시장 상태
    kospi_mkt = check_kospi_market()
    if kospi_mkt and market_status is not None:
        market_status["kospi_price"] = round(kospi_mkt["price"], 2)
        market_status["kospi_golden_cross"] = kospi_mkt["is_golden"]
        market_status["kospi_ma20"] = round(kospi_mkt["ma20"], 2)
        market_status["kospi_ma60"] = round(kospi_mkt["ma60"], 2)
        market_status["kospi_gap_pct"] = round(kospi_mkt["gap_pct"], 2)
    elif kospi_mkt and market_status is None:
        market_status = {
            "kospi_price": round(kospi_mkt["price"], 2),
            "kospi_golden_cross": kospi_mkt["is_golden"],
            "kospi_ma20": round(kospi_mkt["ma20"], 2),
            "kospi_ma60": round(kospi_mkt["ma60"], 2),
            "kospi_gap_pct": round(kospi_mkt["gap_pct"], 2),
        }

    # 동적 유니버스 수집
    logger.info("유니버스 수집 중...")
    us_tickers, us_sectors = fetch_sp500_tickers()
    ndx_tickers, ndx_sectors = fetch_nasdaq100_tickers()

    # S&P500과 중복 제거 후 NASDAQ-100 신규 종목만 추가
    sp500_set = set(us_tickers)
    ndx_new = [t for t in ndx_tickers if t not in sp500_set]
    ndx_new_sectors = {t: s for t, s in ndx_sectors.items() if t not in sp500_set}
    logger.info("  NASDAQ-100 신규 추가: %d개 (S&P500 중복 %d개 제거)", len(ndx_new), len(ndx_tickers) - len(ndx_new))

    us_tickers = us_tickers + ndx_new
    us_sectors = {**us_sectors, **ndx_new_sectors}

    # screener_v3의 유니버스/섹터 맵을 US 전용으로 교체 (v3.2: US/KR 분리)
    sc.ALL_UNIVERSE.clear()
    sc.ALL_UNIVERSE.update(us_sectors)

    # ── US 데이터 다운로드 + 지표 계산 ────────────────────────
    logger.info("US 데이터 다운로드 중...")
    us_data, etf_data = {}, {}
    for i in range(0, len(us_tickers), 50):
        us_data.update(download_for_date(us_tickers[i:i + 50], screening_date))
    etf_raw = download_for_date(list(set(sc.SECTOR_ETF.values())), screening_date)
    for t, df in etf_raw.items():
        etf_data[t] = sc.calc_indicators(df)

    logger.info("US 지표 계산 중 (%d개 종목)...", len(us_data))
    us_data_ind: dict = {}
    for t, df in us_data.items():
        us_data_ind[t] = sc.calc_indicators(df)

    # ── KR 데이터 다운로드 (pykrx, v3.2 신규) ────────────────
    logger.info("KR 유니버스 수집 중 (pykrx)...")
    kr_tickers_pykrx, kr_sectors_pykrx = sc_kr.fetch_kr_universe()
    logger.info("KR 데이터 다운로드 중 (%d종목)...", len(kr_tickers_pykrx))

    # screening_date가 지정된 경우 해당 날짜까지의 데이터를 다운로드
    if screening_date:
        end_date_kr = screening_date
        start_date_kr = (
            pd.Timestamp(screening_date) - pd.Timedelta(days=400)
        ).strftime("%Y-%m-%d")
    else:
        end_date_kr = None
        start_date_kr = None

    kr_raw = sc_kr.download_kr_pykrx(kr_tickers_pykrx, start=start_date_kr, end=end_date_kr)
    logger.info("KR 지표 계산 중 (%d개 종목)...", len(kr_raw))
    kr_data_ind: dict = {}
    for t, df in kr_raw.items():
        kr_data_ind[t] = sc.calc_indicators(df)

    # all_data_ind = US 전용 (v3.2: KR은 별도 처리)
    all_data_ind = us_data_ind

    # 적응형 국면 판별
    adaptive_regime, adaptive_atr = detect_adaptive_regime(mkt)

    # ── US 4전략 스크리닝 ────────────────────────────────────
    strategies_output = {}
    for key, preset in STRATEGIES.items():
        atr_mult = preset["atr_mult"]
        top_n = preset["top_n"]
        logger.info("  US %s (ATR=%s, TOP=%s) 스크리닝 중...", preset["label"], atr_mult, top_n)
        passed = run_screening_with_atr(all_data_ind, etf_data, atr_mult)
        results = build_results(passed, etf_data, top_n)

        strategy_info = {
            "key": key,
            "label": preset["label"],
            "atr_mult": atr_mult,
            "rebal_freq": preset["rebal_freq"],
            "top_n": top_n,
            "total_screened": len(all_data_ind),
            "total_passed": len(passed),
            "results": results,
        }

        # 적응형 전략에는 현재 국면 정보 추가
        if key == "adaptive":
            strategy_info["current_regime"] = adaptive_regime
            strategy_info["regime_label"] = STRATEGIES[adaptive_regime]["label"]

        strategies_output[key] = strategy_info

    # ── KR 4전략 스크리닝 (v3.2 신규) ───────────────────────
    kr_strategies_output = {}
    kr_names: dict[str, str] = {}
    if kr_data_ind:
        logger.info("KR 스크리닝 중 (%d개 종목)...", len(kr_data_ind))
        # KR 유니버스로 ALL_UNIVERSE 임시 교체
        sc.ALL_UNIVERSE.clear()
        sc.ALL_UNIVERSE.update(kr_sectors_pykrx)

        for key, preset in STRATEGIES.items():
            atr_mult = preset["atr_mult"]
            top_n = preset["top_n"]
            logger.info("  KR %s (ATR=%s, TOP=%s) 스크리닝 중...", preset["label"], atr_mult, top_n)
            kr_passed, _ = sc_kr.run_kr_screening(
                kr_tickers_pykrx, kr_sectors_pykrx, atr_mult, kr_data=kr_data_ind
            )
            # KR 종목명 (처음 한번만 수집)
            if not kr_names and kr_passed:
                kr_names = sc_kr.fetch_kr_names(list(kr_passed.keys()))
            kr_results = _build_kr_results(kr_passed, kr_names, kr_sectors_pykrx, top_n)

            kr_strategy_info = {
                "key": key,
                "label": preset["label"],
                "atr_mult": atr_mult,
                "rebal_freq": preset["rebal_freq"],
                "top_n": top_n,
                "total_screened": len(kr_data_ind),
                "total_passed": len(kr_passed),
                "results": kr_results,
            }
            if key == "adaptive":
                kr_strategy_info["current_regime"] = adaptive_regime
                kr_strategy_info["regime_label"] = STRATEGIES[adaptive_regime]["label"]
            kr_strategies_output[key] = kr_strategy_info

        # ALL_UNIVERSE를 US로 복원
        sc.ALL_UNIVERSE.clear()
        sc.ALL_UNIVERSE.update(us_sectors)
        logger.info("KR 스크리닝 완료")
    else:
        logger.warning("KR 데이터 없음 — KR 스크리닝 건너뜀")

    # BTC V10 시그널 계산
    btc_signal = calculate_btc_signal()

    # 날짜 결정: 히스토리 모드면 screening_date, 아니면 오늘
    if is_history_only:
        run_dt = datetime.strptime(screening_date, "%Y-%m-%d")
    else:
        run_dt = now

    output = {
        "run_id": int(run_dt.strftime("%Y%m%d")),
        "run_date": run_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "market_status": market_status,
        "btc_signal": btc_signal,
        "strategies": strategies_output,          # US 전용 (v3.2)
        "kr_strategies": kr_strategies_output,    # KR 전용 (v3.2 신규)
    }

    if not is_history_only:
        # screening_latest.json (하위 호환: 균형형을 기본으로, US 전용)
        balanced = strategies_output["balanced"]
        compat_output = {
            "run_id": output["run_id"],
            "run_date": output["run_date"],
            "market_status": market_status,
            "btc_signal": btc_signal,
            "total_screened": balanced["total_screened"],
            "total_passed": balanced["total_passed"],
            "results": balanced["results"],
        }
        compat_path = output_dir / "screening_latest.json"
        with open(compat_path, "w", encoding="utf-8") as f:
            json.dump(compat_output, f, ensure_ascii=False, indent=2)

        # screening_strategies.json (US 4전략 전체)
        full_path = output_dir / "screening_strategies.json"
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        # screening_kr_strategies.json (KR 4전략 전체, v3.2 신규)
        if kr_strategies_output:
            kr_output = {
                "run_id": output["run_id"],
                "run_date": output["run_date"],
                "market_status": market_status,
                "strategies": kr_strategies_output,
            }
            kr_full_path = output_dir / "screening_kr_strategies.json"
            with open(kr_full_path, "w", encoding="utf-8") as f:
                json.dump(kr_output, f, ensure_ascii=False, indent=2)
            logger.info("  KR 전략 결과 저장: %s", kr_full_path)

        # 숏스퀴즈 스크리닝
        export_short_squeeze(output_dir, us_tickers, kr_tickers_pykrx, run_dt)

    # 시총 Top 20 (트렌드 모니터링)
    try:
        mc_data = fetch_market_cap_top20(us_tickers, us_sectors, output_dir)
        mc_path = output_dir / "market_cap.json"
        with open(mc_path, "w", encoding="utf-8") as f:
            json.dump(mc_data, f, ensure_ascii=False, indent=2)
        logger.info("  시총 Top 20 저장: %s", mc_path)
    except Exception as e:
        logger.warning("  시총 Top 20 수집 실패 (%s), 건너뜀", e)

    # VIX ETF 현재가 (서버리스 모드 계산기용)
    if not is_history_only:
        try:
            vix_data = fetch_vix_etf_prices()
            if "vix" in vix_data:
                vix_path = output_dir / "vix_etf_prices.json"
                with open(vix_path, "w", encoding="utf-8") as f:
                    json.dump(vix_data, f, ensure_ascii=False, indent=2)
                logger.info("  VIX ETF 가격 저장: %s", vix_path)
        except Exception as e:
            logger.warning("  VIX ETF 가격 수집 실패 (%s), 건너뜀", e)

    # history/{date}.json 저장 및 index.json 업데이트
    save_history(output_dir, output, run_dt)

    date_label = screening_date or run_dt.strftime("%Y-%m-%d")
    logger.info("완료 (%s):", date_label)
    logger.info("  [US]")
    for k in ("aggressive", "balanced", "conservative"):
        s = strategies_output[k]
        logger.info("    %s: %d종목 선정 / %d개 통과", s["label"], len(s["results"]), s["total_passed"])
    s = strategies_output["adaptive"]
    logger.info("    %s: %d종목 선정 / %d개 통과 (현재 국면: %s)",
                s["label"], len(s["results"]), s["total_passed"], STRATEGIES[adaptive_regime]["label"])
    if kr_strategies_output:
        logger.info("  [KR]")
        for k in ("aggressive", "balanced", "conservative"):
            s = kr_strategies_output[k]
            logger.info("    %s: %d종목 선정 / %d개 통과", s["label"], len(s["results"]), s["total_passed"])
    return output


def fetch_usdkrw() -> "float | None":
    """yfinance로 USD/KRW 현재 환율 조회. 실패 시 None 반환."""
    try:
        import yfinance as yf
        df = yf.download("USDKRW=X", period="5d", auto_adjust=True, progress=False)
        if df.empty:
            logger.warning("  환율 조회 결과 없음")
            return None
        # yfinance 최신 버전은 단일 ticker도 multi-level column을 반환하므로 squeeze() 필요
        close = df["Close"].squeeze()
        rate = float(close.dropna().iloc[-1])
        logger.info("  USD/KRW 환율: %s", f"{rate:,.2f}")
        return rate
    except Exception as e:
        logger.warning("  환율 조회 실패 (%s)", e)
        return None


def _calc_atr_stop(df_ohlc: pd.DataFrame, period: int = 14, atr_mult: float = 2.0) -> "float | None":
    """ATR 기반 스톱로스 계산: 20일 고점 - ATR(14) × atr_mult.

    pandas_ta 없이 Wilder's ATR을 직접 계산한다.
    """
    if len(df_ohlc) < period + 5:
        return None
    h = df_ohlc["High"].astype(float)
    l = df_ohlc["Low"].astype(float)
    c = df_ohlc["Close"].astype(float)
    tr = pd.concat([
        (h - l),
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr_series = tr.ewm(alpha=1 / period, min_periods=period).mean()
    atr_vals = atr_series.dropna()
    if atr_vals.empty:
        return None
    atr_val = float(atr_vals.iloc[-1])
    peak_20 = float(h.tail(20).max())
    return round(peak_20 - atr_val * atr_mult, 2)


def portfolio_to_json(output_dir: Path, xlsx_path: Path | None = None) -> None:
    """portfolio.xlsx를 읽어서 현재가·수익률을 계산하고 portfolio.json으로 저장.

    엑셀이 없으면 빈 포트폴리오를 저장한다 (에러 없음).
    KR 종목(원화)·US 종목(달러)를 각각 기준으로 계산하고,
    전체 합계는 KRW·USD 양방향 환율 변환으로 산출한다.
    """
    import yfinance as yf

    # 검색 경로: 명시적 경로 → scripts/portfolio.xlsx → data/portfolio.xlsx
    candidates = [xlsx_path] if xlsx_path else []
    candidates += [
        Path(__file__).parent / "portfolio.xlsx",
        Path(__file__).parent / "data" / "portfolio.xlsx",
    ]
    found = next((p for p in candidates if p and p.exists()), None)

    now_str = datetime.now().isoformat(timespec="seconds")
    usdkrw = fetch_usdkrw()

    empty_output = {
        "updated_at": now_str,
        "exchange_rate": {"usdkrw": round(usdkrw, 2) if usdkrw is not None else None, "updated_at": now_str},
        "total_invested": 0.0,
        "total_current": 0.0,
        "total_return_pct": 0.0,
        "total_invested_krw": 0.0,
        "total_current_krw": 0.0,
        "total_invested_usd": 0.0,
        "total_current_usd": 0.0,
        "holdings": [],
    }

    if found is None:
        logger.info("  portfolio.xlsx 파일 없음 — 빈 포트폴리오 저장")
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / "portfolio.json", "w", encoding="utf-8") as f:
            json.dump(empty_output, f, ensure_ascii=False, indent=2)
        return

    logger.info("  포트폴리오 파일 로드: %s", found)
    try:
        df = pd.read_excel(found, sheet_name="Portfolio", dtype=str)
    except Exception as e:
        logger.warning("  엑셀 읽기 실패 (%s) — 빈 포트폴리오 저장", e)
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / "portfolio.json", "w", encoding="utf-8") as f:
            json.dump(empty_output, f, ensure_ascii=False, indent=2)
        return

    # 컬럼명 정규화 (한글 헤더 지원)
    col_map = {
        "ticker": "ticker", "티커": "ticker",
        "name": "name", "종목명": "name",
        "market": "market", "시장(us/kr)": "market", "시장": "market",
        "entry_price": "entry_price", "진입가": "entry_price",
        "shares": "shares", "주수": "shares",
        "entry_date": "entry_date", "진입일": "entry_date",
        "stop_loss": "stop_loss", "스톱로스": "stop_loss",
        "target_price": "target_price", "목표가": "target_price",
        "memo": "memo", "메모": "memo",
    }
    df.columns = [col_map.get(c.strip().lower(), c.strip().lower()) for c in df.columns]

    # 빈 행 제거 (ticker 없는 행)
    df = df[df.get("ticker", pd.Series(dtype=str)).notna()].copy()
    df = df[df["ticker"].str.strip() != ""]
    if df.empty:
        logger.info("  포트폴리오 종목 없음 — 빈 포트폴리오 저장")
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / "portfolio.json", "w", encoding="utf-8") as f:
            json.dump(empty_output, f, ensure_ascii=False, indent=2)
        return

    # empty_output 갱신 (환율 포함)은 이미 위에서 처리됨

    # 숫자 변환
    for col in ("entry_price", "shares", "stop_loss", "target_price"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    tickers = df["ticker"].str.strip().tolist()
    logger.info("  현재가 조회 중 (%d개 종목)...", len(tickers))

    # yfinance 일괄 조회 (60일 OHLC — ATR 계산에 필요)
    price_map: dict[str, float] = {}
    raw = None
    try:
        raw = yf.download(tickers, period="60d", auto_adjust=True, progress=False)
        close = raw["Close"] if "Close" in raw.columns else raw
        if isinstance(close, pd.Series):
            # 단일 종목
            last = float(close.dropna().iloc[-1]) if not close.dropna().empty else None
            price_map[tickers[0]] = last
        else:
            for t in tickers:
                if t in close.columns:
                    series = close[t].dropna()
                    price_map[t] = float(series.iloc[-1]) if not series.empty else None
    except Exception as e:
        logger.warning("  yfinance 일괄 조회 실패 (%s), 개별 조회로 재시도...", e)
        for t in tickers:
            try:
                series = yf.download(t, period="2d", auto_adjust=True, progress=False)["Close"].squeeze().dropna()
                price_map[t] = float(series.iloc[-1]) if not series.empty else None
            except Exception:
                price_map[t] = None

    # ATR 스톱 계산 (균형형 기준 ATR×2.0, 추세 이탈 판단용)
    ATR_PORTFOLIO_MULT = 2.0
    atr_stop_map: dict[str, "float | None"] = {}
    if raw is not None:
        try:
            close_df = raw["Close"] if "Close" in raw.columns else None
            is_single = isinstance(close_df, pd.Series)
            for t in tickers:
                try:
                    if is_single and t == tickers[0]:
                        df_t = pd.DataFrame({
                            "High": raw["High"],
                            "Low": raw["Low"],
                            "Close": raw["Close"],
                        }).dropna(subset=["High", "Low", "Close"])
                    elif not is_single and close_df is not None and t in close_df.columns:
                        df_t = pd.DataFrame({
                            "High": raw["High"][t],
                            "Low": raw["Low"][t],
                            "Close": raw["Close"][t],
                        }).dropna(subset=["High", "Low", "Close"])
                    else:
                        atr_stop_map[t] = None
                        continue
                    atr_stop_map[t] = _calc_atr_stop(df_t, atr_mult=ATR_PORTFOLIO_MULT)
                except Exception:
                    atr_stop_map[t] = None
        except Exception:
            pass

    # 종목별 계산
    holdings = []
    for _, row in df.iterrows():
        ticker = str(row["ticker"]).strip()
        market = str(row.get("market", "US")).strip().upper() if pd.notna(row.get("market")) else "US"
        name = str(row.get("name", "")).strip() if pd.notna(row.get("name")) else None
        entry_price = float(row["entry_price"]) if pd.notna(row.get("entry_price")) else None
        shares = float(row["shares"]) if pd.notna(row.get("shares")) else 0.0
        entry_date = str(row.get("entry_date", "")).strip() if pd.notna(row.get("entry_date")) else ""
        stop_loss = float(row["stop_loss"]) if "stop_loss" in df.columns and pd.notna(row.get("stop_loss")) else None
        target_price = float(row["target_price"]) if "target_price" in df.columns and pd.notna(row.get("target_price")) else None
        memo = str(row.get("memo", "")).strip() if pd.notna(row.get("memo")) else ""

        current_price = price_map.get(ticker)

        is_kr = market == "KR"

        if entry_price and entry_price > 0:
            invested = round(entry_price * shares, 2)
            current_value = round(current_price * shares, 2) if current_price else None
            return_pct = round((current_price - entry_price) / entry_price * 100, 2) if current_price else None
        else:
            invested = 0.0
            current_value = None
            return_pct = None

        # 환율 변환: KR=원화 기준, US=달러 기준
        inv_val = invested or 0.0
        cur_val = current_value or inv_val
        if is_kr:
            invested_krw = inv_val
            current_krw = cur_val
            invested_usd = round(inv_val / usdkrw, 2) if usdkrw else None
            current_usd = round(cur_val / usdkrw, 2) if usdkrw else None
        else:
            invested_usd = inv_val
            current_usd = cur_val
            invested_krw = round(inv_val * usdkrw) if usdkrw else None
            current_krw = round(cur_val * usdkrw) if usdkrw else None

        stop_triggered = bool(current_price and stop_loss and current_price < stop_loss)

        atr_stop = atr_stop_map.get(ticker)
        if current_price and atr_stop and current_price > 0:
            atr_stop_dist_pct = round((current_price - atr_stop) / current_price * 100, 2)
        else:
            atr_stop_dist_pct = None
        atr_stop_triggered = bool(current_price and atr_stop and current_price < atr_stop)

        holdings.append({
            "ticker": ticker,
            "name": name or ticker,
            "market": market,
            "entry_price": safe_float(entry_price),
            "current_price": safe_float(current_price),
            "shares": shares,
            "entry_date": entry_date,
            "stop_loss": safe_float(stop_loss),
            "target_price": safe_float(target_price),
            "memo": memo,
            "invested": safe_float(invested),
            "current_value": safe_float(current_value),
            "return_pct": safe_float(return_pct),
            "weight_pct": None,  # 나중에 계산
            "stop_triggered": stop_triggered,
            "invested_krw": safe_float(invested_krw),
            "current_value_krw": safe_float(current_krw),
            "invested_usd": safe_float(invested_usd),
            "current_value_usd": safe_float(current_usd),
            "atr_stop": safe_float(atr_stop),
            "atr_stop_dist_pct": safe_float(atr_stop_dist_pct),
            "atr_stop_triggered": atr_stop_triggered,
        })

    # 전체 합계 (KRW 기준: KR 원화 그대로 + US 달러×환율)
    total_invested_krw = sum(h["invested_krw"] or 0 for h in holdings)
    total_current_krw = sum(h["current_value_krw"] or h["invested_krw"] or 0 for h in holdings)
    total_invested_usd = sum(h["invested_usd"] or 0 for h in holdings)
    total_current_usd = sum(h["current_value_usd"] or h["invested_usd"] or 0 for h in holdings)

    # 하위 호환: total_invested/total_current는 KRW 기준
    total_invested = total_invested_krw
    total_current = total_current_krw
    total_return_pct = round((total_current_krw - total_invested_krw) / total_invested_krw * 100, 2) if total_invested_krw > 0 else 0.0

    # 비중 계산 (투자금 기준)
    for h in holdings:
        invested_val = h["invested_krw"] or 0
        h["weight_pct"] = round(invested_val / total_invested_krw * 100, 1) if total_invested_krw > 0 else 0.0

    output = {
        "updated_at": now_str,
        "exchange_rate": {"usdkrw": round(usdkrw, 2) if usdkrw is not None else None, "updated_at": now_str},
        "total_invested": round(total_invested, 2),
        "total_current": round(total_current, 2),
        "total_return_pct": total_return_pct,
        "total_invested_krw": round(total_invested_krw),
        "total_current_krw": round(total_current_krw),
        "total_invested_usd": round(total_invested_usd, 2),
        "total_current_usd": round(total_current_usd, 2),
        "holdings": holdings,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "portfolio.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info("  포트폴리오 JSON 저장 완료: %s (%d개 종목)", out_path, len(holdings))


def export_short_squeeze(
    output_dir: Path,
    us_tickers: list[str],
    kr_tickers: list[str],
    now: datetime,
) -> None:
    """숏스퀴즈 스크리닝 실행 후 short_squeeze_latest.json으로 저장.

    screener/short_squeeze_screener.py의 run_us_screening / run_kr_screening을
    호출하여 결과를 output_dir/short_squeeze_latest.json에 저장한다.
    실패 시 경고 로그만 남기고 전체 스크리닝 파이프라인은 계속 진행한다.
    """
    try:
        import short_squeeze_screener as sqz  # screener/ 경로는 sys.path에 추가됨

        logger.info(
            "숏스퀴즈 스크리닝 중 (US %d개, KR %d개)...",
            len(us_tickers), len(kr_tickers),
        )
        us_df = sqz.run_us_screening(us_tickers)
        kr_df = sqz.run_kr_screening(kr_tickers)

        sq_output: dict = {
            "run_id":            int(now.strftime("%Y%m%d")),
            "run_date":          now.strftime("%Y-%m-%dT%H:%M:%S"),
            "params": {
                "us_si_float_min":  float(sqz.US_SI_FLOAT_MIN),
                "us_dtc_min":       float(sqz.US_DTC_MIN),
                "us_ctb_min":       float(sqz.US_CTB_MIN),
                "us_vol_ratio_min": float(sqz.US_VOL_RATIO_MIN),
                "kr_si_pct_min":    float(sqz.KR_SI_PCT_MIN),
            },
            "total_us_screened": len(us_tickers),
            "total_kr_screened": len(kr_tickers),
            "total_us_passed":   len(us_df),
            "total_kr_passed":   len(kr_df),
            "us_results":        sqz.build_output_records(us_df),
            "kr_results":        sqz.build_output_records(kr_df),
        }

        out_path = output_dir / "short_squeeze_latest.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(_sanitize_nan(sq_output), f, ensure_ascii=False, indent=2)
        logger.info(
            "  숏스퀴즈 결과 저장: %s (US %d개, KR %d개)",
            out_path, len(us_df), len(kr_df),
        )
    except Exception as e:
        logger.warning("  숏스퀴즈 스크리닝 실패 (%s), 건너뜀", e)


def _sanitize_nan(obj):
    """dict/list 내 float NaN/Inf를 None으로 재귀 변환 (JSON 표준 준수)."""
    import math
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


def save_history(output_dir: Path, output: dict, now: datetime, keep_days: int = 30) -> None:
    """일자별 스크리닝 결과를 history/ 폴더에 저장하고 최근 keep_days일치만 유지.

    keep_days 초과 파일은 삭제하지 않고 history/archive/ 로 이동하여 영구 보존한다.
    """
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = history_dir / "archive"

    today = now.strftime("%Y-%m-%d")

    # 오늘 날짜 파일 저장 (NaN → null 정규화로 유효한 JSON 보장)
    day_path = history_dir / f"{today}.json"
    with open(day_path, "w", encoding="utf-8") as f:
        json.dump(_sanitize_nan(output), f, ensure_ascii=False, indent=2)
    logger.info("  history 저장: %s", day_path)

    # 기존 history 파일 NaN 정규화 (Python json은 NaN 읽기 허용하나 Dart는 불가)
    for existing_path in history_dir.glob("????-??-??.json"):
        if existing_path == day_path:
            continue
        try:
            with open(existing_path, encoding="utf-8") as f:
                existing_data = json.load(f)
            sanitized = _sanitize_nan(existing_data)
            if sanitized != existing_data:
                with open(existing_path, "w", encoding="utf-8") as f:
                    json.dump(sanitized, f, ensure_ascii=False, indent=2)
                logger.info("  history NaN 정규화: %s", existing_path.name)
        except Exception as e:
            logger.warning("  history 정규화 실패 (%s): %s", existing_path.name, e)

    # 기존 날짜 파일 목록 수집 (YYYY-MM-DD.json 패턴)
    existing = sorted(
        [p.stem for p in history_dir.glob("????-??-??.json")],
        reverse=True,
    )

    # keep_days 초과 파일은 archive/로 이동 (영구 보존)
    for old_date in existing[keep_days:]:
        old_path = history_dir / f"{old_date}.json"
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / f"{old_date}.json"
        shutil.move(str(old_path), str(dest))
        logger.info("  history 아카이브 이동: %s.json → archive/", old_date)

    # 최신 날짜 목록으로 index.json 갱신
    dates = sorted(
        [p.stem for p in history_dir.glob("????-??-??.json")],
        reverse=True,
    )[:keep_days]
    index_path = history_dir / "index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"dates": dates}, f, ensure_ascii=False, indent=2)
    logger.info("  history index 갱신: %s", dates)


def save_to_db(output: dict, now: datetime) -> None:
    """스크리닝 결과를 SQLite DB에 저장한다.

    export_all_strategies()가 반환한 output dict를 그대로 받아
    screening_history(전체 JSON)와 screening_result(종목별 행)를 INSERT/REPLACE 한다.
    """
    import os
    import sys

    # 프로젝트 루트(backend 패키지가 있는 위치)를 sys.path에 추가
    project_root = Path(__file__).parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from backend.db.database import SessionLocal, init_db
    from backend.db.models import ScreeningHistory, ScreeningResult

    init_db()
    today = now.strftime("%Y-%m-%d")

    db = SessionLocal()
    try:
        # screening_history — 날짜 UNIQUE, 이미 있으면 업데이트
        existing = db.query(ScreeningHistory).filter_by(date=today).first()
        sanitized_json = json.dumps(_sanitize_nan(output), ensure_ascii=False)
        if existing:
            existing.data_json = sanitized_json
            existing.created_at = datetime.utcnow().isoformat(timespec="seconds")
        else:
            db.add(ScreeningHistory(date=today, data_json=sanitized_json))

        # screening_result — 오늘 날짜 기존 행 삭제 후 재삽입
        db.query(ScreeningResult).filter_by(date=today).delete()

        for strategy_key, strategy_info in output.get("strategies", {}).items():
            for item in strategy_info.get("results", []):
                ticker = item.get("ticker", "")
                market = "KR" if ticker.endswith(".KS") else "US"
                # 핵심 필드 외 나머지를 data_json으로 저장
                extra = {k: v for k, v in item.items()
                         if k not in ("ticker", "name", "rank", "score")}
                db.add(ScreeningResult(
                    date=today,
                    strategy=strategy_key,
                    ticker=ticker,
                    name=item.get("name"),
                    rank=item.get("rank"),
                    score=item.get("score"),
                    market=market,
                    data_json=json.dumps(_sanitize_nan(extra), ensure_ascii=False) if extra else None,
                ))

        db.commit()
        logger.info("  DB 저장 완료: %s (%d개 전략)", today, len(output.get("strategies", {})))
    except Exception as exc:
        db.rollback()
        print(f"  DB 저장 실패: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


def generate_history_batch(output_dir: Path, dates: list[str]) -> None:
    """여러 날짜의 히스토리를 한 번의 다운로드로 효율적으로 생성.

    최신 날짜(dates 중 가장 늦은 날짜)까지의 데이터를 한 번 다운로드한 후,
    각 날짜별로 데이터를 슬라이싱하여 스크리닝을 실행한다.
    """
    if not dates:
        logger.warning("생성할 날짜 목록이 없습니다.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    # 이미 생성된 날짜는 건너뜀
    existing = {p.stem for p in history_dir.glob("????-??-??.json")}
    dates_to_gen = [d for d in dates if d not in existing]
    if not dates_to_gen:
        logger.info("모든 날짜의 히스토리가 이미 존재합니다.")
        return

    logger.info("배치 히스토리 생성: %s", dates_to_gen)
    latest_date = max(dates_to_gen)

    # 유니버스 수집
    logger.info("유니버스 수집 중...")
    us_tickers, us_sectors = fetch_sp500_tickers()
    ndx_tickers, ndx_sectors = fetch_nasdaq100_tickers()
    sp500_set = set(us_tickers)
    ndx_new = [t for t in ndx_tickers if t not in sp500_set]
    ndx_new_sectors = {t: s for t, s in ndx_sectors.items() if t not in sp500_set}
    us_tickers = us_tickers + ndx_new
    us_sectors = {**us_sectors, **ndx_new_sectors}
    kr_tickers = fetch_kr_tickers()

    sc.US_UNIVERSE = us_sectors
    sc.KR_UNIVERSE = {t: "Unknown" for t in kr_tickers}
    sc.ALL_UNIVERSE = {**sc.US_UNIVERSE, **sc.KR_UNIVERSE}

    # 최신 날짜 기준으로 데이터 1회 다운로드
    logger.info("데이터 다운로드 중 (기준일: %s)...", latest_date)
    us_data_raw, kr_data_raw, etf_data_raw = {}, {}, {}
    for i in range(0, len(us_tickers), 50):
        us_data_raw.update(download_for_date(us_tickers[i:i + 50], latest_date))
    for i in range(0, len(kr_tickers), 30):
        kr_data_raw.update(download_for_date(kr_tickers[i:i + 30], latest_date))
    etf_raw = download_for_date(list(set(sc.SECTOR_ETF.values())), latest_date)

    # 각 날짜별 처리
    for target_date in sorted(dates_to_gen):
        logger.info("\n=== %s 스크리닝 ===", target_date)
        cutoff = pd.Timestamp(target_date)

        # 해당 날짜까지 데이터 슬라이싱
        us_data = {t: df[df.index <= cutoff] for t, df in us_data_raw.items()
                   if len(df[df.index <= cutoff]) >= 60}
        kr_data = {t: df[df.index <= cutoff] for t, df in kr_data_raw.items()
                   if len(df[df.index <= cutoff]) >= 60}
        etf_data = {}
        for t, df in etf_raw.items():
            sliced = df[df.index <= cutoff]
            if len(sliced) >= 60:
                etf_data[t] = sc.calc_indicators(sliced)

        all_data = {**us_data, **kr_data}
        logger.info("  지표 계산 중 (%d개 종목)...", len(all_data))
        all_data_ind = {t: sc.calc_indicators(df) for t, df in all_data.items()}

        # 시장 상태 (SPY 기준 해당 날짜)
        market_status = None
        spy_df = us_data_raw.get("SPY") or us_data_raw.get("SPY.US")
        if spy_df is not None:
            spy_sliced = spy_df[spy_df.index <= cutoff]
            if len(spy_sliced) >= 60:
                spy_ind = sc.calc_indicators(spy_sliced)
                row = spy_ind.iloc[-1]
                ma20 = float(row.get("MA20", float("nan")))
                ma60 = float(spy_sliced["Close"].rolling(60).mean().iloc[-1])
                price = float(row["Close"])
                if not any(pd.isna(v) for v in [price, ma20, ma60]):
                    gap = (ma20 - ma60) / ma60 * 100
                    market_status = {
                        "spy_price": round(price, 2),
                        "is_golden_cross": ma20 > ma60,
                        "ma20": round(ma20, 2),
                        "ma60": round(ma60, 2),
                        "gap_pct": round(gap, 2),
                    }

        # 적응형 국면 판별
        adaptive_regime, adaptive_atr = detect_adaptive_regime(market_status)

        # 4전략 스크리닝
        strategies_output = {}
        for key, preset in STRATEGIES.items():
            atr_mult = preset["atr_mult"]
            top_n = preset["top_n"]
            passed = run_screening_with_atr(all_data_ind, etf_data, atr_mult)
            results = build_results(passed, etf_data, top_n)
            strategy_info = {
                "key": key,
                "label": preset["label"],
                "atr_mult": atr_mult,
                "rebal_freq": preset["rebal_freq"],
                "top_n": top_n,
                "total_screened": len(all_data),
                "total_passed": len(passed),
                "results": results,
            }
            if key == "adaptive":
                strategy_info["current_regime"] = adaptive_regime
                strategy_info["regime_label"] = STRATEGIES[adaptive_regime]["label"]
            strategies_output[key] = strategy_info
            logger.info("  %s: %d종목 선정 / %d개 통과", preset["label"], len(results), len(passed))

        run_dt = datetime.strptime(target_date, "%Y-%m-%d")
        output = {
            "run_id": int(run_dt.strftime("%Y%m%d")),
            "run_date": run_dt.strftime("%Y-%m-%dT00:00:00"),
            "market_status": market_status,
            "btc_signal": None,
            "strategies": strategies_output,
        }
        save_history(output_dir, output, run_dt)

    logger.info("배치 히스토리 생성 완료!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="4전략 스크리닝 결과 JSON 내보내기")
    parser.add_argument("--output", type=str, default="frontend/web/data/",
                        help="JSON 출력 디렉토리")
    parser.add_argument("--portfolio-only", action="store_true",
                        help="포트폴리오 JSON만 생성 (스크리닝 생략)")
    parser.add_argument("--xlsx", type=str, default=None,
                        help="portfolio.xlsx 경로 (기본: scripts/portfolio.xlsx)")
    parser.add_argument("--db", action="store_true",
                        help="스크리닝 결과를 SQLite DB에도 저장")
    parser.add_argument("--date", type=str, default=None,
                        help="히스토리 모드: YYYY-MM-DD 날짜 기준으로 history/{date}.json만 생성 "
                             "(screening_latest.json, screening_strategies.json은 갱신하지 않음)")
    parser.add_argument("--batch-dates", type=str, default=None,
                        help="배치 히스토리 모드: 쉼표로 구분된 날짜 목록 (예: 2026-03-23,2026-03-24)")
    parser.add_argument("--verbose", action="store_true", help="진행 상황 출력")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    output_path = Path(args.output)
    xlsx_path = Path(args.xlsx) if args.xlsx else None

    if args.portfolio_only:
        logger.info("포트폴리오 JSON 생성 중...")
        portfolio_to_json(output_path, xlsx_path)
    elif args.batch_dates:
        dates_list = [d.strip() for d in args.batch_dates.split(",")]
        generate_history_batch(output_path, dates_list)
    else:
        try:
            _output = export_all_strategies(output_path, screening_date=args.date)
            if args.db and _output is not None:
                logger.info("DB 저장 중...")
                save_to_db(_output, datetime.now())
        except Exception as e:
            print(f"\n[경고] 스크리닝 실패: {e}", file=sys.stderr)
            print("스크리닝은 건너뛰고 포트폴리오 현재가 업데이트를 계속합니다.", file=sys.stderr)
        if not args.date:
            logger.info("포트폴리오 JSON 생성 중...")
            portfolio_to_json(output_path, xlsx_path)
