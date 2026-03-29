"""
트렌드+모멘텀 vs 모멘텀만 백테스트
══════════════════════════════════════════════════════════════
비교 전략:
  1) 모멘텀만    : screen_A (ADX+MA+RSI+ATR) — 전 섹터 대상
  2) 트렌드+모멘텀: 시총 Top 20 섹터 감지 → 연관섹터 필터 + 모멘텀

트렌드 감지:
  - 매 리밸런싱 시점에 시총 Top 20 종목 확인
  - 해당 종목들의 GICS 섹터 = "활성 트렌드 섹터"
  - 활성 섹터 + 연관섹터(정적 SECTOR_RELATIONS + 동적 ETF 상관관계) 종목만 매매

청산 조건:
  - ATR 스톱로스 (리밸런싱 구간 중 일별 체크)
  - 리밸런싱 시점에 해당 섹터가 Top 20에서 빠진 경우 자동 제외

유니버스: S&P500 + NASDAQ-100 + KOSPI200 + KOSDAQ150 (동적 수집)
리밸런싱: 월간 (BME)
수수료  : 편도 0.2% (왕복 0.4%)
기간    : 2015-01-01 ~ 현재
══════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import sys
import importlib.util
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

# ── 경로 설정 ──────────────────────────────────────────────────
_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent))

from data_cache import load_full_universe
from screener.trend_momentum_screener import (
    add_indicators,
    fetch_shares_outstanding,
    get_top_n_market_cap,
    detect_active_trend_sectors,
    get_related_sectors,
    screen_momentum,
    rank_stocks,
    position_weights,
    normalize_sector,
    SECTOR_ETF_MAP,
)

RESULTS_DIR = _THIS_DIR / 'results'
RESULTS_DIR.mkdir(exist_ok=True)

# ── 파라미터 ───────────────────────────────────────────────────
START         = '2015-01-01'
END           = datetime.today().strftime('%Y-%m-%d')
REBAL_FREQ    = 'BME'     # 월말 리밸런싱
PERIODS_PY    = 12        # 연간 기간 수 (월별: 12)
COMMISSION    = 0.002     # 편도 0.2%
ATR_MULT      = 2.0       # 균형형
TOP_N         = 10
MAX_WEIGHT    = 0.10


# ══════════════════════════════════════════════════════════════
# 성과 지표 계산
# ══════════════════════════════════════════════════════════════

def calc_metrics(nav_list: list, label: str) -> dict:
    s    = pd.Series(nav_list, dtype=float)
    ret  = s.pct_change().dropna()
    n    = len(ret)
    years = n / PERIODS_PY
    cagr  = (s.iloc[-1] ** (1 / max(years, 0.1))) - 1 if s.iloc[-1] > 0 else -1.0
    mdd   = ((s - s.cummax()) / s.cummax()).min()
    sharp = (ret.mean() / (ret.std() + 1e-9)) * np.sqrt(PERIODS_PY)
    win   = (ret > 0).mean()
    # 손익비 (Profit/Loss ratio)
    gains  = ret[ret > 0]
    losses = ret[ret < 0]
    pl_ratio = (gains.mean() / abs(losses.mean())) if len(losses) > 0 and abs(losses.mean()) > 0 else np.nan
    return {
        'label':    label,
        '총수익률': s.iloc[-1] - 1,
        'CAGR':     cagr,
        'MDD':      mdd,
        '샤프':     sharp,
        '기간승률': win,
        '손익비':   pl_ratio,
        'nav':      nav_list,
        '거래횟수': n,
    }


def print_metrics(m: dict):
    pl_str = f"{m['손익비']:.2f}" if not np.isnan(m['손익비']) else 'N/A'
    print(f"  {'─'*60}")
    print(f"  {m['label']}")
    print(f"  총수익률 {m['총수익률']:>+8.1%}   CAGR {m['CAGR']:>+8.1%}")
    print(f"  MDD      {m['MDD']:>+8.1%}   샤프 {m['샤프']:>8.2f}")
    print(f"  기간승률 {m['기간승률']:>8.1%}   손익비 {pl_str:>6}   리밸 횟수 {m['거래횟수']:>3}회")


# ══════════════════════════════════════════════════════════════
# 구간 ATR 스톱 체크
# ══════════════════════════════════════════════════════════════

def check_stops(holdings: dict, all_data: dict, prev_dt, curr_dt) -> dict:
    """리밸런싱 구간 중 ATR 스톱 트리거 종목 제거."""
    daily_range = pd.date_range(prev_dt, curr_dt, freq='B')[1:]
    for day in daily_range:
        if not holdings:
            break
        to_remove = []
        for ticker, info in holdings.items():
            df_t = all_data.get(ticker)
            if df_t is None:
                continue
            day_px = df_t[df_t.index <= day]['Close']
            if len(day_px) == 0:
                continue
            cur_px = float(day_px.iloc[-1])
            info['peak'] = max(info['peak'], cur_px)
            atr_stop = info.get('atr_stop', np.nan)
            if not pd.isna(atr_stop) and cur_px <= atr_stop:
                to_remove.append(ticker)
        for t in to_remove:
            del holdings[t]
    return holdings


# ══════════════════════════════════════════════════════════════
# 모멘텀만 백테스트 (비교 기준)
# ══════════════════════════════════════════════════════════════

def run_momentum_only(all_data: dict, etf_data: dict, universe_map: dict) -> list:
    """
    전 섹터 대상 모멘텀 스크리닝 (sector 필터 없음).
    screen_A 방식: ADX + MA정배열 + RSI + ATR 스톱.
    """
    rebal_dates = pd.date_range(start=START, end=END, freq=REBAL_FREQ)
    nav         = [1.0]
    holdings    = {}
    prev_dt     = None

    for rd in rebal_dates:
        # ── 구간 스톱 체크
        if prev_dt and holdings:
            holdings = check_stops(holdings, all_data, prev_dt, rd)

        # ── 구간 수익 반영
        if prev_dt:
            ret = _calc_period_return(holdings, all_data, prev_dt, rd)
            nav.append(nav[-1] * (1 + ret))

        # ── 수수료 (턴오버 기반)
        passed = {}
        for ticker, df_t in all_data.items():
            ok, m = screen_momentum(df_t, rd, ATR_MULT)
            if ok:
                passed[ticker] = m

        ranked = rank_stocks(passed, etf_data, universe_map, rd)
        top    = ranked.head(TOP_N)

        if prev_dt and len(top) > 0:
            nav[-1] *= _apply_commission(holdings, top, rd, all_data)

        # ── 포지션 구성
        holdings = _build_holdings(top, all_data, rd)
        prev_dt  = rd

    return nav


# ══════════════════════════════════════════════════════════════
# 트렌드+모멘텀 백테스트
# ══════════════════════════════════════════════════════════════

def run_trend_momentum(
    all_data: dict,
    etf_data: dict,
    shares_map: dict,
    universe_map: dict,
) -> tuple[list, list]:
    """
    트렌드 섹터 필터 + 모멘텀 스크리닝.

    Returns
    -------
    nav           : NAV 리스트
    sector_history: [(date, active_sectors, target_sectors), ...]
    """
    rebal_dates    = pd.date_range(start=START, end=END, freq=REBAL_FREQ)
    nav            = [1.0]
    holdings       = {}
    prev_dt        = None
    sector_history = []

    for rd in rebal_dates:
        # ── 시총 Top N 및 활성 트렌드 섹터 계산
        top_n_list     = get_top_n_market_cap(all_data, shares_map, rd)
        active_sectors = detect_active_trend_sectors(top_n_list, universe_map)
        target_sectors = get_related_sectors(active_sectors, etf_data, rd)

        sector_history.append((rd, active_sectors.copy(), target_sectors.copy()))

        # ── 구간 스톱 체크
        if prev_dt and holdings:
            holdings = check_stops(holdings, all_data, prev_dt, rd)

        # ── 트렌드 종료 종목 청산 (섹터가 target에서 빠진 경우)
        if holdings and target_sectors:
            holdings = {
                t: info for t, info in holdings.items()
                if normalize_sector(universe_map.get(t, 'Unknown')) in target_sectors
            }

        # ── 구간 수익 반영
        if prev_dt:
            ret = _calc_period_return(holdings, all_data, prev_dt, rd)
            nav.append(nav[-1] * (1 + ret))

        # ── 트렌드+모멘텀 스크리닝
        passed = {}
        for ticker, df_t in all_data.items():
            # 섹터 필터
            sec = normalize_sector(universe_map.get(ticker, 'Unknown'))
            if target_sectors and sec not in target_sectors:
                continue
            ok, m = screen_momentum(df_t, rd, ATR_MULT)
            if ok:
                passed[ticker] = m

        ranked = rank_stocks(passed, etf_data, universe_map, rd)
        top    = ranked.head(TOP_N)

        # ── 수수료
        if prev_dt and len(top) > 0:
            nav[-1] *= _apply_commission(holdings, top, rd, all_data)

        # ── 포지션 구성
        holdings = _build_holdings(top, all_data, rd)
        prev_dt  = rd

    return nav, sector_history


# ══════════════════════════════════════════════════════════════
# 공통 유틸 함수
# ══════════════════════════════════════════════════════════════

def _calc_period_return(holdings: dict, all_data: dict, prev_dt, curr_dt) -> float:
    ret = 0.0
    for ticker, info in holdings.items():
        df_t = all_data.get(ticker)
        if df_t is None:
            continue
        p0 = df_t[df_t.index <= prev_dt]['Close']
        p1 = df_t[df_t.index <= curr_dt]['Close']
        if len(p0) and len(p1) and float(p0.iloc[-1]) > 0:
            ret += info['w'] * (float(p1.iloc[-1]) / float(p0.iloc[-1]) - 1)
    return ret


def _apply_commission(old_holdings: dict, top: pd.DataFrame,
                       rd, all_data: dict) -> float:
    """턴오버 기반 수수료 적용. (1 - commission_cost) 반환."""
    if len(top) == 0:
        return 1.0
    new_set  = set(top.index)
    old_set  = set(old_holdings.keys())
    ws_tmp   = position_weights(top['score'])
    sold_w   = sum(old_holdings[t]['w'] for t in old_set - new_set)
    bought_w = sum(float(ws_tmp.get(t, 0)) for t in new_set - old_set)
    rebal_w  = sum(
        abs(float(ws_tmp.get(t, 0)) - old_holdings[t]['w'])
        for t in old_set & new_set
    )
    total_comm = (sold_w + bought_w + rebal_w) * COMMISSION
    return 1 - total_comm


def _build_holdings(top: pd.DataFrame, all_data: dict, rd) -> dict:
    if len(top) == 0:
        return {}
    ws       = position_weights(top['score'])
    holdings = {}
    for ticker in top.index:
        df_t  = all_data.get(ticker)
        entry = float(df_t[df_t.index <= rd]['Close'].iloc[-1]) \
                if df_t is not None else 1.0
        atr_s = float(top.loc[ticker, 'atr_stop']) \
                if 'atr_stop' in top.columns and not pd.isna(top.loc[ticker, 'atr_stop']) \
                else np.nan
        holdings[ticker] = {
            'w':        float(ws.get(ticker, 0)),
            'entry':    entry,
            'peak':     entry,
            'atr_stop': atr_s,
        }
    return holdings


# ══════════════════════════════════════════════════════════════
# 차트 저장
# ══════════════════════════════════════════════════════════════

def plot_results(all_metrics: list, spy_nav: list):
    rebal_dates = list(pd.date_range(START, END, freq=REBAL_FREQ))
    dates = [pd.Timestamp(START)] + rebal_dates

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle(
        f'트렌드+모멘텀 vs 모멘텀만  (수수료 0.2%RT, {START}~{END[:7]})',
        fontsize=13, fontweight='bold',
    )
    colors = ['#2E75B6', '#ED7D31', '#70AD47']

    ax1 = axes[0]
    for i, m in enumerate(all_metrics[:2]):
        nav = m['nav']
        n   = min(len(nav), len(dates))
        ax1.plot(dates[:n], nav[:n], label=m['label'], color=colors[i], lw=2.0)
    n_spy = min(len(spy_nav), len(dates))
    ax1.plot(dates[:n_spy], spy_nav[:n_spy], label='SPY',
             color='gray', lw=1.2, ls='--', alpha=0.7)
    ax1.set_ylabel('누적 자산 (배)')
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.1f}x'))
    ax1.set_title('누적 NAV 곡선')
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.25)

    ax2 = axes[1]
    labels_bar = [m['label'] for m in all_metrics[:2]]
    cagrs  = [m['CAGR'] * 100    for m in all_metrics[:2]]
    mdds   = [abs(m['MDD']) * 100 for m in all_metrics[:2]]
    sharps = [m['샤프']           for m in all_metrics[:2]]
    x = np.arange(len(labels_bar))
    w = 0.25
    ax2.bar(x - w, cagrs,  width=w, label='CAGR(%)',  color='#2E75B6', alpha=0.8)
    ax2.bar(x,     mdds,   width=w, label='MDD(%)',   color='#FF4444', alpha=0.8)
    ax2.bar(x + w, sharps, width=w, label='샤프',     color='#70AD47', alpha=0.8)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels_bar, rotation=15, fontsize=9)
    ax2.set_title('CAGR / MDD / 샤프 비교')
    ax2.legend(fontsize=9)
    ax2.grid(axis='y', alpha=0.25)

    path = RESULTS_DIR / 'trend_momentum_comparison.png'
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches='tight')
    print(f'\n  차트 저장: {path}')


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print('=' * 70)
    print('  트렌드+모멘텀 vs 모멘텀만 백테스트')
    print(f'  기간     : {START} ~ {END}')
    print(f'  리밸런싱 : 월간 ({REBAL_FREQ})')
    print(f'  수수료   : 편도 {COMMISSION*100:.1f}% (왕복 {COMMISSION*2*100:.1f}%)')
    print(f'  ATR 승수 : {ATR_MULT} (균형형)  TOP_N={TOP_N}')
    print(f'  유니버스 : 풀 유니버스 (S&P500 + NASDAQ-100 + KOSPI200 + KOSDAQ150)')
    print('=' * 70)

    # ── [1] 데이터 로드 ──────────────────────────────────────
    print('\n[1] 데이터 로드 (캐시 또는 yfinance 다운로드)...')
    all_data_raw, spy_df, etf_raw, universe_map = load_full_universe(START)
    print(f'  → 종목 {len(all_data_raw)}개 로드 완료 (유니버스: {len(universe_map)}개)')

    # ── [2] 지표 계산 ─────────────────────────────────────────
    print(f'\n[2] 종목 지표 계산 ({len(all_data_raw)}종목)...')
    all_data = {t: add_indicators(df) for t, df in all_data_raw.items()}
    etf_data = {t: add_indicators(df) for t, df in etf_raw.items()}
    print('  완료')

    # ── [3] Shares Outstanding 조회 (US 종목만) ───────────────
    print('\n[3] Shares Outstanding 조회 (US 종목, 시총 계산용)...')
    us_tickers = [t for t in all_data if not (t.endswith('.KS') or t.endswith('.KQ'))]
    shares_map = fetch_shares_outstanding(us_tickers)
    print(f'  → {len(shares_map)}종목 shares outstanding 확보')

    # SPY 벤치마크 NAV (월간 기준)
    spy_close   = spy_df['Close'].squeeze()
    spy_monthly = spy_close.resample(REBAL_FREQ).last().pct_change().fillna(0)
    spy_nav     = [1.0] + list((1 + spy_monthly).cumprod().values.flatten())

    # ── [4] 모멘텀만 백테스트 ─────────────────────────────────
    print(f'\n[4] 모멘텀만 백테스트 실행 (리밸런싱: {REBAL_FREQ})...')
    nav_momentum = run_momentum_only(all_data, etf_data, universe_map)
    m_momentum   = calc_metrics(nav_momentum, '모멘텀만 (전 섹터)')
    print_metrics(m_momentum)

    # ── [5] 트렌드+모멘텀 백테스트 ───────────────────────────
    print(f'\n[5] 트렌드+모멘텀 백테스트 실행...')
    nav_tm, sector_hist = run_trend_momentum(
        all_data, etf_data, shares_map, universe_map
    )
    m_tm = calc_metrics(nav_tm, '트렌드+모멘텀')
    print_metrics(m_tm)

    # SPY 지표
    m_spy = calc_metrics(spy_nav, 'SPY 벤치마크')

    # ── [6] 섹터 이력 샘플 출력 ───────────────────────────────
    print('\n[6] 트렌드 섹터 이력 (최근 6회)')
    print(f"  {'날짜':<12} {'활성 섹터 수':>8} {'타겟 섹터 수':>10}  {'활성 섹터 (상위 3개)'}")
    print('  ' + '─' * 70)
    for rd, active, target in sector_hist[-6:]:
        top3 = sorted(active)[:3]
        print(f"  {str(rd.date()):<12} {len(active):>8} {len(target):>10}"
              f"  {', '.join(top3)}")

    # ── [7] 종합 비교 ─────────────────────────────────────────
    all_metrics = [m_momentum, m_tm, m_spy]
    print('\n' + '═' * 70)
    print('  종합 성과 비교')
    print('═' * 70)
    print(f"  {'전략':<30} {'CAGR':>8} {'MDD':>8} {'샤프':>7} {'기간승률':>8} {'손익비':>7}")
    print('  ' + '─' * 65)
    for m in all_metrics:
        pl_str = f"{m['손익비']:.2f}" if not np.isnan(m.get('손익비', np.nan)) else '  N/A'
        print(f"  {m['label']:<30} {m['CAGR']:>+8.1%} "
              f"{m['MDD']:>+8.1%} {m['샤프']:>7.2f} "
              f"{m['기간승률']:>8.1%} {pl_str:>7}")

    # ── [8] CSV 저장 ──────────────────────────────────────────
    rows = [{
        '전략':     m['label'],
        '총수익률': f"{m['총수익률']:+.1%}",
        'CAGR':     f"{m['CAGR']:+.1%}",
        'MDD':      f"{m['MDD']:+.1%}",
        '샤프지수': f"{m['샤프']:.2f}",
        '기간승률': f"{m['기간승률']:.1%}",
        '손익비':   f"{m['손익비']:.2f}" if not np.isnan(m.get('손익비', np.nan)) else 'N/A',
        '리밸횟수': m['거래횟수'],
    } for m in all_metrics]
    csv_path = RESULTS_DIR / 'trend_momentum_comparison.csv'
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f'\n  결과 CSV: {csv_path}')

    # ── [9] 차트 ─────────────────────────────────────────────
    plot_results(all_metrics, spy_nav)

    print('\n' + '=' * 70)
    print('  백테스트 완료')
    print('=' * 70)
