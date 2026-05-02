# 배포 계획서: 앱 + 웹 듀얼 타겟

> **상태**: 토론용 초안 (v0.1, 2026-05-02 작성)
> **결정**: 본 문서는 사용자 검토용 초안이다. 13개 결정 항목(D1~D13) 및 5장의 신규 항목(N1~N5)에 대해 사용자가 답을 확정한 뒤에야 실제 구현/마이그레이션 작업을 시작한다.
> **자율 판단 금지**: 본 문서는 비교·정리·권장만 담는다. 단정형 결정은 포함하지 않는다.
> **코드 변경 0건**: 본 PR/커밋은 문서 추가만 포함한다.

---

## 0. TL;DR

- 서비스를 **앱(모바일)** 과 **웹** 두 채널로 제공한다.
- **앱 타겟**의 데이터 갱신/저장은 **호스트 머신**(자체 서버 또는 VPS)에서 수행 → `backend/app`(FastAPI + APScheduler + PostgreSQL) 활용.
- **웹 타겟**의 데이터 갱신/저장은 **Cloudflare 계열 서버리스 환경**에서 수행 → 단, "Python 스크립트 실행"이라는 핵심 제약이 있어 옵션 A~E의 트레이드오프가 다음 큰 결정점이다.
- 이 듀얼 타겟 결정만으로 D1~D13 중 다수 항목의 답이 채널별로 자동 분기된다(아래 4장 매트릭스 참고). 다만 **공통 코드 공유 / 데이터 sync / 인증 / 비용** 등 신규 결정 항목이 추가로 발생한다.

---

## 1. 개요

### 1.1 현재 상태(2026-05-02 기준)

- **프로덕션 모델**: GitHub Actions cron(KST 04:00 KR, KST 08:00 US) → Python 스크리너 실행 → 정적 JSON 산출 → GitHub Pages로 배포 → Flutter Web 앱이 정적 JSON을 fetch.
- **DB**: 사용 안 함. 모든 결과는 `*.json` 파일로 저장.
- **백엔드 코드**:
  - `backend/app/`: FastAPI + APScheduler + SQLAlchemy(async, asyncpg) + PostgreSQL + FCM. **구현은 되어 있으나 미사용.**
  - `backend/api/`: 더 단순한 라우터 모듈(`main.py`, `screening.py`, `portfolio.py`). 역할 모호 (5장 N5 참조).
- **프론트엔드**: Flutter (Web 빌드는 GitHub Pages에서 운영 중, iOS/Android/macOS/Windows 빌드 자산은 존재하나 **모바일 앱 빌드는 곧 시작 예정**).
- **GitHub Actions 워크플로 5개**:
  - `daily-screening.yml` — 일일 스크리닝(KR 04:00 / US 08:00 KST) + 서버리스 배포
  - `_screening-deploy.yml` — 재사용 워크플로(스크리닝→Pages 배포)
  - `deploy-web.yml` — Flutter Web 빌드/배포
  - `btc-signal.yml` — BTC 신호
  - `test.yml` — 테스트
- **환경변수 분기**: `DEPLOY_ENV=serverless|local|cloud` 가 이미 코드에 존재 (구체 동작은 추후 확인 필요).

### 1.2 사용자 시나리오 가정 (확정 필요)

| 채널 | 주 이용 시간 | 갱신 빈도 기대 | 푸시/알림 | 사용자 규모 가정 |
|---|---|---|---|---|
| 앱 (iOS/Android) | 출퇴근/장중/장후 | 실시간성 기대 (장중 모니터링, 스톱 트리거 푸시) | FCM 푸시 필요 | 소수 ~ 중규모 (가정값 미확정) |
| 웹 | 데스크톱 분석/공유 | 일 1~2회로 충분 | 불필요 | 가벼운 트래픽, 공개/공유 가능성 |

> **미확정**: 위 가정은 검토용. 사용자 시나리오·규모 가정을 확정하지 않으면 비용/스케일 의사결정 정확도가 떨어진다.

### 1.3 트래픽·비용 가정 (개략)

- **웹**: 정적 JSON + 정적 SPA, 트래픽 < 10만 req/월 가정 시 Cloudflare Pages 무료 티어 내.
- **앱 백엔드(호스트)**: VPS 1대(2vCPU/4GB) 기준 월 5~20 USD. PostgreSQL 동거 가정.
- **데이터 갱신 컴퓨팅(웹용)**: Cloudflare Containers 또는 별도 PaaS(Railway/Fly.io/Render) 가격은 옵션 비교 표(3.2.2) 참조.

---

## 2. 아키텍처 다이어그램

### 2.1 앱 타겟 (모바일) — 호스트 머신 백엔드

```
┌──────────────────────┐
│ Flutter iOS/Android  │
│  (모바일 앱 패키지)   │
└──────────┬───────────┘
           │ HTTPS REST + (FCM Push 수신)
           ▼
┌──────────────────────────────────────────────┐
│  Host Machine (VPS / 자체 서버)               │
│ ┌──────────────────────────────────────────┐ │
│ │ FastAPI (backend/app)                    │ │
│ │  - /api/screening, /api/portfolio, ...   │ │
│ │ APScheduler                              │ │
│ │  - 일간 스크리닝 / 스톱체크 / 리밸런싱   │ │
│ │  - run_screening() 호출 (in-process)     │ │
│ └────────────┬─────────────────────────────┘ │
│              │                               │
│ ┌────────────▼────────────┐  ┌────────────┐ │
│ │ PostgreSQL              │  │ FCM 자격증명│ │
│ │  - ScreeningRun/Result  │  │ (서비스계정)│ │
│ │  - Holding, DeviceToken │  └────────────┘ │
│ └─────────────────────────┘                  │
│                                              │
│ scripts/screener/*.py  ← 동일 코드 import    │
└──────────────────────────────────────────────┘
```

### 2.2 웹 타겟 — Cloudflare-like 서버리스

```
┌──────────────────────┐
│ Flutter Web build    │
│  (정적 SPA)          │
└──────────┬───────────┘
           │ HTTPS GET (정적 JSON or REST)
           ▼
┌──────────────────────────────────────────────┐
│  Cloudflare Pages                            │
│  (Flutter Web 정적 호스팅)                   │
└──────────┬───────────────────────────────────┘
           │  fetch JSON (R2/KV/Pages 정적 파일)
           ▼
┌──────────────────────────────────────────────┐
│  데이터 저장: R2 / KV / D1 (옵션)            │
└──────────────────────────────────────────────┘
           ▲
           │ 데이터 갱신 push
           │
┌──────────┴───────────────────────────────────┐
│  데이터 갱신 컴퓨팅 (옵션 A~E 중 선택)        │
│  - A: CF Workers Python (베타)               │
│  - B: CF Containers + cron                   │
│  - C: 외부 PaaS(Railway/Fly/Render) cron     │
│  - D: GitHub Actions 유지 (현행)             │
│  - E: TS로 포팅                              │
└──────────────────────────────────────────────┘
```

### 2.3 데이터 정합성

- **두 타겟이 같은 데이터를 보여주는가?** — 같은 사용자라면 동일 결과를 기대할 가능성이 높음(같은 알고리즘, 같은 유니버스).
- **갱신 시점 sync 문제**:
  - 두 환경이 각자 cron을 돌리면 **결과 산출 시각 차이**, **외부 API(yfinance 등) 응답 차이**, **시드 의존성** 등으로 미세 불일치 가능.
  - 단일 진실 소스(SSoT) 전략(신규 항목 N3에서 다룸):
    - (a) 호스트만 갱신 → 웹은 호스트 산출물을 fetch
    - (b) 웹용만 갱신 → 호스트는 웹 산출물을 import
    - (c) 두 환경 독립 갱신 + 공통 sanity check
- **권고 톤**: 어느 모델이든 "어느 쪽이 SSoT인가"를 먼저 정해야 한다. 사용자 결정 항목 N3 참고.

---

## 3. 채널별 기술 스택

### 3.1 앱 (모바일) — 호스트 머신 백엔드

#### 3.1.1 컴포넌트
- **프론트엔드**: Flutter (iOS/Android 빌드). API base URL은 환경별 분기 필요(N2).
- **백엔드 프레임워크**: `backend/app/` 의 FastAPI (이미 구현되어 있는 자산 활용).
- **스케줄러**: `backend/app/scheduler.py` 의 APScheduler (동일 프로세스 in-process).
- **DB**: PostgreSQL (config.py 기본값 `postgresql+asyncpg://...`).
- **푸시**: Firebase Cloud Messaging — `app/services/notification.py`, 자격증명 파일은 `APP_FCM_CREDENTIALS_PATH` 환경변수.

#### 3.1.2 데이터 갱신 흐름
- APScheduler가 `run_screening()` (즉, `scripts/screener/screener_v3*.py` 로직) 을 **함수 호출** 로 실행.
- 결과는 `ScreeningRun` / `ScreeningResult` 테이블에 INSERT.
- 모바일 앱은 REST `/api/screening`, `/api/portfolio`, `/api/market` 호출.
- 스톱 트리거 발생 시 `DeviceToken` 대상으로 FCM push.

#### 3.1.3 운영
- 단일 호스트(VPS) — `uvicorn` + systemd 또는 docker compose 1대.
- 백업: PostgreSQL `pg_dump` cron, 외부 스토리지로 업로드.
- 모니터링: 별도 결정 필요(N5).

### 3.2 웹 — Cloudflare-like 서버리스

#### 3.2.1 컴포넌트
- **호스팅**: Cloudflare Pages (현재 GitHub Pages → Cloudflare Pages 이전 가정).
- **빌드**: Flutter Web (`fvm flutter build web --base-href /`).
- **데이터 갱신**: Python 실행이라는 핵심 제약 → 옵션 A~E 중 택일 필요.
- **데이터 저장**: R2(S3 호환 오브젝트), KV(소형 KV), D1(SQLite 호환 RDB) 중 택일.

#### 3.2.2 Python 실행 옵션 비교 (핵심 결정점)

| 옵션 | 설명 | 장점 | 단점 | 적합도 메모 |
|---|---|---|---|---|
| **A. CF Workers Python (베타)** | Pyodide 기반 Python 런타임을 Workers 위에서 실행 | • CF 단일 콘솔로 통합<br>• 서버리스, scale-to-zero | • **베타** — 안정성·SLA 약함<br>• `pandas`/`yfinance`/`pykrx` 등 C-extension 의존 패키지 호환성 제한<br>• 메모리/실행 시간 한계(Workers 제약 적용)<br>• 콜드 스타트 시 패키지 로딩 비용 | 현재 의존성 셋(yfinance/pandas/pykrx/scipy 등)과 호환성 확인 필요. 그대로 쓰기 어려울 가능성 큼. |
| **B. CF Containers + cron** | Docker 컨테이너를 CF 인프라에서 cron 트리거로 실행 | • Python/의존성 자유도 그대로<br>• CF 단일 벤더 유지<br>• cron 트리거 내장 | • **신규 기능** — 가용성·요금 변경 가능성<br>• 콜드 스타트/타임아웃 정책 확인 필요<br>• 지역 가용성/제한 확인 필요 | 가장 직관적인 후보 중 하나. 가격·SLA·Trigger 한도 검증 필요. |
| **C. 외부 PaaS cron + R2/KV push** | Railway/Fly.io/Render 등에서 Python cron 실행 → 결과를 R2/KV에 업로드 → CF Pages에서 fetch | • Python 환경 100% 자유<br>• 안정적/보편적 패턴<br>• 벤더 락인 분산 | • 멀티 벤더 운영<br>• 인증/시크릿 관리가 두 곳<br>• 외부 PaaS 요금 별도 | 안정성·자유도 측면에서 가장 무난. |
| **D. GH Actions 유지 + CF Pages만 호스팅 이전** | 현행 모델에서 호스팅만 GitHub Pages → CF Pages 이전 | • **사실상 변경 0**<br>• 검증된 모델<br>• 비용 거의 무증가 | • 사용자가 "Cloudflare 같은 서버리스에서 갱신"이라고 명시한 요구와 부합하지 않음<br>• GH Actions 분 사용량 제약(public repo면 무제한, private 시 한도) | 사용자가 "Cloudflare에서 갱신 수행" 을 명확히 요구했으므로 후보로만 둠. 그러나 가장 리스크 적음. |
| **E. TS 포팅** | 스크리닝 로직 전체를 TypeScript로 재구현하여 Workers JS에서 실행 | • Workers 네이티브, 가장 가벼움<br>• 호환성 고민 없음 | • **대규모 리팩터** — 알고리즘 동치성 검증 부담<br>• yfinance/pykrx 대체 데이터 소스 필요<br>• 백테스트/연구 코드는 Python 그대로라 이중 유지보수 | 단기 비추, 장기 옵션. |

> **권고 톤**: 위 5개 중 **B(Containers)** 또는 **C(외부 PaaS + R2)** 가 "Python 자유도 + 서버리스 정신" 양립 면에서 무난해 보임. **D(현상 유지)** 는 안전판으로 둘 만함. **A/E** 는 추가 실험·리팩터 비용이 큼. **사용자 결정 필요.**

#### 3.2.3 데이터 저장소 비교

| 저장소 | 형식 | 용량/요금(개략) | 적합도 |
|---|---|---|---|
| **R2** | 오브젝트 스토리지(S3 호환) | 10GB까지 무료, 이그레스 무료 | 정적 JSON/parquet 산출물 보관에 적합 |
| **KV** | 글로벌 KV | 작은 키/값, 읽기 매우 빠름 | "최신 결과 1개" 같은 hot path에 적합, 큰 페이로드 비추 |
| **D1** | SQLite 호환 RDB | 베타 → GA 진행 중 | 이력/검색 쿼리가 필요해질 때 |

> **권고 톤**: 정적 JSON 산출물이 그대로면 **R2** 가 무난. 이력 조회/필터가 필요하면 **D1** 로 확장 검토. 사용자 결정 필요.

---

## 4. 13개 결정 항목 매트릭스

> **읽는 법**: 각 항목은 **앱 타겟**과 **웹 타겟**에서 답이 다를 수 있다. 듀얼 타겟 결정으로 자동 해결되는 부분과, 그래도 사용자 결정이 남는 부분을 분리한다.

| ID | 항목 | 앱 타겟 (호스트) | 웹 타겟 (CF-like) | 사용자 결정 필요 |
|---|---|---|---|---|
| **D1** | DB 종류 | PostgreSQL (`backend/app/config.py` 기본값) | 정적 JSON(R2) / KV / D1 중 택일 | 웹 측 저장소 선택 (R2/KV/D1) |
| **D2** | 백엔드 구현 (`backend/app` vs `backend/api`) | `backend/app` 사용 (FastAPI + APScheduler + ORM 풀스택) | 백엔드 프로세스 없음(서버리스). 단 데이터 생성 스크립트는 `scripts/screener/*` 직접 사용 | `backend/api` 의 존속 여부(N5에서 다룸) |
| **D3** | 스케줄러 라이브러리 / 작업 정의 위치 | APScheduler (`backend/app/scheduler.py` 그대로) | 옵션별로 다름:<br>• B: CF Containers cron<br>• C: 외부 PaaS cron(또는 별도 워커)<br>• D: GitHub Actions cron(현행 유지) | 웹 측 옵션 선택(3.2.2) — D3 답이 거기 종속 |
| **D4** | 스케줄러가 호출할 인터페이스 | **함수 호출**(in-process). `run_screening()` 직접 import | 옵션별로 다름:<br>• A: 함수 호출(베타 제약)<br>• B/C: 컨테이너 안에서 `python script.py` subprocess 또는 함수 호출<br>• D: GH Actions에서 `python` 그대로 | 옵션 결정 후 자동 종속 |
| **D5** | 갱신 주기 | 사용자 정책에 따름. 추천 후보:<br>• 일 2회 (현행 모델 그대로)<br>• 장중 추가(예: 30분 간격, 시장 시간 동안)<br>• 푸시 트리거(스톱 체크는 더 잦게) | 일 2회(KR 04:00, US 08:00 KST) 유지 권장 (현행과 동일) | **앱 측에서 추가 잦은 주기를 운영할지 여부** |
| **D6** | 출력 파일/데이터 저장 위치 | DB(PostgreSQL) — `ScreeningRun` / `ScreeningResult` 테이블 | R2 버킷(또는 KV/D1). Pages 정적 파일도 검토 가능 | 웹 측 저장 매체 결정 |
| **D7** | 프론트엔드 동작 모드 | **로컬 API 모드** — `lib/config/api_config.dart` 의 base URL을 호스트 백엔드로 | **서버리스 정적 JSON 모드** — 현행과 동일 | 환경별 base URL 분기 전략(N2) |
| **D8** | 포트 할당 | FastAPI 8000(기본), PostgreSQL 5432. 호스트에서 reverse proxy(Caddy/nginx) 80/443 | 해당 없음 (서버리스) | 호스트 측 reverse proxy 선택 |
| **D9** | 환경변수 파일/설정 위치 | `.env` (호스트 머신 로컬), `APP_*` prefix(`backend/app/config.py`). 시크릿은 systemd `Environment=` 또는 `.env` 권한 600 | CF Pages 환경변수 + Workers/Containers Secrets, GH Actions Secrets(옵션 D 시) | 시크릿 매니저 선택 (특히 FCM 자격증명 위치) |
| **D10** | 의존성 설치 방식 | `uv sync` (개인 Mac) 또는 `pip install -r` 컨테이너 내부 (Linux 호스트) | 옵션별로 다름. B: Docker 이미지에 빌드. C: PaaS 빌드. D: GH Actions 캐시. | 호스트 운영 방식(systemd vs docker compose) |
| **D11** | DB 마이그레이션 방식 | `alembic upgrade head` (이미 `backend/alembic/` 존재) | 해당 없음(R2/KV) 또는 D1 일 경우 D1 마이그레이션 도구 | D1 채택 시 마이그레이션 전략 |
| **D12** | 시작 명령 / 단일 진입점 | docker compose 1개 파일에서 `db + api`. `deploy/docker/docker-compose.yml` 기존 자산 활용 검토 | 빌드 명령(`fvm flutter build web`) + 배포(`wrangler` 등) | 호스트 운영 매뉴얼 1쪽 작성 여부 |
| **D13** | `portfolio.xlsx` 위치 / 캐시 디렉토리 | 호스트의 정해진 경로(예: `/var/lib/momentum/portfolio.xlsx`) + `data_cache/` | R2 버킷 내 prefix 또는 빌드 시 동봉 | `portfolio.xlsx` 의 SSoT 정의(누가 편집/업로드?) — 5장 N1 일부와 연결 |

> **요약**: 듀얼 타겟 결정으로 D1·D2·D3·D4·D6·D7·D8·D11·D12 는 채널별로 자동 분기됨. **여전히 사용자 결정이 필요한 핵심 잔여 항목**:
> - 웹 측 Python 실행 옵션 (A/B/C/D/E)
> - 웹 측 저장소 (R2/KV/D1)
> - 앱 측 갱신 주기 정책(D5)
> - 시크릿 매니저(D9)
> - `portfolio.xlsx` SSoT(D13/N1)

---

## 5. 신규 결정 항목 (듀얼 아키텍처 도입으로 발생)

### N1. 코드 공유: 두 백엔드가 공통 Python 로직을 어떻게 공유?

- **현황**: 스크리닝 로직은 `scripts/screener/*.py` 와 `backend/app/services/screener.py` 가 공존(추정). 단일 진실 소스 정의 필요.
- **옵션**:
  - (a) 단일 모듈 + 양쪽이 동일 Python 모듈 import (현재 단일 repo이므로 자연스러움)
  - (b) 공통 패키지(`momentum_core/`)로 분리 → `scripts/`, `backend/app/`, `웹용 컨테이너` 모두 import
  - (c) 코드 복제 (비추, 일관성 위험)
- **권고 톤**: 단일 repo이므로 (b) 가 자연스러워 보임. 단, 분리 비용·테스트 영향 검토 필요. **사용자 결정**.

### N2. 모바일 앱의 API base URL 환경별 분기

- **현황**: `frontend/lib/config/api_config.dart` 가 base URL을 보유한다고 추정.
- **옵션**:
  - (a) `--dart-define` 빌드 플래그 (`API_BASE_URL=https://...`)로 빌드 시 주입
  - (b) Flutter flavor (dev/staging/prod)로 분리
  - (c) 런타임 설정 화면에서 사용자가 입력
- **권고 톤**: (a) 가 가장 단순. 다만 앱스토어 빌드 vs 사이드로드 빌드의 base URL이 다를 수 있어 (b) 도 검토할 만함. **사용자 결정**.

### N3. 데이터 sync — 두 환경이 동시에 cron 돌면 어떻게 SSoT 유지?

- **위험**: 같은 알고리즘이라도 외부 데이터 소스의 응답 시점·캐시·결측 처리에 따라 미세하게 다른 결과가 나올 수 있음. 사용자가 앱과 웹에서 다른 결과를 보면 신뢰도 손상.
- **옵션**:
  - (a) **호스트 SSoT 모델**: 호스트가 갱신 → 결과를 R2에 업로드 → 웹은 R2 fetch (웹 측 컴퓨팅 불필요)
  - (b) **웹 SSoT 모델**: 웹용 컴퓨팅이 갱신 → 결과를 호스트가 fetch → DB에 INSERT
  - (c) **독립 갱신 + sanity check**: 두 환경이 각자 갱신 후 일치성 검증 작업
- **권고 톤**: 운영 단순성 면에서 (a) 가 매력적. (a) 를 택하면 웹 측 컴퓨팅 옵션 자체가 단순화(D 옵션에 가까워짐)됨. **사용자 결정**.

### N4. 인증/접근 제어

- **호스트 백엔드 노출 여부**: 모바일 앱이 호출하므로 공개 IP/도메인 필요. 인증 미적용 시 누구나 호출 가능.
- **옵션**:
  - (a) API 키 헤더(`X-API-Key`) — 가장 단순
  - (b) JWT (사용자 계정 도입 — 비용 큼)
  - (c) 단순 프라이빗 게이트(Cloudflare Tunnel, Tailscale 등으로 직접 노출 회피)
- **FCM 자격증명 분리**: 호스트에만 두는 것이 자연스러움 (웹 푸시 미사용 가정).
- **웹 측 인증**: 정적 JSON 공개 가정 시 인증 불필요.
- **권고 톤**: 모바일 앱만 호출한다면 (a) 또는 (c) 로 충분해 보임. 사용자 계정/포트폴리오 개인화가 들어오면 (b) 필요. **사용자 결정**.

### N5. 비용·모니터링·알림

- **비용 집계 후보**:
  - 호스트 VPS (월 5~20 USD)
  - PostgreSQL 백업 스토리지 (월 1~3 USD)
  - Cloudflare Pages (무료 티어 가정)
  - 데이터 갱신 컴퓨팅(옵션별 상이)
  - FCM (현재 무료)
  - 도메인 (연 10~15 USD)
- **모니터링/알림 옵션**:
  - (a) Healthcheck.io / UptimeRobot — cron이 안 돌면 알림
  - (b) Grafana Cloud 무료 티어
  - (c) 단순 Slack/Discord webhook
- **백엔드 `backend/api` 의 존속**: 역할 모호. (i) `backend/app` 으로 통합 후 삭제, (ii) 단순 read-only API로 별도 운영, (iii) 실험 코드로 보존 — 셋 중 사용자 결정.
- **권고 톤**: 단순함을 원하면 (c) 알림 + (i) 단일 백엔드 통합. **사용자 결정**.

---

## 6. 마이그레이션 단계 / 로드맵

> **전제**: 본 로드맵은 D1~D13 + N1~N5 결정이 끝난 후 적용. 결정 전에는 단계 0~1만 가능.

### 단계 0 — 결정 회의 (즉시)
- [ ] 사용자가 D1~D13 + N1~N5 항목별 답을 확정
- [ ] 본 문서에 결정 결과를 추가하여 v1.0으로 픽스
- 검증 기준: 매트릭스의 "사용자 결정 필요" 칸이 모두 비어 있음

### 단계 1 — 사실관계 정리(코드 변경 0)
- [ ] `backend/api` 와 `backend/app` 의 차이를 명확히 문서화
- [ ] `frontend/lib/config/api_config.dart` 와 `lib/services/api_client.dart` 의 현재 base URL 경로 점검
- [ ] `data_cache/` / `portfolio.xlsx` 위치 확인 (5장 N1·N3 자료)
- [ ] `DEPLOY_ENV=serverless|local|cloud` 분기가 코드 어디에 어떻게 영향 주는지 정리
- 검증 기준: 7장 "위험·미해결" 5건 모두 해소

### 단계 2 — 앱 타겟 가능 상태(호스트 백엔드 활성화)
- [ ] 호스트 1대 셋업 (VPS or 자체 서버)
- [ ] PostgreSQL 셋업 + `alembic upgrade head`
- [ ] `backend/app` 기동 (uvicorn + systemd 또는 docker compose)
- [ ] APScheduler 가 일간 스크리닝/스톱 체크/리밸런싱 정상 실행 (1주 관찰)
- [ ] FCM 자격증명 배치 + 푸시 동작 검증
- [ ] 모바일 앱(Flutter) 빌드 — base URL을 호스트로 설정
- [ ] 인증(N4) 적용
- 검증 기준: 모바일 앱이 호스트 백엔드와 정상 통신, 푸시 수신, 1주 무중단

### 단계 3 — 웹 타겟 Cloudflare 이전
- [ ] 호스팅: GitHub Pages → Cloudflare Pages 이전 (Flutter Web 빌드 산출물 배포)
- [ ] 데이터 갱신 옵션(A~E) 결정값에 따라 구현
  - 옵션 D 채택 시: GH Actions 그대로 두고 산출물 push 대상만 R2 또는 CF Pages assets로 변경
  - 옵션 B/C 채택 시: 컨테이너 이미지 빌드 + cron 트리거 + R2 push 파이프라인 구축
- [ ] 데이터 sync 정책(N3) 적용
- 검증 기준: 일 2회 갱신 정상, 웹과 앱이 동일 데이터 표시(N3 결정안 충족)

### 단계 4 — 풀 듀얼 운영
- [ ] 모니터링/알림(N5) 적용 — cron miss / 호스트 다운 / 빌드 실패 알림
- [ ] 비용 집계 1개월 관찰
- [ ] `backend/api` 처분 결정 적용(N5 (i)/(ii)/(iii))
- [ ] GitHub Actions 의 `daily-screening.yml` 등 잔존 워크플로 정리
- 검증 기준: 한 달 무중단, 비용이 가정 범위 내, 사용자가 양 채널을 동시에 쓰는 시나리오에 문제 없음

### 단계별 예상 소요(아주 개략)
- 단계 1: 0.5~1일
- 단계 2: 3~5일 (호스트 운영 노하우 정도에 따라 가변)
- 단계 3: 옵션 B/C는 3~7일, 옵션 D는 0.5~1일, 옵션 A/E는 1~4주
- 단계 4: 운영 안정화 1개월

---

## 7. 위험 / 가정 / 미해결

### 7.1 코드 사실 관계 미해결 5건
> 본 계획서가 단정하기에는 코드 확인이 더 필요한 항목.

1. **ApiClient 스키마 mismatch 가능성** — `frontend/lib/services/api_client.dart` 가 호출하는 응답 스키마와 `backend/app/schemas/*` 가 정의한 스키마가 일치하는지 미확인. 듀얼 운영 전에 점검 필요.
2. **`data_cache` 위치** — 어떤 스크립트가 어디에 캐시를 만드는지(예: `scripts/monitor/download_data.py` 의 parquet 캐시 위치) 확정 필요. 호스트/컨테이너에서 같은 경로 가정 가능성 점검.
3. **`/api/screening` 경로 mismatch** — `backend/app/routers/screening.py` 의 라우트 경로와 프론트엔드 호출 경로가 일치하는지 미확인.
4. **collector 역할** — `scripts/collector/` 의 Dockerfile + crontab(KST 23:00 KR / 07:00 US)이 GH Actions cron(KST 04:00 / 08:00)과 별개 역할인지, 중복인지 미확인. 단계 1에서 정리 필요.
5. **FCM 자격증명** — 자격증명 파일의 출처/소유/회전 정책이 미정. 단계 2 전에 확정 필요.

### 7.2 듀얼 운영 시 데이터 일관성 위험
- 두 환경이 각자 cron을 돌릴 경우 결과가 미세하게 어긋날 수 있음. N3 결정으로 SSoT를 명확히 하지 않으면 "어느 화면이 맞아요?" 라는 사용자 혼란 가능.
- **완화책**: SSoT 모델(N3 (a)/(b)) 채택을 우선 검토.

### 7.3 Cloudflare 옵션별 락인 정도
- **A (Workers Python)**: 강한 락인 + 베타 → 가장 위험.
- **B (Containers)**: 중간 락인. 표준 Docker 이미지이므로 다른 PaaS로 이주는 가능. CF의 Containers cron 트리거 방식에는 약간 의존.
- **C (외부 PaaS + R2)**: R2 → S3 호환이므로 데이터 락인 약함. PaaS는 교체 가능.
- **D (GH Actions 유지)**: 락인 거의 없음.
- **E (TS 포팅)**: 코드 자체는 이식 가능하지만, 다른 환경에서 다시 실행할 인프라가 필요.

### 7.4 가정 목록 (사용자 검토 요망)
- 모바일 앱 사용자 수가 호스트 1대로 감당 가능한 규모(가정값 미확정).
- 웹 트래픽이 Cloudflare Pages 무료 티어 내(월 < 10만 req).
- `portfolio.xlsx` 는 사용자가 수동 편집/업로드. 자동 동기화 없음.
- 인증은 N4 결정 전까지 단순 API key 가정.

---

## 8. 부록: 13개 항목 원본 정의 (참고)

| ID | 항목 | 설명 |
|---|---|---|
| D1 | DB 종류 | 어떤 DB(또는 파일/오브젝트 스토어)를 사용할지 |
| D2 | 백엔드 구현 | `backend/app` (풀스택 FastAPI+APScheduler+ORM) vs `backend/api` (단순 라우터) |
| D3 | 스케줄러 라이브러리/작업 정의 위치 | APScheduler vs 외부 cron(GH Actions, CF cron, OS cron 등) 및 작업 정의 코드 위치 |
| D4 | 스케줄러가 호출할 인터페이스 | subprocess(`python script.py`) vs 함수 호출(`run_screening()`) vs 스크립트 리팩터 후 함수화 |
| D5 | 갱신 주기 | GH Actions cron(KR 04:00/US 08:00)과 동일하게 갈지, 더 잦거나 다른 주기로 갈지 |
| D6 | 출력 파일/데이터 저장 위치 | DB row vs 파일(JSON/parquet) vs 오브젝트 스토어(R2/S3) |
| D7 | 프론트엔드 동작 모드 | serverless 정적 JSON fetch vs 로컬 REST API 호출 |
| D8 | 포트 할당 | FastAPI/DB/proxy 의 포트 매핑 |
| D9 | 환경변수 파일/설정 위치 | `.env` 위치, 시크릿 매니저, 빌드 시점 vs 런타임 분리 |
| D10 | 의존성 설치 방식 | `uv` vs `pip` vs Docker 이미지 vs PaaS buildpack |
| D11 | DB 마이그레이션 방식 | Alembic upgrade vs 수동 SQL vs 자동 적용 |
| D12 | 시작 명령 / 단일 진입점 | docker compose up vs systemd vs `make run` 등 |
| D13 | `portfolio.xlsx` 위치 / 캐시 디렉토리 | 파일 SSoT, 백업, 컨테이너 마운트 정책 |

---

## 9. 다음 행동 (사용자 입장)

1. 본 문서를 읽고 **D1~D13 + N1~N5 의 답을 확정**.
2. 답은 본 파일 9장 또는 별도 섹션에 inline 으로 추가.
3. 5장 N1~N5 중 결정이 어려운 항목은 **사용자가 직접 답을 정하지 않고 후보를 좁힌 뒤** 별도 회의에서 확정 가능.
4. 결정 완료 후, 단계 1(사실관계 정리)부터 실제 작업 착수.

> 본 문서는 결정용 초안이며, 자율 판단에 기반한 단정형 결정은 포함하지 않는다. 추가 정보가 필요하면 7장의 "코드 사실 관계 미해결 5건"을 먼저 점검할 것.
