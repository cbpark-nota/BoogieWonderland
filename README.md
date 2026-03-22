# 모멘텀 주식 스크리너

매크로 모멘텀 팔로잉 전략 기반의 종목 선별 및 포트폴리오 관리 시스템.

## 개요

꾸준히 우상향하는 종목을 자동으로 선별하고, ATR 기반 동적 스톱로스로 리스크를 관리합니다.

- **유니버스**: 미국 32종목 (S&P 500) + 한국 14종목 (KOSPI) = 46종목
- **리밸런싱**: 격주 (매 2주 금요일)
- **스톱로스**: ATR(14) × 2.5 동적 스톱
- **포지션 사이징**: 복합점수 비례 배분 (단일 종목 최대 20%)

## 백테스트 성과 (2010~2024, 거래비용 반영)

| 유형 | ATR | 주기 | CAGR(순) | 총수익(순) | MDD | 샤프 | 승률 |
|---|---|---|---|---|---|---|---|
| 공격적 | 2.0 | 주간 | +46.3% | +29,955% | -8.6% | 3.02 | 44.8% |
| **균형형** | **2.5** | **격주** | **+38.5%** | **+13,049%** | **-7.2%** | **2.35** | **51.7%** |
| 보수적 | 3.5 | 월간 | +35.4% | +9,064% | -7.0% | 2.10 | 55.9% |

> 벤치마크 SPY: CAGR +13.7%, MDD -33.7%

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

## 프로젝트 구조

```
├── scripts/
│   ├── screener/       # 스크리닝 알고리즘 (v1, v2, v3)
│   ├── backtest/       # 백테스트 (주기별, ATR 튜닝)
│   └── monitor/        # 포트폴리오 모니터링, 데이터 다운로드
├── docs/               # 문서 (핸드오프, 백테스트 결과, 제안서)
├── backend/            # FastAPI + PostgreSQL (구현 예정)
└── frontend/           # Flutter 앱 (구현 예정)
```

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
