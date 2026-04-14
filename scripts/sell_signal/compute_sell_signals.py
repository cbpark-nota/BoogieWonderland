"""
매도 신호 계산 (서버리스 배포용)
────────────────────────────────────────────────────────────
모멘텀 스크리닝 Top N에 최근 30일 내 1회 이상 노출된 종목을 추적하여
v3.3 트레일링 스톱 방식으로 매도 신호를 계산한다.

알고리즘:
  1. history/ JSON에서 최근 30일간 각 전략 결과에 등장한 종목 수집
  2. 종목별 가상 진입일(최초 노출일) 기준 ATR(14)×2.5 트레일링 스톱 계산
     - peak = max(그동안 일간 고가)
     - stop = peak - ATR(14) × 2.5  (스톱가는 하락 불가)
  3. 매도 조건: 현재가 ≤ stop_price  OR  aggressive 전략에서 이탈 (rank_out)
  4. 매도 신호 발생 후 영업일 3일만 표시; 재발생 시 타이머 리셋

출력: frontend/web/data/sell_signals.json

참고:
  current_rank 판정은 최신 screening_strategies.json의 aggressive 결과(top_n=15)를
  사용한다. aggressive top 15에 없으면 "rank_out"으로 처리한다.
"""
import json
import logging
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

import numpy as np
import pandas as pd
import yfinance as yf

# ── 상수 ──────────────────────────────────────────────────────
ATR_PERIOD = 14
ATR_MULT = 2.5
LOOK_BACK_DAYS = 30        # 히스토리 탐색 기간 (달력 기준)
DISPLAY_BDAYS = 3          # 매도 신호 발생 후 표시 기간 (영업일)
HISTORY_FETCH_DAYS = 45    # ATR 계산 여유 기간 (달력 기준)

ROOT = Path(__file__).parent.parent.parent
HISTORY_DIR = ROOT / "frontend/web/data/history"
STRATEGIES_FILE = ROOT / "frontend/web/data/screening_strategies.json"
OUTPUT_FILE = ROOT / "frontend/web/data/sell_signals.json"


# ── 날짜 유틸 ────────────────────────────────────────────────

def _is_bday(dt: datetime) -> bool:
    return dt.weekday() < 5


def _bdays_since(date_str: str) -> int:
    """date_str(YYYY-MM-DD)부터 오늘까지 경과 영업일 수 (당일 = 1)."""
    start = datetime.strptime(date_str, "%Y-%m-%d")
    today = datetime.now()
    count = 0
    cur = start
    while cur.date() <= today.date():
        if _is_bday(cur):
            count += 1
        cur += timedelta(days=1)
    return count


# ── 히스토리 로드 ─────────────────────────────────────────────

def load_candidate_tickers(look_back_days: int) -> dict[str, str]:
    """
    최근 look_back_days 동안 history JSON에서 등장한 종목 수집.

    반환: {ticker: first_entry_date_str}
      - first_entry_date_str = 가장 오래된(처음) 노출일 (YYYY-MM-DD)
    """
    today = datetime.now()
    cutoff = today - timedelta(days=look_back_days)
    ticker_first: dict[str, str] = {}

    if not HISTORY_DIR.exists():
        return ticker_first

    index_path = HISTORY_DIR / "index.json"
    if index_path.exists():
        try:
            with open(index_path) as f:
                idx = json.load(f)
            dates = idx.get("dates", [])
        except Exception:
            dates = []
    else:
        dates = sorted(
            [p.stem for p in HISTORY_DIR.glob("*.json") if p.stem != "index"],
            reverse=True,
        )

    for date_str in dates:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if dt < cutoff:
            continue

        json_path = HISTORY_DIR / f"{date_str}.json"
        if not json_path.exists():
            continue

        try:
            with open(json_path) as f:
                data = json.load(f)
        except Exception:
            continue

        strategies = data.get("strategies", {})
        for strat_key in ("aggressive", "balanced", "conservative", "adaptive"):
            for item in strategies.get(strat_key, {}).get("results", []):
                t = item.get("ticker")
                if not t:
                    continue
                # 더 오래된 날짜(작은 날짜 문자열)로 업데이트
                if t not in ticker_first or date_str < ticker_first[t]:
                    ticker_first[t] = date_str

    return ticker_first


# ── 현재 순위 로드 ────────────────────────────────────────────

def load_current_ranks() -> dict[str, int]:
    """
    최신 screening_strategies.json에서 ticker → rank 매핑 반환.
    aggressive 전략 기준 (top_n=15). 없으면 빈 딕셔너리.
    """
    if not STRATEGIES_FILE.exists():
        return {}
    try:
        with open(STRATEGIES_FILE) as f:
            data = json.load(f)
    except Exception:
        return {}

    strategies = data.get("strategies", {})
    ranks: dict[str, int] = {}
    # aggressive 우선, 나머지로 보완 (겹치면 aggressive 값 유지)
    for strat_key in ("aggressive", "balanced", "conservative", "adaptive"):
        for item in strategies.get(strat_key, {}).get("results", []):
            t = item.get("ticker")
            r = item.get("rank")
            if t and r is not None and t not in ranks:
                ranks[t] = int(r)
    return ranks


# ── 이전 신호 로드 ────────────────────────────────────────────

def load_previous_signals(output_path: Path) -> dict[str, dict]:
    """이전 sell_signals.json에서 활성 신호 로드 → {ticker: signal_dict}."""
    if not output_path.exists():
        return {}
    try:
        with open(output_path) as f:
            data = json.load(f)
        return {s["ticker"]: s for s in data.get("signals", [])}
    except Exception:
        return {}


# ── ATR 트레일링 스톱 계산 ────────────────────────────────────

def calc_trailing_stop(ticker: str, entry_date_str: str) -> dict | None:
    """
    entry_date_str 이후 데이터로 v3.3 트레일링 스톱 계산.

    반환:
      {current_price, stop_price, peak_price}  또는  None (데이터 부족)
    """
    try:
        entry_dt = datetime.strptime(entry_date_str, "%Y-%m-%d")
    except ValueError:
        return None

    fetch_start = entry_dt - timedelta(days=HISTORY_FETCH_DAYS)
    fetch_end = datetime.now() + timedelta(days=1)

    try:
        df = yf.download(
            ticker,
            start=fetch_start.strftime("%Y-%m-%d"),
            end=fetch_end.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )
    except Exception:
        return None

    if df is None or len(df) < ATR_PERIOD + 1:
        return None

    # MultiIndex 처리 (단일 ticker여도 생길 수 있음)
    if isinstance(df.columns, pd.MultiIndex):
        try:
            df = df.xs(ticker, axis=1, level=1)
        except Exception:
            df = df.droplevel(1, axis=1)

    high = df["High"].squeeze()
    low = df["Low"].squeeze()
    close = df["Close"].squeeze()

    # ATR 계산 (EWM 방식)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=ATR_PERIOD, adjust=False).mean()

    # entry_date 이후만 사용
    entry_ts = pd.Timestamp(entry_date_str)
    mask = df.index >= entry_ts
    if mask.sum() == 0:
        return None

    highs_after = high[mask].values
    atr_after = atr[mask].values
    current_price = float(close.iloc[-1])

    # 트레일링 스톱: peak 추적, stop은 하락 불가
    peak = float(highs_after[0])
    stop = peak - float(atr_after[0]) * ATR_MULT
    for i in range(1, len(highs_after)):
        new_peak = max(peak, float(highs_after[i]))
        new_stop = new_peak - float(atr_after[i]) * ATR_MULT
        stop = max(stop, new_stop)
        peak = new_peak

    return {
        "current_price": round(current_price, 4),
        "stop_price": round(stop, 4),
        "peak_price": round(peak, 4),
    }


# ── 메인 ────────────────────────────────────────────────────

def compute_sell_signals(output_path: Path = OUTPUT_FILE) -> None:
    today_str = datetime.now().strftime("%Y-%m-%d")

    candidates = load_candidate_tickers(LOOK_BACK_DAYS)
    if not candidates:
        _write(output_path, today_str, [])
        return

    current_ranks = load_current_ranks()
    prev_signals = load_previous_signals(output_path)
    # TOP_N 기준: aggressive top_n=15를 proxy로 사용
    # aggressive에 없으면 rank > 15 (> 25 대용)
    RANK_THRESHOLD = 25

    signals = []
    for ticker, entry_date_str in candidates.items():
        price_data = calc_trailing_stop(ticker, entry_date_str)
        if price_data is None:
            continue

        current_price = price_data["current_price"]
        stop_price = price_data["stop_price"]
        peak_price = price_data["peak_price"]
        current_rank = current_ranks.get(ticker, RANK_THRESHOLD + 1)

        sell_reasons = []
        if current_price <= stop_price:
            sell_reasons.append("stop_loss")
        if current_rank > RANK_THRESHOLD:
            sell_reasons.append("rank_out")

        if not sell_reasons:
            continue

        # sell_triggered_date: 이전 신호가 같은 ticker로 이미 활성화되어 있으면 유지
        prev = prev_signals.get(ticker)
        if prev and prev.get("sell_reasons"):
            sell_triggered_date = prev["sell_triggered_date"]
        else:
            sell_triggered_date = today_str

        days_elapsed = _bdays_since(sell_triggered_date)
        days_remaining = DISPLAY_BDAYS + 1 - days_elapsed
        if days_remaining <= 0:
            continue

        signals.append({
            "ticker": ticker,
            "current_price": current_price,
            "stop_price": stop_price,
            "peak_price": peak_price,
            "rank": current_rank,
            "entry_date": entry_date_str,
            "sell_triggered_date": sell_triggered_date,
            "sell_reasons": sell_reasons,
            "days_remaining": days_remaining,
        })

    _write(output_path, today_str, signals)


def _write(output_path: Path, updated_at: str, signals: list) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"updated_at": updated_at, "signals": signals}, f,
                  ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="매도 신호 계산")
    parser.add_argument("--output", default=str(OUTPUT_FILE),
                        help="출력 JSON 경로")
    args = parser.parse_args()
    compute_sell_signals(Path(args.output))
