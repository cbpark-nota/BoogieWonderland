# 모멘텀 주식 투자 앱 — 프로젝트 인수인계 문서

> 최종 업데이트: 2026-03-23 (v3 최적 파라미터 반영)

---

## 1. 프로젝트 개요

**목적:** 모멘텀 기반 주식 스크리닝 + 4전략 선택 + 포트폴리오 관리 크로스플랫폼 투자 보조 앱

**대상 시장:** 미국 (S&P500) + 한국 (KOSPI/KOSDAQ)

**투자 철학:** 계단식 상승 주도주 추종 — 급등주를 피하고 구조적으로 상승 중인 종목에 투자

**배포:** GitHub Pages (서버리스) + Docker (풀스택)

---

## 2. 기술 스택

| 레이어 | 기술 | 비고 |
|---|---|---|
| 프론트엔드 | Flutter 3.41.5 (Dart, Riverpod) | iOS·Android·Web·macOS·Windows |
| 백엔드 | FastAPI + PostgreSQL + APScheduler | 스크리닝 배치 서버 |
| 주가 데이터 | yfinance (무료) | MVP 단계 |
| ORM | SQLAlchemy 2.0 (async + asyncpg) | |
| 푸시 알림 | Firebase Cloud Messaging | |
| 패키지 관리 | Python: uv, Flutter: fvm | |
| 데이터 수집 | Docker cron 컨테이너 | KST 23:00 KR, 07:00 US |
| CI/CD | GitHub Actions | 서버리스 웹 자동 배포 |

---

## 3. 개발 환경

### Mac (Darwin)
```bash
source .venv/bin/activate        # Python 가상환경
fvm flutter <command>            # Flutter (FVM)
uv add <패키지>                   # Python 의존성 추가
```

### 공용 머신 (Linux)
```bash
docker compose up -d             # 전체 서비스
docker compose run collector python collect_daily.py all  # 수동 수집
```

---

## 4. 디렉토리 구조

```
/
├── CLAUDE.md                        # Claude 규칙
├── .project-context.md              # 프로젝트 요약 (빠른 파악용)
├── pyproject.toml                   # Python 의존성
├── docker-compose.yml               # db + backend + collector
│
├── scripts/
│   ├── screener/
│   │   ├── screener_v1.py           # 스크리너 v1 (기본)
│   │   ├── screener_v2.py           # 스크리너 v2 (개선)
│   │   └── screener_v3.py           # 스크리너 v3 (프로덕션)
│   ├── backtest/
│   │   ├── backtest_adaptive.py     # 적응형 전략 멀티 윈도우 백테스트
│   │   ├── backtest_full_universe.py # 풀 유니버스 백테스트
│   │   ├── backtest_atr_tuning.py   # ATR 승수 튜닝
│   │   └── results/                 # 출력 (.csv, .png)
│   ├── monitor/
│   │   ├── monitor.py               # 스톱로스 체커
│   │   └── download_data.py         # 백테스트 데이터 캐시
│   ├── collector/
│   │   ├── collect_daily.py         # 일별 시장 데이터 수집
│   │   ├── Dockerfile               # cron 컨테이너
│   │   └── crontab                  # 수집 스케줄
│   └── export_json.py               # 4전략 → JSON (서버리스용)
│
├── crypto/
│   ├── collect_data.py              # BTC 온체인/시장 데이터 수집 (yfinance, blockchain.com, alternative.me)
│   ├── backtest_btc.py              # BTC 장기 매매 알고리즘 v1~v5 백테스트
│   ├── backtest_btc_daytrading.py   # BTC 데이 트레이딩 v1~v5 백테스트 (일봉)
│   ├── btc_daytrading_v2.py         # BTC 데이 트레이딩 v1~v10 (일봉, 스퀴즈 모멘텀 기반)
│   ├── btc_daytrading_4h.py         # BTC 데이 트레이딩 v1~v10 (4시간봉, Binance API)
│   └── btc_signal_v10.py            # V10 알고리즘 독립 실행 시그널 체커
│
├── backend/
│   ├── app/main.py                  # FastAPI 엔트리포인트
│   ├── app/config.py                # Pydantic Settings
│   ├── app/database.py              # SQLAlchemy async
│   ├── app/scheduler.py             # 배치 스케줄러
│   ├── app/models/                  # ORM (stock, portfolio, market)
│   ├── app/schemas/                 # Pydantic 스키마
│   ├── app/services/                # screener, monitor, notification
│   ├── app/routers/                 # screening, portfolio, market
│   ├── alembic/                     # DB 마이그레이션
│   └── tests/                       # pytest 단위 테스트
│
├── frontend/
│   ├── lib/main.dart                # 앱 엔트리 (서버리스/풀스택 분기)
│   ├── lib/config/                  # ApiConfig, AppConfig
│   ├── lib/models/                  # ScreeningResult, Holding, StrategyType
│   ├── lib/services/                # ApiClient, StaticDataSource, LocalPortfolioService
│   ├── lib/providers/               # Riverpod (screening, portfolio, market, serverless)
│   ├── lib/screens/                 # Dashboard, Screening, Portfolio, Settings
│   ├── lib/widgets/                 # StockCard, MarketStatusBanner, StopLossIndicator
│   └── test/                        # flutter test 단위 테스트
│
├── docs/                            # 프로젝트 문서
└── .github/workflows/               # CI/CD
```

---

## 5. 핵심 알고리즘

### 스크리너 v3 (프로덕션)

**스크리닝 조건** (모두 통과해야 후보 등록):
- ADX ≥ 20 (추세 강도, v3: 25→20 완화)
- 20MA > 50MA > 200MA (이동평균 정배열)
- RSI 50~77 (과매수/과매도 제외, v3: 75→77 완화)
- 거래량 급등 없음 (20일 내 60일평균 3배 초과 없음)
- 단기 급등 없음 (5일 내 ±10% 변동 없음)
- HH-HL 스윙 패턴 2회 이상 (60일, v3: 3회→2회 완화)
- 현재가 ≥ 52주 고점의 75% (v3: 80%→75% 완화)

**복합점수:**
```
점수 = ADX×0.4 + 3개월수익률×0.3 + 섹터ETF초과수익률×0.2 + 거래량안정성×0.1
```

**포지션:** 점수 비례 배분, 단일 종목 최대 10% (v3: 20%→10%), 상위 10개

**스크리닝 유니버스 (v3):** S&P 500 + KOSPI 200 + KOSDAQ 150 동적 수집 (~850개, 구버전 하드코딩 59개 → 교체)

### 4전략 프리셋

| 전략 | ATR 승수 | 리밸런싱 | 스톱로스 |
|---|---|---|---|
| 공격적 | 1.5 | 격주 | 좁은 스톱, 빠른 교체 |
| 균형형 | 2.0 | 격주 | 중간 |
| 보수적 | 2.5 | 격주 | 넓은 스톱, 느린 교체 |
| 적응형 | 동적 | 격주 | 3계층 국면 판별로 자동 전환 |

### 국면 판별 (적응형 전략)

```
Layer 1 (추세): SPY 50MA vs 200MA gap
  gap > 5%  → 공격적 / 0~5% → 균형형 / < 0% → 보수적

Layer 2 (모멘텀): RSI + MA 기울기로 1단계 다운그레이드
  RSI < 35 또는 20MA 기울기 < -3% → 한 단계 보수적

Layer 3 (리스크): 즉시 보수적 전환
  주간 수익률 < -5% / 200MA 하회+RSI<40 / 변동성 상위10%+하락

비대칭 전환: 다운그레이드 즉시, 업그레이드 1주 확인
```

---

## 5-1. Crypto 모듈 (BTC 트레이딩)

### 파일 구성

| 파일 | 설명 |
|---|---|
| `crypto/collect_data.py` | BTC 온체인/시장 데이터 수집. yfinance(가격), blockchain.com(해시레이트·NVT), alternative.me(공포탐욕지수) API 통합 |
| `crypto/backtest_btc.py` | BTC 장기 매매 알고리즘 v1~v5 백테스트 (일봉 기반, 다중 전략 비교) |
| `crypto/backtest_btc_daytrading.py` | BTC 데이 트레이딩 v1~v5 백테스트 (일봉 기반, 단기 매매 로직) |
| `crypto/btc_daytrading_v2.py` | BTC 데이 트레이딩 v1~v10 구현 (일봉). 스퀴즈 모멘텀(TTM Squeeze) 기반, v6~v10은 2021+ 데이터 최적화 |
| `crypto/btc_daytrading_4h.py` | BTC 데이 트레이딩 v1~v10 구현 (4시간봉). Binance API로 OHLCV 수집, 전략별 백테스트 지원 |
| `crypto/btc_signal_v10.py` | V10 알고리즘 독립 실행 시그널 체커. 현재 BTC 시장 상태를 분석해 매수/매도/홀드 신호 출력 |

### 실행 명령어

```bash
source .venv/bin/activate
python crypto/collect_data.py                    # BTC 데이터 수집
python crypto/backtest_btc.py                    # BTC 장기 전략 v1~v5 백테스트
python crypto/backtest_btc_daytrading.py         # BTC 데이 트레이딩 v1~v5 백테스트
python crypto/btc_daytrading_v2.py               # BTC 데이 트레이딩 v1~v10 백테스트 (일봉)
python crypto/btc_daytrading_4h.py               # BTC 데이 트레이딩 v1~v10 백테스트 (4h봉)
python crypto/btc_signal_v10.py                  # 현재 BTC V10 시그널 확인
```

---

## 6. 백테스트 결과 요약

### 현대시장 (2015-2024, 거래비용 편도 0.1%)

| 전략 | CAGR | MDD | 샤프 |
|---|---|---|---|
| 공격적 | +53.0% | -8.5% | 3.10 |
| 적응형 | +44.0% | -10.6% | 2.65 |
| 보수적 | +39.8% | -3.9% | 4.54 |
| 균형형 | +39.3% | -10.4% | 3.33 |
| SPY | +13.1% | -33.7% | 0.36 |

상세: `docs/backtest_results.md`, `docs/adaptive_strategy_results.md`, `docs/full_universe_refit_report.md`

---

## 7. 배포 모드

### 서버리스 (GitHub Pages)
```bash
# 빌드
fvm flutter build web --release \
  --base-href "/BoogieWonderland/" \
  --dart-define=DEPLOY_MODE=serverless

# 자동: main push 시 GitHub Actions로 배포
# URL: https://cbpark-nota.github.io/BoogieWonderland/
```

- `export_json.py`가 4전략 스크리닝 → `screening_strategies.json` 생성
- Flutter 앱이 정적 JSON 읽어서 표시
- 포트폴리오는 localStorage (SharedPreferences)

### 풀스택 (Docker)
```bash
docker compose up -d   # db + backend + collector
```

- Flutter 앱이 FastAPI 백엔드와 통신
- PostgreSQL에 데이터 영속화
- APScheduler로 배치 스크리닝/스톱 체크

---

## 8. 테스트

### 백엔드 (pytest, 25개)

```bash
source .venv/bin/activate
cd backend && python -m pytest tests/ -v
```

| 파일 | 테스트 수 | 범위 |
|---|---|---|
| `test_services.py` | 5 | 지표 계산, 포지션 비중, 정규화, HH-HL |
| `test_screener_edge_cases.py` | 9 | 스크리닝 필터 엣지 케이스 (ADX, MA, RSI, 거래량, ATR 스톱) |
| `test_monitor.py` | 3 | 스톱로스 BREACH/WARNING/OK |
| `test_schemas.py` | 8 | Pydantic 스키마 직렬화/검증 |

**주요 테스트 내용:**
- `screen()` — 데이터 부족, ADX<25, MA역배열, RSI범위초과, 거래량급등 시 False 반환
- `calc_atr_stop()` — 정상 계산 및 NaN 처리
- `rank_stocks()` — 빈 입력 시 빈 DataFrame
- `check_stop_loss()` — 현재가/스톱가 관계에 따른 이벤트 타입 판정
- 스키마 — ScreeningResultOut, HoldingCreate, StopCheckResult, MarketStatusResponse 직렬화

### 프론트엔드 (flutter test, 37개)

```bash
cd frontend && fvm flutter test test/models_test.dart -v
```

| 그룹 | 테스트 수 | 범위 |
|---|---|---|
| ScreeningResult.fromJson | 7 | 필드 파싱, nullable, flag, 타입 변환 |
| MarketStatus.fromJson | 4 | 정상, null, 기본값 |
| ScreeningRun.fromJson | 4 | 전체 구조, null, 빈 리스트 |
| Holding.fromJson | 4 | 정상, is_active 기본값 |
| StopCheckResult.fromJson | 4 | BREACH, WARNING, null |
| StrategyType enum | 5 | 4전략 key/label/description |
| StrategyScreeningData | 5 | 4전략 파싱, toScreeningRun 변환 |
| StrategyResult | 4 | 정상, null, 기본값 |

**모든 테스트는 DB/외부 API 없이 순수 단위 테스트로 동작**

---

## 9. 데이터 수집 (Docker Cron)

| 시간 (KST) | 대상 | 저장 |
|---|---|---|
| 23:00 월~금 | KOSPI/KOSDAQ 전체 | 월별 parquet + 시총 순위 |
| 07:00 월~금 | S&P500 전체 + SPY | 월별 parquet + 시총 순위 |

```bash
docker compose up -d collector      # 자동 실행
docker compose logs -f collector    # 로그 확인
docker compose run collector python collect_daily.py all  # 수동 실행
```

저장 구조:
```
/data/daily/
├── kospi/kospi_YYYYMM.parquet
├── kosdaq/kosdaq_YYYYMM.parquet
├── sp500/sp500_YYYYMM.parquet
└── spy/spy_YYYYMM.parquet
```

---

## 10. API 엔드포인트

### Screening
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/v1/screening/run` | 스크리닝 실행 |
| GET | `/api/v1/screening/latest` | 최신 결과 |
| GET | `/api/v1/screening/history` | 이력 (limit=20) |
| GET | `/api/v1/screening/{run_id}` | 특정 실행 결과 |

### Portfolio
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/v1/portfolio/holdings` | 활성 보유 종목 |
| POST | `/api/v1/portfolio/holdings` | 종목 추가 |
| DELETE | `/api/v1/portfolio/holdings/{ticker}` | 종목 비활성화 |
| POST | `/api/v1/portfolio/check-stops` | 스톱로스 검사 |

### Market & System
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/v1/market/status` | SPY 시장 상태 |
| GET | `/api/v1/market/rebalance-schedule` | 리밸런싱 일정 |
| POST | `/api/v1/notifications/register` | FCM 토큰 등록 |
| DELETE | `/api/v1/notifications/register/{token}` | 토큰 해제 |
| POST | `/api/v1/system/refresh` | 수동 갱신 |
| GET | `/api/v1/system/status` | 시스템 상태 |

---

## 11. 프론트엔드 화면 구성

| 화면 | 기능 |
|---|---|
| **Dashboard** | 시장 상태 배너 + 리밸런싱 D-day + TOP 3 미리보기 |
| **Screening** | 4전략 ChoiceChip 선택 + 종목 카드 리스트 (서버리스: 정적 JSON / 풀스택: API) |
| **Portfolio** | 보유 종목 관리 + 스톱로스 인디케이터 + 스와이프 삭제 |
| **Settings** | 푸시 알림 토글 + 파라미터 표시 |

### 상태 관리 (Riverpod)
- `screeningProvider` — 스크리닝 결과 (AsyncNotifier)
- `holdingsProvider` — 포트폴리오 (AsyncNotifier)
- `marketStatusProvider` — 시장 상태 (FutureProvider)
- `stopCheckProvider` — 스톱로스 체크 (FutureProvider.family)
- `strategyDataProvider` — 4전략 데이터 (FutureProvider, 서버리스 전용)

서버리스 모드에서는 `ProviderScope.overrides`로 위 Provider들을 `Serverless*` 구현체로 교체.

---

## 12. 현재 상태 및 미결 사항

### 완료

| 항목 | 상태 |
|---|---|
| 스크리너 v1/v2/v3 | ✅ |
| v3 최적 파라미터 적용 (ADX 20, RSI 77, HH-HL 2, 52w 75%, 최대비중 10%) | ✅ |
| 유니버스 동적 구성 (S&P 500 + KOSPI 200 + KOSDAQ 150, ~850개) | ✅ |
| 풀 유니버스 백테스트 (v1~v3 결과: docs/full_universe_refit_report.md) | ✅ |
| 백테스트 (ATR 튜닝, 적응형, 멀티 윈도우) | ✅ |
| FastAPI 백엔드 (모델/스키마/라우터/서비스/스케줄러) | ✅ |
| Flutter 프론트엔드 (4화면 + 4전략 선택) | ✅ |
| 서버리스 배포 (GitHub Pages + Actions) | ✅ |
| Docker 구성 (db + backend + collector) | ✅ |
| 단위 테스트 (백엔드 25개 + 프론트엔드 37개) | ✅ |
| 데이터 수집 cron 컨테이너 | ✅ |

### 미결

1. **API 라우터 통합 테스트** — FastAPI TestClient 기반 (미작성)
2. **Alembic 마이그레이션** — 스켈레톤만 존재, 마이그레이션 파일 미생성
3. **실서비스 데이터 파이프라인** — yfinance → KIS API (한국) / Alpha Vantage (미국)
4. **수익 모델 정의** — 구독형 vs 광고형
5. **법적 고지** — 투자 정보 제공 vs 투자 권유 구분

---

*본 문서는 투자 조언이 아니며, 내부 개발 참고용입니다.*
