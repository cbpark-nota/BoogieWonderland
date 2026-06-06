# docs/ 카테고리 정리 작업 — 핸드오프 (WIP)

> **상태**: 1~3단계(조사 + 분류 제안 + 영향 점검) 완료. 4단계(`git mv` + 참조 갱신 + 커밋) 대기 중.
> **이 문서의 목적**: 다른 Claude 세션이 4단계를 이어받기 위한 인수인계.
> **코드 변경**: 0건. (현재까지 이 핸드오프 문서 1개만 추가됨)

---

## 1. 배경 & 목표

- 현재 `docs/` 디렉토리는 **33개 파일 + 하위 13개**가 한 곳에 평면(flat)으로 쌓여 있어 탐색·유지보수가 어렵다.
- 백테스트 리포트, 전략 문서, 리서치, 아키텍처, 운영 문서가 한 디렉토리에 섞여 있다.
- **목표**: 의미 기반 **6개 카테고리**로 재분류하여 디렉토리 구조를 정리한다.
- **제약**: `git mv`로 이동하여 git history를 보존하고, 깨지는 참조(16곳)를 동시에 갱신한다. 코드 동작에는 영향이 없어야 한다.

---

## 2. 결정 상태 (이전 라운드)

| 항목 | 상태 |
|------|------|
| docs/ 평면 구조 → 카테고리화 필요성 | **확정** |
| 6개 카테고리 골격(backtest/strategy/research/architecture/operations/dev) | **제안 — 사용자 승인 대기** |
| `git mv` 기반 이동(history 보존) | **확정 (방법론)** |
| 깨지는 참조 16곳 동시 갱신 | **확정 (방법론)** |
| `figures/` 미이동 | **확정 (코드 의존성 때문)** |
| dev/ 카테고리 유지 여부 | **논의 중 — 결정 #2** |
| .docx 2개 위치 | **논의 중 — 결정 #3** |
| requirements_legacy.txt 처리 | **논의 중 — 결정 #4** |
| screening-algorithms/ 내부 중복 파일 정리 | **논의 중 — 결정 #5** |
| 파일명 단축 rename 동반 여부 | **논의 중 — 결정 #6** |

---

## 3. 카테고리 권장안

| 카테고리 | 제안 경로 | 파일 수 | 대표 파일 |
|----------|-----------|---------|-----------|
| 백테스트 | `docs/backtest/` | 13 | `backtest_results.md`, `adaptive_strategy_results.md` |
| 전략 | `docs/strategy/` (기존 폴더 활용) | 6 | `bitcoin_daytrading_algorithm.md`, `vix_trading_strategy.md` |
| 리서치 | `docs/research/` | 4 | `analysis_btc_eth_correlation.md`, `full_universe_refit_report.md` |
| 아키텍처 | `docs/architecture/` | 2 + 하위 9 | `screening_criteria.md`, `screening-algorithms/` 전체 |
| 운영 | `docs/operations/` | 4 | `HANDOFF.md`, `deployment.md` |
| 개발 | `docs/dev/` | 2 | `acceptance_criteria.md`, `frontend_code_review_2026-05-01.md` |

---

## 4. 카테고리별 파일 매핑 (현재 경로 → 제안 경로)

### 4.1 backtest/ (13)

| 현재 경로 | 제안 경로 |
|-----------|-----------|
| `docs/backtest_results.md` | `docs/backtest/backtest_results.md` |
| `docs/backtest_results_vix.md` | `docs/backtest/backtest_results_vix.md` |
| `docs/backtest_5w_120w_cross.md` | `docs/backtest/backtest_5w_120w_cross.md` |
| `docs/backtest_eth_strategies_comparison.md` | `docs/backtest/backtest_eth_strategies_comparison.md` |
| `docs/backtest_instant_sell_comparison.md` | `docs/backtest/backtest_instant_sell_comparison.md` |
| `docs/backtest_trailing_stop_comparison.md` | `docs/backtest/backtest_trailing_stop_comparison.md` |
| `docs/bitcoin_daytrading_4h.md` | `docs/backtest/bitcoin_daytrading_4h.md` |
| `docs/bitcoin_daytrading_v2.md` | `docs/backtest/bitcoin_daytrading_v2.md` |
| `docs/btc_4h_backtest_results_20260415.md` | `docs/backtest/btc_4h_backtest_results_20260415.md` |
| `docs/btc_longterm_backtest_20260415.md` | `docs/backtest/btc_longterm_backtest_20260415.md` |
| `docs/eth_4h_backtest_results_20260427.md` | `docs/backtest/eth_4h_backtest_results_20260427.md` |
| `docs/eth_4h_btc_driven_backtest_20260427.md` | `docs/backtest/eth_4h_btc_driven_backtest_20260427.md` |
| `docs/adaptive_strategy_results.md` | `docs/backtest/adaptive_strategy_results.md` |

### 4.2 strategy/ (6, 기존 폴더 활용)

| 현재 경로 | 제안 경로 |
|-----------|-----------|
| `docs/bitcoin_daytrading_algorithm.md` | `docs/strategy/bitcoin_daytrading_algorithm.md` |
| `docs/vix_trading_strategy.md` | `docs/strategy/vix_trading_strategy.md` |
| `docs/vix_svxy_svix_trading_algorithm.md` | `docs/strategy/vix_svxy_svix_trading_algorithm.md` |
| `docs/strategy_guide_rollback.md` | `docs/strategy/strategy_guide_rollback.md` |
| `docs/strategy/sell_strategy_v3_3.md` | `docs/strategy/sell_strategy_v3_3.md` (이미 위치, 이동 없음) |

> 참고: `docs/strategy/` 폴더는 이미 존재하며 `sell_strategy_v3_3.md`가 들어있다. 나머지 4개를 이 폴더로 이동한다.

### 4.3 research/ (4)

| 현재 경로 | 제안 경로 |
|-----------|-----------|
| `docs/analysis_btc_eth_correlation.md` | `docs/research/analysis_btc_eth_correlation.md` |
| `docs/entry_timing_analysis.md` | `docs/research/entry_timing_analysis.md` |
| `docs/market_entry_analysis.md` | `docs/research/market_entry_analysis.md` |
| `docs/full_universe_refit_report.md` | `docs/research/full_universe_refit_report.md` |

### 4.4 architecture/ (2 + 하위 9)

| 현재 경로 | 제안 경로 |
|-----------|-----------|
| `docs/screening_criteria.md` | `docs/architecture/screening_criteria.md` |
| `docs/refactoring_analysis.md` | `docs/architecture/refactoring_analysis.md` |
| `docs/screening-algorithms/` (전체, 9개) | `docs/architecture/screening-algorithms/` |

### 4.5 operations/ (4)

| 현재 경로 | 제안 경로 |
|-----------|-----------|
| `docs/HANDOFF.md` | `docs/operations/HANDOFF.md` |
| `docs/deployment.md` | `docs/operations/deployment.md` |
| `docs/cloud_deployment_review.md` | `docs/operations/cloud_deployment_review.md` |
| `docs/cache_update_report.md` | `docs/operations/cache_update_report.md` |

### 4.6 dev/ (2)

| 현재 경로 | 제안 경로 |
|-----------|-----------|
| `docs/acceptance_criteria.md` | `docs/dev/acceptance_criteria.md` |
| `docs/frontend_code_review_2026-05-01.md` | `docs/dev/frontend_code_review_2026-05-01.md` |

---

## 5. 단독/잡종 파일 (4) — 결정 필요

| 파일 | 비고 |
|------|------|
| `docs/api_comparison.docx` | 바이너리 .docx. 카테고리 모호 → 결정 #3 |
| `docs/momentum_stock_project_proposal_v0.2.docx` | 바이너리 .docx. 제안서 → 결정 #3 |
| `docs/requirements_legacy.txt` | 레거시 요구사항. 삭제 vs 보존 → 결정 #4 |
| `docs/screening-algorithms/` 내 `v3.0_*` / `v3.1_*` 중복 파일들 | 버전 중복. 정리 범위 포함 여부 → 결정 #5 |

---

## 6. figures/ 는 이동하지 않는다 (중요)

- `scripts/crypto/btc_eth_correlation.py` 가 `docs/figures/*.png` 를 직접 경로로 사용할 가능성이 있다.
- 이동 시 코드의 출력/참조 경로가 깨질 수 있으므로 **`docs/figures/` 는 현재 위치 그대로 유지**한다.
- 이동 대상에서 제외.

---

## 7. 사용자 결정 대기 (5+1가지)

> 4단계 진행 **전에** 반드시 사용자에게 아래를 확인할 것.

1. **카테고리 6개 골격** 그대로 진행해도 되는가? (backtest / strategy / research / architecture / operations / dev)
2. **dev/ 카테고리 처리** — 옵션 A: architecture/에 흡수하고 dev/ 폐기 / 옵션 B: dev/ 독립 유지. 어느 쪽?
3. **.docx 2개** (`api_comparison.docx`, `momentum_stock_project_proposal_v0.2.docx`) → `docs/` 루트 유지 vs `operations/` 흡수?
4. **`requirements_legacy.txt`** → 삭제 vs `operations/` 로 보존?
5. **screening-algorithms/ 내부 `v3.0_*` / `v3.1_*` 중복 파일** 정리를 이번 범위에 포함할지?
6. **파일명 단축 rename** (예: `backtest_results.md` → `results.md`) 를 이동과 함께 진행할지?

---

## 8. 영향 점검 결과 — 깨질 참조 16곳

> 파일 이동 시 함께 갱신해야 하는 참조. **코드 동작에 영향을 주는 것은 없으며**(대부분 docstring/문서 링크), 표시 정확성을 위해 갱신한다.

### 8.1 루트 메타 문서 (5건)

| 위치 | 비고 |
|------|------|
| `README.md:50` | docs 경로 참조 |
| `CLAUDE.md:9-11` | 주요 참조 문서 목록 |
| `AGENTS.md:9-11` | 주요 참조 문서 목록 |
| `.project-context.md:66-78` | 파일맵 |
| `deploy.md:846` | docs 경로 참조 |

### 8.2 스크립트 docstring (9건 — 코드 동작 영향 없음, 표시만)

| 위치 |
|------|
| `scripts/crypto/run_4h_backtest.sh:42` |
| `scripts/crypto/eth_daytrading_4h.py:14` |
| `scripts/crypto/eth_btc_driven_4h.py:20` |
| `scripts/crypto/update_eth_signal.py:6` |
| `scripts/crypto/btc_eth_correlation.py:12-13` |
| `scripts/crypto/backtest_btc.py:13,686` |
| `scripts/backtest/backtest_entry_timing.py:13` |

### 8.3 docs 내부 상호 링크 (2곳, 링크 3개)

| 위치 | 비고 |
|------|------|
| `docs/backtest_eth_strategies_comparison.md:12` | 다른 docs 문서 링크 |
| `docs/vix_trading_strategy.md:251-252` | 다른 docs 문서 링크 (2개) |

### 8.4 screening-algorithms/README.md 표 경로 (8곳)

- `docs/screening-algorithms/README.md` 내부 표의 경로 8곳. architecture/ 하위로 이동 시 표 경로 갱신 필요.

---

## 9. 이미 깨진 참조 (이번 정리 범위 밖)

- `scripts/crypto/backtest_btc.py` 가 `docs/bitcoin_trading_algorithm.md` 를 참조하지만 **그 파일은 `docs/`에 존재하지 않는다**(현재 워킹트리에 `docs/bitcoin_trading_algorithm.md`가 untracked로 새로 생겼을 수 있으니 다음 세션에서 재확인). 본 정리 작업과 무관하므로 별도 처리하거나 그대로 둔다.

---

## 10. 4단계 실행 순서 (다음 세션이 진행)

1. **§7의 6개 결정사항을 사용자로부터 받기.**
2. `git mv` 로 파일 이동 (git history 보존). §4 매핑표 기준.
3. **깨지는 참조 16곳을 동시에** 업데이트 (§8).
4. `develop` 브랜치에 커밋. (이 핸드오프 브랜치가 아닌, 결정 후 develop 기준 작업 브랜치 권장)
5. `main` 머지는 사용자 결정 후 별도 단계로.

---

## 11. 안전성 노트

- ❌ `main`에 직접 머지 금지. 사용자가 명시적으로 요청한 경우에만.
- ❌ 강제 push(`--force`) 금지.
- ❌ `docs/figures/` 이동 금지 (코드 의존성, §6).
- ✅ `docs/screening-algorithms/README.md` 표 경로 8곳 갱신 필수 (§8.4).
- ✅ 모든 이동은 `git mv` 로 수행하여 history 보존.
- ✅ 이동 후 참조 16곳 갱신 누락 없는지 grep 재확인.

---

*작성: docs/ 카테고리 정리 1~3단계 완료 시점. 4단계 인수인계용.*
