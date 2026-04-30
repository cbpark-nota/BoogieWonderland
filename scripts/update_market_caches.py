"""
백테스트 데이터 캐시 최신화 (시간 누락 보충)
══════════════════════════════════════════════════════════════
각 캐시의 마지막 timestamp 확인 → 그 이후 ~ 현재까지 다운로드 → append.

대상:
  · data/full_universe/{TICKER}.parquet  (S&P500 + NASDAQ100 + KOSPI200 + KOSDAQ150 + ETF + SPY)
  · scripts/crypto/data/btc_4h.csv       (Binance + yfinance fallback)
  · scripts/crypto/data/eth_4h.csv       (Binance + yfinance fallback)

⚠️ 생존자 편향 한계:
  현재 지수 구성 종목만 다운로드되므로 과거 편출 종목은 빠져있음.
  이 스크립트는 *시간 누락만* 채움. 편출 종목 복원은 별개 작업.
══════════════════════════════════════════════════════════════
"""
import argparse
import json
import logging
import sys
import warnings
from datetime import date, datetime
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*yfinance.*")

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR))


def _resolve_full_universe_dir() -> Path:
    """worktree 환경에서 main repo의 data/full_universe 경로 탐색."""
    candidates = [
        _THIS_DIR.parent / "data" / "full_universe",
        _THIS_DIR.parents[3] / "data" / "full_universe",  # worktree → main
    ]
    for d in candidates:
        if (d / "manifest.json").exists():
            return d
    raise FileNotFoundError(f"full_universe 캐시 미발견: {candidates}")


def _resolve_crypto_dir() -> Path:
    """worktree 환경에서 main repo의 scripts/crypto/data 경로 탐색."""
    candidates = [
        _THIS_DIR / "crypto" / "data",
        _THIS_DIR.parents[3] / "scripts" / "crypto" / "data",
    ]
    for d in candidates:
        if d.exists():
            return d
    # 없으면 worktree 안쪽 경로 그대로 (생성됨)
    return candidates[0]


# ══════════════════════════════════════════════════════════════
# 일봉 캐시 (parquet) 업데이트
# ══════════════════════════════════════════════════════════════

def _last_date(df: pd.DataFrame) -> pd.Timestamp | None:
    if df.empty:
        return None
    return pd.to_datetime(df.index.max())


def _yf_download_batch(tickers: list[str], start: str, end: str) -> dict:
    if not tickers:
        return {}
    try:
        raw = yf.download(
            tickers,
            start=start,
            end=end,
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        logger.warning("yfinance 배치 실패 (%s): %s", start, e)
        return {}
    if raw.empty:
        return {}
    out: dict[str, pd.DataFrame] = {}
    if isinstance(raw.columns, pd.MultiIndex):
        for t in tickers:
            try:
                df = raw.xs(t, axis=1, level=1).dropna(how="all")
                if not df.empty:
                    out[t] = df
            except Exception:
                pass
    elif len(tickers) == 1:
        if not raw.empty:
            out[tickers[0]] = raw
    return out


def _normalize_new(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance OHLCV → 캐시와 동일한 컬럼·dtype으로 정규화."""
    required = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in required):
        return pd.DataFrame()
    out = df[required].copy()
    out.index = pd.to_datetime(out.index)
    out.index.name = "Date"
    for col in ("Open", "High", "Low", "Close"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["Volume"] = pd.to_numeric(out["Volume"], errors="coerce").fillna(0).astype("int64")
    out = out.dropna(subset=["Close"])
    return out


def update_full_universe(dry_run: bool = False) -> dict:
    """모든 parquet 캐시에 시간 누락분 append."""
    cache_dir = _resolve_full_universe_dir()
    manifest_path = cache_dir / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    today = pd.Timestamp.today().normalize()
    end_str = (today + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    # 모든 파일 (stocks + etfs + spy) 수집
    targets: list[tuple[str, Path]] = []
    for ticker, fname in manifest.get("stocks", {}).items():
        targets.append((ticker, cache_dir / fname))
    for ticker, fname in manifest.get("etfs", {}).items():
        targets.append((ticker, cache_dir / fname))
    targets.append(("SPY", cache_dir / "spy.parquet"))

    # 마지막 date 별로 그룹핑하여 배치 다운로드
    by_last: dict[str, list[tuple[str, Path]]] = {}
    skipped = 0
    for ticker, path in targets:
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
        except Exception:
            continue
        last = _last_date(df)
        if last is None:
            continue
        next_start = (last + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        if next_start >= end_str:
            skipped += 1
            continue
        by_last.setdefault(next_start, []).append((ticker, path))

    summary = {
        "cache_dir": str(cache_dir),
        "total_targets": len(targets),
        "already_up_to_date": skipped,
        "updated": 0,
        "new_rows_total": 0,
        "groups": {},
    }

    for start_str, group in sorted(by_last.items()):
        tickers = [t for t, _ in group]
        path_map = {t: p for t, p in group}
        logger.info("배치 다운로드 [%s ~ %s] %d종목", start_str, end_str, len(tickers))
        new_rows_group = 0
        updated_group = 0

        for i in range(0, len(tickers), 50):
            batch = tickers[i:i + 50]
            new_data = _yf_download_batch(batch, start_str, end_str)
            for t in batch:
                df_new_raw = new_data.get(t)
                if df_new_raw is None or df_new_raw.empty:
                    continue
                df_new = _normalize_new(df_new_raw)
                if df_new.empty:
                    continue
                path = path_map[t]
                try:
                    df_old = pd.read_parquet(path)
                except Exception:
                    continue
                df_old.index = pd.to_datetime(df_old.index)
                df_new = df_new[df_new.index > df_old.index.max()]
                if df_new.empty:
                    continue
                df_combined = pd.concat([df_old, df_new]).sort_index()
                df_combined = df_combined[~df_combined.index.duplicated(keep="last")]
                if not dry_run:
                    df_combined.to_parquet(path)
                new_rows_group += len(df_new)
                updated_group += 1

        summary["groups"][start_str] = {
            "tickers": len(tickers),
            "updated": updated_group,
            "new_rows": new_rows_group,
        }
        summary["updated"] += updated_group
        summary["new_rows_total"] += new_rows_group

    # manifest.json downloaded_at 갱신
    if not dry_run and summary["updated"] > 0:
        manifest["downloaded_at"] = date.today().isoformat()
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    return summary


# ══════════════════════════════════════════════════════════════
# Crypto 4h 캐시 업데이트
# ══════════════════════════════════════════════════════════════

def _update_crypto_4h(symbol: str, csv_path: Path, yf_ticker: str) -> dict:
    """Binance API로 증분 다운로드. 실패 시 yfinance fallback (1h→4h 리샘플)."""
    import requests
    import time

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    now_ts = pd.Timestamp.now(tz="UTC")

    if csv_path.exists():
        df_old = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        df_old.index = pd.to_datetime(df_old.index, utc=True)
        last_ts = df_old.index.max()
    else:
        df_old = pd.DataFrame()
        last_ts = pd.Timestamp("2021-01-01", tz="UTC")

    inc_start_ms = int(last_ts.timestamp() * 1000) + 4 * 3600 * 1000
    now_ms = int(now_ts.timestamp() * 1000)

    if inc_start_ms >= now_ms:
        return {
            "symbol": symbol,
            "path": str(csv_path),
            "last_ts": str(last_ts),
            "new_rows": 0,
            "source": "noop",
        }

    # ── Binance 시도 ─────────────────────────────────
    rows: list = []
    cur = inc_start_ms
    binance_ok = True
    while cur < now_ms:
        params = {
            "symbol": symbol,
            "interval": "4h",
            "startTime": cur,
            "endTime": now_ms,
            "limit": 1000,
        }
        try:
            resp = requests.get(
                "https://api.binance.com/api/v3/klines",
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            page = resp.json()
        except Exception as e:
            logger.warning("  Binance %s 실패 (%s) — yfinance fallback", symbol, e)
            binance_ok = False
            break
        if not page:
            break
        rows.extend(page)
        cur = page[-1][0] + 4 * 3600 * 1000
        time.sleep(0.05)

    df_new = pd.DataFrame()
    source = "binance" if binance_ok else ""
    if binance_ok and rows:
        df_new = pd.DataFrame(
            rows,
            columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_vol", "n_trades",
                "taker_base", "taker_quote", "ignore",
            ],
        )
        df_new["open_time"] = pd.to_datetime(df_new["open_time"], unit="ms", utc=True)
        df_new = df_new.set_index("open_time")
        df_new = df_new[["open", "high", "low", "close", "volume"]].astype(float)
        df_new = df_new[~df_new.index.duplicated(keep="first")].sort_index()

    # ── yfinance fallback ───────────────────────────
    if not binance_ok or df_new.empty:
        try:
            yf_df = yf.download(
                yf_ticker,
                start=last_ts.strftime("%Y-%m-%d"),
                interval="1h",
                auto_adjust=True,
                progress=False,
            )
            if not yf_df.empty:
                yf_df.index = pd.to_datetime(yf_df.index, utc=True)
                yf_df = yf_df.rename(columns={
                    "Open": "open", "High": "high", "Low": "low",
                    "Close": "close", "Volume": "volume",
                })
                # 1h → 4h 리샘플
                df_4h = yf_df.resample("4h").agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }).dropna()
                df_new = df_4h[df_4h.index > last_ts]
                source = "yfinance"
        except Exception as e:
            logger.warning("  yfinance %s 실패: %s", yf_ticker, e)

    new_rows = 0
    if not df_new.empty:
        df_combined = pd.concat([df_old, df_new]) if not df_old.empty else df_new
        df_combined = df_combined[~df_combined.index.duplicated(keep="last")].sort_index()
        df_combined.to_csv(csv_path)
        new_rows = len(df_new)

    return {
        "symbol": symbol,
        "path": str(csv_path),
        "last_ts_before": str(last_ts),
        "new_rows": new_rows,
        "source": source or "none",
    }


def update_crypto() -> list[dict]:
    crypto_dir = _resolve_crypto_dir()
    return [
        _update_crypto_4h("BTCUSDT", crypto_dir / "btc_4h.csv", "BTC-USD"),
        _update_crypto_4h("ETHUSDT", crypto_dir / "eth_4h.csv", "ETH-USD"),
    ]


# ══════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="백테스트 캐시 시간 누락 업데이트")
    parser.add_argument("--skip-stocks", action="store_true", help="주식 캐시 갱신 건너뜀")
    parser.add_argument("--skip-crypto", action="store_true", help="암호화폐 캐시 갱신 건너뜀")
    parser.add_argument("--dry-run", action="store_true", help="다운로드만 하고 저장 안 함")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    summary = {"stocks": None, "crypto": None}

    if not args.skip_stocks:
        summary["stocks"] = update_full_universe(dry_run=args.dry_run)

    if not args.skip_crypto:
        summary["crypto"] = update_crypto()

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
