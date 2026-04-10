"""
트렌드+모멘텀 스크리너
══════════════════════════════════════════════════════════════
핵심 아이디어:
  시총 Top 20에 새로 진입한 종목의 섹터 = 거시 트렌드 변화 신호.
  해당 섹터 + 연관 섹터에 속한 종목만 모멘텀 스크리닝해서 매매.

2단계 필터:
  1단계: 시총 Top 20 감지 → 활성 트렌드 섹터 확정
  2단계: 섹터 연관 매핑 (정적 SECTOR_RELATIONS + 동적 ETF 상관관계)
  3단계: 모멘텀 스크리닝 (ADX, MA 정배열, RSI 등) + 섹터 필터
══════════════════════════════════════════════════════════════
"""
import warnings
warnings.filterwarnings("ignore")

import sys
import json
import numpy as np
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from pathlib import Path
from datetime import datetime, date

# ── 경로 설정 ─────────────────────────────────────────────────
_THIS_DIR   = Path(__file__).parent
_SCRIPTS    = _THIS_DIR.parent
_REPO_ROOT  = _SCRIPTS.parent
SHARES_CACHE_PATH = _REPO_ROOT / "data" / "shares_outstanding.json"

# ── 파라미터 상수 ─────────────────────────────────────────────
TOP_N_MARKET_CAP      = 20        # 시총 상위 종목 수
CORRELATION_THRESHOLD = 0.6       # 동적 섹터 상관관계 임계값
CORR_WINDOW           = 60        # ETF 수익률 상관관계 계산 기간 (영업일)
ATR_PERIOD            = 14
ATR_MULT              = 2.0       # 균형형
ADX_THRESH            = 20
RSI_LO                = 50
RSI_HI                = 77
HH_HL_MIN             = 2
HH_HL_WINDOW          = 60
PRICE_52W_THR         = 0.75
VOL_SPIKE             = 3.0
DAILY_MOVE            = 0.10
TOP_N                 = 10
MAX_WEIGHT            = 0.10
WEIGHTS               = dict(adx=0.4, ret3m=0.3, sector=0.2, vol_stab=0.1)

# ── GICS 섹터 간 정적 연관 관계 ──────────────────────────────
SECTOR_RELATIONS: dict[str, list[str]] = {
    'Energy':                 ['Materials', 'Industrials'],
    'Information Technology': ['Communication Services', 'Consumer Discretionary'],
    'Health Care':            ['Consumer Staples'],
    'Financials':             ['Real Estate'],
    'Materials':              ['Energy', 'Industrials'],
    'Industrials':            ['Materials', 'Energy'],
    'Consumer Discretionary': ['Information Technology', 'Communication Services'],
    'Communication Services': ['Information Technology', 'Consumer Discretionary'],
    'Utilities':              ['Real Estate'],
    'Real Estate':            ['Financials', 'Utilities'],
    'Consumer Staples':       ['Health Care'],
    # 구형 섹터명 호환
    'Technology':             ['Communication Services', 'Consumer Discretionary'],
    'Communication':          ['Information Technology', 'Consumer Discretionary'],
    'Consumer Disc':          ['Information Technology', 'Communication Services'],
    'Health':                 ['Consumer Staples'],
}

# ── 섹터 ETF 매핑 ─────────────────────────────────────────────
SECTOR_ETF_MAP: dict[str, str] = {
    'Energy':                 'XLE',
    'Information Technology': 'XLK',
    'Health Care':            'XLV',
    'Financials':             'XLF',
    'Materials':              'XLB',
    'Industrials':            'XLI',
    'Consumer Discretionary': 'XLY',
    'Communication Services': 'XLC',
    'Utilities':              'XLU',
    'Real Estate':            'XLRE',
    'Consumer Staples':       'XLP',
    # 구형 섹터명 호환
    'Technology':             'XLK',
    'Communication':          'XLC',
    'Consumer Disc':          'XLY',
    'Health':                 'XLV',
}

ALL_SECTOR_ETFS = ['XLE', 'XLK', 'XLV', 'XLF', 'XLB', 'XLI',
                   'XLY', 'XLC', 'XLU', 'XLRE', 'XLP']

# ETF → 정규화된 GICS 섹터명
_ETF_TO_SECTOR: dict[str, str] = {
    'XLE':  'Energy',
    'XLK':  'Information Technology',
    'XLV':  'Health Care',
    'XLF':  'Financials',
    'XLB':  'Materials',
    'XLI':  'Industrials',
    'XLY':  'Consumer Discretionary',
    'XLC':  'Communication Services',
    'XLU':  'Utilities',
    'XLRE': 'Real Estate',
    'XLP':  'Consumer Staples',
}

# ── 섹터명 정규화 ─────────────────────────────────────────────
_NORMALIZE: dict[str, str] = {
    'Technology':             'Information Technology',
    'Communication':          'Communication Services',
    'Consumer Disc':          'Consumer Discretionary',
    'Health':                 'Health Care',
}

def normalize_sector(sector: str) -> str:
    """구형/약식 섹터명을 GICS 표준으로 정규화."""
    return _NORMALIZE.get(sector, sector)


# ══════════════════════════════════════════════════════════════
# 주식 수 (Shares Outstanding) 캐시
# ══════════════════════════════════════════════════════════════

def load_shares_cache() -> dict:
    """캐시에서 shares outstanding 로드 (당일 유효)."""
    if not SHARES_CACHE_PATH.exists():
        return {}
    try:
        with open(SHARES_CACHE_PATH, encoding='utf-8') as f:
            data = json.load(f)
        if data.get('date') != date.today().isoformat():
            return {}
        return data.get('shares', {})
    except Exception:
        return {}


def save_shares_cache(shares: dict):
    """shares outstanding 캐시 저장."""
    SHARES_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SHARES_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump({'date': date.today().isoformat(), 'shares': shares}, f)


def fetch_shares_outstanding(tickers: list, verbose: bool = True) -> dict:
    """
    yfinance fast_info에서 주식 수(shares outstanding) 가져오기.
    당일 캐시가 있으면 재사용.
    """
    cached = load_shares_cache()
    missing = [t for t in tickers if t not in cached]

    if verbose and missing:
        print(f"  shares outstanding 조회: {len(missing)}종목 (캐시: {len(cached)}개)...",
              end='', flush=True)

    result = dict(cached)
    for i, t in enumerate(missing):
        try:
            fi = yf.Ticker(t).fast_info
            shares = getattr(fi, 'shares', None)
            if shares and shares > 0:
                result[t] = int(shares)
        except Exception:
            pass
        if verbose and (i + 1) % 50 == 0:
            print(f"\r  shares outstanding 조회: {i+1}/{len(missing)}...",
                  end='', flush=True)

    if missing:
        save_shares_cache(result)
        if verbose:
            print(f"\r  shares outstanding 조회 완료: {len(result)}종목  ", flush=True)

    return result


# ══════════════════════════════════════════════════════════════
# 시총 Top N 계산
# ══════════════════════════════════════════════════════════════

def get_top_n_market_cap(
    all_data: dict,
    shares_map: dict,
    as_of,
    top_n: int = TOP_N_MARKET_CAP,
) -> list[str]:
    """
    Close × shares_outstanding 근사로 시총 Top N 종목 반환.
    shares_map에 없는 종목은 제외 (KR 종목 등).
    """
    caps: dict[str, float] = {}
    for ticker, df in all_data.items():
        shares = shares_map.get(ticker)
        if not shares or shares <= 0:
            continue
        hist = df[df.index <= as_of]
        if len(hist) == 0:
            continue
        close = float(hist['Close'].iloc[-1])
        if close > 0:
            caps[ticker] = close * shares

    return sorted(caps, key=lambda t: caps[t], reverse=True)[:top_n]


# ══════════════════════════════════════════════════════════════
# 트렌드 섹터 감지
# ══════════════════════════════════════════════════════════════

def detect_active_trend_sectors(
    curr_top_n: list[str],
    universe_map: dict,
) -> set[str]:
    """
    현재 시총 Top N에 있는 종목들의 GICS 섹터 = 활성 트렌드 섹터.
    (Unknown 제외)
    """
    sectors = set()
    for t in curr_top_n:
        sec = normalize_sector(universe_map.get(t, 'Unknown'))
        if sec != 'Unknown':
            sectors.add(sec)
    return sectors


# ══════════════════════════════════════════════════════════════
# 연관 섹터 계산 (정적 + 동적)
# ══════════════════════════════════════════════════════════════

def get_related_sectors(
    active_sectors: set[str],
    etf_data: dict,
    as_of,
    threshold: float = CORRELATION_THRESHOLD,
) -> set[str]:
    """
    활성 트렌드 섹터 + 연관 섹터 반환.
    - 정적: SECTOR_RELATIONS 매핑
    - 동적: 섹터 ETF 간 60일 수익률 상관관계 ≥ threshold

    Parameters
    ----------
    active_sectors : 활성 트렌드 섹터 집합 (GICS 정규화된 이름)
    etf_data       : dict[etf_ticker, DataFrame(OHLCV)]
    as_of          : 기준일
    threshold      : 상관관계 임계값

    Returns
    -------
    target_sectors : 활성 섹터 + 연관 섹터 집합
    """
    target = set(active_sectors)

    # ── 정적 매핑 ──────────────────────────────────────────
    for sec in list(active_sectors):
        for rel in SECTOR_RELATIONS.get(sec, []):
            target.add(normalize_sector(rel))

    # ── 동적 매핑: ETF 상관관계 ────────────────────────────
    etf_rets: dict[str, pd.Series] = {}
    for etf_sym in ALL_SECTOR_ETFS:
        if etf_sym not in etf_data:
            continue
        hist = etf_data[etf_sym][etf_data[etf_sym].index <= as_of]
        if len(hist) < CORR_WINDOW + 1:
            continue
        ret = hist['Close'].pct_change().dropna().tail(CORR_WINDOW)
        etf_rets[etf_sym] = ret

    # 활성 섹터에 해당하는 ETF 식별
    active_etfs = {
        etf for etf, sec in _ETF_TO_SECTOR.items()
        if sec in active_sectors and etf in etf_rets
    }

    for a_etf in active_etfs:
        for o_etf, o_ret in etf_rets.items():
            if o_etf == a_etf:
                continue
            o_sec = _ETF_TO_SECTOR.get(o_etf, '')
            if not o_sec or o_sec in target:
                continue
            aligned = pd.concat([etf_rets[a_etf], o_ret], axis=1, join='inner').dropna()
            if len(aligned) < 30:
                continue
            corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
            if corr >= threshold:
                target.add(o_sec)

    return target


# ══════════════════════════════════════════════════════════════
# 지표 계산
# ══════════════════════════════════════════════════════════════

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c, h, l, v = d['Close'], d['High'], d['Low'], d['Volume']
    d['MA20']    = ta.sma(c, 20)
    d['MA50']    = ta.sma(c, 50)
    d['MA200']   = ta.sma(c, 200)
    d['RSI']     = ta.rsi(c, 14)
    adx_res      = ta.adx(h, l, c, 14)
    d['ADX']     = adx_res['ADX_14'] if adx_res is not None and 'ADX_14' in adx_res.columns else np.nan
    d['VolMA20'] = v.rolling(20).mean()
    d['VolMA60'] = v.rolling(60).mean()
    d['High52w'] = h.rolling(252).max()
    atr_res      = ta.atr(h, l, c, length=ATR_PERIOD)
    d['ATR']     = atr_res if atr_res is not None else np.nan
    return d


def _swing_hh_hl(df_win: pd.DataFrame, n: int = 3) -> int:
    highs = df_win['High'].values
    lows  = df_win['Low'].values
    sh = [highs[i] for i in range(n, len(highs) - n)
          if highs[i] == max(highs[i - n:i + n + 1])]
    sl = [lows[i]  for i in range(n, len(lows) - n)
          if lows[i]  == min(lows[i - n:i + n + 1])]
    return min(
        sum(sh[i] > sh[i - 1] for i in range(1, len(sh))),
        sum(sl[i] > sl[i - 1] for i in range(1, len(sl))),
    )


# ══════════════════════════════════════════════════════════════
# 모멘텀 스크리닝 (screen_A 방식)
# ══════════════════════════════════════════════════════════════

def screen_momentum(df: pd.DataFrame, as_of, atr_mult: float = ATR_MULT) -> tuple[bool, dict]:
    """
    ADX + MA정배열 + RSI + 거래량/변동성 + HH-HL + 52주고점 + ATR스톱 필터.
    backtest_hybrid_entry.screen_A 와 동일 로직.
    """
    hist = df[df.index <= as_of]
    if len(hist) < 220:
        return False, {}

    row  = hist.iloc[-1]
    adx  = row.get('ADX', np.nan)
    if pd.isna(adx) or adx < ADX_THRESH:
        return False, {}

    ma20, ma50, ma200 = row.get('MA20'), row.get('MA50'), row.get('MA200')
    if any(pd.isna(v) for v in [ma20, ma50, ma200]) or not (ma20 > ma50 > ma200):
        return False, {}

    rsi = row.get('RSI', np.nan)
    if pd.isna(rsi) or not (RSI_LO <= rsi <= RSI_HI):
        return False, {}

    vol60 = row.get('VolMA60', np.nan)
    r20   = hist.tail(20)
    if pd.isna(vol60) or vol60 == 0 or (r20['Volume'] > vol60 * VOL_SPIKE).any():
        return False, {}

    r5 = hist.tail(6)
    if (r5['Close'].pct_change().abs() > DAILY_MOVE).any():
        return False, {}

    r60 = hist.tail(HH_HL_WINDOW)
    if len(r60) >= 2 * 3 + 1 and _swing_hh_hl(r60) < HH_HL_MIN:
        return False, {}

    high52 = row.get('High52w', np.nan)
    if not pd.isna(high52) and high52 > 0 and row['Close'] < high52 * PRICE_52W_THR:
        return False, {}

    r63    = hist.tail(63)
    ret3m  = float(hist['Close'].iloc[-1] / r63['Close'].iloc[0]) - 1 \
             if len(r63) >= 60 else np.nan
    vol_cv   = r20['Volume'].std() / (vol60 + 1e-9)
    vol_stab = float(1 / (vol_cv + 1e-6))

    atr_series = hist['ATR'].dropna() if 'ATR' in hist.columns else pd.Series(dtype=float)
    atr_val    = float(atr_series.iloc[-1]) if len(atr_series) > 0 else np.nan
    peak20     = float(hist['High'].tail(20).max())
    atr_stop   = peak20 - atr_val * atr_mult if not pd.isna(atr_val) else np.nan

    cur_price = float(hist['Close'].iloc[-1])
    if not pd.isna(atr_stop) and cur_price <= atr_stop:
        return False, {}

    return True, {
        'ADX':      float(adx),
        'RSI':      float(rsi),
        'ret3m':    ret3m,
        'vol_stab': vol_stab,
        'price':    cur_price,
        'atr_stop': atr_stop,
        'atr':      atr_val,
    }


# ══════════════════════════════════════════════════════════════
# 랭킹 & 포지션 사이징
# ══════════════════════════════════════════════════════════════

def _minmax(s: pd.Series) -> pd.Series:
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn + 1e-9)


def rank_stocks(passed: dict, etf_data: dict, universe_map: dict,
                as_of) -> pd.DataFrame:
    if not passed:
        return pd.DataFrame()
    df = pd.DataFrame(passed).T
    df['sector']  = [normalize_sector(universe_map.get(t, 'Unknown')) for t in df.index]
    df['sec_str'] = 0.0
    for idx, row in df.iterrows():
        sec = row['sector']
        etf_sym = SECTOR_ETF_MAP.get(sec)
        if etf_sym and etf_sym in etf_data:
            ec = etf_data[etf_sym][etf_data[etf_sym].index <= as_of]['Close']
            if len(ec) >= 63:
                df.loc[idx, 'sec_str'] = (
                    row['ret3m'] - float(ec.iloc[-1] / ec.iloc[-63] - 1)
                ) if not pd.isna(row['ret3m']) else 0.0
    df['sec_n'] = _minmax(df['sec_str'])
    df['score'] = (
        _minmax(df['ADX'])                 * WEIGHTS['adx']     +
        _minmax(df['ret3m'].fillna(0))     * WEIGHTS['ret3m']   +
        _minmax(df['sec_n'])               * WEIGHTS['sector']  +
        _minmax(df['vol_stab'])            * WEIGHTS['vol_stab']
    )
    return df.sort_values('score', ascending=False)


def position_weights(scores: pd.Series, max_w: float = MAX_WEIGHT) -> pd.Series:
    n = len(scores)
    if n == 0:
        return pd.Series(dtype=float)
    adj = scores.clip(lower=1e-9)
    w   = adj / adj.sum()
    for _ in range(20):
        if (w <= max_w + 1e-8).all():
            break
        excess = (w - max_w).clip(lower=0).sum()
        w      = w.clip(upper=max_w)
        under  = w < max_w
        if under.sum() > 0:
            w[under] += excess * w[under] / w[under].sum()
    return w / w.sum()


# ══════════════════════════════════════════════════════════════
# 통합 스크리닝 함수 (외부 공개 API)
# ══════════════════════════════════════════════════════════════

def screen_trend_momentum(
    all_data: dict,
    etf_data: dict,
    shares_map: dict,
    universe_map: dict,
    as_of,
    top_n: int = TOP_N,
    atr_mult: float = ATR_MULT,
) -> tuple[pd.DataFrame, set[str], list[str]]:
    """
    트렌드+모멘텀 스크리닝.

    Returns
    -------
    ranked_df      : 트렌드 섹터 필터 + 모멘텀 통과 종목 (점수순)
    target_sectors : 이번 기준일의 활성+연관 섹터 집합
    top_n_list     : 이번 기준일의 시총 Top N 종목 리스트
    """
    top_n_list     = get_top_n_market_cap(all_data, shares_map, as_of)
    active_sectors = detect_active_trend_sectors(top_n_list, universe_map)
    target_sectors = get_related_sectors(active_sectors, etf_data, as_of)

    passed = {}
    for ticker, df in all_data.items():
        sec = normalize_sector(universe_map.get(ticker, 'Unknown'))
        if sec not in target_sectors:
            continue
        ok, metrics = screen_momentum(df, as_of, atr_mult)
        if ok:
            passed[ticker] = metrics

    ranked = rank_stocks(passed, etf_data, universe_map, as_of)
    return ranked.head(top_n), target_sectors, top_n_list


# ══════════════════════════════════════════════════════════════
# 스탠드얼론 실행 (현재 시점 스크리닝)
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    sys.path.insert(0, str(_SCRIPTS))
    from data_cache import load_full_universe

    today = datetime.now().strftime('%Y-%m-%d')
    print('=' * 64)
    print(f'  트렌드+모멘텀 스크리너   기준일: {today}')
    print(f'  Top N 시총: {TOP_N_MARKET_CAP}   상관관계 임계값: {CORRELATION_THRESHOLD}')
    print('=' * 64)

    # [1] 데이터 로드
    print('\n[1] 풀 유니버스 데이터 로드...')
    all_data_raw, spy_df, etf_raw, universe_map = load_full_universe('2015-01-01')
    print(f'  → {len(all_data_raw)}종목 로드 완료')

    # [2] 지표 계산
    print('\n[2] 지표 계산...')
    all_data = {t: add_indicators(df) for t, df in all_data_raw.items()}
    etf_data = {t: add_indicators(df) for t, df in etf_raw.items()}

    # [3] Shares Outstanding 조회 (US 종목만)
    print('\n[3] Shares Outstanding 조회...')
    us_tickers = [t for t in all_data if not (t.endswith('.KS') or t.endswith('.KQ'))]
    shares_map = fetch_shares_outstanding(us_tickers)

    # [4] 트렌드+모멘텀 스크리닝
    as_of = pd.Timestamp(today)
    print(f'\n[4] 트렌드+모멘텀 스크리닝 (기준일: {today})...')
    top_n_list     = get_top_n_market_cap(all_data, shares_map, as_of)
    active_sectors = detect_active_trend_sectors(top_n_list, universe_map)
    target_sectors = get_related_sectors(active_sectors, etf_data, as_of)

    print(f'\n  ▶ 시총 Top {TOP_N_MARKET_CAP}: {", ".join(top_n_list[:5])} ...')
    print(f'  ▶ 활성 트렌드 섹터: {sorted(active_sectors)}')
    print(f'  ▶ 활성+연관 섹터:   {sorted(target_sectors)}')

    ranked_tm, _, _ = screen_trend_momentum(
        all_data, etf_data, shares_map, universe_map, as_of
    )

    print(f'\n  스크리닝 결과: {len(ranked_tm)}개 종목 통과\n')
    if not ranked_tm.empty:
        print(f"  {'순위'} {'종목':<13} {'섹터':<28} {'점수':>6} {'ADX':>5} {'RSI':>5} {'3M수익':>7}")
        print('  ' + '─' * 72)
        for rank, (ticker, row) in enumerate(ranked_tm.iterrows(), 1):
            ret_s = f"{row['ret3m']:+.1%}" if not pd.isna(row.get('ret3m')) else '  N/A'
            print(f"  {rank:2d}위  {ticker:<13} {row.get('sector',''):<28}"
                  f" {row['score']:>6.3f} {row['ADX']:>5.1f} {row['RSI']:>5.1f} {ret_s:>7}")
    else:
        print('  현재 조건을 통과한 종목이 없습니다.')
