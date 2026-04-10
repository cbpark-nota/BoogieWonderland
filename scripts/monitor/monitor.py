"""
보유 종목 스톱로스 모니터링
══════════════════════════════════════════════════════════
매일 실행해서 보유 종목의 현재가가 ATR 기반 스톱가에
도달했는지 체크하고 매도 신호를 출력합니다.

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
ATR_MULT      = 2.5      # 스톱 = 고점 - ATR × 2.5
WARN_BUFFER   = 0.05     # 스톱가 5% 이내 접근 시 경고


# ══════════════════════════════════════════════════════════════
# 보유 종목 파일 관리
# ══════════════════════════════════════════════════════════════
def load_holdings() -> dict:
    """
    holdings.json 구조:
    {
      "NVDA": {"entry_price": 130.50, "entry_date": "2025-01-15", "peak_price": 145.20},
      "005930.KS": {"entry_price": 68000, "entry_date": "2025-02-01", "peak_price": 72000}
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
    holdings[ticker.upper()] = {
        "entry_price": entry_price,
        "entry_date" : datetime.now().strftime("%Y-%m-%d"),
        "peak_price" : entry_price,
    }
    save_holdings(holdings)
    print(f"  ✅ {ticker.upper()} 추가 (매수가: {entry_price:,.2f})")

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
    print(f"\n  {'종목':<14} {'매수가':>10} {'매수일':>12} {'현재 고점':>12}")
    print("  " + "─"*52)
    for t, info in holdings.items():
        print(f"  {t:<14} {info['entry_price']:>10,.2f} "
              f"{info['entry_date']:>12} {info['peak_price']:>12,.2f}")


# ══════════════════════════════════════════════════════════════
# ATR 기반 스톱가 계산
# ══════════════════════════════════════════════════════════════
def calc_atr_stop(df: pd.DataFrame, peak_price: float) -> dict:
    """
    스톱가 = peak_price - ATR(14) × ATR_MULT
    반환: {stop_price, atr, pct_from_stop}
    """
    h = df["High"].squeeze()
    l = df["Low"].squeeze()
    c = df["Close"].squeeze()

    atr_series = ta.atr(h, l, c, length=ATR_PERIOD)
    if atr_series is None or len(atr_series) == 0:
        return {}

    atr        = float(atr_series.iloc[-1])
    cur_price  = float(c.iloc[-1])
    stop_price = peak_price - atr * ATR_MULT
    pct_from_stop = (cur_price - stop_price) / stop_price

    return {
        "current"  : cur_price,
        "atr"      : atr,
        "stop"     : stop_price,
        "pct_margin": pct_from_stop,   # 양수 = 스톱가 위, 음수 = 스톱가 아래
    }


# ══════════════════════════════════════════════════════════════
# 수익률 계산
# ══════════════════════════════════════════════════════════════
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
        print("             python monitor.py --add 005930.KS 68000")
        return

    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    print("=" * 62)
    print(f"  📊 보유 종목 스톱로스 모니터링  {today}")
    print(f"  ATR({ATR_PERIOD}) × {ATR_MULT} 기반 동적 스톱")
    print("=" * 62)

    tickers   = list(holdings.keys())
    sell_list = []
    warn_list = []
    safe_list = []

    updated_holdings = {}

    for ticker in tickers:
        info = holdings[ticker]
        entry_px = info["entry_price"]
        peak_px  = info.get("peak_price", entry_px)

        try:
            raw = yf.download(ticker, period="3mo",
                              auto_adjust=True, progress=False)
            if raw.empty or len(raw) < ATR_PERIOD + 2:
                print(f"  ⚠️  {ticker} — 데이터 수신 실패", file=sys.stderr)
                updated_holdings[ticker] = info
                continue

            cur_px = float(raw["Close"].iloc[-1])

            # 고점 갱신
            new_peak = max(peak_px, cur_px)
            info["peak_price"] = new_peak

            calc = calc_atr_stop(raw, new_peak)
            if not calc:
                updated_holdings[ticker] = info
                continue

            ret_pct  = calc_return(entry_px, cur_px)
            margin   = calc["pct_margin"]
            flag     = "🇺🇸" if not ticker.endswith(".KS") else "🇰🇷"

            row = {
                "ticker"  : ticker,
                "flag"    : flag,
                "entry"   : entry_px,
                "current" : cur_px,
                "peak"    : new_peak,
                "stop"    : calc["stop"],
                "atr"     : calc["atr"],
                "ret_pct" : ret_pct,
                "margin"  : margin,
            }

            if margin < 0:
                sell_list.append(row)      # 스톱 이탈
            elif margin < WARN_BUFFER:
                warn_list.append(row)      # 스톱 근접 경고
            else:
                safe_list.append(row)

        except Exception as e:
            print(f"  ⚠️  {ticker} 처리 오류: {e}", file=sys.stderr)

        updated_holdings[ticker] = info

    # 고점 업데이트 저장
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
                f"\n     ⛔ 현재가가 스톱가 아래입니다 — 매도 검토 권장"
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
        description="보유 종목 ATR 스톱로스 모니터링"
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
