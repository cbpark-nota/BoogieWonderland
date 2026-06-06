# 모멘텀 주식 스크리너

매크로 모멘텀 팔로잉 전략 기반의 종목 선별 및 포트폴리오 관리 시스템.

## 개요

꾸준히 우상향하는 종목을 자동으로 선별하고, ATR 기반 동적 스톱로스로 리스크를 관리합니다.

- **유니버스**: 미국 32종목 (S&P 500) + 한국 14종목 (KOSPI) = 46종목
- **리밸런싱**: 격주 (매 2주 금요일)
- **스톱로스**: ATR(14) × 2.5 동적 스톱
- **포지션 사이징**: 복합점수 비례 배분 (단일 종목 최대 20%)

## 백테스트 성과 (2015~2024, 거래비용 반영)

| 전략 | ATR 승수 | 리밸런싱 | CAGR | MDD | 샤프 |
|---|---|---|---|---|---|
| 공격적 | 2.0 | 주간 | +53.0% | -8.5% | 3.10 |
| **균형형** | **2.5** | **격주** | **+39.3%** | **-10.4%** | **3.33** |
| 보수적 | 3.5 | 월간 | +39.8% | -3.9% | 4.54 |
| 적응형 | 동적 | 동적 | +44.0% | -10.6% | 2.65 |

> 벤치마크 SPY: CAGR +13.1%, MDD -33.7%, 샤프 0.36

## 스크리닝 알고리즘 (v3)

7가지 진입 조건을 모두 통과한 종목에 복합점수를 부여하여 상위 10개를 선정합니다.

**진입 조건**:
1. ADX ≥ 25 (추세 강도)
2. 이동평균 정배열: 20MA > 50MA > 200MA
3. RSI 50~75 (모멘텀 구간)
4. 20일간 거래량 스파이크 없음 (60일 평균 × 3 이하)
5. 5일간 ±10% 급등락 없음
6. 60일간 HH-HL 스윙 패턴 ≥ 3회
7. 현재가 ≥ 52주 고점의 80%

**복합점수**: `ADX × 0.4 + 3개월수익률 × 0.3 + 섹터강도 × 0.2 + 거래량안정성 × 0.1`

## 프로젝트 구조 및 책임 분리

```
├── scripts/            # 알고리즘 R&D / 백테스트 / 검증 (배포 대상 아님)
│   ├── screener/       # 스크리닝 알고리즘 실험 (v1, v2, v3)
│   ├── backtest/       # 백테스트 (주기별, ATR 튜닝)
│   └── monitor/        # 포트폴리오 모니터링, 데이터 다운로드
├── backend/            # 프로덕션 코드의 단일 소스 (SSoT)
│   └── app/services/   # scripts/에서 검증된 알고리즘을 복사하여 운영
├── frontend/           # Flutter (iOS / Android / Web)
├── docs/               # 문서 (6개 카테고리: backtest, strategy, research, architecture, operations, dev)
└── deploy/             # 배포 설정 (로컬, Docker, AWS)
```

### 디렉토리별 역할

- **`scripts/`** — 알고리즘 R&D / 테스트 / 백테스트 코드 보관소.
  - 자유롭게 실험·반복하는 공간. **프로덕션 배포 대상 아님.**
  - 새 알고리즘은 여기서 검증한 뒤 `backend/`로 이식한다.
- **`backend/`** — 프로덕션 코드의 **단일 소스(SSoT)**.
  - 호스트 백엔드(FastAPI)와 Cloudflare Container 모두 이 디렉토리의 코드를 사용한다.
  - CF Container Dockerfile은 `backend/` 만 빌드 컨텍스트로 포함하여 이미지를 가볍게 유지한다.
- **`frontend/`** — Flutter (iOS / Android / Web). 환경별 API base URL 분기 정책은 별도(`deploy.md` §5 N2).

### 알고리즘 변경 워크플로

1. `scripts/screener/` 에서 신규 알고리즘 실험·백테스트.
2. 성능·안정성 검증 완료.
3. **`backend/app/services/` 로 알고리즘을 복사** (import 공유가 아닌 **코드 복사** 기반).
4. 백엔드 단위 테스트 + 스모크 테스트 통과.
5. 호스트 백엔드 + CF Container 양쪽에 반영 (둘 다 `backend/` 코드 베이스를 사용).

### 동기화 책임 (drift 주의)

- `scripts/screener/*.py` 와 `backend/app/services/*.py` 는 **수동 복사** 로 동기화된다. 시간이 지나면서 두 코드가 어긋날(drift) 수 있다.
- 알고리즘을 수정할 때는 반드시 다음을 점검:
  - 어느 쪽에서 먼저 변경됐는가?
  - 다른 쪽에 동기화 PR이 필요한가?
- 향후 drift 감지 자동화(예: CI에서 핵심 함수 시그니처/해시 비교) 도입 여부는 별도 결정 사항이다.

## 트렌드 분석 도구 (시총 Top 20)

시총 Top 20은 **매매 전략이 아닌 시장 트렌드 모니터링 참고 도구**입니다.
- S&P500 + NASDAQ100 기준 시가총액 상위 20개 종목 조회
- 전일 대비 신규 진입 종목 하이라이트
- 섹터 분포 시각화
- 드로어 메뉴 → **트렌드 분석** 에서 확인

## 빠른 시작

```bash
# 환경 설정
uv venv --python 3.12 .venv
source .venv/bin/activate
uv sync

# 데이터 다운로드 (최초 1회)
python scripts/monitor/download_data.py

# 스크리닝 실행
python scripts/screener/screener_v3.py

# 포트폴리오 모니터링
python scripts/monitor/monitor.py --add NVDA 130.50
python scripts/monitor/monitor.py

# 백테스트
python scripts/backtest/backtest_rebal_freq.py
python scripts/backtest/backtest_atr_tuning.py
python scripts/backtest/backtest_short_squeeze.py  # 숏스퀴즈: 대형주 vs 소형주 vs 전체
```

## 기술 스택

| 구분 | 기술 |
|---|---|
| 언어 | Python 3.12, Dart (Flutter) |
| 패키지 관리 | uv |
| 데이터 | yfinance, pandas, pandas-ta |
| 백엔드 | FastAPI, SQLAlchemy, PostgreSQL, APScheduler |
| 프론트엔드 | Flutter, Riverpod, fl_chart |
| 알림 | Firebase Cloud Messaging |
| 컨테이너 | Docker |

## 라이선스

Private - All rights reserved.
