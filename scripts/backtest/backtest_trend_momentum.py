# DEPRECATED — 매매 전략 아님
# ──────────────────────────────────────────────────────────────────────────────
# 이 파일은 시가총액 Top 20 종목의 트렌드를 모니터링하기 위한 참고 도구입니다.
# 매매 시그널이나 포트폴리오 편입 판단에 사용하지 않습니다.
#
# 목적: 시장 전체 트렌드(Bull / Bear / Sideways) 파악용 보조 지표
# 사용처: 투자 환경 모니터링, 전략 국면 판단 참고 (거래 실행 X)
# ──────────────────────────────────────────────────────────────────────────────
"""
시총 Top 20 트렌드 모멘텀 백테스트 (참고용 — 매매 전략 아님)

S&P 500 / KOSPI 시가총액 상위 20개 종목의 모멘텀 지표를 분석하여
시장 트렌드 방향성을 파악하는 참고 도구입니다.
실제 매매 포트폴리오는 screener_v3.py 기반 4전략을 사용합니다.
"""

import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent / "screener"))

# ── 시총 Top 20 (미국 — 참고용, 분기별 검토 권장) ──────────────────────────
US_TOP20 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "TSLA", "BRK-B", "AVGO", "JPM",
    "LLY", "UNH", "V", "XOM", "MA",
    "COST", "HD", "PG", "JNJ", "ORCL",
]

# ── 시총 Top 20 (한국 — 참고용) ────────────────────────────────────────────
KR_TOP20 = [
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


def calc_trend_score(tickers: list[str], period: str = "6mo") -> pd.DataFrame:
    """
    시총 Top 20 종목의 트렌드 점수를 계산합니다.
    (매매 목적 아님 — 시장 방향성 파악용)

    Returns
    -------
    DataFrame: ticker, price, ma20, ma60, above_ma20, above_ma60,
               ret_1m, ret_3m, trend_score
    """
    print(f"[트렌드 분석] {len(tickers)}개 종목 데이터 다운로드 중...")
    raw = yf.download(tickers, period=period, auto_adjust=True, progress=False)

    if raw.empty:
        print("  데이터 없음")
        return pd.DataFrame()

    close = raw["Close"] if "Close" in raw.columns else raw
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])

    rows = []
    for ticker in tickers:
        if ticker not in close.columns:
            continue
        s = close[ticker].dropna()
        if len(s) < 60:
            continue
        price = float(s.iloc[-1])
        ma20 = float(s.rolling(20).mean().iloc[-1])
        ma60 = float(s.rolling(60).mean().iloc[-1])
        ret_1m = float((s.iloc[-1] / s.iloc[-21] - 1) * 100) if len(s) >= 21 else None
        ret_3m = float((s.iloc[-1] / s.iloc[-63] - 1) * 100) if len(s) >= 63 else None

        above_ma20 = price > ma20
        above_ma60 = price > ma60
        trend_score = sum([above_ma20, above_ma60,
                           ret_1m is not None and ret_1m > 0,
                           ret_3m is not None and ret_3m > 0])
        rows.append({
            "ticker": ticker,
            "price": round(price, 2),
            "ma20": round(ma20, 2),
            "ma60": round(ma60, 2),
            "above_ma20": above_ma20,
            "above_ma60": above_ma60,
            "ret_1m_pct": round(ret_1m, 2) if ret_1m is not None else None,
            "ret_3m_pct": round(ret_3m, 2) if ret_3m is not None else None,
            "trend_score": trend_score,  # 0~4 (4=강한 상승추세)
        })

    df = pd.DataFrame(rows).sort_values("trend_score", ascending=False)
    return df


def summarize_market_trend(df: pd.DataFrame, label: str = "시장") -> str:
    """
    시총 Top 20 트렌드 점수 요약 — 시장 방향성 판단 참고용.
    실제 포트폴리오 진입 결정에는 사용하지 않음.
    """
    if df.empty:
        return f"{label}: 데이터 없음"
    bull_pct = (df["trend_score"] >= 3).mean() * 100
    bear_pct = (df["trend_score"] <= 1).mean() * 100

    if bull_pct >= 60:
        phase = "Bull (강한 상승)"
    elif bear_pct >= 60:
        phase = "Bear (하락 우위)"
    else:
        phase = "Sideways (혼조)"

    return (
        f"{label} 트렌드 ({len(df)}종목): {phase} "
        f"| Bull 비율 {bull_pct:.0f}% / Bear 비율 {bear_pct:.0f}%"
    )


if __name__ == "__main__":
    print("=" * 60)
    print("시총 Top 20 트렌드 모니터링 (매매 전략 아님 — 참고용)")
    print("=" * 60)

    us_df = calc_trend_score(US_TOP20)
    kr_df = calc_trend_score(KR_TOP20)

    print("\n[미국 시총 Top 20]")
    print(summarize_market_trend(us_df, "미국"))
    if not us_df.empty:
        print(us_df[["ticker", "above_ma20", "above_ma60",
                      "ret_1m_pct", "ret_3m_pct", "trend_score"]].to_string(index=False))

    print("\n[한국 시총 Top 20]")
    print(summarize_market_trend(kr_df, "한국"))
    if not kr_df.empty:
        print(kr_df[["ticker", "above_ma20", "above_ma60",
                      "ret_1m_pct", "ret_3m_pct", "trend_score"]].to_string(index=False))

    print("\n※ 위 결과는 시장 트렌드 파악용 참고 정보입니다.")
    print("  실제 매매는 screener_v3.py 기반 4전략을 사용하세요.")
