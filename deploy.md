# 배포 계획서: 앱 + 웹 듀얼 타겟

> **상태**: v0.3 (2026-05-02 갱신) — 코드 공유 구조 + 앱 측 DB 종류 확정
> **확정 결정 요약 (v0.3 추가분 포함)**:
> 1. **N3 SSoT 모델**: "각 채널 독립 운영" — 앱·웹 각자 on-demand 스크리닝, 데이터 소스 공유 안 함. **cron 기반 정기 갱신 폐기**, 사용자 요청 시점에 스크리닝.
> 2. **데이터 전송 방식**: **DB 저장 + 캐시 패턴**. 라이브 캐시 TTL 5분, 종가 스냅샷은 KST 06:30 / 15:35 두 번. 콜드 캐시 첫 사용자는 그냥 대기.
> 3. **웹 측 Python 실행 (§3.2.2)**: **B. Cloudflare Containers** 확정. 웹 인프라 전체가 CF 단일 벤더 (D1 / R2 / KV / Workers / Cron Triggers).
> 4. **N1 코드 공유 구조 (v0.3 신규)**: **`scripts/` = 알고리즘 R&D**, **`backend/` = 프로덕션 단일 소스**. 호스트 백엔드와 CF Container 모두 `backend/` 코드를 사용. `scripts/screener/*.py` → `backend/app/services/*.py` 는 **수동 복사** 기반(import 공유 패키지 추출 X). 정책은 프로젝트 루트 `README.md` 에 명문화됨.
> 5. **D1 앱 측 DB (v0.3 신규)**: **PostgreSQL** 확정. asyncpg + Alembic 그대로. docker compose 에 `db` 서비스 포함. 도미노로 D8/D10/D11/D12 자동 결정.
> **여전히 미결**: 인증/접근 제어, GH Actions 워크플로 처분, `backend/api` 처분, 비용·모니터링, 모바일 앱 base URL 분기, TTL 매핑, 콜드 UX, `portfolio.xlsx` 위치 등 → §9 체크리스트 참조.
> **코드 변경 0건**: 본 커밋은 문서 갱신만 포함.
> **자율 판단 금지**: 미결 항목에 대해서는 단정형 결정을 포함하지 않는다.

---

## 0. TL;DR

- 서비스를 **앱(모바일)** 과 **웹** 두 채널로 제공한다.
- 두 채널은 **완전 독립 운영**: 같은 알고리즘·같은 외부 소스를 참조하지만 **공통 데이터 저장소·sync 절차 없음**. 미세한 결과 차이는 수용한다(§7.2).
- **갱신 모델 전환**:
  - 이전 모델: GitHub Actions cron (KR 04:00 / US 08:00 KST) → 정적 JSON push.
  - **새 모델**: 사용자 요청 시점에 **on-demand 스크리닝** + **5분 TTL 라이브 캐시** + **KST 06:30(US 마감 후) / 15:35(KR 마감 후) 종가 스냅샷 2회 저장**.
- **앱 타겟**: 호스트 머신(VPS/자체 서버)에 FastAPI(`backend/app`) + APScheduler(종가 스냅샷용 cron만 잔존) + **PostgreSQL**.
- **웹 타겟**: Cloudflare 단일 벤더. **CF Pages**(Flutter Web 호스팅) + **CF Workers**(API 라우팅) + **CF Containers**(Python 스크리너 실행, **빌드 컨텍스트 = `backend/`**) + **D1**(캐시 + 종가 스냅샷) + **R2**(정적 자산/대형 산출물) + **CF Cron Triggers**(종가 스냅샷 트리거).
- **코드 공유**: `backend/` 가 호스트와 컨테이너 양쪽의 단일 소스. `scripts/` 는 R&D 전용이며 배포 대상이 아님(상세는 `README.md`).

---

## 1. 개요

### 1.1 현재 상태(2026-05-02 기준)

- **이전 프로덕션 모델** *(폐기 예정 — §7.5 GH Actions 워크플로 처분 결정 필요)*: GitHub Actions cron(KST 04:00 KR, KST 08:00 US) → Python 스크리너 → 정적 JSON → GitHub Pages → Flutter Web fetch.
- **DB**: 사용 안 함. 결과는 `*.json` 파일.
- **백엔드 코드**:
  - `backend/app/`: FastAPI + APScheduler + SQLAlchemy(async, asyncpg) + PostgreSQL + FCM. **구현은 되어 있으나 미사용.**
  - `backend/api/`: 단순 라우터(`main.py`, `screening.py`, `portfolio.py`). **역할 모호** (§5 N5 참조).
- **프론트엔드**: Flutter (Web 빌드는 GH Pages, iOS/Android 자산 존재, **모바일 앱 빌드 곧 시작**).
- **GitHub Actions 워크플로 5개**: `daily-screening.yml` / `_screening-deploy.yml` / `deploy-web.yml` / `btc-signal.yml` / `test.yml`. 본 결정 후 처분 정책 필요.
- **환경변수 분기**: `DEPLOY_ENV=serverless|local|cloud` 가 코드에 존재. on-demand 모델로 전환 시 `local` 변형 필요(§4 매트릭스 D7).

### 1.2 새 운영 모델 — "on-demand + 단기 캐시 + 종가 아카이브"

#### 1.2.1 흐름
```
[사용자 요청] → [캐시 조회]
       ├── HIT(< 5분 경과)  → 즉시 응답
       └── MISS              → 스크리닝 실행 (5~30초 소요 예상)
                              → DB(또는 캐시 테이블)에 저장
                              → 응답
                              → 다음 5분 동안 동일 요청은 HIT
[종가 스냅샷 cron (06:30, 15:35 KST)]
       → 강제 스크리닝 → "종가 스냅샷" 테이블에 영속 저장 (TTL 없음)
```

#### 1.2.2 캐시 정책 정리

| 항목 | 값 | 비고 |
|---|---|---|
| 라이브 캐시 TTL (전체 시장 스크리닝) | **5분** | 비싼 작업. 캐시 적중률이 비용/응답 시간 핵심 |
| 라이브 캐시 TTL (BTC/ETH 단일 시그널 등 싼 작업) | **짧은 TTL 또는 stateless** | 하이브리드. 정확한 TTL 값/매핑은 **미결** (§4 신규 항목) |
| 종가 스냅샷 시점 | **KST 06:30** (US 정규장 마감 후), **KST 15:35** (KR 정규장 마감 후) | 시장별 스냅샷 페어 관리 |
| 콜드 캐시 첫 사용자 정책 | **그냥 대기** | stale-while-revalidate 미사용. UX 위험은 §7.4 |

> **하이브리드 매핑(=어떤 엔드포인트가 어느 TTL 그룹인지) 자체는 미결**. §9 체크리스트 항목.

### 1.3 사용자 시나리오 가정 (검토 요망)

| 채널 | 주 이용 시간 | 갱신 트리거 | 푸시/알림 | 사용자 규모 가정 |
|---|---|---|---|---|
| 앱 (iOS/Android) | 출퇴근/장중/장후 | 사용자 진입·새로고침 + 종가 cron | FCM 푸시 (스톱 트리거 등) | 소수~중규모 (값 미확정) |
| 웹 | 데스크톱 분석/공유 | 사용자 진입·새로고침 + 종가 cron | 불필요 | 가벼운 트래픽 |

> 위 가정은 검토용. 비용·스케일 정밀도가 필요하면 사용자 규모 가정 확정 필요.

### 1.4 트래픽·비용 가정 (개략)

- **웹**: CF Pages(정적) + Workers(요청 라우팅) + Containers(스크리닝) + D1/R2.
  - Pages: 무료 티어 가정.
  - Workers: 100k req/day 무료 티어 가정.
  - Containers: 신규 서비스 — 정확 요금/가용성 검증 필요(§7.3).
  - D1/R2: 무료 티어 또는 소액.
- **앱 백엔드(호스트)**: VPS 1대(2vCPU/4GB, 월 5~20 USD) + DB 동거.
- **종가 스냅샷 cron**: 일 2~4회 실행. on-demand 캐시 미스 비용은 사용자 진입 패턴에 종속.

---

## 2. 아키텍처 다이어그램

### 2.1 앱 타겟 (모바일) — 호스트 머신 백엔드

```
┌──────────────────────┐
│ Flutter iOS/Android  │
└──────────┬───────────┘
           │ HTTPS REST  +  (FCM Push 수신)
           ▼
┌──────────────────────────────────────────────────────────┐
│  Host Machine (VPS / 자체 서버)                           │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ FastAPI (backend/app)                                │ │
│ │  GET /api/screening                                  │ │
│ │   ├─ DB 캐시 조회 (TTL 5분)                          │ │
│ │   │    HIT  → 즉시 응답                              │ │
│ │   │    MISS → run_screening() 동기 실행 (5~30s)      │ │
│ │   │           → 캐시 테이블 INSERT                   │ │
│ │   │           → 응답                                  │ │
│ │   └─ /api/screening/snapshot/{date} → 종가 스냅샷    │ │
│ │                                                      │ │
│ │ APScheduler (cron 2회만 잔존)                        │ │
│ │  - KST 06:30 → US 종가 스냅샷 강제 갱신 + 저장       │ │
│ │  - KST 15:35 → KR 종가 스냅샷 강제 갱신 + 저장       │ │
│ │  - (선택) 스톱 체크 잡 — N4/N5와 함께 결정           │ │
│ └────────────┬─────────────────────────────────────────┘ │
│              │                                           │
│ ┌────────────▼────────────┐  ┌────────────────────────┐  │
│ │ DB (Postgres or SQLite) │  │ FCM 자격증명 (선택)     │  │
│ │  - cache_snapshot       │  │ /etc/momentum/fcm.json  │  │
│ │  - eod_snapshot         │  └────────────────────────┘  │
│ │  - holdings (모바일별)  │                              │
│ │  - device_tokens        │                              │
│ └─────────────────────────┘                              │
│                                                          │
│ scripts/screener/*.py  ← 호스트 Python 모노레포 import   │
└──────────────────────────────────────────────────────────┘
```

### 2.2 웹 타겟 — Cloudflare 단일 벤더 (옵션 B 확정)

```
┌──────────────────────┐
│ Flutter Web build    │
│  (정적 SPA)          │
└──────────┬───────────┘
           │ HTTPS GET (HTML/JS/CSS/icons)
           ▼
┌──────────────────────────────────────────────────────────┐
│  Cloudflare Pages                                        │
│  (Flutter Web 정적 호스팅 + 도메인)                       │
└──────────┬───────────────────────────────────────────────┘
           │
           │  fetch /api/screening, /api/snapshot/{date}, ...
           ▼
┌──────────────────────────────────────────────────────────┐
│  Cloudflare Workers (라우팅 + 캐시 게이트)                │
│   - GET /api/screening                                   │
│      ├─ D1 캐시 조회 (TTL 5분)                           │
│      │    HIT  → 즉시 응답                               │
│      │    MISS → CF Containers 호출 (Python 스크리너)    │
│      │           → 결과 D1 INSERT                        │
│      │           → 응답                                   │
│      └─ /api/snapshot/{date} → D1 종가 스냅샷 조회        │
│   - (선택) R2 의 대형 산출물(parquet, history) 직접 서명URL│
└──────────┬───────────────────────────────────────────────┘
           │ 호출
           ▼
┌──────────────────────────────────────────────────────────┐
│  Cloudflare Containers                                   │
│   - Docker 이미지 = scripts/screener/* + python deps     │
│   - 입력: 시장 코드(US/KR), 모드(live/snapshot)          │
│   - 출력: JSON 결과                                       │
└──────────┬───────────────────────────────────────────────┘
           │ 종가 스냅샷 결과 저장 (대형은 R2)
           ▼
┌──────────────────────────────────────────────────────────┐
│  D1 (cache + eod_snapshot)   |   R2 (대형 산출물)         │
└──────────────────────────────────────────────────────────┘
           ▲
           │ 트리거
           │
┌──────────┴───────────────────────────────────────────────┐
│  Cloudflare Cron Triggers                                │
│   - KST 06:30 → Worker → Container → US 종가 스냅샷 저장 │
│   - KST 15:35 → Worker → Container → KR 종가 스냅샷 저장 │
└──────────────────────────────────────────────────────────┘
```

### 2.3 데이터 정합성 (각 채널 독립 모델 채택의 의미)

- 앱과 웹은 **공유 저장소를 두지 않는다**. 각자 자기 DB(앱: 호스트 DB, 웹: D1)에 캐시·스냅샷을 가진다.
- 같은 시각에 두 채널이 스크리닝해도 외부 소스(yfinance/pykrx) 응답 시점·결측 처리·실행 머신 차이로 **결과가 미세하게 다를 수 있음**. 본 결정은 그 차이를 **수용**하는 입장.
- 종가 스냅샷도 두 채널에서 별도 저장. 일치 검증 절차 없음.
- 위험 인지·대응은 §7.2.

---

## 3. 채널별 기술 스택

### 3.1 앱 (모바일) — 호스트 머신 백엔드

#### 3.1.1 컴포넌트
- **프론트엔드**: Flutter (iOS/Android). API base URL 환경 분기 정책 미결(§5 N2).
- **백엔드 프레임워크**: `backend/app/` 의 FastAPI 활용. **`backend/` 는 프로덕션 코드의 단일 소스** — CF Container 도 같은 디렉토리를 빌드 컨텍스트로 사용한다(§3.2).
- **스케줄러**: `backend/app/scheduler.py` — 정기 cron은 **종가 스냅샷 2회(06:30/15:35 KST)** 만 잔존. 일간 스크리닝 잡은 on-demand 모델로 전환되어 사실상 폐기 (코드 수정은 단계 1에서).
- **DB**: ✅ **PostgreSQL 확정** (`postgresql+asyncpg://...`).
  - 드라이버: `asyncpg` 유지.
  - 마이그레이션: `alembic` 그대로(`backend/alembic/`). 첫 revision 생성 여부는 단계 1에서 결정 (§6 단계 1 체크리스트).
  - 운영 형태: docker compose `db` 서비스 또는 호스트 PostgreSQL 별도 운영 — 단계 1에서 확정.
- **알고리즘 코드**: `backend/app/services/screener.py` 가 운영용 단일 소스. R&D 결과는 `scripts/screener/*.py` 에서 검증한 뒤 **수동 복사** 로 반영(§7.1 #6 drift 위험 참조).
- **푸시**: Firebase Cloud Messaging — `app/services/notification.py`, 자격증명은 `APP_FCM_CREDENTIALS_PATH`.

#### 3.1.2 데이터 갱신 흐름
- **on-demand**: 모바일 앱이 `/api/screening` 호출 → DB 캐시 조회(TTL 5분) → MISS면 `run_screening()` **함수 호출(in-process)** → 결과 INSERT → 응답.
- **종가 스냅샷**: APScheduler 가 KST 06:30 / 15:35 에 강제 실행 → `eod_snapshot` 테이블 INSERT (TTL 없음, 영속).
- **싼 작업(BTC/ETH 시그널)**: 짧은 TTL 또는 stateless. 매핑은 미결.

#### 3.1.3 운영
- 단일 호스트(VPS) — `uvicorn` + systemd 또는 docker compose 1대.
- 백업: **`pg_dump` cron + 외부 스토리지 업로드** (권장 패턴, 사용자 결정 필요 — §9 체크리스트).
- 모니터링: 별도 결정 필요(N5).

### 3.2 웹 — Cloudflare 단일 벤더 (옵션 B 확정)

#### 3.2.1 컴포넌트
- **호스팅**: Cloudflare Pages — Flutter Web 빌드 산출물.
- **라우팅·캐시 게이트**: Cloudflare Workers (TS/JS) — `/api/*` 진입점, D1 캐시 조회 후 MISS 시 Containers 호출.
- **스크리너 실행**: Cloudflare Containers — 호스트 측과 동일한 **`backend/`** 디렉토리를 Docker 빌드 컨텍스트로 사용. 즉 컨테이너 안에서도 `backend/app/services/*` 코드를 실행한다. (이미지 사이즈 최적화 + 단일 소스 유지 목적. `scripts/` 는 컨테이너에 포함하지 않음.)
- **DB**: D1 (SQLite 호환). 캐시 + 종가 스냅샷.
- **오브젝트 스토리지**: R2 — 대형 산출물(parquet, history archive) 또는 정적 자산.
- **KV**: 작은 키/값(예: 마지막 cron 실행 시각). **사용 여부는 미결** — 단계 3에서 확정 가능.
- **cron**: Cloudflare Cron Triggers — Worker 발화 → Container 호출.

#### 3.2.2 Python 실행 옵션 비교 — **B 선택 확정**

| 옵션 | 설명 | 결과 |
|---|---|---|
| A. CF Workers Python (베타) | Pyodide 기반 Workers Python | **탈락** — pandas/yfinance/pykrx 호환성 위험, 베타 |
| **B. CF Containers + cron** | **Docker 컨테이너 + CF Cron Triggers** | **선택됨** — Python 자유도 + CF 단일 벤더 |
| C. 외부 PaaS cron + R2 push | Railway/Fly/Render 등에서 갱신 | 탈락 — 멀티벤더 운영 회피 |
| D. GH Actions 유지 + CF Pages만 이전 | 사실상 변경 0 | 탈락 — on-demand 모델/CF 통합 요구와 부합 X |
| E. TS 포팅 | 스크리닝 로직을 TS로 재구현 | 탈락 — 대규모 리팩터, 이중 유지보수 |

> **B 선택의 함의**:
> - 웹 인프라 전체가 CF 단일 벤더로 묶임 → 락인 강해짐 (§7.3)
> - Containers는 신규 서비스 — 가용성·요금·콜드 스타트 정책을 단계 3 시작 시 검증 필수
> - 호스트 측 Python 코드와 컨테이너 내 Python 코드가 **동일 모듈 트리**여야 운영 단순 → §5 N1 (코드 공유) 결정 필요

#### 3.2.3 데이터 저장소 — **D1 + R2 사용 확정 (KV 선택)**

| 저장소 | 용도 | 사용 |
|---|---|---|
| **D1** (SQLite 호환) | `cache_snapshot`, `eod_snapshot` 테이블 | **사용 확정** |
| **R2** (S3 호환) | parquet, history, 대형 정적 산출물 | **사용 확정** (정적 자산만) |
| **KV** (글로벌 KV) | hot path 소형 키 (예: 마지막 갱신 ts) | **선택** — 단계 3에서 필요 시 추가 |

---

## 4. 13개 결정 항목 매트릭스 (+ 신규 3 항목)

> **읽는 법**: ✅ = 본 갱신으로 결정됨. ❓ = 사용자 결정 필요. 채널별로 답이 분기됨.

| ID | 항목 | 앱 타겟 (호스트) | 웹 타겟 (CF) |
|---|---|---|---|
| **D1** | DB 종류 | ✅ **PostgreSQL** (asyncpg) | ✅ **D1** (+ R2 보조) |
| **D2** | 백엔드 구현 (`backend/app` vs `backend/api`) | ✅ `backend/app` 사용 | ✅ 백엔드 프로세스 없음 — Workers + Containers (`backend/api` 처분은 N5) |
| **D3** | 스케줄러 라이브러리 / 작업 정의 위치 | ✅ APScheduler (잡은 종가 스냅샷 2회만 잔존) | ✅ **CF Cron Triggers** (06:30 / 15:35 KST) |
| **D4** | 스케줄러가 호출할 인터페이스 | ✅ **함수 호출(in-process)** — `run_screening()` | ✅ **Worker → Container HTTP 호출** (Container 내부는 함수 호출 또는 subprocess — 컨테이너 진입점 설계 시 결정) |
| **D5** | 갱신 주기 | ✅ on-demand + 종가 스냅샷 2회. 별도 정기 cron 없음 | ✅ on-demand + 종가 스냅샷 2회. 별도 정기 cron 없음 |
| **D6** | 출력 파일/데이터 저장 위치 | ✅ DB 테이블(`cache_snapshot`, `eod_snapshot`). 파일 산출물은 비핵심 | ✅ D1 테이블(동일 스키마 권장) + 대형은 R2 |
| **D7** | 프론트엔드 동작 모드 | ✅ **로컬 REST API 모드** (모바일이 호스트 백엔드 호출) — `DEPLOY_ENV=local` 변형 정합성 점검 필요 | ✅ Workers `/api/*` → 정적 SPA가 호출. 정적 JSON 직접 fetch 모델은 폐기 |
| **D8** | 포트 할당 | ✅ 골격 결정 — FastAPI **8000** + Postgres **5432** + reverse proxy **80/443**. ❓ 외부 노출 여부/매핑 세부는 운영 방식(systemd vs docker compose)에 종속 | ✅ 해당 없음 (서버리스) |
| **D9** | 환경변수 파일/설정 위치 | ❓ `.env` 위치/시크릿 매니저 미결 (특히 FCM 자격증명) | ✅ CF Pages 환경변수 + Workers/Containers Secrets (CF 표준 패턴) |
| **D10** | 의존성 설치 방식 | ✅ **`uv sync`** (개인 Mac 개발) + **Docker 이미지** (Linux 호스트) 병행. `pyproject.toml` 단일 매니페스트 사용 | ✅ Docker 이미지 빌드 (`backend/` 컨텍스트) — 동일 `pyproject.toml` 사용 |
| **D11** | DB 마이그레이션 방식 | ✅ **Alembic + asyncpg** (`backend/alembic/`). ❓ 첫 revision 생성 vs `Base.metadata.create_all` 잔존 — 단계 1에서 결정 | ✅ **D1 마이그레이션 도구**(`wrangler d1 migrations`) |
| **D12** | 시작 명령 / 단일 진입점 | ✅ **docker compose** (`api` + `db` 2개 서비스) 권장 패턴. ❓ systemd 옵션 vs docker compose 옵션 최종 선택은 단계 1에서 | ✅ `wrangler deploy` (Workers + Cron Triggers + Containers) + Pages 배포 |
| **D13** | `portfolio.xlsx` 위치 / 캐시 디렉토리 | ❓ 호스트 경로 미결 (예: `/var/lib/momentum/portfolio.xlsx`) | ❓ R2 prefix vs 컨테이너 이미지 동봉 미결 — 누가 편집/업로드하는지 SSoT 정의 필요 |

### 4.1 신규 항목 (on-demand + 캐시 모델 도입으로 추가)

| 신규 ID | 항목 | 결정 / 미결 |
|---|---|---|
| **C1** | 라이브 캐시 TTL | ✅ 전체 시장 스크리닝 = **5분**. 싼 작업(BTC/ETH 시그널 등) = 짧은 TTL 또는 stateless. **엔드포인트별 TTL 매핑 표는 미결** (§9 체크리스트) |
| **C2** | 종가 스냅샷 시점 | ✅ **KST 06:30** (US 정규장 마감 후) + **KST 15:35** (KR 정규장 마감 후) |
| **C3** | 콜드 캐시 정책 | ✅ **그냥 대기** — stale-while-revalidate 미사용. 첫 사용자는 5~30초 로딩. **로딩 인디케이터/예상 시간 표시 정책은 UX 권장 사항으로 §7.4** |

### 4.2 매트릭스 요약
- v0.3 결정으로 **추가 해결된 항목**: D1(앱), D10(앱), D11(앱) 골격, D12(앱) 골격, D8(앱) 골격, N1.
- **자동 해결된 항목 누적**: D1, D2, D3, D4, D5, D6, D7, D10, D11, D12 (앱/웹 양측), C1·C2·C3 원칙.
- **여전히 사용자 결정이 필요한 항목**: D8(앱) 외부 노출 세부, D9(앱), D11(앱) 첫 revision 정책, D12(앱) systemd vs docker compose 최종 선택, D13, 그리고 §5 N2·N4·N5, C1 매핑 표, §3.1.3 백업 정책.

---

## 5. 신규 결정 항목 (듀얼 아키텍처 도입으로 발생)

### N1. 코드 공유 — 호스트 Python ↔ CF Container Python ✅ **확정 (v0.3)**
- **결정**: **(a) 모노레포 변형** — `scripts/` 는 알고리즘 R&D / 백테스트 전용이며 배포 대상 아님. **`backend/` 가 프로덕션 코드의 단일 소스(SSoT)** 이며, 호스트 백엔드와 CF Container 모두 이 디렉토리를 사용한다.
- **세부**:
  - CF Container Dockerfile 빌드 컨텍스트 = **`backend/` 디렉토리만** (이미지 사이즈 최적화).
  - `scripts/screener/*.py` ↔ `backend/app/services/*.py` 는 **수동 복사** 로 동기화. import 공유 패키지(`momentum_core/`) 추출은 하지 않음.
  - 정책은 프로젝트 루트 `README.md` 의 "프로젝트 구조 및 책임 분리" 섹션에 명문화됨.
- **수반 위험**: 수동 복사이므로 두 코드가 어긋날(drift) 수 있음 → §7.1 #6 항목으로 별도 관리.
- **함의**:
  - 호스트와 컨테이너가 동일 `pyproject.toml` 의존성 셋을 사용 → D10 자동 결정.
  - 컨테이너 빌드 캐시가 `scripts/`, `docs/`, `frontend/` 변경의 영향을 받지 않음.

### N2. 모바일 앱의 API base URL 환경별 분기 ❓ **미결**
- **현황**: `frontend/lib/config/api_config.dart` 가 base URL을 보유한다고 추정. 모바일 앱은 항상 호스트 백엔드를 호출하지만, 개발/스테이징/프로덕션 호스트가 다를 수 있음.
- **옵션**:
  - (a) `--dart-define=API_BASE_URL=https://...` 빌드 플래그
  - (b) Flutter flavor (dev/staging/prod)
  - (c) 런타임 설정 화면에서 사용자 입력
- **결정 필요 질문**: 모바일 앱 빌드 파이프라인에서 어느 방식이 가장 단순한가?

### N3. SSoT — 데이터 sync ✅ **확정**
- **결정**: 각 채널 독립 운영. 공유 저장소·sync 절차·일치 검증 모두 없음. 결과 미세 차이 수용.
- **함의**: 본 결정으로 §3.2.2 의 옵션 후보가 좁혀졌고(B 선택), 갱신 모델이 cron 기반에서 on-demand + 종가 cron 으로 전환됨.

### N4. 인증/접근 제어 ❓ **미결**
- **호스트 백엔드 노출**: 모바일 앱이 외부에서 호출하므로 공개 도메인/IP 필요. 인증 미적용 시 누구나 호출 가능.
- **CF Worker 노출**: 웹은 정적 자산 + Worker API. on-demand 스크리닝이 외부에서 호출 가능 → **악의적 캐시 무효화/리소스 소진 위험**.
- **옵션 (호스트)**:
  - (a) API 키 헤더(`X-API-Key`) — 단순
  - (b) JWT (사용자 계정 도입)
  - (c) Cloudflare Tunnel / Tailscale 로 직접 노출 회피
- **옵션 (Worker)**:
  - (a) 도메인별 Origin 검사 + 레이트리밋
  - (b) Turnstile (CF 캡차) + 레이트리밋
  - (c) 익명 허용 + 캐시 TTL 보호 (5분 TTL 자체가 보호막)
- **결정 필요 질문**: 사용자 계정 개념을 도입할 것인가? 안 한다면 (a)/(c) + 레이트리밋 조합으로 충분한가?

### N5. 비용·모니터링·`backend/api` 처분 ❓ **미결**
- **비용 집계 후보**: 호스트 VPS, DB 백업, CF Pages/Workers/Containers/D1/R2, FCM, 도메인.
- **모니터링 옵션**: Healthcheck.io / UptimeRobot, Grafana Cloud 무료, Slack/Discord webhook.
- **`backend/api` 처분**: (i) `backend/app` 으로 통합 후 삭제, (ii) read-only API로 보존, (iii) 실험 코드로 보존.
- **결정 필요 질문**:
  - 모니터링/알림 채널 1개를 정할 것인가?
  - `backend/api` 를 단계 1에서 삭제할 것인가, 별도 PR로 미루는가?

---

## 6. 마이그레이션 단계 / 로드맵 (on-demand 모델 기준 재작성)

> **전제**: §9 미결 항목 결정이 단계 1 시작 전에 끝나야 함 (특히 앱 측 DB 종류, 인증 정책).

### 단계 1 — 앱 측 호스트 백엔드 구현 (on-demand + 캐시)
- [ ] **PostgreSQL 셋업** — docker compose `db` 서비스 또는 호스트 Postgres 별도 운영 (D12 최종 선택은 단계 1 시작 시)
- [ ] **Alembic 첫 revision 생성** — 현재 `Base.metadata.create_all` 잔존 여부 확인 후 마이그레이션 기준선 확립 (D11 세부)
- [ ] DB 스키마 적용:
  - `cache_snapshot(market, payload, expires_at, ...)`
  - `eod_snapshot(market, snapshot_date, payload, ...)`
  - 기존 `holdings` / `device_tokens` 유지
- [ ] **알고리즘 코드 복사 정책 코드화** — 현재 `scripts/screener/screener_v3.py` 의 검증된 로직을 `backend/app/services/screener.py` 로 복사·정리. 두 파일 간 핵심 함수 시그니처/상수 1차 동기화 (drift 방지를 위한 베이스라인 — §7.1 #6).
- [ ] `backend/app/scheduler.py` 정리: 일간 스크리닝 잡 제거, **KST 06:30 / 15:35 두 잡만 잔존**
- [ ] `backend/app/routers/screening.py`: on-demand 캐시 게이트 구현 (TTL 5분, MISS 시 동기 실행)
- [ ] BTC/ETH 시그널 등 싼 엔드포인트 TTL 매핑 적용 (C1)
- [ ] `pg_dump` cron 백업 스크립트 (사용자 결정 후 적용 — §3.1.3)
- [ ] 단위 테스트 + 스모크 테스트 (캐시 HIT/MISS, TTL 만료, 종가 스냅샷 cron 발화)
- **검증 기준**:
  - 호스트 단독으로 on-demand 응답 5~30초 이내
  - 5분 내 동일 요청은 < 100ms 응답
  - 06:30/15:35 cron이 실제로 발화 + DB INSERT 확인
  - `backend/app/services/screener.py` 결과가 `scripts/screener/screener_v3.py` 결과와 **동일 시점·동일 입력에서 일치** (drift 베이스라인)
  - 1주 무중단

### 단계 2 — 모바일 앱 통합 + 환경 분기
- [ ] N2 결정 적용 (base URL 환경 분기)
- [ ] N4 결정 적용 (인증 헤더 / JWT 등)
- [ ] iOS/Android 빌드 + 호스트 백엔드 통신 검증
- [ ] FCM 푸시 동작 검증 (스톱 트리거가 잔존한다면)
- **검증 기준**:
  - 모바일 앱이 호스트 백엔드와 정상 통신
  - 빌드 환경(dev/staging/prod)별 base URL 분기 동작
  - 푸시 수신 성공률

### 단계 3 — 웹 측 CF Containers 인프라 구축
- [ ] CF 계정 셋업 + 도메인 연결
- [ ] D1 데이터베이스 생성 + 마이그레이션(`wrangler d1 migrations`)
- [ ] R2 버킷 생성 (대형 산출물용)
- [ ] **Container 이미지 빌드** (호스트 Python 코드 베이스 동일 — N1 결정 적용)
- [ ] Workers 작성: `/api/*` 라우트 + D1 캐시 게이트 + Container 호출
- [ ] Cron Triggers 설정: KST 06:30 / 15:35 → Worker → Container → D1 INSERT
- [ ] CF Pages 배포: Flutter Web 빌드(`fvm flutter build web --base-href /`)
- **검증 기준**:
  - 웹에서 `/api/screening` 호출 시 캐시 HIT/MISS 동작
  - Container 콜드 스타트 + 스크리닝 실행 시간 측정 (UX 위험 §7.4 평가용)
  - Cron Trigger 발화 + D1 종가 스냅샷 저장 확인
  - 호스트와 D1의 같은 시점 스냅샷 비교(미세 차이 허용 — §7.2)

### 단계 4 — 도메인·DNS·모니터링·인증 정책 + 정리
- [ ] 웹 도메인 / DNS 운영 정착
- [ ] N4 인증 정책 적용 (Worker 측 레이트리밋, Origin 검사 등)
- [ ] N5 모니터링 채널 1개 활성 (cron miss / 호스트 다운 / 빌드 실패 알림)
- [ ] **GH Actions 워크플로 처분**: `daily-screening.yml`, `_screening-deploy.yml`, `deploy-web.yml` 보존/제거 결정 적용 (§7.5)
- [ ] **`backend/api` 처분** (N5)
- [ ] 비용 1개월 관찰 + 가정 검증
- **검증 기준**:
  - 한 달 무중단
  - 비용이 §1.4 가정 범위 내
  - 사용자가 양 채널을 동시에 쓰는 시나리오에 문제 없음

### 단계별 예상 소요 (개략)
- 단계 1: 5~7일 (캐시 테이블 설계 + cron 정리 + 테스트)
- 단계 2: 3~5일 (모바일 빌드/인증/푸시)
- 단계 3: 7~14일 (CF Containers 신규 인프라 학습 + 빌드 파이프라인)
- 단계 4: 운영 안정화 1개월

---

## 7. 위험 / 가정 / 미해결

### 7.1 코드 사실 관계 미해결 6건
1. **ApiClient 스키마 mismatch 가능성** — `frontend/lib/services/api_client.dart` 와 `backend/app/schemas/*` 일치 점검 필요. on-demand 엔드포인트 응답 스펙 정합성 확인 필수.
2. **`data_cache` 위치** — `scripts/monitor/download_data.py` 의 parquet 캐시 위치. 호스트/컨테이너가 같은 경로 가정 가능한지 점검.
3. **`/api/screening` 경로 mismatch** — `backend/app/routers/screening.py` 라우트와 프론트엔드 호출 경로 일치 여부 미확인.
4. **collector 역할** — `scripts/collector/` Dockerfile + crontab(KST 23:00 KR / 07:00 US) 의 역할이 신규 종가 스냅샷 cron(06:30/15:35)과 중복인지 확인 후 정리 필요.
5. **FCM 자격증명** — 출처/소유/회전 정책 미정. 단계 2 전에 확정 필요.
6. **`scripts/` ↔ `backend/services/` 동기화 (drift)** — N1 결정에 따라 두 디렉토리는 **수동 복사** 로 동기화된다. 현재 `scripts/screener/screener_v3.py` 와 `backend/app/services/screener.py` 가 어느 정도 일치하는지 미확인. 단계 1 첫 작업으로 베이스라인을 맞춰야 하며, 이후에도:
   - 알고리즘 변경 시 양쪽 모두 반영했는지 검증할 수단 부재 (수동 점검에 의존).
   - 향후 drift 감지 자동화(예: 핵심 함수 해시 비교 CI) 도입 여부는 별도 결정.
   - 위험: 백테스트와 프로덕션이 다른 알고리즘으로 돌아가는 silent drift 가능.

### 7.2 각 채널 독립 운영의 데이터 일관성 위험 (수용)
- 같은 시점에 두 채널이 스크리닝해도 외부 소스 응답 시점·결측 처리·실행 머신 차이로 결과 미세 차이 발생 가능.
- 본 결정(N3)은 그 차이를 **수용**. 단, 사용자가 양 채널을 동시에 보고 다른 결과를 발견할 가능성은 존재.
- **완화책 제안 (자율 결정 아님, 검토용)**: 종가 스냅샷에 "산출 환경(host/cf)" 메타 필드를 두면 디버깅 시 차이 추적 가능.

### 7.3 CF Containers 신생 서비스 락인 위험
- Containers는 신규 기능 → 가용성/요금/지역/제한 변경 가능성.
- 웹 인프라 전체가 CF에 묶임 (Pages/Workers/Containers/D1/R2/Cron).
- **이주 비용**:
  - Containers → 다른 PaaS (Railway/Fly): Docker 이미지 그대로 → 비교적 낮음
  - D1 → 외부 SQLite/Postgres: 스키마 호환되지만 마이그레이션 절차 필요
  - Workers → 다른 엣지 런타임(Vercel/Deno Deploy): 코드 일부 재작성 필요
- **단계 3 시작 시 점검 필수**: 콜드 스타트 시간, 동시 실행 한도, 월 요금 상한.

### 7.4 콜드 캐시 + 첫 사용자 UX 위험
- 사용자가 OK했지만, 첫 진입 시 5~30초 대기는 모바일/웹 모두에서 이탈 위험 요인.
- **권장(자율 결정 아님)**:
  - 로딩 인디케이터 + 예상 소요 시간 텍스트 표시 ("최신 데이터 가져오는 중... 약 10~30초")
  - 종가 스냅샷이 있는 시간대(예: 새벽~오전)는 스냅샷을 폴백으로 우선 표시 후 백그라운드 갱신
  - 실패 시 직전 스냅샷으로 폴백
- 위 권장 사항을 적용할지/말지는 사용자 결정 필요 (§9 체크리스트).

### 7.5 GH Actions 워크플로 처분 결정 ❓ **미결**
- 이전 cron 기반 정기 갱신 모델이 폐기되면서 다음 워크플로의 운명을 정해야 함:
  - `daily-screening.yml` — 폐기 후보. 단, 단계 1~3 완료 전 안전망 역할 가능.
  - `_screening-deploy.yml` — 폐기 후보 (재사용 워크플로).
  - `deploy-web.yml` — CF Pages 이전 후 폐기 후보. 단, GH Pages 이중 운영 기간이 필요할 수 있음.
  - `btc-signal.yml`, `test.yml` — 일단 보존 가정.
- **결정 필요 질문**:
  - 단계별 워크플로 보존/제거 시점 (단계 4 일괄 vs 단계별 점진)
  - 안전망으로 1~2개월 병행 운영 후 제거할지

### 7.6 가정 목록 (사용자 검토 요망)
- 모바일 앱 사용자 수가 호스트 1대로 감당 가능한 규모.
- 웹 트래픽이 CF 무료 티어 내 (월 < 10만 req).
- `portfolio.xlsx` 는 사용자가 수동 편집/업로드. 자동 동기화 없음.
- 인증은 N4 결정 전까지 단순 API key 가정.
- 종가 스냅샷 시점 KST 06:30 / 15:35 가 시장 데이터 소스의 종가 데이터 가용 시점과 일치한다 (yfinance/pykrx 의 종가 갱신 시점 확인 필요).

---

## 8. 부록: 13개 항목 원본 정의 (참고)

> v0.1 원문 그대로 보존.

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

## 9. 다음 행동 (사용자 입장) — 미결 항목 체크리스트

v0.3 갱신으로 N1(코드 공유), D1(앱 측 DB)이 추가 확정되었다. 단계 1 시작 전 다음 미결 항목에 대한 사용자 답이 필요하다.

- [ ] **인증/접근 제어 정책** — 호스트 측(API key/JWT/터널), Worker 측(레이트리밋/Turnstile/익명) (N4)
- [ ] **GH Actions 워크플로 처분** — 5개 워크플로 각각 보존/제거 시점 (§7.5)
- [ ] **`backend/api` 처분** — 통합 후 삭제 vs 보존 (N5)
- [ ] **비용·모니터링 정책** — 모니터링 채널 1개 선택 (N5)
- [ ] **모바일 앱 base URL 환경 분기** — `--dart-define` vs flavor vs 런타임 입력 (N2)
- [ ] **싼 작업 TTL 매핑 표** — BTC/ETH 시그널 등 엔드포인트별 TTL 값 (C1 매핑)
- [ ] **콜드 캐시 UX 권장 적용 여부** — 로딩 인디케이터/예상 시간 표시, 종가 스냅샷 폴백 (§7.4)
- [ ] **앱 호스트 운영 세부** — docker compose vs systemd 최종 선택, 외부 노출 매핑, `.env` 위치 (D8 세부 / D9 / D12 세부)
- [ ] **DB 마이그레이션 첫 revision 정책** — Alembic 첫 revision 생성 vs `Base.metadata.create_all` 잔존 (D11 세부)
- [ ] **`pg_dump` 백업 정책** — 빈도/보관 기간/외부 스토리지 (§3.1.3)
- [ ] **`portfolio.xlsx` SSoT** — 호스트 경로 / R2 prefix / 컨테이너 동봉 (D13)
- [ ] **종가 스냅샷 시점 검증** — 06:30 / 15:35 가 yfinance/pykrx 종가 갱신 시점과 정합한지 (§7.6)
- [ ] **drift 감지 자동화 도입 여부** — `scripts/` ↔ `backend/services/` 일치 검증 CI (§7.1 #6)

> 위 항목이 결정되면 §6 단계 1 작업을 시작할 수 있다.

---

## 10. 결정 이력 / 변경 로그

### v0.3 — 2026-05-02
**확정**:
- **N1 코드 공유 구조**: `scripts/` = R&D 전용(배포 대상 아님), `backend/` = 프로덕션 단일 소스(SSoT). 호스트 + CF Container 모두 `backend/` 사용. `scripts/` ↔ `backend/services/` 는 **수동 복사** 동기화. 정책은 `README.md` 에 명문화.
- **D1 앱 측 DB**: PostgreSQL (asyncpg) 확정.
- 도미노로 자동 결정: D10(`uv` + Docker 병행, 동일 `pyproject.toml`), D11 골격(Alembic + asyncpg), D12 골격(docker compose `api` + `db`), D8 골격(8000 + 5432 + 80/443).

**변경**:
- 머리말에 결정 4·5 추가, 미결 목록 갱신
- §3.1 — DB Postgres 확정, `backend/` 단일 소스 명시, 알고리즘 코드 복사 정책 추가
- §3.1.3 — `pg_dump` cron 백업 권장 명시 (사용자 결정 필요)
- §3.2.1 — CF Container 빌드 컨텍스트 = `backend/` 명시 (`scripts/` 미포함)
- §4 매트릭스 — D1/D8/D10/D11/D12 ✅ 갱신, §4.2 요약 다시 정리
- §5 N1 — 확정 표기로 전환, (a) 변형 + drift 위험 함의 명시
- §6 단계 1 — Postgres 셋업 / Alembic 첫 revision / 알고리즘 복사 정책 코드화 / 백업 cron 항목 추가, 검증 기준에 drift 베이스라인 추가
- §7.1 — #6 항목 신설 (scripts/ ↔ backend/ 동기화 drift 위험)
- §9 — N1·D1 항목 제거, 새 미결 항목(첫 revision 정책 / `pg_dump` 정책 / drift 자동화) 추가
- §10 — v0.3 항목 신설

**미해결 (사용자 결정 대기)**:
- §9 체크리스트 12개

### v0.2 — 2026-05-02
**확정**:
- **N3 SSoT**: 각 채널 독립 운영 (앱·웹 별도 저장, 일치 검증 없음)
- **갱신 모델**: cron 기반 정기 갱신 폐기 → on-demand + 단기 캐시 + 종가 스냅샷 2회
- **C1 라이브 캐시 TTL**: 전체 시장 5분 / 싼 작업 짧은 TTL or stateless 하이브리드
- **C2 종가 스냅샷 시점**: KST 06:30 (US) + KST 15:35 (KR)
- **C3 콜드 캐시 정책**: 첫 사용자 그냥 대기 (stale-while-revalidate 미사용)
- **§3.2.2 웹 Python 실행**: B (Cloudflare Containers) 선택 — A/C/D/E 탈락
- **D1(웹)**: D1 + R2 (KV는 선택)
- **D3(웹)**: CF Cron Triggers
- **D7**: 정적 JSON fetch 모델 폐기, 두 채널 모두 REST API 모드
- **D2(앱)**: `backend/app` 사용 확정 (`backend/api` 처분은 N5에서 별도)

**변경**:
- §1 개요 — "on-demand + 단기 캐시 + 종가 아카이브" 모델로 전체 재서술
- §2 다이어그램 — 앱·웹 모두 새 모델 반영하여 재작성
- §3 채널별 스택 — 앱은 cron 잡 종가 2회만 잔존, 웹은 CF 단일 벤더 명시
- §3.2.2 옵션 표 — B 선택됨 / A·C·D·E 탈락 표기
- §4 매트릭스 — 결정/미결 ✅/❓ 표기, 신규 C1/C2/C3 항목 추가
- §5 신규 항목 — N3 확정 표기, 나머지 N1/N2/N4/N5 미결 유지 + Worker 인증 옵션 추가
- §6 로드맵 — 4단계 재작성 (앱 → 모바일 → 웹 CF → 운영 정착)
- §7 위험 — §7.4 콜드 스타트 UX, §7.5 GH Actions 처분 신설
- §9 체크리스트 — 미결 12개 항목 신설
- §10 결정 이력 신설

**미해결 (사용자 결정 대기)**:
- §9 체크리스트 12개 전부

### v0.1 — 2026-05-02 (초안)
- 13개 결정 항목(D1~D13) 매트릭스 정의
- 신규 항목 N1~N5 식별
- Cloudflare Python 실행 옵션 A~E 비교 표
- 4단계 마이그레이션 로드맵 초안
- 위험·미해결 5건 명시
