#!/usr/bin/env python3
"""
Bitcoin 트레이딩 알고리즘 - 데이터 수집 모듈
무료 API만 사용:
  - BTC/ETH 가격: yfinance (Yahoo Finance)
  - BTC 시가총액/도미넌스: CoinGecko free API
  - Fear & Greed Index: alternative.me
  - Hash Rate + Active Addresses: blockchain.com public charts API
"""

import time
import warnings
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import date

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

START_DATE = "2015-01-01"

# ────────────────────────────────────────────────────────────────
# 헬퍼
# ────────────────────────────────────────────────────────────────

def _is_fresh(path: Path, max_age_days: int = 2) -> bool:
    """파일이 최근 max_age_days일 이내에 생성된 경우 True"""
    if not path.exists():
        return False
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if df.empty:
        return False
    try:
        last = pd.to_datetime(df.index[-1]).date()
        return last >= date.today() - pd.Timedelta(days=max_age_days)
    except Exception:
        return False


def _get_with_retry(url: str, headers: dict | None = None, timeout: int = 60,
                    max_retries: int = 3, wait: float = 5.0) -> requests.Response:
    """재시도 로직 포함 HTTP GET"""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers or {}, timeout=timeout)
            if resp.status_code == 429:  # rate limit
                wait_sec = 65
                print(f"  Rate limit (429). {wait_sec}초 대기 후 재시도...")
                time.sleep(wait_sec)
                continue
            return resp
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise
            print(f"  네트워크 오류 ({e}). {wait}초 후 재시도...")
            time.sleep(wait)
    raise RuntimeError(f"최대 재시도 초과: {url}")


# ────────────────────────────────────────────────────────────────
# 1. BTC / ETH 가격 (yfinance)
# ────────────────────────────────────────────────────────────────

def fetch_btc_price(start: str = START_DATE) -> pd.DataFrame:
    """BTC-USD OHLCV (yfinance)"""
    cache = DATA_DIR / "btc_price.csv"
    if _is_fresh(cache, max_age_days=1):
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        print(f"  [캐시] BTC 가격: {len(df)}행")
        return df

    print("  BTC-USD 다운로드 중...")
    raw = yf.download("BTC-USD", start=start, auto_adjust=True, progress=False)
    if raw.empty:
        raise RuntimeError("BTC-USD 데이터 다운로드 실패")

    # yfinance 버전별 MultiIndex 처리
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0].lower() for c in raw.columns]
    else:
        raw.columns = [c.lower() for c in raw.columns]
    raw.index.name = "date"
    raw.to_csv(cache)
    print(f"  BTC-USD 완료: {len(raw)}행 ({raw.index[0].date()} ~ {raw.index[-1].date()})")
    return raw


def fetch_eth_price(start: str = START_DATE) -> pd.DataFrame:
    """ETH-USD OHLCV — BTC 도미넌스 프록시 계산용"""
    cache = DATA_DIR / "eth_price.csv"
    if _is_fresh(cache, max_age_days=1):
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        print(f"  [캐시] ETH 가격: {len(df)}행")
        return df

    print("  ETH-USD 다운로드 중...")
    raw = yf.download("ETH-USD", start=start, auto_adjust=True, progress=False)
    if raw.empty:
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0].lower() for c in raw.columns]
    else:
        raw.columns = [c.lower() for c in raw.columns]
    raw.index.name = "date"
    raw.to_csv(cache)
    print(f"  ETH-USD 완료: {len(raw)}행")
    return raw


# ────────────────────────────────────────────────────────────────
# 2. BTC 도미넌스 + 총 시가총액 (CoinGecko free)
# ────────────────────────────────────────────────────────────────

def fetch_btc_dominance() -> pd.DataFrame:
    """
    CoinGecko free API로 BTC 시가총액 + 총 시가총액 수집 → 도미넌스 계산.
    총 시가총액 API 실패 시 ETH 시가총액 합산 방식으로 근사.
    """
    cache = DATA_DIR / "dominance.csv"
    if _is_fresh(cache, max_age_days=2):
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        print(f"  [캐시] 도미넌스: {len(df)}행")
        return df

    print("  CoinGecko BTC 시가총액 수집 중...")
    HEADERS = {"accept": "application/json", "User-Agent": "btc-algo-backtest/1.0"}

    # BTC 시가총액 이력
    btc_mcap_series = None
    try:
        url = ("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
               "?vs_currency=usd&days=max&interval=daily")
        resp = _get_with_retry(url, headers=HEADERS, timeout=90)
        if resp.status_code == 200:
            data = resp.json()
            btc_rows = data.get("market_caps", [])
            s = pd.DataFrame(btc_rows, columns=["ts", "btc_mcap"])
            s["date"] = pd.to_datetime(s["ts"], unit="ms").dt.normalize()
            s = s.drop_duplicates("date").set_index("date")["btc_mcap"]
            btc_mcap_series = s
            print(f"  BTC 시가총액 완료: {len(s)}행")
        else:
            print(f"  BTC 시가총액 실패 (HTTP {resp.status_code})")
    except Exception as e:
        print(f"  BTC 시가총액 예외: {e}")

    # 총 시가총액 이력 (무료 tier에서 가능 여부 불확실 → 시도)
    total_mcap_series = None
    time.sleep(2)
    try:
        url2 = "https://api.coingecko.com/api/v3/global/market_cap_chart?days=max"
        resp2 = _get_with_retry(url2, headers=HEADERS, timeout=90)
        if resp2.status_code == 200:
            data2 = resp2.json()
            # 응답 구조 탐색
            mcap_list = (data2.get("market_cap_chart", {}).get("market_cap")
                         or data2.get("total_market_caps")
                         or data2.get("market_cap"))
            if mcap_list:
                s2 = pd.DataFrame(mcap_list, columns=["ts", "total_mcap"])
                s2["date"] = pd.to_datetime(s2["ts"], unit="ms").dt.normalize()
                s2 = s2.drop_duplicates("date").set_index("date")["total_mcap"]
                total_mcap_series = s2
                print(f"  총 시가총액 완료: {len(s2)}행")
        else:
            print(f"  총 시가총액 API 실패 (HTTP {resp2.status_code})")
    except Exception as e:
        print(f"  총 시가총액 예외: {e}")

    # ETH 시가총액으로 보완 (fallback)
    if total_mcap_series is None and btc_mcap_series is not None:
        print("  ETH 시가총액으로 총 시가총액 근사 시도...")
        time.sleep(2)
        try:
            url3 = ("https://api.coingecko.com/api/v3/coins/ethereum/market_chart"
                    "?vs_currency=usd&days=max&interval=daily")
            resp3 = _get_with_retry(url3, headers=HEADERS, timeout=90)
            if resp3.status_code == 200:
                data3 = resp3.json()
                eth_rows = data3.get("market_caps", [])
                s3 = pd.DataFrame(eth_rows, columns=["ts", "eth_mcap"])
                s3["date"] = pd.to_datetime(s3["ts"], unit="ms").dt.normalize()
                s3 = s3.drop_duplicates("date").set_index("date")["eth_mcap"]
                # BTC + ETH ≈ 60~80% of total market cap (근사치로 역산)
                # BTC 도미넌스가 평균 ~45%라고 가정하면 total = btc_mcap / 0.45
                # 더 안정적 방법: BTC/(BTC+ETH) 비율을 프록시로 사용
                combined = pd.concat([btc_mcap_series, s3], axis=1).dropna()
                combined.columns = ["btc_mcap", "eth_mcap"]
                combined["btc_eth_dominance"] = (
                    combined["btc_mcap"] / (combined["btc_mcap"] + combined["eth_mcap"]) * 100
                )
                # 이 값을 btc_dominance_proxy로 저장
                df_out = combined.copy()
                df_out["btc_dominance"] = np.nan  # 실제 도미넌스 없음
                df_out.to_csv(cache)
                print(f"  ETH 프록시 도미넌스 완료: {len(df_out)}행")
                return df_out
        except Exception as e:
            print(f"  ETH 시가총액 예외: {e}")

    # 결과 조합
    if btc_mcap_series is not None and total_mcap_series is not None:
        df_out = pd.DataFrame({
            "btc_mcap": btc_mcap_series,
            "total_mcap": total_mcap_series,
        }).dropna()
        df_out["btc_dominance"] = df_out["btc_mcap"] / df_out["total_mcap"] * 100
        df_out.to_csv(cache)
        print(f"  도미넌스 계산 완료: {len(df_out)}행 "
              f"(도미넌스 {df_out['btc_dominance'].mean():.1f}% 평균)")
        return df_out
    elif btc_mcap_series is not None:
        df_out = pd.DataFrame({"btc_mcap": btc_mcap_series, "btc_dominance": np.nan})
        df_out.to_csv(cache)
        return df_out
    else:
        print("  도미넌스 데이터 수집 완전 실패 — BTC/ETH 가격 비율로 대체 예정")
        return pd.DataFrame()


# ────────────────────────────────────────────────────────────────
# 3. Fear & Greed Index (alternative.me)
# ────────────────────────────────────────────────────────────────

def fetch_fear_greed() -> pd.DataFrame:
    """alternative.me Fear & Greed Index (2018-02-01 ~, 무료, 키 불필요)"""
    cache = DATA_DIR / "fear_greed.csv"
    if _is_fresh(cache, max_age_days=1):
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        print(f"  [캐시] Fear&Greed: {len(df)}행")
        return df

    print("  Fear & Greed Index 수집 중...")
    try:
        url = "https://api.alternative.me/fng/?limit=0&format=json"
        resp = _get_with_retry(url, timeout=30)
        resp.raise_for_status()
        records = resp.json()["data"]

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s").dt.normalize()
        df["fear_greed"] = df["value"].astype(float)
        df = (df[["date", "fear_greed"]]
              .drop_duplicates("date")
              .set_index("date")
              .sort_index())
        df.to_csv(cache)
        print(f"  Fear&Greed 완료: {len(df)}행 ({df.index[0].date()} ~ {df.index[-1].date()})")
        return df
    except Exception as e:
        print(f"  Fear&Greed 수집 실패: {e}")
        return pd.DataFrame()


# ────────────────────────────────────────────────────────────────
# 4. Hash Rate (blockchain.com)
# ────────────────────────────────────────────────────────────────

def fetch_hash_rate() -> pd.DataFrame:
    """blockchain.com Hash Rate 이력 (무료, 키 불필요)"""
    cache = DATA_DIR / "hash_rate.csv"
    if _is_fresh(cache, max_age_days=7):
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        print(f"  [캐시] Hash Rate: {len(df)}행")
        return df

    print("  Hash Rate 수집 중 (blockchain.com)...")
    try:
        url = ("https://api.blockchain.info/charts/hash-rate"
               "?timespan=all&format=json&sampled=true")
        resp = _get_with_retry(url, timeout=90)
        resp.raise_for_status()
        values = resp.json()["values"]

        df = pd.DataFrame(values, columns=["x", "y"])
        df["date"] = pd.to_datetime(df["x"], unit="s").dt.normalize()
        df["hash_rate"] = df["y"].astype(float)
        df = (df[["date", "hash_rate"]]
              .drop_duplicates("date")
              .set_index("date")
              .sort_index())
        df.to_csv(cache)
        print(f"  Hash Rate 완료: {len(df)}행")
        return df
    except Exception as e:
        print(f"  Hash Rate 수집 실패: {e}")
        return pd.DataFrame()


# ────────────────────────────────────────────────────────────────
# 5. Active Addresses (blockchain.com)
# ────────────────────────────────────────────────────────────────

def fetch_active_addresses() -> pd.DataFrame:
    """blockchain.com 일별 고유 주소 수 (무료, 키 불필요)"""
    cache = DATA_DIR / "active_addresses.csv"
    if _is_fresh(cache, max_age_days=7):
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        print(f"  [캐시] Active Addresses: {len(df)}행")
        return df

    print("  Active Addresses 수집 중 (blockchain.com)...")
    try:
        url = ("https://api.blockchain.info/charts/n-unique-addresses"
               "?timespan=all&format=json&sampled=true")
        resp = _get_with_retry(url, timeout=90)
        resp.raise_for_status()
        values = resp.json()["values"]

        df = pd.DataFrame(values, columns=["x", "y"])
        df["date"] = pd.to_datetime(df["x"], unit="s").dt.normalize()
        df["active_addr"] = df["y"].astype(float)
        df = (df[["date", "active_addr"]]
              .drop_duplicates("date")
              .set_index("date")
              .sort_index())
        df.to_csv(cache)
        print(f"  Active Addresses 완료: {len(df)}행")
        return df
    except Exception as e:
        print(f"  Active Addresses 수집 실패: {e}")
        return pd.DataFrame()


# ────────────────────────────────────────────────────────────────
# 통합 데이터 로더
# ────────────────────────────────────────────────────────────────

def load_all_data(start: str = START_DATE) -> pd.DataFrame:
    """
    모든 데이터를 수집하고 일별 DataFrame으로 병합.

    컬럼:
      open/high/low/close/volume  — BTC OHLCV
      eth_close                  — ETH 종가
      btc_mcap                   — BTC 시가총액 (USD)
      total_mcap                 — 총 암호화폐 시가총액 (있으면)
      btc_dominance              — BTC 도미넌스 % (있으면)
      btc_eth_dominance          — BTC/(BTC+ETH) % (fallback)
      fear_greed                 — F&G 지수 0~100
      hash_rate                  — TH/s
      active_addr                — 일별 고유 주소 수
    """
    print("\n" + "="*55)
    print("  데이터 수집 시작")
    print("="*55)

    btc   = fetch_btc_price(start)
    eth   = fetch_eth_price(start)
    dom   = fetch_btc_dominance()
    fg    = fetch_fear_greed()
    hr    = fetch_hash_rate()
    aa    = fetch_active_addresses()

    print("\n  데이터 병합 중...")
    df = btc.copy()
    df.index = pd.to_datetime(df.index)

    # ETH
    if not eth.empty and "close" in eth.columns:
        eth.index = pd.to_datetime(eth.index)
        df["eth_close"] = eth["close"].reindex(df.index)

    # 도미넌스
    if not dom.empty:
        dom.index = pd.to_datetime(dom.index)
        for col in ["btc_mcap", "total_mcap", "btc_dominance", "btc_eth_dominance"]:
            if col in dom.columns:
                df[col] = dom[col].reindex(df.index)

    # 도미넌스 최종 프록시 결정
    # btc_dominance가 없거나 비어있으면 btc_eth_dominance 사용
    if "btc_dominance" not in df.columns or df["btc_dominance"].isna().mean() > 0.8:
        if "btc_eth_dominance" in df.columns:
            print("  → 도미넌스 실제값 부재: btc_eth_dominance 프록시 사용")
            df["dom"] = df["btc_eth_dominance"]
        elif "eth_close" in df.columns:
            print("  → 도미넌스 프록시: BTC/(BTC+ETH) 가격 기반")
            btc_cap_proxy = df["close"]
            eth_cap_proxy = df["eth_close"].ffill()
            df["dom"] = btc_cap_proxy / (btc_cap_proxy + eth_cap_proxy) * 100
        else:
            df["dom"] = 50.0  # 중립
    else:
        df["dom"] = df["btc_dominance"]

    # F&G
    if not fg.empty:
        fg.index = pd.to_datetime(fg.index)
        df["fear_greed"] = fg["fear_greed"].reindex(df.index)

    # Hash Rate (주간 샘플 → 일별 보간)
    if not hr.empty:
        hr.index = pd.to_datetime(hr.index)
        df["hash_rate"] = hr["hash_rate"].reindex(df.index).interpolate("time")

    # Active Addresses (주간 샘플 → 일별 보간)
    if not aa.empty:
        aa.index = pd.to_datetime(aa.index)
        df["active_addr"] = aa["active_addr"].reindex(df.index).interpolate("time")

    # 시작일 필터
    df = df[df.index >= pd.Timestamp(start)].copy()

    # 결측치 처리 (forward fill)
    ffill_cols = ["dom", "hash_rate", "active_addr"]
    for c in ffill_cols:
        if c in df.columns:
            df[c] = df[c].ffill()

    print(f"\n  병합 완료: {df.index[0].date()} ~ {df.index[-1].date()}, "
          f"{len(df)}행, 컬럼={list(df.columns)}\n")
    return df


if __name__ == "__main__":
    df = load_all_data()
    print(df.tail(5).to_string())
