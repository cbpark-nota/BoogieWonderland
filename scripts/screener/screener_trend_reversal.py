"""
추세 전환 스크리너 — 일봉 5MA / 120MA 골든크로스 (최근 발생 종목)
══════════════════════════════════════════════════════════════
백테스트(`backtest_5w_120w_cross.py`)와 동일한 MA/ATR 정의를 사용하되,
스크리너는 "현재 유지 중"이 아니라 **최근 10영업일 내에 신규 돌파한 종목**만 노출.

  - MA_SHORT  = 25일  (5주 × 5거래일)
  - MA_LONG   = 600일 (120주 × 5거래일)
  - 후보 조건: 최근 CROSS_LOOKBACK(=10) 영업일 내에
                MA25 ≤ MA600 → MA25 > MA600 으로 전환된 시점이 존재 ∧
                오늘 시점 MA25 > MA600 유지
  - 데이터 길이: MA_LONG + ATR_PERIOD + 5 = 619 행 이상 (백테스트와 동일)
  - 스코어   : MA gap ratio = (MA25 - MA600) / MA600
  - 정렬 기본: cross_days_ago 오름차순 (가장 최근 돌파부터)
  - Top N    : 시장별 25개
  - 스톱가  : 진입일(=오늘) High - ATR(14) × 2.5
              ↳ 백테스트 진입 시점의 peak = 진입일 단일 High와 동일

유니버스 분리 (백테스트와 동일 — `is_kr` 접미사 기반):
  - US  : `.KS`/`.KQ` 가 아닌 모든 캐시 종목 (≈ S&P500 + NASDAQ100)
  - KR  : `.KS`/`.KQ` 종목 (≈ KOSPI200 + KOSDAQ150)
  - ALL : US + KR 통합 (백테스트 [3-3] 통합 시나리오 — 최우수 성과)

데이터 소스:
  - 1순위: 데이터 캐시 manifest (`data/full_universe/`) — 백테스트와 동일
  - 2순위: yfinance 다운로드 — 캐시가 부족할 때 폴백

출력: trend_reversal_us.json, trend_reversal_kr.json, trend_reversal_all.json
══════════════════════════════════════════════════════════════
"""
import argparse
import json
import logging
import sys
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*yfinance.*")

import numpy as np
import pandas as pd
import pandas_ta as ta
import yfinance as yf

logger = logging.getLogger(__name__)

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent))

from data_cache import (  # noqa: E402
    fetch_sp500_tickers,
    fetch_nasdaq100_tickers,
    fetch_kr_tickers,
    CACHE_DIR,
)

# ── 백테스트와 동일한 파라미터 ───────────────────────────────
MA_SHORT     = 25      # 5주 × 5거래일
MA_LONG      = 600     # 120주 × 5거래일
ATR_PERIOD   = 14
ATR_MULT     = 2.5
TOP_N        = 25
MIN_ROWS     = MA_LONG + ATR_PERIOD + 5     # 백테스트 [C]와 동일 (619)
DOWNLOAD_DAYS = 800                          # MA600 워밍업 + 버퍼

# ── 스크리너 전용: 최근 돌파 윈도우 ──────────────────────────
CROSS_LOOKBACK = 10    # 영업일 10일 ≒ 최근 2주


# ── 시장 분류 (백테스트와 동일) ──────────────────────────────

def is_kr(ticker: str) -> bool:
    return ticker.endswith(".KS") or ticker.endswith(".KQ")


# ── 지표 계산 ────────────────────────────────────────────────

def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c = d["Close"].squeeze()
    h = d["High"].squeeze()
    l = d["Low"].squeeze()

    d["MA_S"] = c.rolling(MA_SHORT, min_periods=MA_SHORT).mean()
    d["MA_L"] = c.rolling(MA_LONG, min_periods=MA_LONG).mean()
    atr = ta.atr(h, l, c, length=ATR_PERIOD)
    d["ATR"] = atr if atr is not None else np.nan
    return d


# ── 데이터 로드 ──────────────────────────────────────────────

def _load_cache_all() -> dict:
    """캐시 manifest의 모든 종목을 로드 (백테스트 `load_cache_direct`와 동일).
    worktree 환경에서는 main 레포 캐시 경로도 탐색."""
    candidate_dirs = [
        CACHE_DIR,
        _THIS_DIR.parents[3] / "data" / "full_universe",
        _THIS_DIR.parents[4] / "data" / "full_universe",  # worktree 상위
    ]
    actual_dir = next(
        (d for d in candidate_dirs if (d / "manifest.json").exists()),
        None,
    )
    if actual_dir is None:
        return {}
    try:
        with open(actual_dir / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception:
        return {}

    out: dict[str, pd.DataFrame] = {}
    for ticker, fname in manifest.get("stocks", {}).items():
        path = actual_dir / fname
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
            if len(df) >= MIN_ROWS:
                out[ticker] = df
        except Exception:
            pass
    logger.info("  캐시 로드: %d종목 (디렉토리=%s)", len(out), actual_dir)
    return out


def _download_market(tickers: list[str], label: str) -> dict:
    """yfinance 배치 다운로드 (캐시 부족 시 폴백)."""
    if not tickers:
        return {}
    out: dict[str, pd.DataFrame] = {}
    end = datetime.today()
    start = end - pd.Timedelta(days=DOWNLOAD_DAYS * 1.5)
    for i in range(0, len(tickers), 50):
        batch = tickers[i:i + 50]
        try:
            raw = yf.download(
                batch,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                for t in batch:
                    try:
                        df = raw.xs(t, axis=1, level=1).dropna(how="all")
                        if len(df) >= MIN_ROWS:
                            out[t] = df
                    except Exception:
                        pass
            elif len(batch) == 1:
                if len(raw) >= MIN_ROWS:
                    out[batch[0]] = raw
        except Exception as e:
            logger.warning("  %s 배치 다운로드 실패 (offset=%d): %s", label, i, e)
    logger.info("  %s 데이터 확보: %d/%d종목", label, len(out), len(tickers))
    return out


# ── 스크리닝 (최근 CROSS_LOOKBACK 영업일 내 신규 골든크로스) ─

def _find_recent_cross(d: pd.DataFrame, lookback: int) -> tuple | None:
    """최근 lookback 영업일 내에 MA25 ≤ MA600 → MA25 > MA600 전환이
    발생한 가장 최근 일자(=cross_date)를 반환.

    백테스트 [C]가 매 리밸런싱 시점에 `MA_S > MA_L` 만 검사하는 것과 동일한
    비교 연산자(≤ vs >)를 사용해 정의:
        cross_at(t) := MA_S(t-1) ≤ MA_L(t-1) AND MA_S(t) > MA_L(t)

    Returns
    -------
    (cross_date: pd.Timestamp, cross_days_ago: int) 또는 None
        cross_days_ago는 최신 영업일 인덱스 기준 0(오늘)부터의 거리.
    """
    n = len(d)
    if n < 2:
        return None
    ma_s = d["MA_S"].to_numpy()
    ma_l = d["MA_L"].to_numpy()
    # 마지막 lookback+1 구간만 검사 (i, i-1 비교를 위해 +1)
    start = max(1, n - lookback)
    # 최근부터 거꾸로 스캔하여 가장 마지막 전환 시점 찾기
    for i in range(n - 1, start - 1, -1):
        s_now, l_now = ma_s[i], ma_l[i]
        s_prev, l_prev = ma_s[i - 1], ma_l[i - 1]
        if (
            not (pd.isna(s_now) or pd.isna(l_now) or pd.isna(s_prev) or pd.isna(l_prev))
            and s_prev <= l_prev
            and s_now > l_now
        ):
            return d.index[i], (n - 1 - i)
    return None


def _screen(all_data: dict, market_label: str) -> list[dict]:
    """최근 CROSS_LOOKBACK 영업일 내 신규 골든크로스 발생 종목 →
    cross_days_ago 오름차순(=가장 최근 돌파부터) Top N.

    market_label: 결과 row의 'market' 필드 — 'US' | 'KR' | 'ALL'
    각 종목의 시장은 ticker 접미사로 별도 판정 (ALL 시 혼합).
    """
    rows: list[dict] = []
    for ticker, df in all_data.items():
        if len(df) < MIN_ROWS:
            continue
        d = _add_indicators(df)
        last = d.iloc[-1]
        ma_s = last.get("MA_S", np.nan)
        ma_l = last.get("MA_L", np.nan)
        atr_v = last.get("ATR", np.nan)
        close = last.get("Close", np.nan)
        high = last.get("High", np.nan)

        if pd.isna(ma_s) or pd.isna(ma_l) or ma_l <= 0:
            continue
        # 현재 시점에서 다시 깨졌으면 후보 제외
        if ma_s <= ma_l:
            continue
        if pd.isna(close) or pd.isna(high):
            continue

        # 최근 윈도우 내 신규 돌파 시점 검사
        cross = _find_recent_cross(d, CROSS_LOOKBACK)
        if cross is None:
            continue
        cross_dt, cross_days_ago = cross

        gap = float((ma_s - ma_l) / ma_l)

        # 백테스트 [F] 진입 스톱가와 동일 — peak = 진입일(오늘) High
        if pd.isna(atr_v) or atr_v <= 0:
            stop_price = None
            stop_dist = None
        else:
            stop_price = round(float(high) - float(atr_v) * ATR_MULT, 2)
            stop_dist = round((stop_price - float(close)) / float(close), 4)

        # row의 market 필드는 ticker 접미사 기준 (US/KR 정확 표시)
        row_market = "KR" if is_kr(ticker) else "US"
        rows.append({
            "ticker": ticker,
            "market": row_market,
            "score": round(gap, 4),
            "ma_short": round(float(ma_s), 4),
            "ma_long": round(float(ma_l), 4),
            "price": round(float(close), 2),
            "stop_price": stop_price,
            "stop_dist_pct": stop_dist,
            "atr": round(float(atr_v), 4) if not pd.isna(atr_v) else None,
            "cross_date": pd.Timestamp(cross_dt).strftime("%Y-%m-%d"),
            "cross_days_ago": int(cross_days_ago),
        })

    # 정렬: cross_days_ago 오름차순 → 동률 시 gap 내림차순
    rows.sort(key=lambda r: (r["cross_days_ago"], -r["score"]))
    top = rows[:TOP_N]
    for i, r in enumerate(top, 1):
        r["rank"] = i
        r["weight_pct"] = round(100.0 / max(len(top), 1), 2)
        r["sector"] = ""
    return top


# ── 메인 ──────────────────────────────────────────────────────

def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    run_dt = now.strftime("%Y-%m-%dT%H:%M:%S")
    run_id = int(now.strftime("%Y%m%d"))

    # ── [1] 캐시 로드 (백테스트와 동일 경로 탐색) ────────────
    cache_data = _load_cache_all()
    us_cache = {t: df for t, df in cache_data.items() if not is_kr(t)}
    kr_cache = {t: df for t, df in cache_data.items() if is_kr(t)}

    # ── [2] 캐시 부족 시 yfinance 폴백 ───────────────────────
    if len(us_cache) < 100:
        sp500_tickers, _ = fetch_sp500_tickers()
        ndx_tickers, _ = fetch_nasdaq100_tickers()
        sp500_set = set(sp500_tickers)
        us_tickers = sp500_tickers + [t for t in ndx_tickers if t not in sp500_set]
        us_data = _download_market(us_tickers, "US")
    else:
        us_data = us_cache

    if len(kr_cache) < 100:
        kr_tickers = fetch_kr_tickers(kospi_n=200, kosdaq_n=150)
        kr_data = _download_market(kr_tickers, "KR")
    else:
        kr_data = kr_cache

    all_data = {**us_data, **kr_data}

    # ── [3] 시장별 스크리닝 ──────────────────────────────────
    payloads = {}
    for key, label, data in [
        ("us", "US", us_data),
        ("kr", "KR", kr_data),
        ("all", "ALL", all_data),
    ]:
        results = _screen(data, label)
        payload = {
            "run_id": run_id,
            "run_date": run_dt,
            "market": label,
            "total_screened": len(data),
            "total_passed": len(results),
            "results": results,
        }
        (output_dir / f"trend_reversal_{key}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        payloads[key] = payload
        logger.info("%s 추세전환 후보: %d종목 (스크리닝 %d)",
                    label, len(results), len(data))

    return payloads


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="추세 전환(5MA/120MA) 스크리너")
    parser.add_argument(
        "--output",
        type=str,
        default="frontend/web/data/",
        help="JSON 출력 디렉토리",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(message)s",
    )
    run(Path(args.output))
