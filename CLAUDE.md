# CLAUDE.md

## 프로젝트 컨텍스트
새 세션 시작 시 `.project-context.md` 파일을 먼저 읽어 프로젝트 구조, 알고리즘, 파일 맵, 실행 명령어 등을 파악할 것.
파일 구조나 알고리즘에 변경이 생기면 `.project-context.md`를 반드시 업데이트할 것.

## 주요 참조 문서
- `.project-context.md` — 프로젝트 전체 요약 (파일맵, 알고리즘, 전략, 명령어)
- `docs/HANDOFF.md` — 프로젝트 인수인계 문서 (아키텍처, API, 테스트, 배포)
- `docs/backtest_results.md` — ATR 튜닝 + 거래비용 반영 백테스트 결과
- `docs/adaptive_strategy_results.md` — 적응형 전략 멀티 윈도우 백테스트 결과

## Git 설정
- 이 프로젝트의 `user.email`은 `sogogimilk@google.com`을 사용한다.
- 커밋 전 `git config --local user.email`이 설정되어 있는지 확인할 것.

## 개발 환경 판별
세션 시작 시 `uname -s` 명령으로 현재 환경을 판별한다.
- **Darwin** → 개인 Mac 환경
- **Linux** → 공용 머신 환경

### 개인 Mac (Darwin)
- Python 가상환경(.venv) 사용, Docker 사용하지 않음
- Python 패키지 매니저: `uv`
- Flutter 버전 관리: `fvm` (프로젝트별 Flutter SDK)
- Python 가상환경 활성화: `source .venv/bin/activate`
- Flutter 명령: `fvm flutter <command>` (프로젝트 가상환경의 Flutter 사용)
- Python 의존성 추가: `uv add <패키지>`
- Flutter 의존성 추가: `cd frontend && fvm flutter pub add <패키지>`
- 절대 `pip install`을 직접 사용하지 않는다.
- 절대 시스템 `flutter` 명령을 직접 사용하지 않는다. 반드시 `fvm flutter`를 사용한다.

### 공용 머신 (Linux)
- Docker 컨테이너 환경에서 실행
- `docker compose`로 서비스 관리
- 컨테이너 내부에서 스크립트 실행
- 의존성은 Dockerfile + pyproject.toml로 관리

## 규칙
1. 항상 한국어로 응답한다.
2. 테스트를 통과하기 위해 테스트 코드를 수정하지 않는다. 단, 의도된 기능 변경으로 인해 기존 테스트의 기대값이 더 이상 유효하지 않은 경우, 테스트 코드 변경이 필요하다는 것을 사용자에게 알리고 승인을 받은 후에만 테스트를 수정한다.
3. 모든 패키지 설치는 가상환경(Python: .venv, Flutter: fvm)에서 수행한다.
4. 코드 실행 전 가상환경이 활성화되었는지 확인한다. (Python: `source .venv/bin/activate`, Flutter: `fvm flutter`)
5. GitHub에서 PR 또는 커밋 메시지를 작성할 때는 반드시 한국어를 사용한다.
6. 커밋 전 `README.md`에 업데이트할 내용이 있는지 확인하고, 필요시 README.md를 함께 업데이트하여 커밋에 포함한다.
7. 주식 백테스트 시에는 항상 풀 유니버스(S&P 500 + Nasdaq 100 + KOSPI 200 + KOSDAQ 150, 동적 수집)로 수행한다. 하드코딩된 축소 유니버스는 절대 사용하지 않는다.
8. commit 전에는 항상 테스트 코드를 실행하고, 테스트를 통과하지 못 하는 경우 디버깅을 시도한다.
9. worktree 또는 별도 브랜치에서 작업 시, push 전에 반드시 main의 최신 변경사항을 rebase/merge한 후 테스트를 실행한다.
10. 백테스트 실행 시 토큰 소비를 최소화한다:
   - 백테스트는 반드시 파일로 리다이렉트하고 완료 후 요약만 읽는다. 예: `python scripts/backtest/xxx.py > /tmp/backtest_result.txt 2>&1`
   - 백테스트 실행 중 read_transcript를 반복 호출해서 진행 상황을 추적하지 않는다.
   - 코드 세션에 백테스트를 위임할 때는 '완료 후 결과 요약만 반환'을 명시한다.
   - verbose 옵션은 기본적으로 사용하지 않는다.
   - 결과 파일의 경우 마지막 요약 부분(50~100줄)만 읽어서 사용자에게 보고한다.

## 백테스트 유니버스
- 주식 백테스트는 **반드시 풀 유니버스**로 수행한다: S&P 500 + Nasdaq 100 + KOSPI 200 + KOSDAQ 150
- 티커 목록은 하드코딩하지 않고 `export_json.py`의 동적 수집 함수를 사용한다:
  - `fetch_sp500_tickers()` — S&P 500 종목 동적 수집
  - `fetch_nasdaq100_tickers()` — Nasdaq 100 종목 동적 수집
  - `fetch_kr_tickers()` — KOSPI 200 + KOSDAQ 150 종목 동적 수집
- 축소 유니버스(예: 임의로 선별한 수십 종목 목록)를 백테스트에 사용하는 것은 금지한다.

## 브랜치 관리
- `develop`, `main` 이외의 브랜치는 merge 후 삭제한다.
- worktree 브랜치(claude/* 등)도 작업 완료 및 merge 후 즉시 삭제한다.

## 코드 컨벤션
- Python 3.12, 의존성 버전 고정
- 프로덕션 스크리너: `scripts/screener/screener_v3.py`
- 출력 파일(.csv, .png, holdings.json)은 gitignore 대상
