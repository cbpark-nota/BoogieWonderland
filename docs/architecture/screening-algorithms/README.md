# 스크리닝 알고리즘 문서 인덱스

이 디렉토리는 모멘텀 종목 스크리너의 알고리즘 설계·백테스트·연구 문서를 버전별로 정리합니다.  
원본 파일은 `docs/` 하위 카테고리 디렉토리에 보존되며, 여기에 버전 레이블을 붙인 복사본이 모여 있습니다.

---

## 버전 히스토리 요약

| 버전 | 주요 변경 | 코드 파일 |
|---|---|---|
| v1.0 | 초기 모멘텀 스크리너 (ADX≥25, MA정배열, RSI 50~70, 고정 스톱 5%, 하드코딩 59개 종목) | `screener_v1.py` |
| v2.0 | 점수 기반 랭킹 + ATR 스톱로스 (ADX≥20, RSI 77, HH-HL≥2, 최대비중 20%) | `screener_v2.py` |
| v3.0 | min-max 정규화 + 가중 합성 점수, 동적 유니버스 (~850개 US+KR), ATR 동적 스톱, 최대비중 10% | `screener_v3.py` |
| v3.1 | KR 제외, 레짐 필터(SPY MA20/MA60), 변동성 스케일링(15%), ret12m_skip1, Buy/Hold Spread(2.5×), 시총√가중 | `screener_v3.py` |
| v3.2 | 한미 분리 스크리닝: US(`screener_v3.py`) + KR(`screener_v3_kr.py`) | `screener_v3.py` + `screener_v3_kr.py` |

---

## 문서 목록

### 알고리즘 명세

| 파일 | 버전 | 설명 | 원본 |
|---|---|---|---|
| [v3.0_screening_criteria.md](v3.0_screening_criteria.md) | v3.0 | 7개 필터 조건 및 복합점수 산식 상세 (ADX 40%+ret3m 30%+sec 20%+vol 10%) | `docs/architecture/screening_criteria.md` |
| [v3.1_strategy_spec.md](v3.1_strategy_spec.md) | v3.1 | v3.1 알고리즘 전체 명세: 필터·스코어·레짐·변동성·시총 가중 (신규 작성) | — |

### 백테스트 결과

| 파일 | 버전 | 설명 | 원본 |
|---|---|---|---|
| [full_universe_refit_report.md](../../research/full_universe_refit_report.md) | v3.0 | v1→v2→v3 파라미터 진화 과정 및 성능 비교 백테스트 (2026-03-23 작성) | `docs/research/full_universe_refit_report.md` |
| [adaptive_strategy_results.md](../../backtest/adaptive_strategy_results.md) | v3.0 | 적응형 전략(3계층 국면 판별) 멀티 윈도우 백테스트 결과 (2026-03-22 작성) | `docs/backtest/adaptive_strategy_results.md` |
| [v3.1_backtest_results.md](v3.1_backtest_results.md) | v3.1 | ATR 튜닝 + 격주×A진입 백테스트, v3.0 vs v3.1 성능 비교 (2026-04-09 최종 업데이트) | `docs/backtest/backtest_results.md` |

### 시장 진입 분석

| 파일 | 버전 | 설명 | 원본 |
|---|---|---|---|
| [market_entry_analysis.md](../../research/market_entry_analysis.md) | v3.0 | 시장 바닥 확인 진입(저점 후 1개월 미이탈) 조건의 유효성 검증 (2026-03-22 작성) | `docs/research/market_entry_analysis.md` |
| [entry_timing_analysis.md](../../research/entry_timing_analysis.md) | v3.0 | MA정배열 vs 바닥확인 vs 3단계 진입 전략 백테스트 비교 (2026-03-24 작성) | `docs/research/entry_timing_analysis.md` |

### 배포 검토

| 파일 | 버전 | 설명 | 원본 |
|---|---|---|---|
| [cloud_deployment_review.md](../../operations/cloud_deployment_review.md) | v3.1 | Flutter 웹 클라우드 배포 방안 비교 (Cloudflare/Firebase/AWS) (2026-03-30 작성) | `docs/operations/cloud_deployment_review.md` |

---

## 버전별 스코어 가중치 변화

| 항목 | v3.0 | v3.1 |
|---|---|---|
| ADX | 40% | 30% |
| ret3m (3개월 수익률) | 30% | 20% |
| ret12m_skip1 (12개월-1개월) | — | 20% |
| Sector Strength | 20% | 20% |
| Vol Stability | 10% | 10% |

---

## 관련 문서 (이 디렉토리 외)

- `docs/operations/HANDOFF.md` — 프로젝트 아키텍처 및 API 인수인계 문서
- `.project-context.md` — 프로젝트 전체 요약 (파일맵, 명령어, 최신 알고리즘 개요)
- `docs/backtest/backtest_results.md` — 백테스트 결과 원본
- `docs/architecture/screening_criteria.md` — 스크리닝 기준 원본
