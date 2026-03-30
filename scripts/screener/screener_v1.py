"""
오늘 기준 모멘텀 종목 스크리닝 (v1 베이스라인)

.. deprecated::
    이 파일은 참고용 베이스라인입니다. 프로덕션에서는 screener_v3.py를 사용하세요.
    하드코딩 유니버스(~80개)만 스크리닝하며 ATR 스톱로스, 점수 비례 포지션 사이징 미지원.
"""
import logging
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta

# ── 유니버스 ──────────────────────────────────────────
# S&P500 주요 종목 (섹터별 균형)
US_UNIVERSE = {
    # Technology
    "NVDA":"Technology","AAPL":"Technology","MSFT":"Technology","AVGO":"Technology",
    "AMD":"Technology","QCOM":"Technology","AMAT":"Technology","LRCX":"Technology",
    "MU":"Technology","KLAC":"Technology","TSM":"Technology","ORCL":"Technology",
    "CRM":"Technology","NOW":"Technology","ADBE":"Technology","INTU":"Technology",
    "PANW":"Technology","CRWD":"Technology","FTNT":"Technology","SNPS":"Technology",
    # Communication
    "META":"Communication","GOOGL":"Communication","NFLX":"Communication",
    "TMUS":"Communication","DIS":"Communication",
    # Consumer Discretionary
    "AMZN":"Consumer Disc","TSLA":"Consumer Disc","HD":"Consumer Disc",
    "MCD":"Consumer Disc","NKE":"Consumer Disc","LULU":"Consumer Disc",
    # Health Care
    "LLY":"Health Care","UNH":"Health Care","ABBV":"Health Care",
    "TMO":"Health Care","ISRG":"Health Care","VRTX":"Health Care","REGN":"Health Care",
    # Financials
    "V":"Financials","MA":"Financials","JPM":"Financials","GS":"Financials","MS":"Financials",
    # Energy
    "XOM":"Energy","CVX":"Energy","SLB":"Energy",
    # Industrials
    "CAT":"Industrials","DE":"Industrials","GE":"Industrials","LMT":"Industrials",
    "RTX":"Industrials","ETN":"Industrials",
    # Materials / Other
    "FCX":"Materials","NEM":"Materials",
    "BRK-B":"Financials","BX":"Financials","KKR":"Financials",
}

KR_UNIVERSE = {
    "005930.KS":"Technology",   # 삼성전자
    "000660.KS":"Technology",   # SK하이닉스
    "009150.KS":"Technology",   # 삼성전기
    "006400.KS":"Technology",   # 삼성SDI
    "373220.KS":"Technology",   # LG에너지솔루션
    "066570.KS":"Technology",   # LG전자
    "207940.KS":"Health Care",  # 삼성바이오로직스
    "068270.KS":"Health Care",  # 셀트리온
    "051910.KS":"Materials",    # LG화학
    "247540.KS":"Materials",    # 에코프로비엠
    "005380.KS":"Consumer Disc",# 현대차
    "000270.KS":"Consumer Disc",# 기아
    "035420.KS":"Communication",# NAVER
    "035720.KS":"Communication",# 카카오
    "105560.KS":"Financials",   # KB금융
    "055550.KS":"Financials",   # 신한지주
    "086790.KS":"Financials",   # 하나금융지주
    "011200.KS":"Industrials",  # HMM
    "096770.KS":"Energy",       # SK이노베이션
    "352820.KS":"Communication",# 하이브
}

ALL_UNIVERSE = {**US_UNIVERSE, **KR_UNIVERSE}

# ── 파라미터 ─────────────────────────────────────────
ADX_MIN       = 25
RSI_MIN, RSI_MAX = 50, 70
VOL_SPIKE     = 3.0
DAILY_MAX     = 0.10
HH_HL_MIN     = 3
TOP_N         = 10
WEIGHTS       = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)

# ── 데이터 다운로드 ──────────────────────────────────
def download(tickers, period="1y"):
    try:
        raw = yf.download(tickers, period=period, auto_adjust=True,
                          progress=False, threads=True)
        result = {}
        if isinstance(raw.columns, pd.MultiIndex):
            for t in tickers:
                try:
                    df = raw.xs(t, axis=1, level=1).dropna(how="all")
                    if len(df) >= 60:
                        result[t] = df
                except Exception as e:
                    logging.debug("screener_v1 download: %s 슬라이스 실패 — %s", t, e)
        else:
            if len(raw) >= 60:
                result[tickers[0]] = raw
        return result
    except Exception as e:
        print(f"  다운로드 오류: {e}")
        return {}

# ── 지표 계산 ────────────────────────────────────────
def calc_indicators(df):
    d = df.copy()
    c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
    d["MA20"]   = ta.sma(c, 20)
    d["MA50"]   = ta.sma(c, 50)
    d["MA200"]  = ta.sma(c, 200)
    d["RSI"]    = ta.rsi(c, 14)
    adx = ta.adx(h, l, c, 14)
    d["ADX"]    = adx["ADX_14"] if adx is not None and "ADX_14" in adx.columns else np.nan
    d["VolMA20"]= v.rolling(20).mean()
    d["VolMA60"]= v.rolling(60).mean()
    return d

# ── 스크리닝 ─────────────────────────────────────────
def screen(df):
    if len(df) < 200:
        return False, {}

    row  = df.iloc[-1]
    r5   = df.tail(6)
    r20  = df.tail(20)
    r60  = df.tail(60)
    r63  = df.tail(63)

    adx = row.get("ADX", np.nan)
    if pd.isna(adx) or adx < ADX_MIN:
        return False, {}

    ma20 = row.get("MA20"); ma50 = row.get("MA50"); ma200 = row.get("MA200")
    if any(pd.isna(v) for v in [ma20, ma50, ma200]):
        return False, {}
    if not (ma20 > ma50 > ma200):
        return False, {}

    rsi = row.get("RSI", np.nan)
    if pd.isna(rsi) or not (RSI_MIN <= rsi <= RSI_MAX):
        return False, {}

    vol60 = row.get("VolMA60", np.nan)
    if pd.isna(vol60) or vol60 == 0:
        return False, {}
    if (r20["Volume"] > vol60 * VOL_SPIKE).any():
        return False, {}

    if (r5["Close"].pct_change().abs() > DAILY_MAX).any():
        return False, {}

    highs, lows = r60["High"].values, r60["Low"].values
    hh_hl = sum(highs[i]>highs[i-1] and lows[i]>lows[i-1] for i in range(1, len(highs)))
    if hh_hl < HH_HL_MIN:
        return False, {}

    ret3m    = float(df["Close"].iloc[-1] / r63["Close"].iloc[0]) - 1 if len(r63) >= 60 else np.nan
    vol_cv   = r20["Volume"].std() / (vol60 + 1e-9)
    vol_stab = float(1 / (vol_cv + 1e-6))

    return True, {"ADX": float(adx), "RSI": float(rsi),
                  "ret3m": ret3m, "vol_stab": vol_stab,
                  "price": float(df["Close"].iloc[-1]),
                  "ma20": float(ma20), "ma50": float(ma50), "ma200": float(ma200)}

# ── 복합점수 ─────────────────────────────────────────
def minmax(s):
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)

def rank_stocks(passed, sector_map):
    df = pd.DataFrame(passed).T
    df["sector"] = [sector_map.get(t, "Unknown") for t in df.index]

    df["sec_str"] = 0.5
    for sec in df["sector"].unique():
        mask = df["sector"] == sec
        if mask.sum() > 1:
            df.loc[mask, "sec_str"] = minmax(df.loc[mask, "ret3m"].fillna(0))

    df["score"] = (
        minmax(df["ADX"])               * WEIGHTS["adx"]      +
        minmax(df["ret3m"].fillna(0))   * WEIGHTS["ret3m"]    +
        minmax(df["sec_str"])           * WEIGHTS["sector"]   +
        minmax(df["vol_stab"])          * WEIGHTS["vol_stab"]
    )
    return df.sort_values("score", ascending=False)

# ── 메인 ─────────────────────────────────────────────
# ── 시장 상태 체크 ───────────────────────────────────
def check_market() -> dict:
    """
    SPY 기준 시장 상태 확인
    - 골든크로스: 50MA > 200MA  → 상승 추세
    - 데드크로스:  50MA < 200MA  → 하락 추세 (관망 권장)
    """
    try:
        spy = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
        close  = spy["Close"].squeeze()
        ma50   = float(close.rolling(50).mean().iloc[-1])
        ma200  = float(close.rolling(200).mean().iloc[-1])
        price  = float(close.iloc[-1])
        gap_pct = (ma50 - ma200) / ma200 * 100   # 양수=골든, 음수=데드

        return {
            "price" : price,
            "ma50"  : ma50,
            "ma200" : ma200,
            "gap_pct" : gap_pct,
            "is_golden": ma50 > ma200,
        }
    except Exception as e:
        print(f"  ⚠️  시장 상태 확인 실패: {e}")
        return None


if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    print("=" * 60)
    print(f"  모멘텀 종목 스크리닝  기준일: {today}")
    print(f"  유니버스: 미국 {len(US_UNIVERSE)}개 + 국내 {len(KR_UNIVERSE)}개")
    print("=" * 60)

    # ── 시장 상태 확인 ──
    print("\n[0/3] 시장 상태 확인 (SPY 기준)...")
    market = check_market()

    if market:
        status  = "골든크로스 ✅" if market["is_golden"] else "데드크로스 ⚠️"
        arrow   = "▲" if market["gap_pct"] >= 0 else "▼"
        print(f"  SPY 현재가  : ${market['price']:.2f}")
        print(f"  50MA        : ${market['ma50']:.2f}")
        print(f"  200MA       : ${market['ma200']:.2f}")
        print(f"  50MA-200MA  : {arrow} {abs(market['gap_pct']):.2f}%  ({status})")

        if not market["is_golden"]:
            print()
            print("  ┌─────────────────────────────────────────────────┐")
            print("  │  ⚠️  관망 권장                                    │")
            print("  │  S&P 500 (SPY) 50MA < 200MA 데드크로스 상태입니다. │")
            print("  │  시장 전반이 하락 추세에 있어 스크리닝 결과가     │")
            print("  │  매우 적거나 신뢰도가 낮을 수 있습니다.           │")
            print("  │  신규 진입보다 현금 보유를 권장합니다.            │")
            print("  └─────────────────────────────────────────────────┘")
        else:
            print(f"  → 시장 상승 추세. 스크리닝 결과 신뢰도 높음.")
    else:
        print("  시장 상태 확인 불가 — 스크리닝은 계속 진행합니다.")

    print()
    print("[1/3] 데이터 다운로드 중...")
    us_tickers = list(US_UNIVERSE.keys())
    kr_tickers = list(KR_UNIVERSE.keys())

    us_data, kr_data = {}, {}
    batch = 30
    for i in range(0, len(us_tickers), batch):
        chunk = us_tickers[i:i+batch]
        us_data.update(download(chunk))
        print(f"  미국 {min(i+batch, len(us_tickers))}/{len(us_tickers)} 완료")

    for i in range(0, len(kr_tickers), batch):
        chunk = kr_tickers[i:i+batch]
        kr_data.update(download(chunk))
    print(f"  국내 {len(kr_tickers)}/{len(kr_tickers)} 완료")

    all_data = {**us_data, **kr_data}
    print(f"  총 {len(all_data)}개 수신 완료")

    # 지표 계산
    print("\n[2/3] 지표 계산 및 스크리닝 중...")
    passed = {}
    for t, df in all_data.items():
        df_ind = calc_indicators(df)
        ok, metrics = screen(df_ind)
        if ok:
            passed[t] = metrics

    print(f"  스크리닝 통과: {len(passed)}개 / {len(all_data)}개")

    if not passed:
        print("\n  ※ 현재 조건을 통과한 종목이 없습니다.")
        exit()

    # 랭킹
    print("\n[3/3] 복합점수 계산 및 순위 선정...")
    ranked = rank_stocks(passed, ALL_UNIVERSE)
    top10  = ranked.head(TOP_N)

    # 결과 출력
    print("\n" + "=" * 60)
    print(f"  ★ 복합점수 상위 {TOP_N}개 종목")
    print(f"  (ADX×0.4 + 3M수익률×0.3 + 섹터강도×0.2 + 거래량안정성×0.1)")
    print("=" * 60)

    for rank, (ticker, row) in enumerate(top10.iterrows(), 1):
        market = "🇺🇸" if not ticker.endswith(".KS") else "🇰🇷"
        ret3m  = row["ret3m"]
        ret_str = f"{ret3m:+.1%}" if not pd.isna(ret3m) else "N/A"
        print(
            f"  {rank:2d}위 {market} {ticker:<12s} "
            f"│ 점수:{row['score']:.3f} "
            f"│ ADX:{row['ADX']:.1f} "
            f"│ RSI:{row['RSI']:.1f} "
            f"│ 3M수익:{ret_str} "
            f"│ 섹터:{row['sector']}"
        )

    # CSV 저장
    out = top10[["score","ADX","RSI","ret3m","vol_stab","sector","price"]].copy()
    out.columns = ["복합점수","ADX","RSI","3M수익률","거래량안정성","섹터","현재가"]
    out.index.name = "종목코드"
    out.to_csv("screener_v1_result.csv", encoding="utf-8-sig")

    # 전체 통과 종목도 저장
    ranked[["score","ADX","RSI","ret3m","sector","price"]].to_csv(
        "screener_v1_all.csv", encoding="utf-8-sig"
    )
    print(f"\n  전체 통과 종목 ({len(passed)}개): screening_all.csv")
    print(f"  상위 {TOP_N}개 결과: screening_result.csv")
