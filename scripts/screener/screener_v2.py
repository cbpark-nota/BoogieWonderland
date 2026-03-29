"""
모멘텀 종목 스크리너 v2 — 5단계 개선 적용

.. deprecated::
    이 파일은 알고리즘 개발 과정 참고용입니다. 프로덕션에서는 screener_v3.py를 사용하세요.
    ATR 기반 동적 스톱로스 및 점수 비례 포지션 사이징은 v3에서 지원합니다.

══════════════════════════════════════════════
개선사항:
  Step1  트레일링 스톱로스 기준 출력 (매도 신호 표시)
  Step2  RSI 상한 70 → 75
  Step3  HH-HL 스윙 포인트 기준
  Step4  섹터 강도 ETF 초과수익률 기준
  Step5  52주 신고가 20% 이내 필터
══════════════════════════════════════════════
"""
import logging
import sys
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.constants import US_UNIVERSE, KR_UNIVERSE, ALL_UNIVERSE, SECTOR_ETF

STOP_PCT  = -0.10   # 트레일링 스톱 기준 (-10%)
WEIGHTS   = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)
TOP_N     = 10


# ── 다운로드 ──────────────────────────────────────────────────
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
                    logging.debug("screener_v2 download: %s 슬라이스 실패 — %s", t, e)
        else:
            if len(raw) >= 60:
                result[tickers[0]] = raw
        return result
    except Exception as e:
        logging.debug("screener_v2 download: 배치 다운로드 실패 — %s", e)
        return {}


# ── 지표 계산 ─────────────────────────────────────────────────
def calc_indicators(df):
    d = df.copy()
    c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
    d["MA20"]    = ta.sma(c, 20)
    d["MA50"]    = ta.sma(c, 50)
    d["MA200"]   = ta.sma(c, 200)
    d["RSI"]     = ta.rsi(c, 14)
    adx = ta.adx(h, l, c, 14)
    d["ADX"]     = adx["ADX_14"] if adx is not None and "ADX_14" in adx.columns else np.nan
    d["VolMA20"] = v.rolling(20).mean()
    d["VolMA60"] = v.rolling(60).mean()
    d["High52w"] = h.rolling(252).max()
    return d


# ── Step3: 스윙 포인트 HH-HL ─────────────────────────────────
def count_hh_hl_swing(df_window, n=3):
    highs = df_window["High"].values
    lows  = df_window["Low"].values

    swing_highs = [highs[i] for i in range(n, len(highs)-n)
                   if highs[i] == max(highs[i-n:i+n+1])]
    swing_lows  = [lows[i]  for i in range(n, len(lows)-n)
                   if lows[i]  == min(lows[i-n:i+n+1])]

    hh = sum(swing_highs[i] > swing_highs[i-1] for i in range(1, len(swing_highs)))
    hl = sum(swing_lows[i]  > swing_lows[i-1]  for i in range(1, len(swing_lows)))
    return min(hh, hl)


# ── 스크리닝 ──────────────────────────────────────────────────
def screen(df):
    if len(df) < 200:
        return False, {}

    row = df.iloc[-1]
    r5  = df.tail(6)
    r20 = df.tail(20)
    r60 = df.tail(60)
    r63 = df.tail(63)

    adx = row.get("ADX", np.nan)
    if pd.isna(adx) or adx < 25:
        return False, {}

    ma20, ma50, ma200 = row.get("MA20"), row.get("MA50"), row.get("MA200")
    if any(pd.isna(v) for v in [ma20, ma50, ma200]):
        return False, {}
    if not (ma20 > ma50 > ma200):
        return False, {}

    # Step2: RSI 상한 75
    rsi = row.get("RSI", np.nan)
    if pd.isna(rsi) or not (50 <= rsi <= 75):
        return False, {}

    vol60 = row.get("VolMA60", np.nan)
    if pd.isna(vol60) or vol60 == 0:
        return False, {}
    if (r20["Volume"] > vol60 * 3.0).any():
        return False, {}

    if (r5["Close"].pct_change().abs() > 0.10).any():
        return False, {}

    # Step3: 스윙 포인트 HH-HL
    if count_hh_hl_swing(r60) < 3:
        return False, {}

    # Step5: 52주 신고가 20% 이내
    high52 = row.get("High52w", np.nan)
    if not pd.isna(high52) and high52 > 0:
        if row["Close"] < high52 * 0.80:
            return False, {}

    ret3m    = float(df["Close"].iloc[-1] / r63["Close"].iloc[0]) - 1 \
               if len(r63) >= 60 else np.nan
    vol_cv   = r20["Volume"].std() / (vol60 + 1e-9)
    vol_stab = float(1 / (vol_cv + 1e-6))

    # 트레일링 스톱 참고가: 최근 20일 고점
    recent_peak = float(df["High"].tail(20).max())
    stop_price  = round(recent_peak * (1 + STOP_PCT), 2)

    return True, {
        "ADX": float(adx), "RSI": float(rsi),
        "ret3m": ret3m, "vol_stab": vol_stab,
        "price": float(df["Close"].iloc[-1]),
        "stop_price": stop_price,
        "high52w": float(high52) if not pd.isna(high52) else np.nan,
    }


# ── 복합점수 ──────────────────────────────────────────────────
def minmax(s):
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)

def rank_stocks(passed, etf_data):
    df = pd.DataFrame(passed).T
    df["sector"] = [ALL_UNIVERSE.get(t, "Unknown") for t in df.index]

    # Step4: ETF 초과수익률 기준 섹터 강도
    df["sec_str"] = 0.0
    for idx, row in df.iterrows():
        sec     = row["sector"]
        etf_sym = SECTOR_ETF.get(sec)
        if etf_sym and etf_sym in etf_data:
            etf_close = etf_data[etf_sym]["Close"]
            if len(etf_close) >= 63:
                etf_ret = float(etf_close.iloc[-1] / etf_close.iloc[-63]) - 1
                df.loc[idx, "sec_str"] = (row["ret3m"] - etf_ret) \
                    if not pd.isna(row["ret3m"]) else 0.0
    df["sec_str_norm"] = minmax(df["sec_str"])

    df["score"] = (
        minmax(df["ADX"])               * WEIGHTS["adx"]      +
        minmax(df["ret3m"].fillna(0))   * WEIGHTS["ret3m"]    +
        minmax(df["sec_str_norm"])      * WEIGHTS["sector"]   +
        minmax(df["vol_stab"])          * WEIGHTS["vol_stab"]
    )
    return df.sort_values("score", ascending=False)


# ── 시장 상태 ─────────────────────────────────────────────────
def check_market():
    try:
        spy = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
        close = spy["Close"].squeeze()
        ma50  = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        price = float(close.iloc[-1])
        gap   = (ma50 - ma200) / ma200 * 100
        return {"price": price, "ma50": ma50, "ma200": ma200,
                "gap_pct": gap, "is_golden": ma50 > ma200}
    except Exception as e:
        logging.debug("screener_v2 check_market: SPY 다운로드 실패 — %s", e)
        return None


# ── 메인 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    print("=" * 62)
    print(f"  모멘텀 종목 스크리너 v2   기준일: {today}")
    print(f"  유니버스: 미국 {len(US_UNIVERSE)}개 + 국내 {len(KR_UNIVERSE)}개")
    print("  적용: 스톱로스·RSI75·스윙HH-HL·ETF섹터·52w신고가")
    print("=" * 62)

    # 0. 시장 상태
    print("\n[0/3] 시장 상태 확인 (SPY)...")
    mkt = check_market()
    if mkt:
        status = "골든크로스 ✅" if mkt["is_golden"] else "데드크로스 ⚠️"
        arrow  = "▲" if mkt["gap_pct"] >= 0 else "▼"
        print(f"  SPY ${mkt['price']:.2f}  │  50MA ${mkt['ma50']:.2f}  │  "
              f"200MA ${mkt['ma200']:.2f}  │  {arrow}{abs(mkt['gap_pct']):.2f}%  {status}")
        if not mkt["is_golden"]:
            print()
            print("  ┌──────────────────────────────────────────────────┐")
            print("  │  ⚠️  관망 권장: 50MA < 200MA 데드크로스 상태         │")
            print("  │  신규 진입보다 현금 보유를 권장합니다.              │")
            print("  └──────────────────────────────────────────────────┘")
        else:
            print("  → 상승 추세. 스크리닝 결과 신뢰도 높음.")

    # 1. 다운로드
    print("\n[1/3] 데이터 다운로드 중...")
    us_tickers = list(US_UNIVERSE.keys())
    kr_tickers = list(KR_UNIVERSE.keys())
    etf_tickers = list(set(SECTOR_ETF.values()))

    us_data, kr_data, etf_data = {}, {}, {}
    for i in range(0, len(us_tickers), 30):
        us_data.update(download(us_tickers[i:i+30]))
    for i in range(0, len(kr_tickers), 30):
        kr_data.update(download(kr_tickers[i:i+30]))
    etf_data = download(etf_tickers)

    all_data = {**us_data, **kr_data}
    print(f"  종목 {len(all_data)}개, 섹터 ETF {len(etf_data)}개 수신 완료")

    # 2. 지표 계산 + 스크리닝
    print("\n[2/3] 지표 계산 및 스크리닝 중...")
    for t in list(etf_data.keys()):
        etf_data[t] = calc_indicators(etf_data[t])

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

    # 3. 랭킹 및 출력
    print("\n[3/3] 복합점수 계산 중...")
    ranked = rank_stocks(passed, etf_data)
    top10  = ranked.head(TOP_N)

    print("\n" + "=" * 62)
    print(f"  ★ 복합점수 상위 {TOP_N}개  (v2 알고리즘 기준)")
    print(f"  ADX×0.4 + 3M수익률×0.3 + ETF초과강도×0.2 + 거래량안정×0.1")
    print("=" * 62)

    for rank, (ticker, row) in enumerate(top10.iterrows(), 1):
        flag    = "🇺🇸" if not ticker.endswith(".KS") else "🇰🇷"
        ret_str = f"{row['ret3m']:+.1%}" if not pd.isna(row["ret3m"]) else "N/A"
        near52  = ""
        if not pd.isna(row.get("high52w", np.nan)) and row["high52w"] > 0:
            pct_from_high = (row["price"] / row["high52w"] - 1) * 100
            near52 = f"│ 52w고점대비:{pct_from_high:+.1f}%"

        print(
            f"  {rank:2d}위 {flag} {ticker:<12s}"
            f"│ 점수:{row['score']:.3f} "
            f"│ ADX:{row['ADX']:.1f} "
            f"│ RSI:{row['RSI']:.1f} "
            f"│ 3M:{ret_str} "
            f"│ 섹터:{row['sector']}"
        )
        # Step1: 스톱로스 참고가 표시
        stop = row.get("stop_price", np.nan)
        if not pd.isna(stop):
            print(f"       ⛔ 스톱로스 참고가: ${stop:.2f}  "
                  f"(현재가 ${row['price']:.2f}의 고점 -10%) {near52}")

    # CSV 저장
    save_cols = ["score","ADX","RSI","ret3m","sec_str",
                 "vol_stab","sector","price","stop_price"]
    save_cols = [c for c in save_cols if c in top10.columns]
    out = top10[save_cols].copy()
    out.index.name = "종목코드"
    out.to_csv("screener_v2_result.csv", encoding="utf-8-sig")
    print(f"\n  결과 저장: screener_v2_result.csv")
    print(f"  전체 통과 종목: {len(passed)}개")
