"""
모멘텀 종목 스크리너 v3
══════════════════════════════════════════════════════════
v2 대비 추가 개선:
  ① ATR 기반 동적 스톱로스   (고정 -10% → ATR×2.5)
  ② 복합점수 비례 포지션 사이징 (동일비중 → 점수 가중 배분)
══════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime

# ── 유니버스 ──────────────────────────────────────────────────
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

ATR_PERIOD   = 14
ATR_MULT     = 2.5
WEIGHTS      = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)
TOP_N        = 10
# 포지션 사이징 방식: "equal"(동일비중) | "score"(점수 비례) | "score_capped"(점수 비례+상한)
SIZING_MODE  = "score_capped"
MAX_WEIGHT   = 0.20   # 단일 종목 최대 비중 (score_capped 모드)


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
                except Exception:
                    pass
        else:
            if len(raw) >= 60:
                result[tickers[0]] = raw
        return result
    except Exception:
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
    # ATR 계산
    atr = ta.atr(h, l, c, length=ATR_PERIOD)
    d["ATR"]     = atr if atr is not None else np.nan
    return d


# ── 스윙 HH-HL ───────────────────────────────────────────────
def count_hh_hl_swing(df_window, n=3):
    highs = df_window["High"].values
    lows  = df_window["Low"].values
    sh = [highs[i] for i in range(n, len(highs)-n)
          if highs[i] == max(highs[i-n:i+n+1])]
    sl = [lows[i]  for i in range(n, len(lows)-n)
          if lows[i]  == min(lows[i-n:i+n+1])]
    hh = sum(sh[i] > sh[i-1] for i in range(1, len(sh)))
    hl = sum(sl[i] > sl[i-1] for i in range(1, len(sl)))
    return min(hh, hl)


# ── ATR 기반 동적 스톱로스 계산 ──────────────────────────────
def calc_atr_stop(df) -> float:
    """
    최근 20일 고점 - ATR(14) × ATR_MULT
    변동성이 높은 종목은 스톱이 넓어지고,
    변동성이 낮은 종목은 스톱이 좁아집니다.
    """
    atr_val = df["ATR"].dropna().iloc[-1] if "ATR" in df.columns else np.nan
    if pd.isna(atr_val):
        return np.nan
    peak_20  = float(df["High"].tail(20).max())
    return round(peak_20 - atr_val * ATR_MULT, 2)


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

    if count_hh_hl_swing(r60) < 3:
        return False, {}

    high52 = row.get("High52w", np.nan)
    if not pd.isna(high52) and high52 > 0:
        if row["Close"] < high52 * 0.80:
            return False, {}

    ret3m    = float(df["Close"].iloc[-1] / r63["Close"].iloc[0]) - 1 \
               if len(r63) >= 60 else np.nan
    vol_cv   = r20["Volume"].std() / (vol60 + 1e-9)
    vol_stab = float(1 / (vol_cv + 1e-6))

    # ATR 기반 동적 스톱가
    stop_price = calc_atr_stop(df)

    # 현재가 대비 스톱 거리 (%)
    cur_price = float(df["Close"].iloc[-1])
    stop_dist = (stop_price - cur_price) / cur_price if not pd.isna(stop_price) else np.nan

    return True, {
        "ADX"       : float(adx),
        "RSI"       : float(rsi),
        "ret3m"     : ret3m,
        "vol_stab"  : vol_stab,
        "price"     : cur_price,
        "stop_price": stop_price,
        "stop_dist" : stop_dist,       # 음수: 현재가에서 스톱까지의 거리
        "high52w"   : float(high52) if not pd.isna(high52) else np.nan,
        "atr"       : float(df["ATR"].dropna().iloc[-1])
                      if "ATR" in df.columns else np.nan,
    }


# ── 복합점수 및 포지션 사이징 ────────────────────────────────
def minmax(s):
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)

def calc_position_weights(scores: pd.Series, mode: str, max_w: float) -> pd.Series:
    """
    equal      : 동일비중 (1/n)
    score      : 점수 비례 (score / sum)
    score_capped: 점수 비례 + 단일 종목 최대 비중 cap
    """
    n = len(scores)
    if mode == "equal" or n == 0:
        return pd.Series([1.0 / n] * n, index=scores.index)

    raw_w = scores / scores.sum()

    if mode == "score":
        return raw_w

    # score_capped: max_w 초과분을 나머지에 재배분 (반복)
    w = raw_w.copy()
    for _ in range(20):   # 최대 20회 반복으로 수렴
        capped  = w.clip(upper=max_w)
        excess  = w[w > max_w].sum() - max_w * (w > max_w).sum()
        if excess <= 1e-8:
            break
        under   = capped < max_w
        if under.sum() == 0:
            break
        capped[under] += excess * (capped[under] / capped[under].sum())
        w = capped

    return w / w.sum()   # 합산 = 1.0 정규화

def rank_stocks(passed, etf_data):
    df = pd.DataFrame(passed).T
    df["sector"] = [ALL_UNIVERSE.get(t, "Unknown") for t in df.index]

    # ETF 초과수익률 기준 섹터 강도
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
        minmax(df["ADX"])               * WEIGHTS["adx"]     +
        minmax(df["ret3m"].fillna(0))   * WEIGHTS["ret3m"]   +
        minmax(df["sec_str_norm"])      * WEIGHTS["sector"]  +
        minmax(df["vol_stab"])          * WEIGHTS["vol_stab"]
    )
    return df.sort_values("score", ascending=False)


# ── 시장 상태 ─────────────────────────────────────────────────
def check_market():
    try:
        spy   = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
        close = spy["Close"].squeeze()
        ma50  = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        price = float(close.iloc[-1])
        gap   = (ma50 - ma200) / ma200 * 100
        return {"price": price, "ma50": ma50, "ma200": ma200,
                "gap_pct": gap, "is_golden": ma50 > ma200}
    except Exception:
        return None


# ── 메인 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    print("=" * 64)
    print(f"  모멘텀 종목 스크리너 v3   기준일: {today}")
    print(f"  유니버스: 미국 {len(US_UNIVERSE)}개 + 국내 {len(KR_UNIVERSE)}개")
    print(f"  스톱로스: ATR({ATR_PERIOD}) × {ATR_MULT}  │  "
          f"포지션: {SIZING_MODE} (상한 {MAX_WEIGHT:.0%})")
    print("=" * 64)

    # 시장 상태
    print("\n[0/3] 시장 상태 확인...")
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

    # 다운로드
    print("\n[1/3] 데이터 다운로드 중...")
    us_data, kr_data, etf_data = {}, {}, {}
    for i in range(0, len(US_UNIVERSE), 30):
        us_data.update(download(list(US_UNIVERSE.keys())[i:i+30]))
    for i in range(0, len(KR_UNIVERSE), 30):
        kr_data.update(download(list(KR_UNIVERSE.keys())[i:i+30]))
    etf_raw = download(list(set(SECTOR_ETF.values())))
    for t, df in etf_raw.items():
        etf_data[t] = calc_indicators(df)

    all_data = {**us_data, **kr_data}
    print(f"  종목 {len(all_data)}개, ETF {len(etf_data)}개 수신 완료")

    # 지표 계산 + 스크리닝
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

    # 랭킹 + 포지션 사이징
    print("\n[3/3] 복합점수 계산 및 포지션 배분 중...")
    ranked = rank_stocks(passed, etf_data)
    top10  = ranked.head(TOP_N).copy()

    # 포지션 비중 계산
    weights = calc_position_weights(top10["score"], SIZING_MODE, MAX_WEIGHT)
    top10["weight"] = weights

    # 결과 출력
    print("\n" + "=" * 64)
    print(f"  ★ 복합점수 상위 {TOP_N}개  (v3 — ATR스톱 + 점수비례배분)")
    print("=" * 64)
    print(f"  {'순위'} {'종목':<13} {'비중':>6} {'점수':>6} "
          f"{'ADX':>5} {'RSI':>5} {'3M수익':>7} "
          f"{'스톱가':>9} {'스톱거리':>8}")
    print("  " + "─" * 66)

    for rank, (ticker, row) in enumerate(top10.iterrows(), 1):
        flag    = "🇺🇸" if not ticker.endswith(".KS") else "🇰🇷"
        ret_str = f"{row['ret3m']:+.1%}" if not pd.isna(row["ret3m"]) else " N/A"
        stop_s  = f"{row['stop_price']:>9,.2f}" \
                  if not pd.isna(row["stop_price"]) else "      N/A"
        dist_s  = f"{row['stop_dist']:>+.1%}" \
                  if not pd.isna(row["stop_dist"]) else "   N/A"
        print(
            f"  {rank:2d}위 {flag} {ticker:<11}"
            f" {row['weight']:>5.1%}"
            f" {row['score']:>6.3f}"
            f" {row['ADX']:>5.1f}"
            f" {row['RSI']:>5.1f}"
            f" {ret_str:>7}"
            f" {stop_s}"
            f" {dist_s}"
        )

    # 포지션 사이징 방식 비교 출력
    print(f"\n  [포지션 사이징 비교]")
    eq_w  = pd.Series([1/len(top10)] * len(top10), index=top10.index)
    sc_w  = calc_position_weights(top10["score"], "score", MAX_WEIGHT)
    cap_w = calc_position_weights(top10["score"], "score_capped", MAX_WEIGHT)

    print(f"  {'종목':<13} {'동일비중':>8} {'점수비례':>8} {'점수비례+상한':>12}")
    print("  " + "─" * 44)
    for t in top10.index:
        print(f"  {t:<13} {eq_w[t]:>8.1%} {sc_w[t]:>8.1%} {cap_w[t]:>12.1%}")
    print(f"  {'합계':<13} {eq_w.sum():>8.1%} {sc_w.sum():>8.1%} {cap_w.sum():>12.1%}")

    # CSV 저장
    save_cols = ["weight","score","ADX","RSI","ret3m",
                 "stop_price","stop_dist","atr","sector","price"]
    save_cols = [c for c in save_cols if c in top10.columns]
    out = top10[save_cols].copy()
    out.index.name = "종목코드"
    out.to_csv("screener_v3_result.csv", encoding="utf-8-sig")
    print(f"\n  결과 저장: screener_v3_result.csv")
