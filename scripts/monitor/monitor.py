"""
보유 종목 스톱로스 모니터링 — v3.3 트레일링 스톱
══════════════════════════════════════════════════════════
v3.3 변경사항:
  - 트레일링 스톱: 보유 중 고점(High) 갱신 시 스톱가도 상향
    stop_price = max(기존 stop_price, new_peak - ATR×2.5)
  - holdings.json에 stop_price, peak_price 필드 영속화
  - 고점 갱신 기준: 종가(Close) → 당일 고가(High)

실행 방법:
    python monitor.py

보유 종목 관리:
    holdings.json 파일을 직접 편집하거나
    python monitor.py --add NVDA 130.50   (매수가 입력)
    python monitor.py --remove NVDA       (종목 제거)
    python monitor.py --list              (보유 목록 출력)
══════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
import pandas_ta as ta

# ── 설정 ──────────────────────────────────────────────────────
HOLDINGS_FILE = "holdings.json"
ATR_PERIOD    = 14
ATR_MULT      = 2.5      # 스톱 = peak - ATR × 2.5
WARN_BUFFER   = 0.05     # 스톱가 5% 이내 접근 시 경고


# ══════════════════════════════════════════════════════════════
# 보유 종목 파일 관리
# ══════════════════════════════════════════════════════════════
def load_holdings() -> dict:
    """
    holdings.json 구조 (v3.3):
    {
      "NVDA": {
        "entry_price": 130.50,
        "entry_date": "2025-01-15",
        "peak_price": 145.20,    ← 보유 중 최고 고가 (High 기준)
        "stop_price": 138.50     ← 트레일링 스톱가 (오르기만 함)
      }
    }
    """
    p = Path(HOLDINGS_FILE)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save_holdings(holdings: dict):
    with open(HOLDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(holdings, f, ensure_ascii=False, indent=2)

def add_holding(ticker: str, entry_price: float):
    holdings = load_holdings()
    t = ticker.upper()
    holdings[t] = {
        "entry_price": entry_price,
        "entry_date" : datetime.now().strftime("%Y-%m-%d"),
        "peak_price" : entry_price,
        "stop_price" : None,   # 최초 실행 시 ATR로 계산
    }
    save_holdings(holdings)
    print(f"  ✅ {t} 추가 (매수가: {entry_price:,.2f})")

def remove_holding(ticker: str):
    holdings = load_holdings()
    t = ticker.upper()
    if t in holdings:
        del holdings[t]
        save_holdings(holdings)
        print(f"  🗑  {t} 제거 완료")
    else:
        print(f"  ⚠️  {t}은 보유 목록에 없습니다", file=sys.stderr)

def list_holdings():
    holdings = load_holdings()
    if not holdings:
        print("  보유 종목 없음")
        return
    print(f"\n  {'종목':<14} {'매수가':>10} {'매수일':>12} {'고점':>12} {'스톱가':>12}")
    print("  " + "─" * 62)
    for t, info in holdings.items():
        stop_str = f"{info['stop_price']:>12,.2f}" if info.get('stop_price') else f"{'(미계산)':>12}"
        print(f"  {t:<14} {info['entry_price']:>10,.2f} "
              f"{info['entry_date']:>12} {info['peak_price']:>12,.2f} {stop_str}")


# ══════════════════════════════════════════════════════════════
# ATR 계산
# ══════════════════════════════════════════════════════════════
def calc_atr(df: pd.DataFrame) -> float:
    """현재 ATR(14) 값 반환."""
    h = df["High"].squeeze()
    l = df["Low"].squeeze()
    c = df["Close"].squeeze()
    atr_series = ta.atr(h, l, c, length=ATR_PERIOD)
    if atr_series is None or len(atr_series) == 0:
        return np.nan
    return float(atr_series.iloc[-1])


# ══════════════════════════════════════════════════════════════
# 트레일링 스톱가 갱신 (v3.3 핵심 로직)
# ══════════════════════════════════════════════════════════════
def update_trailing_stop(
    old_peak: float,
    old_stop: float | None,
    current_high: float,
    atr: float,
) -> tuple[float, float]:
    """
    트레일링 스톱 갱신.
    - new_peak = max(old_peak, current_high)
    - new_stop = new_peak - ATR × ATR_MULT
    - stop     = max(old_stop, new_stop)  ← 스톱가는 오르기만 함

    Returns: (new_peak, new_stop)
    """
    new_peak = max(old_peak, current_high)
    new_stop = new_peak - atr * ATR_MULT
    if old_stop is None or np.isnan(old_stop):
        return new_peak, new_stop
    return new_peak, max(old_stop, new_stop)


def calc_return(entry_price: float, current_price: float) -> float:
    return (current_price - entry_price) / entry_price


# ══════════════════════════════════════════════════════════════
# 메인 모니터링
# ══════════════════════════════════════════════════════════════
def run_monitor():
    holdings = load_holdings()
    if not holdings:
        print("\n  보유 종목이 없습니다.")
        print("  추가 방법: python monitor.py --add <종목코드> <매수가>")
        print("  예시:      python monitor.py --add NVDA 130.50")
        return

    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    print("=" * 62)
    print(f"  📊 보유 종목 트레일링 스톱 모니터링  {today}")
    print(f"  ATR({ATR_PERIOD}) × {ATR_MULT} 트레일링 스톱 (v3.3)")
    print("=" * 62)

    tickers   = list(holdings.keys())
    sell_list = []
    warn_list = []
    safe_list = []

    updated_holdings = {}

    for ticker in tickers:
        info     = holdings[ticker]
        entry_px = info["entry_price"]
        peak_px  = info.get("peak_price", entry_px)
        stop_px  = info.get("stop_price")   # None이면 최초 계산

        try:
            raw = yf.download(ticker, period="3mo",
                              auto_adjust=True, progress=False)
            if raw.empty or len(raw) < ATR_PERIOD + 2:
                print(f"  ⚠️  {ticker} — 데이터 수신 실패", file=sys.stderr)
                updated_holdings[ticker] = info
                continue

            cur_px      = float(raw["Close"].iloc[-1])
            cur_high    = float(raw["High"].iloc[-1])   # v3.3: High로 peak 갱신
            atr         = calc_atr(raw)

            if np.isnan(atr):
                updated_holdings[ticker] = info
                continue

            # ── v3.3 트레일링 스톱 갱신 ──────────────────────
            new_peak, new_stop = update_trailing_stop(
                old_peak=peak_px,
                old_stop=stop_px,
                current_high=cur_high,
                atr=atr,
            )
            info["peak_price"] = new_peak
            info["stop_price"] = new_stop

            pct_margin = (cur_px - new_stop) / new_stop
            ret_pct    = calc_return(entry_px, cur_px)
            flag       = "🇺🇸" if not ticker.endswith(".KS") else "🇰🇷"

            row = {
                "ticker" : ticker,
                "flag"   : flag,
                "entry"  : entry_px,
                "current": cur_px,
                "high"   : cur_high,
                "peak"   : new_peak,
                "stop"   : new_stop,
                "atr"    : atr,
                "ret_pct": ret_pct,
                "margin" : pct_margin,
            }

            if pct_margin < 0:
                sell_list.append(row)
            elif pct_margin < WARN_BUFFER:
                warn_list.append(row)
            else:
                safe_list.append(row)

        except Exception as e:
            print(f"  ⚠️  {ticker} 처리 오류: {e}", file=sys.stderr)

        updated_holdings[ticker] = info

    # 갱신된 peak/stop 저장
    save_holdings(updated_holdings)

    # ── 매도 신호 ──────────────────────────────────────────
    if sell_list:
        print(f"\n  {'🚨 매도 신호':=<56}")
        for r in sell_list:
            print(
                f"\n  {r['flag']} {r['ticker']}"
                f"\n     현재가   : {r['current']:>10,.2f}"
                f"   매수가   : {r['entry']:>10,.2f}"
                f"   수익률 {r['ret_pct']:>+.1%}"
                f"\n     고점     : {r['peak']:>10,.2f}"
                f"   스톱가   : {r['stop']:>10,.2f}"
                f"   ATR     : {r['atr']:>8,.2f}"
                f"\n     ⛔ 현재가가 트레일링 스톱가 아래 — 매도 검토 권장"
            )
    else:
        print("\n  🚨 매도 신호: 없음")

    # ── 경고 ───────────────────────────────────────────────
    if warn_list:
        print(f"\n  {'⚠️  스톱 근접 경고 (5% 이내)':=<52}")
        for r in warn_list:
            print(
                f"\n  {r['flag']} {r['ticker']}"
                f"\n     현재가 {r['current']:>10,.2f}"
                f"  스톱가 {r['stop']:>10,.2f}"
                f"  여유 {r['margin']:>+.1%}"
                f"  수익률 {r['ret_pct']:>+.1%}"
            )
    else:
        print("  ⚠️  스톱 근접 경고: 없음")

    # ── 안전 보유 ──────────────────────────────────────────
    if safe_list:
        print(f"\n  {'✅ 안전 보유':=<56}")
        print(f"  {'종목':<14} {'현재가':>10} {'스톱가':>10} "
              f"{'여유':>8} {'수익률':>8} {'고점대비':>8}")
        print("  " + "─" * 60)
        for r in safe_list:
            from_peak = (r["current"] / r["peak"] - 1)
            print(
                f"  {r['flag']} {r['ticker']:<12}"
                f" {r['current']:>10,.2f}"
                f" {r['stop']:>10,.2f}"
                f" {r['margin']:>+8.1%}"
                f" {r['ret_pct']:>+8.1%}"
                f" {from_peak:>+8.1%}"
            )

    # ── 요약 ───────────────────────────────────────────────
    total = len(sell_list) + len(warn_list) + len(safe_list)
    print(f"\n  {'─'*62}")
    print(f"  총 {total}개 종목  │  "
          f"🚨 매도 {len(sell_list)}개  │  "
          f"⚠️ 경고 {len(warn_list)}개  │  "
          f"✅ 안전 {len(safe_list)}개")
    print(f"  {'─'*62}")


# ══════════════════════════════════════════════════════════════
# CLI 파서
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="보유 종목 ATR 트레일링 스톱 모니터링 (v3.3)"
    )
    parser.add_argument("--add",    nargs=2,
                        metavar=("TICKER", "PRICE"),
                        help="종목 추가 (예: --add NVDA 130.50)")
    parser.add_argument("--remove", metavar="TICKER",
                        help="종목 제거 (예: --remove NVDA)")
    parser.add_argument("--list",   action="store_true",
                        help="보유 목록 출력")

    args = parser.parse_args()

    if args.add:
        ticker, price = args.add
        add_holding(ticker, float(price))
    elif args.remove:
        remove_holding(args.remove)
    elif args.list:
        list_holdings()
    else:
        run_monitor()
