"""
모멘텀 주식 투자 백테스트 엔진
─────────────────────────────────────────────────────────
대상  : 미국 (S&P 500 유니버스) + 국내 (KOSPI 주요 종목)
전략  : 스크리닝 통과 종목 중 복합점수 상위 10개 동일비중 투자
리밸  : 매월 마지막 거래일
─────────────────────────────────────────────────────────
복합점수 = ADX×0.4 + 3M수익률×0.3 + 섹터강도×0.2 + 거래량안정성×0.1

스크리닝 조건
  ① ADX ≥ 25
  ② 이동평균 정배열 (20MA > 50MA > 200MA)
  ③ RSI 50 ~ 70
  ④ 최근 20일 내 거래량 60일평균 대비 3배 초과 없음
  ⑤ 최근 5일 내 단일 일봉 +10% 초과 없음
  ⑥ 최근 60일 내 HH-HL 패턴 3회 이상

의존 패키지 설치:
  pip install yfinance pandas-ta pandas numpy matplotlib
─────────────────────────────────────────────────────────
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
import pandas_ta as ta
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from datetime import datetime

# ═══════════════════════════════════════════════════════
# 0. 설정값
# ═══════════════════════════════════════════════════════
CONFIG = {
    "start_date" : "2019-01-01",
    "end_date"   : "2024-12-31",
    "top_n"      : 10,           # 포트폴리오 종목 수
    "weights"    : {             # 복합점수 가중치
        "adx"          : 0.4,
        "return_3m"    : 0.3,
        "sector_str"   : 0.2,
        "vol_stability": 0.1,
    },
    # 스크리닝 파라미터
    "adx_min"        : 25,
    "rsi_min"        : 50,
    "rsi_max"        : 70,
    "vol_spike_mult" : 3.0,      # 거래량 3배 초과 시 제외
    "daily_gain_max" : 0.10,     # 5일 내 단일 +10% 초과 시 제외
    "hh_hl_min"      : 3,        # HH-HL 최소 연속 횟수
    "min_history"    : 220,      # 지표 계산을 위한 최소 데이터 일수
}

# ═══════════════════════════════════════════════════════
# 1. 유니버스 정의
# ═══════════════════════════════════════════════════════
def get_us_tickers() -> list[str]:
    """S&P 500 구성 종목 파싱 (위키피디아)"""
    try:
        table = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        )[0]
        tickers = table["Symbol"].str.replace(".", "-", regex=False).tolist()
        print(f"  [US] S&P500 {len(tickers)}개 파싱 성공")
        return tickers
    except Exception as e:
        # 네트워크 오류 시 주요 종목 폴백
        fallback = [
            "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","JPM","V",
            "MA","UNH","XOM","JNJ","PG","HD","MRK","ABBV","CVX","BAC","KO","PEP",
            "COST","TMO","MCD","WMT","ABT","CSCO","CRM","ORCL","NFLX","AMD","QCOM",
            "TXN","HON","CAT","GE","LMT","RTX","DE","SBUX","INTU","NOW","ADBE",
            "ISRG","REGN","VRTX","GILD","AMGN","BMY","PFE","MU","AMAT","LRCX",
            "KLAC","MRVL","ON","PANW","CRWD","SNOW","PLTR","COIN","SQ",
        ]
        print(f"  [US] 위키 파싱 실패 → 주요 {len(fallback)}개 사용")
        return fallback


KOSPI_UNIVERSE = {
    # 반도체·IT
    "005930.KS": "Technology",   # 삼성전자
    "000660.KS": "Technology",   # SK하이닉스
    "009150.KS": "Technology",   # 삼성전기
    "066570.KS": "Technology",   # LG전자
    "006400.KS": "Technology",   # 삼성SDI
    "373220.KS": "Technology",   # LG에너지솔루션
    # 바이오·헬스
    "207940.KS": "Health Care",  # 삼성바이오로직스
    "068270.KS": "Health Care",  # 셀트리온
    "326030.KS": "Health Care",  # SK바이오팜
    "000100.KS": "Health Care",  # 유한양행
    # 자동차
    "005380.KS": "Consumer Discretionary",  # 현대차
    "000270.KS": "Consumer Discretionary",  # 기아
    "012330.KS": "Consumer Discretionary",  # 현대모비스
    # 화학·소재
    "051910.KS": "Materials",    # LG화학
    "247540.KS": "Materials",    # 에코프로비엠
    "086520.KS": "Materials",    # 에코프로
    # 인터넷·미디어
    "035420.KS": "Communication Services",  # NAVER
    "035720.KS": "Communication Services",  # 카카오
    "036570.KS": "Communication Services",  # 엔씨소프트
    "352820.KS": "Communication Services",  # 하이브
    # 에너지·산업재
    "010950.KS": "Energy",       # S-Oil
    "096770.KS": "Energy",       # SK이노베이션
    "011200.KS": "Industrials",  # HMM
    "047810.KS": "Industrials",  # 한국항공우주
    # 금융
    "105560.KS": "Financials",   # KB금융
    "055550.KS": "Financials",   # 신한지주
    "086790.KS": "Financials",   # 하나금융지주
    "138040.KS": "Financials",   # 메리츠금융지주
}


# ═══════════════════════════════════════════════════════
# 2. 데이터 다운로드
# ═══════════════════════════════════════════════════════
def download_ohlcv(tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    data = {}
    batch = 50
    min_rows = CONFIG["min_history"]

    for i in range(0, len(tickers), batch):
        chunk = tickers[i : i + batch]
        try:
            raw = yf.download(
                chunk, start=start, end=end,
                auto_adjust=True, progress=False, threads=True,
            )
            if raw.empty:
                continue

            if isinstance(raw.columns, pd.MultiIndex):
                for t in chunk:
                    try:
                        df = raw.xs(t, axis=1, level=1).dropna(how="all")
                        if len(df) >= min_rows:
                            data[t] = df
                    except KeyError:
                        pass
            else:
                t = chunk[0]
                if len(raw) >= min_rows:
                    data[t] = raw

        except Exception:
            pass

    return data


# ═══════════════════════════════════════════════════════
# 3. 기술적 지표 계산
# ═══════════════════════════════════════════════════════
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    close, high, low, vol = d["Close"], d["High"], d["Low"], d["Volume"]

    d["MA20"]   = ta.sma(close, length=20)
    d["MA50"]   = ta.sma(close, length=50)
    d["MA200"]  = ta.sma(close, length=200)
    d["RSI"]    = ta.rsi(close, length=14)

    adx_df = ta.adx(high, low, close, length=14)
    if adx_df is not None and "ADX_14" in adx_df.columns:
        d["ADX"] = adx_df["ADX_14"]
    else:
        d["ADX"] = np.nan

    d["VolMA20"] = vol.rolling(20).mean()
    d["VolMA60"] = vol.rolling(60).mean()

    return d


# ═══════════════════════════════════════════════════════
# 4. 스크리닝 (단일 종목, 특정 날짜 기준)
# ═══════════════════════════════════════════════════════
def screen(df: pd.DataFrame, as_of: pd.Timestamp) -> tuple[bool, dict]:
    hist = df[df.index <= as_of]
    if len(hist) < CONFIG["min_history"]:
        return False, {}

    row     = hist.iloc[-1]
    r5      = hist.tail(6)
    r20     = hist.tail(20)
    r60     = hist.tail(60)
    r63     = hist.tail(63)   # ~3개월

    # ① ADX ≥ 25
    adx = row.get("ADX", np.nan)
    if pd.isna(adx) or adx < CONFIG["adx_min"]:
        return False, {}

    # ② 이동평균 정배열
    ma20, ma50, ma200 = row.get("MA20"), row.get("MA50"), row.get("MA200")
    if any(pd.isna(v) for v in [ma20, ma50, ma200]):
        return False, {}
    if not (ma20 > ma50 > ma200):
        return False, {}

    # ③ RSI 50 ~ 70
    rsi = row.get("RSI", np.nan)
    if pd.isna(rsi) or not (CONFIG["rsi_min"] <= rsi <= CONFIG["rsi_max"]):
        return False, {}

    # ④ 거래량 급등 필터
    vol_ma60 = row.get("VolMA60", np.nan)
    if pd.isna(vol_ma60) or vol_ma60 == 0:
        return False, {}
    if (r20["Volume"] > vol_ma60 * CONFIG["vol_spike_mult"]).any():
        return False, {}

    # ⑤ 단기 급등 필터
    if (r5["Close"].pct_change() > CONFIG["daily_gain_max"]).any():
        return False, {}

    # ⑥ HH-HL 패턴
    highs, lows = r60["High"].values, r60["Low"].values
    hh_hl = sum(
        highs[i] > highs[i - 1] and lows[i] > lows[i - 1]
        for i in range(1, len(highs))
    )
    if hh_hl < CONFIG["hh_hl_min"]:
        return False, {}

    # ── 복합점수 원재료 ──
    ret_3m = (hist["Close"].iloc[-1] / r63["Close"].iloc[0]) - 1 if len(r63) >= 60 else np.nan
    vol_cv = r20["Volume"].std() / (vol_ma60 + 1e-9)   # 변동계수 (낮을수록 안정)
    vol_stab = 1 / (vol_cv + 1e-6)

    return True, {"ADX": adx, "Return3M": ret_3m, "VolStab": vol_stab}


# ═══════════════════════════════════════════════════════
# 5. 복합점수 계산 및 종목 선택
# ═══════════════════════════════════════════════════════
def minmax(s: pd.Series) -> pd.Series:
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)


def select_top(candidates: dict, sector_map: dict, top_n: int) -> pd.DataFrame:
    if not candidates:
        return pd.DataFrame()

    df = pd.DataFrame(candidates).T.copy()
    df["Sector"] = [sector_map.get(t, "Unknown") for t in df.index]

    # 섹터 상대 강도 (동일 섹터 내 3M 수익률 순위)
    df["SectorStr"] = 0.5
    for sec in df["Sector"].unique():
        mask = df["Sector"] == sec
        if mask.sum() > 1:
            df.loc[mask, "SectorStr"] = minmax(df.loc[mask, "Return3M"].fillna(0))

    w = CONFIG["weights"]
    df["Score"] = (
        minmax(df["ADX"])             * w["adx"]           +
        minmax(df["Return3M"].fillna(0)) * w["return_3m"]  +
        minmax(df["SectorStr"])       * w["sector_str"]    +
        minmax(df["VolStab"])         * w["vol_stability"]
    )

    return df.sort_values("Score", ascending=False).head(top_n)


# ═══════════════════════════════════════════════════════
# 6. 백테스트 루프
# ═══════════════════════════════════════════════════════
def run_backtest(all_data: dict, sector_map: dict) -> tuple[list, list]:
    rebal_dates = pd.date_range(
        start=CONFIG["start_date"], end=CONFIG["end_date"], freq="BME"
    )

    nav      = [1.0]      # Net Asset Value (정규화)
    log      = []
    holdings = {}         # {ticker: weight}
    prev_dt  = None

    for rd in rebal_dates:
        rd_ts = rd

        # ── 월수익 반영 ──
        if prev_dt and holdings:
            monthly_ret = 0.0
            for ticker, w in holdings.items():
                df_t = all_data.get(ticker)
                if df_t is None:
                    continue
                p0 = df_t[df_t.index <= prev_dt]["Close"]
                p1 = df_t[df_t.index <= rd_ts]["Close"]
                if len(p0) and len(p1) and p0.iloc[-1] > 0:
                    monthly_ret += w * ((p1.iloc[-1] / p0.iloc[-1]) - 1)
            nav.append(nav[-1] * (1 + monthly_ret))

        # ── 스크리닝 ──
        passed = {}
        for ticker, df_t in all_data.items():
            ok, metrics = screen(df_t, rd_ts)
            if ok:
                passed[ticker] = metrics

        # ── 종목 선택 ──
        selected_df = select_top(passed, sector_map, CONFIG["top_n"])
        n = len(selected_df)
        holdings = {t: 1.0 / n for t in selected_df.index} if n > 0 else {}

        print(
            f"  {rd.date()}  통과 {len(passed):3d}개 → "
            f"선택 {n}개: {list(selected_df.index[:4])}{'...' if n > 4 else ''}"
        )

        log.append({
            "date"      : rd.date(),
            "n_pass"    : len(passed),
            "selected"  : list(selected_df.index),
            "scores"    : selected_df["Score"].round(4).to_dict() if n > 0 else {},
            "nav"       : nav[-1],
        })

        prev_dt = rd_ts

    return nav, log


# ═══════════════════════════════════════════════════════
# 7. 벤치마크 (SPY)
# ═══════════════════════════════════════════════════════
def get_benchmark_nav(n_periods: int) -> np.ndarray:
    spy = yf.download(
        "SPY", start=CONFIG["start_date"], end=CONFIG["end_date"],
        auto_adjust=True, progress=False,
    )
    monthly = spy["Close"].resample("BME").last().pct_change().fillna(0)
    cumret  = (1 + monthly).cumprod().values
    # 기간 맞춤
    if len(cumret) >= n_periods:
        out = np.concatenate([[1.0], cumret[:n_periods]])
    else:
        out = np.concatenate([[1.0], cumret, [cumret[-1]] * (n_periods - len(cumret))])
    return out


# ═══════════════════════════════════════════════════════
# 8. 성과 지표
# ═══════════════════════════════════════════════════════
def calc_metrics(nav_list: list, label: str) -> dict:
    s   = pd.Series(nav_list, dtype=float)
    ret = s.pct_change().dropna()
    n   = len(ret)

    total  = s.iloc[-1] - 1
    cagr   = (s.iloc[-1] ** (12 / max(n, 1))) - 1
    mdd    = ((s - s.cummax()) / s.cummax()).min()
    sharpe = (ret.mean() / (ret.std() + 1e-9)) * np.sqrt(12)
    win    = (ret > 0).mean()

    return {
        "label"       : label,
        "총수익률"    : total,
        "CAGR"        : cagr,
        "MDD"         : mdd,
        "샤프"        : sharpe,
        "월승률"      : win,
        "운용월수"    : n,
    }


def print_metrics(m: dict):
    print(f"\n  ┌── {m['label']} ──────────────────────────")
    print(f"  │  총 수익률   : {m['총수익률']:+.1%}")
    print(f"  │  CAGR        : {m['CAGR']:+.1%}")
    print(f"  │  MDD         : {m['MDD']:.1%}")
    print(f"  │  샤프 지수   : {m['샤프']:.2f}")
    print(f"  │  월간 승률   : {m['월승률']:.1%}  ({m['운용월수']}개월)")
    print(f"  └────────────────────────────────────────")


# ═══════════════════════════════════════════════════════
# 9. 차트 출력
# ═══════════════════════════════════════════════════════
def plot_results(nav_strat: list, nav_bench: np.ndarray, log: list):
    dates = [pd.Timestamp(CONFIG["start_date"])] + [
        pd.Timestamp(entry["date"]) for entry in log
    ]

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), gridspec_kw={"height_ratios": [3, 1, 1]})
    fig.suptitle("모멘텀 주식 백테스트 결과 (2019–2024)", fontsize=14, fontweight="bold")

    # ── (1) NAV 곡선 ──
    ax1 = axes[0]
    ax1.plot(dates[:len(nav_strat)], nav_strat, label="전략 (상위 10 모멘텀)", color="#2E75B6", lw=2)
    ax1.plot(dates[:len(nav_bench)], nav_bench, label="S&P 500 (SPY)", color="#ED7D31", lw=1.5, ls="--")
    ax1.set_ylabel("누적 자산 (배)")
    ax1.yaxis.set_major_formatter(mtick.FormatStrFormatter("%.1fx"))
    ax1.legend()
    ax1.grid(alpha=0.3)

    # ── (2) 드로우다운 ──
    ax2 = axes[1]
    s = pd.Series(nav_strat)
    dd = (s - s.cummax()) / s.cummax()
    ax2.fill_between(dates[:len(dd)], dd * 100, 0, color="#C00000", alpha=0.5)
    ax2.set_ylabel("드로우다운 (%)")
    ax2.grid(alpha=0.3)

    # ── (3) 스크리닝 통과 종목 수 ──
    ax3 = axes[2]
    n_pass = [e["n_pass"] for e in log]
    log_dates = [pd.Timestamp(e["date"]) for e in log]
    ax3.bar(log_dates, n_pass, color="#70AD47", alpha=0.7, width=20)
    ax3.set_ylabel("스크리닝 통과 수")
    ax3.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig("backtest_result.png", dpi=150, bbox_inches="tight")
    print("\n  차트 저장: backtest_result.png")
    plt.show()


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":

    print("=" * 56)
    print("  모멘텀 주식 투자 백테스트")
    print(f"  기간: {CONFIG['start_date']} ~ {CONFIG['end_date']}")
    print(f"  리밸런싱: 매월 말 | 보유 종목: {CONFIG['top_n']}개")
    print(f"  복합점수: ADX×0.4 + 3M수익률×0.3 + 섹터강도×0.2 + 거래량안정성×0.1")
    print("=" * 56)

    # ── 1. 유니버스 ──
    print("\n[1/5] 유니버스 구성")
    us_tickers = get_us_tickers()
    kr_tickers = list(KOSPI_UNIVERSE.keys())
    all_tickers = us_tickers + kr_tickers

    # 섹터 맵
    sector_map = {}
    # US 섹터: 위키에서 가져오기 시도
    try:
        tbl = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        for _, row in tbl.iterrows():
            t = row["Symbol"].replace(".", "-")
            sector_map[t] = row["GICS Sector"]
    except Exception:
        pass
    # KR 섹터 추가
    sector_map.update(KOSPI_UNIVERSE)

    # ── 2. 데이터 다운로드 ──
    print(f"\n[2/5] 데이터 다운로드 ({len(all_tickers)}개 종목)")
    print("  미국 종목 다운로드 중...")
    us_data = download_ohlcv(us_tickers, CONFIG["start_date"], CONFIG["end_date"])
    print(f"  → {len(us_data)}개 완료")

    print("  국내 종목 다운로드 중...")
    kr_data = download_ohlcv(kr_tickers, CONFIG["start_date"], CONFIG["end_date"])
    print(f"  → {len(kr_data)}개 완료")

    all_data = {**us_data, **kr_data}
    print(f"  총 {len(all_data)}개 종목 사용")

    # ── 3. 지표 계산 ──
    print(f"\n[3/5] 기술적 지표 계산 ({len(all_data)}개)")
    for i, (t, df) in enumerate(all_data.items()):
        all_data[t] = add_indicators(df)
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(all_data)} 완료")
    print("  지표 계산 완료")

    # ── 4. 백테스트 ──
    print("\n[4/5] 백테스트 실행 (매월 리밸런싱)")
    nav_strat, log = run_backtest(all_data, sector_map)

    # 벤치마크
    print("\n  벤치마크(SPY) 데이터 로딩...")
    nav_bench = get_benchmark_nav(len(nav_strat) - 1)

    # ── 5. 결과 출력 ──
    print("\n[5/5] 성과 분석")
    m_strat = calc_metrics(nav_strat, "전략 (상위 10 모멘텀)")
    m_bench = calc_metrics(nav_bench.tolist(), "벤치마크 S&P500 (SPY)")

    print_metrics(m_strat)
    print_metrics(m_bench)

    # 초과 수익
    excess = m_strat["CAGR"] - m_bench["CAGR"]
    print(f"\n  전략 초과수익(CAGR 기준): {excess:+.1%}")

    # ── 리밸런싱 로그 저장 ──
    pd.DataFrame([
        {
            "날짜"        : e["date"],
            "통과종목수"  : e["n_pass"],
            "선택종목"    : ", ".join(e["selected"]),
            "NAV"         : round(e["nav"], 4),
        }
        for e in log
    ]).to_csv("rebalance_log.csv", index=False, encoding="utf-8-sig")
    print("\n  리밸런싱 로그 저장: rebalance_log.csv")

    # ── 최근 6회 리밸런싱 ──
    print("\n  [최근 6회 리밸런싱]")
    for e in log[-6:]:
        names = e["selected"][:4]
        tail  = "..." if len(e["selected"]) > 4 else ""
        print(f"  {e['date']}  통과 {e['n_pass']:3d}개 │ {', '.join(names)}{tail}")

    # ── 차트 ──
    plot_results(nav_strat, nav_bench, log)
