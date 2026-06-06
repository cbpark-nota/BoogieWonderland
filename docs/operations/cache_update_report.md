# 백테스트 캐시 시간 누락 업데이트 보고

## 실행
- 일시: 2026-05-01
- 스크립트: `scripts/update_market_caches.py`

## 결과

### 일봉 주식 캐시 (`data/full_universe/`)

| 항목 | 값 |
|---|---|
| 캐시 디렉토리 | `data/full_universe/` (메인 레포) |
| 대상 파일 | 875개 (S&P500 + NASDAQ100 + KOSPI200 + KOSDAQ150 + 섹터 ETF + SPY) |
| 갱신된 파일 | 875개 |
| 신규 행 합계 | 23,701개 |
| 갱신 전 `downloaded_at` | 2026-03-24 |
| 갱신 후 `downloaded_at` | 2026-05-01 |

배치 그룹 (마지막 timestamp 기준):
- `2026-03-07` → 다운로드 1종목 (38행)
- `2026-03-24` → 다운로드 874종목 (23,663행)

### 4시간봉 암호화폐 캐시

| 자산 | 경로 | 갱신 전 마지막 | 신규 행 | 소스 |
|---|---|---|---|---|
| BTC | `scripts/crypto/data/btc_4h.csv` | 2026-04-15 12:00 UTC | 91 | Binance |
| ETH | `scripts/crypto/data/eth_4h.csv` | (없음 → 신규 생성) | 11,674 | Binance |

> ETH 캐시는 기존에 없어서 2021-01-01부터 일괄 생성. 갱신 후 두 캐시 모두 2026-04-30 16:00 UTC까지 데이터 보유.

## ⚠️ 생존자 편향 한계

이번 작업은 **현재 지수 구성 종목**에 한해 시간 누락만 보충한 것이다. 다음 한계가 그대로 남아 있다:

- 2026-03-24 ~ 2026-05-01 구간에 지수에서 편입된 신규 종목이 있다면 캐시에 포함되지 않는다. (캐시에는 manifest 기준 종목만 있음)
- 과거(2015~) 시점에 지수에 있었으나 그 후 편출·상장폐지된 종목은 여전히 빠져 있다 → 백테스트는 본질적으로 생존자 편향을 안고 있다.

편출 종목을 복원하려면 별도 작업이 필요하다 (예: `scripts/data_cache.py`의 유니버스 수집을 *과거 시점 기준*으로 가져오도록 재설계). 본 PR은 시간 누락만 처리하므로 **편출 종목 복원은 후속 과제**로 남겨둔다.

## 사용법

```bash
# 일봉 + 4h 모두 갱신
python scripts/update_market_caches.py --verbose

# 특정 영역만
python scripts/update_market_caches.py --skip-crypto --verbose
python scripts/update_market_caches.py --skip-stocks --verbose

# 다운로드만 하고 저장 안 함 (검증용)
python scripts/update_market_caches.py --dry-run --verbose
```
