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
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent / "screener"))
sys.path.insert(0, str(Path(__file__).parent / "crypto"))

import screener_v3 as sc

# ICB Industry (Wikipedia NASDAQ-100) → GICS Sector 매핑
_ICB_TO_GICS = {
    "Technology":              "Information Technology",
    "Consumer Discretionary":  "Consumer Discretionary",
    "Health Care":             "Health Care",
    "Utilities":               "Utilities",
    "Industrials":             "Industrials",
    "Energy":                  "Energy",
    "Telecommunications":      "Communication Services",
    "Consumer Staples":        "Consumer Staples",
    "Real Estate":             "Real Estate",
    "Basic Materials":         "Materials",
    "Financials":              "Financials",
}

# 4가지 전략 프리셋 — v3 최적 ATR 승수 + 전략별 종목 수
# top_n: 공격적(15) > 균형형(10) > 보수적(7) — 위험선호도에 따라 포트폴리오 집중도 차별화
STRATEGIES = {
    "aggressive":   {"atr_mult": 1.5, "label": "공격적", "rebal_freq": "주간",  "top_n": 15},
    "balanced":     {"atr_mult": 2.0, "label": "균형형", "rebal_freq": "격주",  "top_n": 10},
    "conservative": {"atr_mult": 2.5, "label": "보수적", "rebal_freq": "월간",  "top_n": 7},
    "adaptive":     {"atr_mult": None, "label": "적응형", "rebal_freq": "동적", "top_n": None},
}

# 적응형 전략의 국면별 종목 수 매핑
TOP_N_MAP = {"aggressive": 15, "balanced": 10, "conservative": 7}


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
        print(f"  S&P500 수집 실패 ({e}), 기본 유니버스 사용")
        return list(sc.US_UNIVERSE.keys()), dict(sc.US_UNIVERSE)


def fetch_nasdaq100_tickers():
    """NASDAQ-100 구성 종목 및 섹터 가져오기 (Wikipedia).

    Wikipedia의 NASDAQ-100 페이지에서 종목 리스트를 수집한다.
    ICB Industry를 GICS 섹터로 변환해서 S&P500과 동일한 형식으로 반환.
    """
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
        # Table 4: Ticker | Company | ICB Industry[14] | ICB Subsector[14]
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


def _fetch_kr_from_naver(kospi_n: int, kosdaq_n: int) -> list[str]:
    """네이버 금융 시가총액 페이지에서 KR 종목 수집 (fallback).

    BeautifulSoup으로 HTML a[href*=code] 링크를 파싱해서 종목코드를 추출한다.
    sosok=0: KOSPI, sosok=1: KOSDAQ
    """
    import re
    from bs4 import BeautifulSoup

    def _scrape_market(sosok: int, n: int, suffix: str) -> list[str]:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
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
        kospi  = _scrape_market(0, kospi_n, ".KS")
        kosdaq = _scrape_market(1, kosdaq_n, ".KQ")
        all_kr = kospi + kosdaq
        print(f"  KR (네이버 fallback) KOSPI {len(kospi)}개 + KOSDAQ {len(kosdaq)}개 수집 완료")
        return all_kr
    except Exception as e:
        print(f"  KR 종목 수집 최종 실패 ({e}), 기본 유니버스 사용")
        return list(sc.KR_UNIVERSE.keys())


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

        all_kr = kospi_tickers + kosdaq_tickers
        print(f"  KR KOSPI {len(kospi_tickers)}개 + KOSDAQ {len(kosdaq_tickers)}개 수집 완료")
        return all_kr
    except Exception as e:
        print(f"  KRX (kind.krx.co.kr) 실패 ({e}), 네이버 금융으로 재시도...")
        return _fetch_kr_from_naver(kospi_n, kosdaq_n)


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
        results.append({
            "rank": rank,
            "ticker": ticker,
            "market": market,
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
        print("BTC V10 시그널 계산 중...")
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
            print(f"  → 매수 신호 (현재가 ${last_close:,.0f}, 레짐: {regime})")
            return {
                "signal": "buy",
                "price": round(last_close, 2),
                "reason": reason,
                "regime": regime,
                "strategy": "V10",
                "timestamp": last_time,
            }
        else:
            print(f"  → 관망 (현재가 ${last_close:,.0f}, 레짐: {regime})")
            return {
                "signal": "hold",
                "price": round(last_close, 2),
                "reason": "매수 조건 미충족 — 현금 보유",
                "regime": regime,
                "strategy": "V10",
                "timestamp": last_time,
            }

    except Exception as e:
        print(f"  BTC 시그널 계산 실패: {e}")
        return {
            "signal": "hold",
            "price": None,
            "reason": f"시그널 계산 실패: {e}",
            "strategy": "V10",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }


def export_all_strategies(output_dir: Path):
    """4전략 스크리닝 실행 후 단일 JSON으로 저장."""
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    # 시장 상태
    mkt = sc.check_market()
    market_status = None
    if mkt:
        market_status = {
            "spy_price": round(mkt["price"], 2),
            "is_golden_cross": mkt["is_golden"],
            "ma50": round(mkt["ma50"], 2),
            "ma200": round(mkt["ma200"], 2),
            "gap_pct": round(mkt["gap_pct"], 2),
        }

    # 동적 유니버스 수집
    print("유니버스 수집 중...")
    us_tickers, us_sectors = fetch_sp500_tickers()
    ndx_tickers, ndx_sectors = fetch_nasdaq100_tickers()

    # S&P500과 중복 제거 후 NASDAQ-100 신규 종목만 추가
    sp500_set = set(us_tickers)
    ndx_new = [t for t in ndx_tickers if t not in sp500_set]
    ndx_new_sectors = {t: s for t, s in ndx_sectors.items() if t not in sp500_set}
    print(f"  NASDAQ-100 신규 추가: {len(ndx_new)}개 (S&P500 중복 {len(ndx_tickers) - len(ndx_new)}개 제거)")

    us_tickers = us_tickers + ndx_new
    us_sectors = {**us_sectors, **ndx_new_sectors}

    kr_tickers = fetch_kr_tickers()

    # screener_v3의 유니버스/섹터 맵을 동적 수집 결과로 교체
    sc.US_UNIVERSE = us_sectors                         # ticker → GICS Sector
    sc.KR_UNIVERSE = {t: "Unknown" for t in kr_tickers}
    sc.ALL_UNIVERSE = {**sc.US_UNIVERSE, **sc.KR_UNIVERSE}

    # 데이터 다운로드 (1회)
    print("데이터 다운로드 중...")
    us_data, kr_data, etf_data = {}, {}, {}
    for i in range(0, len(us_tickers), 50):
        us_data.update(sc.download(us_tickers[i:i + 50]))
    for i in range(0, len(kr_tickers), 30):
        kr_data.update(sc.download(kr_tickers[i:i + 30]))
    etf_raw = sc.download(list(set(sc.SECTOR_ETF.values())))
    for t, df in etf_raw.items():
        etf_data[t] = sc.calc_indicators(df)

    all_data = {**us_data, **kr_data}

    # 지표 계산 (1회)
    print(f"지표 계산 중 ({len(all_data)}개 종목)...")
    all_data_ind = {}
    for t, df in all_data.items():
        all_data_ind[t] = sc.calc_indicators(df)

    # 적응형 국면 판별
    adaptive_regime, adaptive_atr = detect_adaptive_regime(mkt)

    # 4전략 스크리닝
    strategies_output = {}
    for key, preset in STRATEGIES.items():
        atr_mult = preset["atr_mult"] if preset["atr_mult"] is not None else adaptive_atr
        top_n = preset["top_n"] if preset["top_n"] is not None else TOP_N_MAP.get(adaptive_regime, sc.TOP_N)
        print(f"  {preset['label']} (ATR={atr_mult}, TOP={top_n}) 스크리닝 중...")
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

        # 적응형 전략에는 현재 국면 정보 추가
        if key == "adaptive":
            strategy_info["current_regime"] = adaptive_regime
            strategy_info["regime_label"] = STRATEGIES[adaptive_regime]["label"]

        strategies_output[key] = strategy_info

    # BTC V10 시그널 계산
    btc_signal = calculate_btc_signal()

    output = {
        "run_id": int(now.strftime("%Y%m%d")),
        "run_date": now.isoformat(timespec="seconds"),
        "market_status": market_status,
        "btc_signal": btc_signal,
        "strategies": strategies_output,
    }

    # screening_latest.json (하위 호환: 균형형을 기본으로)
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

    # screening_strategies.json (4전략 전체)
    full_path = output_dir / "screening_strategies.json"
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n완료: {full_path}")
    for k in ("aggressive", "balanced", "conservative"):
        s = strategies_output[k]
        print(f"  {s['label']}: {len(s['results'])}종목 선정 / {s['total_passed']}개 통과")
    s = strategies_output["adaptive"]
    print(f"  {s['label']}: {len(s['results'])}종목 선정 / {s['total_passed']}개 통과 "
          f"(현재 국면: {STRATEGIES[adaptive_regime]['label']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="4전략 스크리닝 결과 JSON 내보내기")
    parser.add_argument("--output", type=str, default="frontend/web/data/",
                        help="JSON 출력 디렉토리")
    args = parser.parse_args()
    export_all_strategies(Path(args.output))
