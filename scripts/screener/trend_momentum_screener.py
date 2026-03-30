# DEPRECATED — 매매 전략 아님
# ──────────────────────────────────────────────────────────────────────────────
# 이 파일은 시가총액 Top 20 종목의 트렌드를 모니터링하기 위한 참고 도구입니다.
# 매매 시그널이나 포트폴리오 편입 판단에 사용하지 않습니다.
#
# 목적: 시장 전체 트렌드(Bull / Bear / Sideways) 파악용 보조 지표
# 사용처: 투자 환경 모니터링, 전략 국면 판단 참고 (거래 실행 X)
# ──────────────────────────────────────────────────────────────────────────────
"""
시총 Top 20 트렌드 스크리너 (참고용 — 매매 전략 아님)

시가총액 상위 20개 종목의 추세 지표(MA, 모멘텀)를 집계하여
시장 트렌드 방향성을 빠르게 파악하는 보조 도구입니다.

실제 종목 선정과 포트폴리오 관리는 screener_v3.py 기반
공격적 / 균형형 / 보수적 / 적응형 4전략을 사용합니다.
"""

from pathlib import Path
import sys

# screener_v3 유틸 재사용 (download, calc_indicators)
sys.path.insert(0, str(Path(__file__).parent))

try:
    import screener_v3 as sc
    _SC_AVAILABLE = True
except ImportError:
    _SC_AVAILABLE = False

import pandas as pd
import yfinance as yf


# ── 트렌드 모니터링 대상 (매매 유니버스와 다름) ──────────────────────────
TREND_UNIVERSE_US = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "TSLA", "BRK-B", "AVGO", "JPM",
    "LLY", "UNH", "V", "XOM", "MA",
    "COST", "HD", "PG", "JNJ", "ORCL",
]

TREND_UNIVERSE_KR = [
    "005930.KS",  # 삼성전자
    "000660.KS",  # SK하이닉스
    "373220.KS",  # LG에너지솔루션
    "005380.KS",  # 현대차
    "000270.KS",  # 기아
    "068270.KS",  # 셀트리온
    "105560.KS",  # KB금융
    "055550.KS",  # 신한지주
    "012330.KS",  # 현대모비스
    "035720.KS",  # 카카오
    "035420.KS",  # NAVER
    "086790.KS",  # 하나금융지주
    "003550.KS",  # LG
    "051910.KS",  # LG화학
    "028260.KS",  # 삼성물산
    "006400.KS",  # 삼성SDI
    "207940.KS",  # 삼성바이오로직스
    "032830.KS",  # 삼성생명
    "017670.KS",  # SK텔레콤
    "030200.KS",  # KT
]


def get_trend_snapshot(tickers: list[str]) -> list[dict]:
    """
    시총 Top 20 종목의 현재 트렌드 스냅샷 반환.

    Returns
    -------
    list of dict: ticker, above_ma20, above_ma60, ret_3m_pct, trend_phase
    """
    if _SC_AVAILABLE:
        raw_data = sc.download(tickers)
        results = []
        for ticker, df in raw_data.items():
            if df is None or df.empty:
                continue
            df_ind = sc.calc_indicators(df)
            if df_ind is None or df_ind.empty:
                continue
            row = df_ind.iloc[-1]
            price = float(row.get("close", 0))
            ma20 = float(row.get("ma20", 0))
            ma60 = float(row.get("ma60", 0))
            ret3m = float(row.get("ret3m", 0)) * 100
            above_ma20 = price > ma20 > 0
            above_ma60 = price > ma60 > 0
            score = sum([above_ma20, above_ma60, ret3m > 0])
            results.append({
                "ticker": ticker,
                "price": round(price, 2),
                "above_ma20": above_ma20,
                "above_ma60": above_ma60,
                "ret_3m_pct": round(ret3m, 2),
                "trend_score": score,  # 0~3
            })
        return sorted(results, key=lambda x: x["trend_score"], reverse=True)

    # screener_v3 없을 경우 yfinance 직접 사용
    raw = yf.download(tickers, period="6mo", auto_adjust=True, progress=False)
    close = raw["Close"] if "Close" in raw.columns else raw
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])

    results = []
    for ticker in tickers:
        if ticker not in close.columns:
            continue
        s = close[ticker].dropna()
        if len(s) < 60:
            continue
        price = float(s.iloc[-1])
        ma20 = float(s.rolling(20).mean().iloc[-1])
        ma60 = float(s.rolling(60).mean().iloc[-1])
        ret3m = float((s.iloc[-1] / s.iloc[-63] - 1) * 100) if len(s) >= 63 else 0.0
        above_ma20 = price > ma20
        above_ma60 = price > ma60
        score = sum([above_ma20, above_ma60, ret3m > 0])
        results.append({
            "ticker": ticker,
            "price": round(price, 2),
            "above_ma20": above_ma20,
            "above_ma60": above_ma60,
            "ret_3m_pct": round(ret3m, 2),
            "trend_score": score,
        })
    return sorted(results, key=lambda x: x["trend_score"], reverse=True)


def classify_market_phase(snapshot: list[dict]) -> str:
    """
    시총 Top 20 트렌드 스냅샷으로 시장 국면 분류.
    — 참고용: screener_v3의 check_market()과 독립적으로 사용 가능.

    Returns
    -------
    'bull' | 'bear' | 'sideways'
    """
    if not snapshot:
        return "sideways"
    bull = sum(1 for r in snapshot if r["trend_score"] >= 2) / len(snapshot)
    bear = sum(1 for r in snapshot if r["trend_score"] == 0) / len(snapshot)
    if bull >= 0.6:
        return "bull"
    if bear >= 0.5:
        return "bear"
    return "sideways"


if __name__ == "__main__":
    print("=" * 60)
    print("시총 Top 20 트렌드 스크리너 (참고용 — 매매 전략 아님)")
    print("=" * 60)

    us_snap = get_trend_snapshot(TREND_UNIVERSE_US)
    kr_snap = get_trend_snapshot(TREND_UNIVERSE_KR)

    us_phase = classify_market_phase(us_snap)
    kr_phase = classify_market_phase(kr_snap)

    print(f"\n미국 시장 국면 (시총 Top 20 기준): {us_phase.upper()}")
    for r in us_snap:
        flag = "▲" if r["above_ma60"] else "▽"
        print(f"  {flag} {r['ticker']:10s}  score={r['trend_score']}  "
              f"3m={r['ret_3m_pct']:+.1f}%")

    print(f"\n한국 시장 국면 (시총 Top 20 기준): {kr_phase.upper()}")
    for r in kr_snap:
        flag = "▲" if r["above_ma60"] else "▽"
        print(f"  {flag} {r['ticker']:14s}  score={r['trend_score']}  "
              f"3m={r['ret_3m_pct']:+.1f}%")

    print("\n※ 이 결과는 시장 트렌드 파악용 참고 정보입니다.")
    print("  실제 매매는 screener_v3.py 기반 4전략을 사용하세요.")
