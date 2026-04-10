"""
시가총액 Top 20 신규 진입 전략 백테스트
════════════════════════════════════════════════════════════
전략:
  매 영업일 시총 Top 20을 시뮬레이션
  → 새로 Top 20에 진입한 종목을 다음 영업일 시가에 매수
  → ATR 기반 스톱로스로 청산
  → 매월 기존 보유 종목 시총 가중 리밸런싱

시총 근사:
  과거 시총 = 일봉 Close × 현재 발행주식수 (한계: shares는 고정값)
  → 상대 순위 변동 추적에 유효

대상:
  US: S&P500 + NASDAQ-100 (중복 제거)
  KR: KOSPI 200 + KOSDAQ 150

성과 지표:
  CAGR, MDD, Sharpe, 승률, 평균 보유기간, 거래 횟수, 손익비
════════════════════════════════════════════════════════════
"""
import io
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent))

RESULTS_DIR = _THIS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── 백테스트 파라미터 ─────────────────────────────────────
START          = "2022-01-01"   # yfinance 시총 데이터 가용 범위 (3년)
END            = datetime.today().strftime("%Y-%m-%d")
TOP_N          = 20             # 시총 Top 20
ATR_PERIOD     = 14
ATR_MULT       = 2.0            # ATR 기반 스톱로스 승수
COST_PER_SIDE  = 0.002          # 편도 수수료 0.2%
INITIAL_CASH   = 1_000_000.0   # 초기 자본

# US/KR 각각 독립 포트폴리오 운용 여부 (False = 합산)
SEPARATE_MARKET = False


# ── 유니버스 수집 ─────────────────────────────────────────

def fetch_sp500_tickers() -> list[str]:
    try:
        url = (
            "https://raw.githubusercontent.com/datasets/"
            "s-and-p-500-companies/main/data/constituents.csv"
        )
        df = pd.read_csv(url)
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        print(f"  S&P500 {len(tickers)}개 수집")
        return tickers
    except Exception as e:
        print(f"  S&P500 수집 실패 ({e})")
        return []


def fetch_nasdaq100_tickers() -> list[str]:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(
            "https://en.wikipedia.org/wiki/Nasdaq-100",
            headers=headers, timeout=15,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        ndx = tables[4]
        tickers = ndx["Ticker"].str.replace(".", "-", regex=False).tolist()
        print(f"  NASDAQ-100 {len(tickers)}개 수집")
        return tickers
    except Exception as e:
        print(f"  NASDAQ-100 수집 실패 ({e})")
        return []


def fetch_kr_tickers(kospi_n: int = 200, kosdaq_n: int = 150) -> list[str]:
    try:
        url = (
            "http://kind.krx.co.kr/corpgeneral/corpList.do"
            "?method=download&searchType=13"
        )
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        r.raise_for_status()
        krx = pd.read_html(io.StringIO(r.content.decode("euc-kr")))[0]
        kospi = krx[
            (krx["시장구분"] == "유가") &
            (krx["종목코드"].astype(str).str.match(r"^\d{6}$"))
        ]
        kosdaq = krx[
            (krx["시장구분"] == "코스닥") &
            (krx["종목코드"].astype(str).str.match(r"^\d{6}$"))
        ]
        kospi_t = [f"{str(c).zfill(6)}.KS" for c in kospi["종목코드"].tolist()][:kospi_n]
        kosdaq_t = [f"{str(c).zfill(6)}.KQ" for c in kosdaq["종목코드"].tolist()][:kosdaq_n]
        result = kospi_t + kosdaq_t
        print(f"  KR {len(result)}개 수집")
        return result
    except Exception as e:
        print(f"  KR 수집 실패 ({e})")
        return []


# ── 데이터 다운로드 ───────────────────────────────────────

def download_prices(tickers: list[str], start: str, end: str, label: str = "") -> dict[str, pd.DataFrame]:
    """yfinance 일봉 OHLCV 다운로드 (배치)."""
    all_data: dict[str, pd.DataFrame] = {}
    batch_size = 50
    total = len(tickers)

    for i in range(0, total, batch_size):
        batch = tickers[i:i + batch_size]
        print(f"\r  {label} 다운로드: {min(i + batch_size, total)}/{total}", end="", flush=True)
        try:
            raw = yf.download(
                batch, start=start, end=end,
                auto_adjust=True, progress=False, threads=True,
            )
            if isinstance(raw.columns, pd.MultiIndex):
                for t in batch:
                    try:
                        df = raw.xs(t, axis=1, level=1).dropna(how="all")
                        if len(df) >= 30:
                            all_data[t] = df
                    except Exception:
                        pass
            elif len(batch) == 1 and len(raw) >= 30:
                all_data[batch[0]] = raw
        except Exception:
            pass

    print(f"\r  {label} 다운로드 완료: {len(all_data)}/{total}개")
    return all_data


def get_shares_outstanding(tickers: list[str]) -> dict[str, int]:
    """현재 발행주식수 조회 (시총 근사 계산용)."""
    shares: dict[str, int] = {}
    for i in range(0, len(tickers), 50):
        batch = tickers[i:i + 50]
        print(f"\r  발행주식수: {i}/{len(tickers)}", end="", flush=True)
        for t in batch:
            try:
                info = yf.Ticker(t).fast_info
                s = info.get("shares", None)
                if s and s > 0:
                    shares[t] = int(s)
            except Exception:
                pass
    print(f"\r  발행주식수 완료: {len(shares)}/{len(tickers)}개")
    return shares


# ── 시총 순위 시계열 계산 ──────────────────────────────────

def compute_market_cap_series(
    all_data: dict[str, pd.DataFrame],
    shares: dict[str, int],
) -> pd.DataFrame:
    """
    각 종목의 일별 근사 시가총액 시계열 계산.
    시총 = 일봉 Close × 발행주식수 (shares는 현재값 고정)
    """
    cap_series: dict[str, pd.Series] = {}
    for t, df in all_data.items():
        if t not in shares:
            continue
        close = df["Close"].squeeze()
        cap = close * shares[t]
        cap_series[t] = cap

    if not cap_series:
        return pd.DataFrame()

    cap_df = pd.DataFrame(cap_series)
    cap_df = cap_df.sort_index()
    return cap_df


def get_daily_top20(cap_df: pd.DataFrame) -> pd.Series:
    """
    날짜별 시총 Top 20 종목 리스트 반환.
    Returns: pd.Series[list[str]] (인덱스=날짜)
    """
    def _top20_on_date(row: pd.Series) -> list[str]:
        valid = row.dropna()
        if valid.empty:
            return []
        return valid.nlargest(TOP_N).index.tolist()

    return cap_df.apply(_top20_on_date, axis=1)


# ── ATR 계산 ─────────────────────────────────────────────

def calc_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """ATR(Average True Range) 계산."""
    high = df["High"].squeeze()
    low = df["Low"].squeeze()
    close = df["Close"].squeeze()
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ── 백테스트 엔진 ─────────────────────────────────────────

class Position:
    """단일 포지션."""
    def __init__(self, ticker: str, entry_date, entry_price: float,
                 shares: float, stop_price: float, market: str):
        self.ticker = ticker
        self.entry_date = entry_date
        self.entry_price = entry_price
        self.shares = shares
        self.stop_price = stop_price
        self.market = market
        self.current_value = entry_price * shares

    def update_stop(self, new_stop: float) -> None:
        """트레일링 스톱 업데이트 (높을 때만)."""
        if new_stop > self.stop_price:
            self.stop_price = new_stop

    @property
    def cost_basis(self) -> float:
        return self.entry_price * self.shares


def run_backtest(
    us_data: dict[str, pd.DataFrame],
    kr_data: dict[str, pd.DataFrame],
    us_shares: dict[str, int],
    kr_shares: dict[str, int],
    spy_data: pd.DataFrame,
) -> dict:
    """
    시가총액 Top 20 신규 진입 전략 백테스트.

    진입: 신규 Top 20 진입 종목을 다음 영업일 시가 매수
    청산: ATR 기반 스톱로스 (20d High - ATR × ATR_MULT)
    리밸런싱: 매월 말 보유 종목 시총 가중 비중 재조정
    """
    all_data = {**us_data, **kr_data}
    all_shares = {**us_shares, **kr_shares}

    # 시총 시계열 계산
    print("\n  시총 시계열 계산 중...")
    cap_df_us = compute_market_cap_series(us_data, us_shares)
    cap_df_kr = compute_market_cap_series(kr_data, kr_shares)

    if cap_df_us.empty and cap_df_kr.empty:
        print("  오류: 시총 데이터 없음")
        return {}

    # 날짜 인덱스 통합
    all_dates = sorted(set(
        (cap_df_us.index.tolist() if not cap_df_us.empty else []) +
        (cap_df_kr.index.tolist() if not cap_df_kr.empty else [])
    ))

    # 영업일 필터 (월~금)
    biz_dates = [d for d in all_dates if pd.Timestamp(d).weekday() < 5]

    print(f"  백테스트 기간: {biz_dates[0].date() if biz_dates else 'N/A'} ~ "
          f"{biz_dates[-1].date() if biz_dates else 'N/A'} ({len(biz_dates)}일)")

    # ── 백테스트 루프 ──
    cash = INITIAL_CASH
    positions: dict[str, Position] = {}
    trades: list[dict] = []
    nav_series: list[tuple] = []

    prev_us_top20: list[str] = []
    prev_kr_top20: list[str] = []

    # 매월 리밸런싱 추적
    last_rebal_month = -1

    def _get_close(ticker: str, date) -> float | None:
        df = all_data.get(ticker)
        if df is None:
            return None
        close_col = df["Close"].squeeze()
        if date in close_col.index:
            v = close_col.loc[date]
            return float(v) if pd.notna(v) else None
        return None

    def _get_open(ticker: str, date) -> float | None:
        df = all_data.get(ticker)
        if df is None:
            return None
        open_col = df["Open"].squeeze()
        if date in open_col.index:
            v = open_col.loc[date]
            return float(v) if pd.notna(v) else None
        return None

    def _get_cap(ticker: str, date) -> float:
        cap_df = cap_df_us if ticker in cap_df_us.columns else cap_df_kr
        if cap_df.empty or ticker not in cap_df.columns:
            return 0.0
        if date in cap_df.index:
            v = cap_df.loc[date, ticker]
            return float(v) if pd.notna(v) else 0.0
        return 0.0

    def _get_atr_stop(ticker: str, date) -> float | None:
        df = all_data.get(ticker)
        if df is None:
            return None
        hist = df[df.index <= date]
        if len(hist) < ATR_PERIOD + 5:
            return None
        atr_ser = calc_atr(hist)
        atr_val = atr_ser.iloc[-1]
        high_20d = hist["High"].squeeze().tail(20).max()
        if pd.isna(atr_val) or pd.isna(high_20d):
            return None
        return float(high_20d - ATR_MULT * atr_val)

    # 진입 대기 큐 (date → list[ticker])
    pending_entries: dict = {}

    for date_idx, date in enumerate(biz_dates):
        ts = pd.Timestamp(date)

        # ── 1. 진입 대기 종목 처리 (전날 신호 → 오늘 시가 매수) ──
        if date in pending_entries:
            for ticker in pending_entries[date]:
                if ticker in positions:
                    continue  # 이미 보유
                open_price = _get_open(ticker, date)
                if open_price is None or open_price <= 0:
                    continue
                stop = _get_atr_stop(ticker, date)
                if stop is None:
                    stop = open_price * 0.92  # fallback: -8%

                # 포지션 비중: 총 자산의 1/TOP_N (상한 1/TOP_N)
                portfolio_value = cash + sum(
                    p.shares * (_get_close(p.ticker, date) or p.entry_price)
                    for p in positions.values()
                )
                alloc = portfolio_value / TOP_N
                alloc = min(alloc, cash * 0.95)
                if alloc < 100:
                    continue

                cost = alloc * (1 + COST_PER_SIDE)
                if cost > cash:
                    alloc = cash * 0.95
                    cost = alloc * (1 + COST_PER_SIDE)

                n_shares = alloc / open_price
                cash -= alloc * (1 + COST_PER_SIDE)
                market = "KR" if ".KS" in ticker or ".KQ" in ticker else "US"
                pos = Position(ticker, date, open_price, n_shares, stop, market)
                positions[ticker] = pos

                trades.append({
                    "type": "BUY",
                    "ticker": ticker,
                    "date": str(date.date()),
                    "price": open_price,
                    "shares": n_shares,
                    "value": alloc,
                    "market": market,
                })

        # ── 2. 스톱로스 체크 ──
        to_exit: list[str] = []
        for ticker, pos in positions.items():
            close_price = _get_close(ticker, date)
            if close_price is None:
                continue
            # 트레일링 스톱 업데이트
            new_stop = _get_atr_stop(ticker, date)
            if new_stop:
                pos.update_stop(new_stop)
            # 스톱 발동
            if close_price < pos.stop_price:
                to_exit.append(ticker)

        for ticker in to_exit:
            pos = positions.pop(ticker)
            exit_price = _get_close(ticker, date) or pos.stop_price
            proceeds = exit_price * pos.shares * (1 - COST_PER_SIDE)
            cash += proceeds
            pnl = proceeds - pos.cost_basis
            holding_days = (date - pos.entry_date).days
            trades.append({
                "type": "SELL_STOP",
                "ticker": ticker,
                "date": str(date.date()),
                "price": exit_price,
                "shares": pos.shares,
                "value": proceeds,
                "pnl": pnl,
                "pnl_pct": pnl / pos.cost_basis * 100 if pos.cost_basis != 0 else 0.0,
                "holding_days": holding_days,
                "market": pos.market,
            })

        # ── 3. 매월 리밸런싱 ──
        if ts.month != last_rebal_month and len(positions) > 0:
            last_rebal_month = ts.month

            # 시총 가중 비중 계산
            total_port = cash + sum(
                p.shares * (_get_close(p.ticker, date) or p.entry_price)
                for p in positions.values()
            )
            caps_now = {t: _get_cap(t, date) for t in positions}
            total_cap = sum(caps_now.values())
            if total_cap > 0:
                target_weights = {
                    t: caps_now[t] / total_cap for t in positions
                }
                # 리밸런싱 실행 (간단: 청산 후 재진입 없이 비중 조정)
                for ticker, pos in positions.items():
                    target_val = total_port * target_weights.get(ticker, 0)
                    curr_close = _get_close(ticker, date) or pos.entry_price
                    curr_val = pos.shares * curr_close
                    diff = target_val - curr_val
                    if abs(diff) / (curr_val + 1e-9) > 0.05:  # 5% 이상 차이시 조정
                        delta_shares = diff / curr_close
                        pos.shares += delta_shares
                        cash -= diff * (1 + COST_PER_SIDE if diff > 0 else 1 - COST_PER_SIDE)

        # ── 4. 시총 Top 20 계산 및 신규 진입 감지 ──
        # US Top 20
        us_top20_today: list[str] = []
        if not cap_df_us.empty and date in cap_df_us.index:
            row = cap_df_us.loc[date].dropna()
            if not row.empty:
                us_top20_today = row.nlargest(TOP_N).index.tolist()

        # KR Top 20
        kr_top20_today: list[str] = []
        if not cap_df_kr.empty and date in cap_df_kr.index:
            row = cap_df_kr.loc[date].dropna()
            if not row.empty:
                kr_top20_today = row.nlargest(TOP_N).index.tolist()

        # 신규 진입 종목
        us_new = [t for t in us_top20_today if t not in prev_us_top20 and prev_us_top20]
        kr_new = [t for t in kr_top20_today if t not in prev_kr_top20 and prev_kr_top20]
        new_entrants = us_new + kr_new

        # 다음 영업일 진입 큐 등록
        if new_entrants and date_idx + 1 < len(biz_dates):
            next_date = biz_dates[date_idx + 1]
            pending_entries.setdefault(next_date, []).extend(new_entrants)

        prev_us_top20 = us_top20_today or prev_us_top20
        prev_kr_top20 = kr_top20_today or prev_kr_top20

        # ── 5. NAV 계산 ──
        port_value = sum(
            pos.shares * (_get_close(pos.ticker, date) or pos.entry_price)
            for pos in positions.values()
        )
        nav = cash + port_value
        nav_series.append((date, nav))

    # 잔여 포지션 청산
    final_date = biz_dates[-1] if biz_dates else None
    for ticker, pos in list(positions.items()):
        exit_price = _get_close(ticker, final_date) or pos.entry_price
        proceeds = exit_price * pos.shares * (1 - COST_PER_SIDE)
        cash += proceeds
        pnl = proceeds - pos.cost_basis
        holding_days = (final_date - pos.entry_date).days if final_date else 0
        trades.append({
            "type": "SELL_FINAL",
            "ticker": ticker,
            "date": str(final_date.date()) if final_date else "N/A",
            "price": exit_price,
            "shares": pos.shares,
            "value": proceeds,
            "pnl": pnl,
            "pnl_pct": pnl / pos.cost_basis * 100,
            "holding_days": holding_days,
            "market": pos.market,
        })

    return {
        "nav_series": nav_series,
        "trades": trades,
        "final_cash": cash,
        "initial_cash": INITIAL_CASH,
    }


# ── 성과 지표 계산 ─────────────────────────────────────────

def calc_metrics(nav_series: list[tuple], trades: list[dict]) -> dict:
    """전략 성과 지표 계산."""
    if not nav_series:
        return {}

    nav_df = pd.DataFrame(nav_series, columns=["date", "nav"])
    nav_df = nav_df.set_index("date")
    nav = nav_df["nav"]

    # CAGR
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / max(years, 0.1)) - 1

    # MDD
    rolling_max = nav.cummax()
    drawdown = (nav - rolling_max) / rolling_max
    mdd = drawdown.min()

    # Sharpe (일별 수익률 기준)
    daily_ret = nav.pct_change().dropna()
    sharpe = (daily_ret.mean() / (daily_ret.std() + 1e-9)) * np.sqrt(252)

    # 거래 통계
    sell_trades = [t for t in trades if t["type"].startswith("SELL") and "pnl" in t]
    n_trades = len(sell_trades)
    winners = [t for t in sell_trades if t["pnl"] > 0]
    losers = [t for t in sell_trades if t["pnl"] <= 0]
    win_rate = len(winners) / n_trades if n_trades > 0 else 0
    avg_win = np.mean([t["pnl_pct"] for t in winners]) if winners else 0
    avg_loss = np.mean([t["pnl_pct"] for t in losers]) if losers else 0
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")
    avg_hold = np.mean([t["holding_days"] for t in sell_trades]) if sell_trades else 0

    total_return = nav.iloc[-1] / nav.iloc[0] - 1

    return {
        "총수익률": total_return,
        "CAGR": cagr,
        "MDD": mdd,
        "Sharpe": sharpe,
        "거래횟수": n_trades,
        "승률": win_rate,
        "평균수익(%)": avg_win,
        "평균손실(%)": avg_loss,
        "손익비": profit_factor,
        "평균보유일": avg_hold,
        "최종자산": nav.iloc[-1],
        "초기자산": INITIAL_CASH,
    }


def print_metrics(metrics: dict) -> None:
    """성과 지표 출력."""
    print("\n" + "=" * 60)
    print("  📊 백테스트 성과 지표")
    print("=" * 60)
    print(f"  기간    : {START} ~ {END}")
    print(f"  초기자산: ${INITIAL_CASH:,.0f}")
    print(f"  최종자산: ${metrics.get('최종자산', 0):,.0f}")
    print(f"  총수익률: {metrics.get('총수익률', 0):.1%}")
    print(f"  CAGR    : {metrics.get('CAGR', 0):.1%}")
    print(f"  MDD     : {metrics.get('MDD', 0):.1%}")
    print(f"  Sharpe  : {metrics.get('Sharpe', 0):.2f}")
    print(f"  거래횟수 : {metrics.get('거래횟수', 0)}회")
    print(f"  승률    : {metrics.get('승률', 0):.1%}")
    print(f"  평균수익 : {metrics.get('평균수익(%)', 0):.1f}%")
    print(f"  평균손실 : {metrics.get('평균손실(%)', 0):.1f}%")
    print(f"  손익비   : {metrics.get('손익비', 0):.2f}")
    print(f"  평균보유 : {metrics.get('평균보유일', 0):.1f}일")
    print("=" * 60)


def plot_nav(nav_series: list[tuple], spy_data: pd.DataFrame) -> None:
    """NAV 차트 저장."""
    if not nav_series:
        return

    nav_df = pd.DataFrame(nav_series, columns=["date", "nav"])
    nav_df["date"] = pd.to_datetime(nav_df["date"])
    nav_df = nav_df.set_index("date")
    nav_df["nav_norm"] = nav_df["nav"] / nav_df["nav"].iloc[0]

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(nav_df.index, nav_df["nav_norm"], label="시총 Top20 전략", linewidth=2, color="royalblue")

    # SPY 벤치마크
    if spy_data is not None and not spy_data.empty:
        spy_close = spy_data["Close"].squeeze().dropna()
        start_ts = nav_df.index[0]
        spy_aligned = spy_close[spy_close.index >= start_ts]
        if not spy_aligned.empty:
            spy_norm = spy_aligned / spy_aligned.iloc[0]
            ax.plot(spy_norm.index, spy_norm, label="SPY (벤치마크)", linewidth=1.5,
                    color="gray", linestyle="--", alpha=0.8)

    ax.set_title("시가총액 Top 20 신규 진입 전략 — NAV 추이", fontsize=14)
    ax.set_ylabel("정규화 NAV (기준=1.0)")
    ax.set_xlabel("날짜")
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}x"))

    out_path = RESULTS_DIR / "backtest_market_cap_nav.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  차트 저장: {out_path}")


def save_trade_log(trades: list[dict]) -> None:
    """거래 내역 CSV 저장."""
    if not trades:
        return
    df = pd.DataFrame(trades)
    out_path = RESULTS_DIR / "backtest_market_cap_trades.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"  거래내역 저장: {out_path}")


# ── 메인 ─────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  시가총액 Top 20 신규 진입 전략 백테스트")
    print(f"  기간: {START} ~ {END}")
    print(f"  ATR 승수: {ATR_MULT}, Top N: {TOP_N}")
    print("=" * 60)

    # 유니버스 수집
    print("\n[1] 유니버스 수집")
    sp500 = fetch_sp500_tickers()
    ndx100 = fetch_nasdaq100_tickers()
    sp500_set = set(sp500)
    ndx_new = [t for t in ndx100 if t not in sp500_set]
    us_universe = sp500 + ndx_new
    kr_universe = fetch_kr_tickers()
    print(f"  US 유니버스: {len(us_universe)}개")
    print(f"  KR 유니버스: {len(kr_universe)}개")

    # 가격 데이터 다운로드
    print("\n[2] 가격 데이터 다운로드")
    us_data = download_prices(us_universe, START, END, "US")
    kr_data = download_prices(kr_universe, START, END, "KR")

    # 벤치마크 (SPY)
    spy_raw = yf.download("SPY", start=START, end=END, auto_adjust=True, progress=False)
    spy_data = spy_raw if not spy_raw.empty else pd.DataFrame()

    # 발행주식수 조회 (시총 근사)
    print("\n[3] 발행주식수 조회 (시총 근사용)")
    all_tickers = list(us_data.keys()) + list(kr_data.keys())
    all_shares = get_shares_outstanding(all_tickers)
    us_shares = {t: v for t, v in all_shares.items() if t in us_data}
    kr_shares = {t: v for t, v in all_shares.items() if t in kr_data}

    print(f"  US shares 확보: {len(us_shares)}개")
    print(f"  KR shares 확보: {len(kr_shares)}개")

    if len(us_shares) < 10 and len(kr_shares) < 5:
        print("  경고: 발행주식수 데이터가 부족합니다. 백테스트 품질이 낮을 수 있습니다.")

    # 백테스트 실행
    print("\n[4] 백테스트 실행")
    result = run_backtest(us_data, kr_data, us_shares, kr_shares, spy_data)

    if not result or not result.get("nav_series"):
        print("  오류: 백테스트 결과 없음 (데이터 부족 또는 거래 없음)")
        return

    # 성과 지표
    print("\n[5] 성과 분석")
    metrics = calc_metrics(result["nav_series"], result["trades"])
    print_metrics(metrics)

    # 차트 및 거래내역 저장
    print("\n[6] 결과 저장")
    plot_nav(result["nav_series"], spy_data)
    save_trade_log(result["trades"])

    # 전략별 KR/US 분리 통계
    trades = result["trades"]
    sell_trades = [t for t in trades if t["type"].startswith("SELL") and "pnl" in t]
    us_sells = [t for t in sell_trades if t.get("market") == "US"]
    kr_sells = [t for t in sell_trades if t.get("market") == "KR"]

    if us_sells:
        us_wr = len([t for t in us_sells if t["pnl"] > 0]) / len(us_sells)
        print(f"\n  US: {len(us_sells)}거래, 승률 {us_wr:.1%}")
    if kr_sells:
        kr_wr = len([t for t in kr_sells if t["pnl"] > 0]) / len(kr_sells)
        print(f"  KR: {len(kr_sells)}거래, 승률 {kr_wr:.1%}")

    print("\n  백테스트 완료!")


if __name__ == "__main__":
    main()
