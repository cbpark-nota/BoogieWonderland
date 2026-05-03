# 배포 계획서: 앱 + 웹 듀얼 타겟

> **상태**: v0.4 (2026-05-03 갱신) — 인증·운영 형태·도메인 확정 + §6 학습용 세분화 + §11 아키텍처 근거 신설
> **확정 결정 요약 (v0.4 추가분 포함)**:
> 1. **N3 SSoT 모델**: "각 채널 독립 운영" — 앱·웹 각자 on-demand 스크리닝, 데이터 소스 공유 안 함. **cron 기반 정기 갱신 폐기**, 사용자 요청 시점에 스크리닝.
> 2. **데이터 전송 방식**: **DB 저장 + 캐시 패턴**. 라이브 캐시 TTL 5분, 종가 스냅샷은 KST 06:30 / 15:35 두 번. 콜드 캐시 첫 사용자는 그냥 대기.
> 3. **웹 측 Python 실행 (§3.2.2)**: **B. Cloudflare Containers** 확정. 웹 인프라 전체가 CF 단일 벤더 (D1 / R2 / KV / Workers / Cron Triggers).
> 4. **N1 코드 공유 구조**: **`scripts/` = 알고리즘 R&D**, **`backend/` = 프로덕션 단일 소스**. 정책은 `README.md` 에 명문화됨.
> 5. **D1 앱 측 DB**: **PostgreSQL** 확정.
> 6. **N4 인증 (v0.4 신규)**: **B안 사용자 계정 + JWT** 확정. `users` 테이블 + 회원가입/로그인 라우터 + JWT 미들웨어. Worker는 호스트와 동일한 시크릿으로 JWT 검증.
> 7. **D8/D12 운영 형태 (v0.4 신규)**: **docker compose** (`api` + `db`) + **Caddy 리버스 프록시**(자동 TLS) 확정. systemd / nginx 옵션 탈락.
> 8. **D9 시크릿 위치 (v0.4 신규)**: **(α) `.env` 파일 + `chmod 600`** 확정. docker compose `env_file:` 또는 systemd `EnvironmentFile=` (전자 채택). 시크릿 매니저 도입은 미룸.
> 9. **도메인 구조 (v0.4 신규)**: `cbpark.com`(개인 랜딩, 별도 프로젝트) / **`stock-portfolio.cbpark.com`**(웹 → CF Pages) / **`api-stock-portfolio.cbpark.com`**(호스트 백엔드 → Caddy + Docker). **도메인 등록처는 미결**(CF Registrar 검토 중).
> **여전히 미결**: 도메인 등록처, GH Actions 워크플로 처분, `backend/api` 처분, 비용·모니터링, 모바일 앱 base URL 분기, TTL 매핑, 콜드 UX, `portfolio.xlsx` 위치, Alembic 첫 revision, `pg_dump` 정책 등 → §9 체크리스트 참조.
> **코드 변경 0건**: 본 커밋은 문서 갱신만 포함.
> **자율 판단 금지**: 미결 항목에 대해서는 단정형 결정을 포함하지 않는다.
> **학습 목적 강화 (v0.4)**: §6 단계가 vertical slice 단위로 세분화되었고, §11에 단계 구분의 아키텍처적 근거 섹션이 추가됨.

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
| **D8** | 포트 할당 | ✅ FastAPI **8000**(컨테이너 내부) + Postgres **5432**(컨테이너 내부) + **Caddy 80/443**(외부 노출). 외부에서는 `api-stock-portfolio.cbpark.com` 만 노출, FastAPI/Postgres 포트는 호스트 외부에 직접 노출 X | ✅ 해당 없음 (서버리스) |
| **D9** | 환경변수 파일/설정 위치 | ✅ **`.env` + `chmod 600`** (α 옵션). docker compose `env_file:` 로 주입. FCM 자격증명은 `/etc/momentum/fcm.json` (호스트 마운트). 시크릿 매니저(Vault 등) 도입은 미룸 | ✅ CF Pages 환경변수 + Workers/Containers Secrets (CF 표준 패턴) |
| **D10** | 의존성 설치 방식 | ✅ **`uv sync`** (개인 Mac 개발) + **Docker 이미지** (Linux 호스트) 병행. `pyproject.toml` 단일 매니페스트 사용 | ✅ Docker 이미지 빌드 (`backend/` 컨텍스트) — 동일 `pyproject.toml` 사용 |
| **D11** | DB 마이그레이션 방식 | ✅ **Alembic + asyncpg** (`backend/alembic/`). ❓ 첫 revision 생성 vs `Base.metadata.create_all` 잔존 — 단계 1.1에서 결정 | ✅ **D1 마이그레이션 도구**(`wrangler d1 migrations`) |
| **D12** | 시작 명령 / 단일 진입점 | ✅ **docker compose**(`api` + `db` 2개 서비스) + **Caddy** 컨테이너 1개(또는 호스트 systemd Caddy). systemd-only 옵션 탈락 | ✅ `wrangler deploy` (Workers + Cron Triggers + Containers) + Pages 배포 |
| **D13** | `portfolio.xlsx` 위치 / 캐시 디렉토리 | ❓ 호스트 경로 미결 (예: `/var/lib/momentum/portfolio.xlsx`) | ❓ R2 prefix vs 컨테이너 이미지 동봉 미결 — 누가 편집/업로드하는지 SSoT 정의 필요 |

### 4.1 신규 항목 (on-demand + 캐시 모델 도입으로 추가)

| 신규 ID | 항목 | 결정 / 미결 |
|---|---|---|
| **C1** | 라이브 캐시 TTL | ✅ 전체 시장 스크리닝 = **5분**. 싼 작업(BTC/ETH 시그널 등) = 짧은 TTL 또는 stateless. **엔드포인트별 TTL 매핑 표는 미결** (§9 체크리스트) |
| **C2** | 종가 스냅샷 시점 | ✅ **KST 06:30** (US 정규장 마감 후) + **KST 15:35** (KR 정규장 마감 후) |
| **C3** | 콜드 캐시 정책 | ✅ **그냥 대기** — stale-while-revalidate 미사용. 첫 사용자는 5~30초 로딩. **로딩 인디케이터/예상 시간 표시 정책은 UX 권장 사항으로 §7.4** |
| **C4** | 도메인 구조 (v0.4 신규) | ✅ 결정 — `cbpark.com`(개인 랜딩, 별도 프로젝트) / `stock-portfolio.cbpark.com`(웹 → CF Pages) / `api-stock-portfolio.cbpark.com`(호스트 백엔드 → Caddy + Docker). ❓ **도메인 등록처는 미결** (CF Registrar 검토 중) |

### 4.2 매트릭스 요약
- v0.4 결정으로 **추가 해결된 항목**: D8(앱) 외부 노출 세부, D9(앱), D12(앱) 최종 선택, N4 본질, C4 도메인 구조.
- v0.3 결정으로 **추가 해결된 항목**: D1(앱), D10(앱), D11(앱) 골격, D12(앱) 골격, D8(앱) 골격, N1.
- **자동 해결된 항목 누적**: D1, D2, D3, D4, D5, D6, D7, D8, D9, D10, D11, D12 (앱/웹 양측 — 단, 일부는 세부 미결), N1, N3, N4, C1·C2·C3 원칙, C4 골격.
- **여전히 사용자 결정이 필요한 항목**: D11(앱) 첫 revision 정책, D13, §5 N2·N5, C1 매핑 표, C4 도메인 등록처, §3.1.3 백업 정책, §7.4 콜드 UX 적용 여부, §7.5 GH Actions 처분.

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

### N4. 인증/접근 제어 ✅ **확정 (v0.4) — B안 사용자 계정 + JWT**
- **결정**: **사용자 계정 도입**. 호스트 백엔드와 CF Worker 모두 JWT 기반 검증.
- **호스트 측 구현**:
  - DB 스키마: `users(id, email, password_hash, created_at, ...)` 테이블 추가 (Alembic 마이그레이션 1건).
  - 라우터: `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh` 신설.
  - 미들웨어: FastAPI `Depends(get_current_user)` 의존성 주입을 보호 라우터에 적용.
  - 비밀번호 해시: `bcrypt` 또는 `argon2` (단계 1.2에서 결정).
  - JWT 시크릿: `.env` 의 `JWT_SECRET` (D9 위치).
- **Worker 측 구현**:
  - 호스트와 **동일한 `JWT_SECRET`** 을 CF Workers Secret 으로 등록 → Worker 가 자체 검증.
  - 또는 호스트 introspection 엔드포인트(`/api/auth/verify`) 호출 (네트워크 비용 ↑, 단계 3.3에서 선택).
  - 익명 허용 라우트 vs 인증 필요 라우트 분리 (예: 종가 스냅샷 조회는 익명 허용, on-demand 스크리닝은 인증 필요 — 정책 단계 3.3에서 결정).
- **모바일 앱 측 구현**:
  - 로그인/회원가입 화면 (단계 2.2).
  - 토큰 저장: iOS Keychain / Android EncryptedSharedPreferences (`flutter_secure_storage` 패키지).
  - 401 응답 시 자동 토큰 재발급 흐름.
- **수반 위험**:
  - 비밀번호 분실 흐름(이메일 인증 등)은 v0.4 범위에 포함 안 함 — 미룸 (§11.3 참조).
  - 사용자 계정 도입은 **개인정보 처리** 책임이 따름 — 약관/개인정보처리방침 별도 작성 필요(법적 사안, 별도 결정).

### N5. 비용·모니터링·`backend/api` 처분 ❓ **미결**
- **비용 집계 후보**: 호스트 VPS, DB 백업, CF Pages/Workers/Containers/D1/R2, FCM, 도메인.
- **모니터링 옵션**: Healthcheck.io / UptimeRobot, Grafana Cloud 무료, Slack/Discord webhook.
- **`backend/api` 처분**: (i) `backend/app` 으로 통합 후 삭제, (ii) read-only API로 보존, (iii) 실험 코드로 보존.
- **결정 필요 질문**:
  - 모니터링/알림 채널 1개를 정할 것인가?
  - `backend/api` 를 단계 1에서 삭제할 것인가, 별도 PR로 미루는가?

---

## 6. 마이그레이션 단계 / 로드맵 (vertical slice 기반 학습용 세분화)

> **전제**: §9 미결 항목 중 단계 1.1 직전 필수 결정(예: Alembic 첫 revision 정책)만 결정하면 시작 가능. 나머지 미결은 해당 sub-step 직전에 결정.
>
> **읽는 법**: 각 단계는 여러 **vertical slice sub-step** 으로 나뉜다. 각 sub-step은 다음 5개 항목으로 기술한다:
> - **Goal**: 이 sub-step에서 달성하려는 한 줄 목표
> - **Deliverable**: 손에 잡히는 산출물(파일·서비스·엔드포인트 등)
> - **Acceptance**: 이 sub-step이 끝났다고 선언할 수 있는 객관적 기준
> - **Estimate**: 예상 소요(개략)
> - **Learning Note**: 이 sub-step을 통해 얻는 일반화 가능한 학습 포인트
>
> **vertical slice 원칙**: 가능한 한 sub-step 종료 시점에 end-to-end 동작 가능한 슬라이스가 남도록 설계. (왜 그런지는 §11 참조)

---

### 단계 1 — 앱 측 호스트 백엔드 (on-demand + 캐시 + 인증) — **5 sub-steps**

> **단계 목표**: `api-stock-portfolio.cbpark.com` 도메인으로 외부 노출되는 호스트 백엔드를 가동하고, 모바일 앱이 호출할 수 있는 인증 + 캐시 + 종가 스냅샷 메커니즘을 검증한다.
> **단계 종료 시 데모 가능**: `curl https://api-stock-portfolio.cbpark.com/api/screening -H "Authorization: Bearer ..."` 가 5분 캐시로 동작한다.

#### 1.1 인프라 슬라이스 — Docker compose + Postgres + Caddy + 도메인
- **Goal**: 빈 FastAPI(`/health` 200만 응답) + Postgres + Caddy 가 docker compose 로 호스트에서 기동되고, 외부 도메인으로 TLS 응답.
- **Deliverable**:
  - `deploy/docker/docker-compose.yml` (api + db + caddy 3개 서비스)
  - `Caddyfile` (`api-stock-portfolio.cbpark.com → api:8000`)
  - `.env` (Postgres 비밀번호, 도메인 이름) — `chmod 600`
  - DNS A 레코드 `api-stock-portfolio.cbpark.com → 호스트 IP`
  - Alembic 첫 revision 1건 (빈 스키마 또는 기존 모델 베이스라인 — D11 세부 결정 적용)
- **Acceptance**:
  - `curl https://api-stock-portfolio.cbpark.com/health` → `200 OK`
  - `docker compose ps` 3개 서비스 healthy
  - Caddy 자동 TLS 인증서 발급 성공 (Let's Encrypt)
  - `alembic upgrade head` 멱등 실행 확인
- **Estimate**: 1.5~2일
- **Learning Note**:
  - **인프라 vertical slice**: DB만 띄우고 끝내지 않고, "외부에서 TLS로 한 줄 요청이 통과하는" 경로 전체를 가장 먼저 검증. 가장 많은 가정(DNS, 방화벽, TLS, 컨테이너 네트워크)을 한 번에 깬다.
  - **TLS는 가장 늦게 하면 안 된다**: 자동 TLS(Caddy)가 안 되는 환경(예: 80 포트 차단, 도메인 미정착)을 단계 4에서 발견하면 재작업 비용이 큼.

#### 1.2 인증 슬라이스 — JWT + users 테이블 + 회원가입/로그인
- **Goal**: `users` 테이블, `/api/auth/register`, `/api/auth/login`, `Depends(get_current_user)` 미들웨어가 동작.
- **Deliverable**:
  - Alembic revision 추가 (`users` 테이블)
  - `backend/app/models/user.py`, `backend/app/routers/auth.py`, `backend/app/services/auth.py`
  - `JWT_SECRET` 등 `.env` 추가
  - 비밀번호 해시 라이브러리 결정·적용 (bcrypt vs argon2 — 1.2 시작 시 결정)
  - pytest: 등록 → 로그인 → 토큰으로 보호 라우터 호출 시나리오
- **Acceptance**:
  - `POST /api/auth/register` → 201 + 사용자 생성
  - `POST /api/auth/login` → 200 + JWT 반환
  - `GET /api/me` (또는 임시 보호 라우터) → 토큰 없으면 401, 토큰 있으면 200
  - 토큰 만료/위변조 케이스 401 반환
- **Estimate**: 1.5~2일
- **Learning Note**:
  - **인증을 알고리즘보다 먼저**: 인증을 나중에 끼워 넣으면 모든 라우터 시그니처를 다시 손봐야 함 → 미들웨어 위치를 라우터 작성 전에 확정.
  - **사용자 계정 도입은 되돌리기 어려운 결정 (reversibility 낮음)**: 한번 사용자가 가입하면 데이터 마이그레이션 부담 발생 → 일찍 결정·구현.

#### 1.3 알고리즘 슬라이스 — `/api/screening` on-demand + 5분 캐시
- **Goal**: `scripts/screener/screener_v3.py` 의 검증된 로직을 `backend/app/services/screener.py` 로 복사·정리하고, `/api/screening` 이 5분 캐시로 동작.
- **Deliverable**:
  - `backend/app/services/screener.py` 갱신 (scripts/와 핵심 함수 시그니처/상수 동기화 — drift 베이스라인 §7.1 #6)
  - `cache_snapshot(market, payload, expires_at, ...)` 테이블 추가 마이그레이션
  - `backend/app/routers/screening.py` — TTL 5분 캐시 게이트 + MISS 시 동기 실행
  - pytest: HIT/MISS, TTL 만료, 동시 요청 처리 시나리오
- **Acceptance**:
  - 첫 호출: 5~30초 응답
  - 5분 내 동일 요청: < 100ms 응답 (HIT)
  - TTL 만료 후 다음 호출: 다시 MISS → 동기 실행
  - 같은 시점·같은 입력 기준 `backend/app/services/screener.py` 결과가 `scripts/screener/screener_v3.py` 결과와 일치
- **Estimate**: 2~3일
- **Learning Note**:
  - **vertical slice = "한 엔드포인트를 끝까지"**: `/api/screening` 한 라우터를 골라 DB 캐시·스크리너 호출·응답까지 한 번에 완성. 라우터 다 만들고 캐시 다 만드는 horizontal layer 방식보다 통합 위험이 적음.
  - **drift 베이스라인은 단계 1에서**: scripts/와 backend/services/의 1차 일치를 단계 1.3에서 확보해 두면 이후 알고리즘 수정 시 비교 기준점이 생김.

#### 1.4 영속 데이터 슬라이스 — 종가 스냅샷 cron + 이력 조회
- **Goal**: APScheduler 가 KST 06:30 / 15:35 에 강제 스크리닝 → `eod_snapshot` 테이블 INSERT, 그리고 `/api/snapshot/{date}` 라우터가 조회 가능.
- **Deliverable**:
  - `eod_snapshot(market, snapshot_date, payload, ...)` 테이블 추가 마이그레이션
  - `backend/app/scheduler.py` 정리 — 일간 스크리닝 잡 제거, **KST 06:30 / 15:35 두 잡만 잔존**
  - `backend/app/routers/screening.py` 에 `GET /api/snapshot/{date}` 추가
  - pytest: 시간 모킹으로 cron 발화 + INSERT 검증
- **Acceptance**:
  - 06:30/15:35 cron이 실제 발화 + DB INSERT 확인 (수동 트리거 또는 시간 모킹)
  - `GET /api/snapshot/2026-05-02` → 해당 날짜 스냅샷 응답
  - 종가 스냅샷이 라이브 캐시와 별도 영속 (TTL 없음)
- **Estimate**: 1~1.5일
- **Learning Note**:
  - **라이브 캐시와 영속 스냅샷의 분리**: 두 저장소를 같은 테이블로 합치면 TTL 정책이 꼬임. 처음부터 분리.
  - **종가 시점 검증 필수**: 06:30 / 15:35 가 yfinance/pykrx 종가 데이터 가용 시점과 일치하는지 1.4 시작 시 실측(§9 체크리스트).

#### 1.5 운영 슬라이스 — 백업 + 로그 + 1주 안정성
- **Goal**: `pg_dump` cron 백업이 외부 스토리지로 저장되고, 1주 동안 무중단 운영 확인.
- **Deliverable**:
  - `pg_dump` cron 스크립트 (빈도/보관 정책 사용자 결정 후 — §3.1.3)
  - 백업 복원 리허설 1회 (실제 새 DB에 복원 후 행 수 확인)
  - 로그 회전 정책 (Caddy / FastAPI / Postgres)
  - 단순 `/health` 폴링 스크립트 (외부에서 1분마다)
- **Acceptance**:
  - 백업 파일이 외부 스토리지에 정상 업로드 + 복원 테스트 통과
  - 1주 무중단 (`/health` 다운타임 0)
  - 로그 디스크 사용량이 허용 범위 내 증가
- **Estimate**: 1~2일 + 1주 관찰
- **Learning Note**:
  - **복원 안 해본 백업은 백업이 아니다**: 백업 만들기보다 복원 리허설이 더 중요. 단계 1에서 한 번 해두면 평생 안전망.
  - **운영 슬라이스를 단계 1에 포함**: 운영(백업·로그·헬스체크)을 단계 4로 미루면 단계 2~3 진행 중 호스트가 죽었을 때 복구가 막막. 가장 작은 운영 안전망은 단계 1에 포함.

---

### 단계 2 — 모바일 앱 통합 — **3 sub-steps**

> **단계 목표**: Flutter 모바일 앱이 단계 1 호스트 백엔드와 인증·통신·푸시를 끝낸다.
> **단계 종료 시 데모 가능**: 실제 폰에서 회원가입 → 로그인 → 스크리닝 결과 화면 표시 → 푸시 알림 수신.

#### 2.1 빌드 파이프라인 + base URL 환경 분기
- **Goal**: dev/staging/prod 빌드가 각각 다른 API base URL 로 빌드되고, 실제 폰에 설치되어 `/health` 호출 성공.
- **Deliverable**:
  - N2 결정 적용 (`--dart-define=API_BASE_URL=...` vs flavor — 2.1 시작 시 결정)
  - `frontend/lib/config/api_config.dart` 갱신
  - iOS/Android 빌드 명령 정리 (또는 Fastlane lane)
- **Acceptance**:
  - `--dart-define=API_BASE_URL=https://api-stock-portfolio.cbpark.com` 로 빌드한 앱이 `/health` 200 수신
  - dev 빌드는 로컬 호스트, prod 빌드는 운영 도메인으로 분리 동작
- **Estimate**: 1~2일
- **Learning Note**:
  - **base URL 분기는 가장 작은 vertical slice**: `/health` 한 엔드포인트만으로 환경 분기 + 빌드 + 설치 + 통신을 한 번에 검증.

#### 2.2 로그인/회원가입 화면 + 토큰 저장
- **Goal**: 모바일 앱에서 회원가입 → 로그인 → 토큰 저장 → 다음 실행 시 자동 로그인 흐름 완성.
- **Deliverable**:
  - 로그인/회원가입 화면 (Flutter)
  - `flutter_secure_storage` 로 토큰 저장
  - 401 응답 시 자동 토큰 재발급 인터셉터
  - 로그아웃 흐름
- **Acceptance**:
  - 신규 가입 → 로그인 → 앱 재시작 → 자동 로그인
  - 토큰 만료 후 호출 → 자동 재발급 → 호출 성공
  - 로그아웃 후 토큰 제거 + 보호 라우터 호출 시 로그인 화면으로 이동
- **Estimate**: 2~3일
- **Learning Note**:
  - **토큰 저장은 secure storage 필수**: SharedPreferences 평문 저장은 단계 4에서 보안 점검 시 반드시 지적됨 → 처음부터 secure storage 채택.

#### 2.3 스크리닝 화면 연동 + FCM 푸시
- **Goal**: 모바일 앱이 `/api/screening` 결과를 화면에 표시하고, FCM 푸시(스톱 트리거 등)를 수신.
- **Deliverable**:
  - 스크리닝 결과 화면 (기존 화면 갱신)
  - 콜드 캐시 로딩 인디케이터 + 예상 소요 시간 텍스트 (§7.4 권장 적용 여부 결정 후)
  - FCM 토큰 등록 → `device_tokens` 테이블 INSERT
  - 푸시 수신 핸들러 (포그라운드/백그라운드)
- **Acceptance**:
  - 첫 진입(콜드 캐시) → 로딩 인디케이터 → 결과 표시
  - 5분 내 재진입 → 즉시 표시 (캐시 HIT)
  - 호스트에서 푸시 발송 → 폰에서 수신
- **Estimate**: 2~3일
- **Learning Note**:
  - **콜드 캐시 UX는 백엔드만의 문제가 아님**: 5~30초 대기를 사용자가 받아들이게 하는 것은 UI의 책임. 단계 2.3에서 인디케이터 정책을 정해두면 단계 3 웹에서도 같은 패턴 재사용 가능.

---

### 단계 3 — 웹 측 CF 인프라 (Pages + Workers + Containers + D1) — **4 sub-steps**

> **단계 목표**: `stock-portfolio.cbpark.com` 도메인에서 웹 SPA + on-demand 스크리닝 + 종가 스냅샷이 모두 CF 단일 벤더 위에서 동작한다.
> **단계 종료 시 데모 가능**: 브라우저에서 `https://stock-portfolio.cbpark.com` → 로그인 → 스크리닝 화면 표시.

#### 3.1 CF 계정 + 도메인 + 빈 Pages 배포
- **Goal**: CF 계정·도메인·DNS·빈 Pages 배포가 끝나서 `https://stock-portfolio.cbpark.com` 이 정적 "Hello" 페이지 응답.
- **Deliverable**:
  - CF 계정 셋업
  - 도메인 등록처 결정 (CF Registrar 등 — C4 미결 해결)
  - DNS 레코드 (`stock-portfolio.cbpark.com` 의 CNAME → CF Pages, `api-stock-portfolio.cbpark.com` 은 단계 1.1 그대로)
  - 빈 Flutter Web 빌드(`fvm flutter build web`) 또는 정적 HTML 1장 Pages 배포
- **Acceptance**:
  - `curl https://stock-portfolio.cbpark.com` → 200 (정적 응답)
  - DNS / TLS / Pages 배포 파이프라인 검증
- **Estimate**: 0.5~1일
- **Learning Note**:
  - **계정·도메인을 가장 먼저**: 신규 벤더 셋업의 가장 큰 함정은 가입·결제·DNS 위임 같은 행정 절차가 시간 차로 발목을 잡는다는 것. 빈 응답이라도 도메인을 일찍 띄워야 한다.

#### 3.2 D1 + R2 + Container 이미지 빌드
- **Goal**: 단계 1의 `backend/` Dockerfile 을 재사용해 CF Container 이미지를 빌드·배포하고, D1 / R2 가 생성되어 마이그레이션이 적용됨.
- **Deliverable**:
  - `wrangler.toml` (Workers + Containers + D1 + R2 정의)
  - D1 마이그레이션 (단계 1의 Postgres 스키마를 SQLite 호환으로 변환 — `cache_snapshot`, `eod_snapshot` 만 우선)
  - R2 버킷 생성
  - Container 이미지 빌드 (`backend/` 컨텍스트, 단계 1 Dockerfile 재사용)
  - 컨테이너에서 임시 진입점(`python -c "from app.services.screener import run_screening; print(run_screening('US'))"`)이 동작
- **Acceptance**:
  - `wrangler d1 execute --command "SELECT 1"` 성공
  - `wrangler r2 object list` 성공
  - 컨테이너가 CF에서 `run_screening()` 1회 실행 후 정상 종료 (콜드 스타트 시간 측정값 기록)
- **Estimate**: 3~5일 (CF Containers 학습 시간 포함)
- **Learning Note**:
  - **가장 불확실한 부분을 단계 3 초반에**: CF Containers 가 yfinance/pykrx 같은 무거운 의존성을 잘 돌리는지가 본 프로젝트의 최대 기술 리스크(§7.3) → 3.2에서 가장 먼저 검증. 이게 안 되면 §3.2.2 옵션 재검토 필요(대규모 리스크).
  - **단계 1 Dockerfile 재사용 = drift 방지 + 작업량 절감**: 단계 1을 컨테이너로 한 보상이 단계 3에서 회수됨.

#### 3.3 Worker `/api/*` 라우팅 + JWT 검증 + 캐시 게이트
- **Goal**: Worker 가 `/api/*` 요청을 받아 JWT 검증 + D1 캐시 조회 + MISS 시 Container 호출.
- **Deliverable**:
  - Workers 코드(TS) — 라우팅 + JWT 검증 (호스트와 동일 시크릿) + D1 SELECT/INSERT + Container 호출
  - 익명 허용 라우트 vs 인증 필요 라우트 구분 (정책 3.3 시작 시 결정)
  - `JWT_SECRET` 을 CF Workers Secret 에 등록
- **Acceptance**:
  - 단계 1.2에서 발급받은 토큰을 Worker `/api/screening` 에 전달 → 200
  - 토큰 없거나 만료 → 401
  - 5분 내 동일 요청 → D1 캐시 HIT (< 100ms)
  - 캐시 MISS → Container 호출 → D1 INSERT → 응답
- **Estimate**: 2~4일
- **Learning Note**:
  - **호스트와 Worker 간 시크릿 공유**: 같은 JWT secret 을 두 곳에 배포하는 운영 패턴이 처음 등장. 회전 시 두 곳 동시에 갱신해야 한다는 운영 부채를 인식.

#### 3.4 Cron Triggers + Flutter Web 통합 + 데이터 일관성 점검
- **Goal**: KST 06:30 / 15:35 Cron Trigger 가 Worker 발화 → Container 실행 → D1 INSERT, 그리고 Flutter Web 빌드를 Pages 에 정식 배포.
- **Deliverable**:
  - `wrangler.toml` Cron Triggers 정의
  - Flutter Web 빌드 정식 배포 (`fvm flutter build web --base-href /`)
  - 호스트 D1 vs CF D1 같은 시점 종가 스냅샷 비교 스크립트 (수동, 일치성 메모)
- **Acceptance**:
  - 다음 06:30 또는 15:35 에 Cron 발화 + D1 종가 스냅샷 INSERT
  - 브라우저에서 `https://stock-portfolio.cbpark.com` → 로그인 → 스크리닝 결과 표시
  - 호스트와 D1 종가 스냅샷 비교: 미세 차이는 §7.2 수용 범위 내인지 메모
- **Estimate**: 2~3일
- **Learning Note**:
  - **데이터 일관성은 검증 가능한 메트릭으로**: "다르다/같다" 가 아니라 "Top10 중 9개 일치, 1개 순위 차이" 같이 측정 → 미세 차이 수용 정책(N3)이 실제로 받아들일 만한지 객관 평가.

---

### 단계 4 — 운영 정착 — **3 sub-steps**

> **단계 목표**: 모니터링·알림이 자리 잡고, 이전 GH Actions 모델·`backend/api` 같은 부산물이 정리되고, 1개월 비용·안정성을 회고한다.
> **단계 종료 시 데모 가능**: 사고 발생 시 알림이 즉시 도달, 비용·다운타임 보고서 1장.

#### 4.1 모니터링 + 알림 채널
- **Goal**: 호스트 다운, cron miss, 빌드 실패 시 사용자(개발자)에게 알림이 도달.
- **Deliverable**:
  - N5 모니터링 채널 결정 후 적용 (Healthcheck.io / UptimeRobot / Slack webhook 중 1개)
  - 호스트 `/health` 외부 폴링 (1분 간격)
  - 06:30 / 15:35 cron 실행 후 핑(heartbeat) 전송
  - CF Worker 에러율 알림 (CF 자체 알림 또는 webhook)
- **Acceptance**:
  - 호스트 의도적 다운 → 5분 내 알림 수신
  - cron 의도적 실패 → 알림 수신
- **Estimate**: 1~2일
- **Learning Note**:
  - **알림 없는 운영은 운영이 아니다**: 기능이 다 돌아가도 사고를 모르면 사용자가 먼저 발견 → 신뢰 손상이 가장 큼.

#### 4.2 GH Actions 워크플로 처분 + `backend/api` 처분
- **Goal**: 이전 cron 기반 정기 갱신 모델의 잔존 워크플로와 모호한 `backend/api` 디렉토리를 정리.
- **Deliverable**:
  - §7.5 결정 적용 (`daily-screening.yml`, `_screening-deploy.yml`, `deploy-web.yml` 보존/제거)
  - N5 결정 적용 (`backend/api` 통합 후 삭제 vs 보존)
  - 정리 PR 1~2개
- **Acceptance**:
  - 보존 결정한 워크플로만 `.github/workflows/` 에 남음
  - `backend/api` 는 결정대로 처분 — 제거된 경우 import 경로 점검
- **Estimate**: 0.5~1일
- **Learning Note**:
  - **부산물 정리는 단계 4에서**: 단계 1~3 중에 정리하면 안전망(GH Pages 병행)이 사라져 사고 시 복구 불가. 단계 4까지 안전망으로 살려뒀다가 자신감이 생긴 후 제거.

#### 4.3 1개월 비용·안정성 회고
- **Goal**: §1.4 비용 가정 검증 + 1개월 다운타임/사고 회고.
- **Deliverable**:
  - CF 청구 내역 1개월 (Pages/Workers/Containers/D1/R2 항목별)
  - 호스트 VPS 1개월 비용
  - 다운타임/사고 로그 1장
  - 회고 문서 (`docs/postmortem-launch-2026-XX.md` — 이 문서만 신규 작성)
- **Acceptance**:
  - 비용이 §1.4 가정 범위 내 또는 초과 시 원인 메모
  - 다운타임 합계 + 주요 사고 1~3건 회고
- **Estimate**: 1일 + 1개월 관찰
- **Learning Note**:
  - **회고는 다음 프로젝트의 시작점**: 가정이 맞았는지/틀렸는지 기록해두지 않으면 다음 프로젝트에서 같은 실수 반복.

---

### 단계별 예상 소요 (개략)
| 단계 | sub-step 수 | 예상 소요 |
|---|---|---|
| 단계 1 | 5 | 7~11일 + 1주 관찰 |
| 단계 2 | 3 | 5~8일 |
| 단계 3 | 4 | 7.5~13일 |
| 단계 4 | 3 | 2.5~4일 + 1개월 관찰 |
| **합계** | **15** | **22~36일 작업 + 1개월 운영 관찰** |

> 위 추정은 1인 작업 가정. 실제 일정은 사용자 가용 시간·미결 항목 결정 지연·CF Containers 학습 곡선 등에 따라 변동.

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

v0.4 갱신으로 N4(인증=JWT), D8/D9/D12(운영 형태=docker compose+Caddy+`.env`), C4(도메인 구조)가 추가 확정되었다. 단계 1.1 시작 전·각 sub-step 시작 전 다음 미결 항목에 대한 사용자 답이 필요하다.

- [ ] **도메인 등록처** — CF Registrar 등 어디서 등록할지 (C4 세부, 단계 3.1 직전 결정 필요)
- [ ] **GH Actions 워크플로 처분** — 5개 워크플로 각각 보존/제거 시점 (§7.5, 단계 4.2 직전)
- [ ] **`backend/api` 처분** — 통합 후 삭제 vs 보존 (N5, 단계 4.2 직전)
- [ ] **비용·모니터링 정책** — 모니터링 채널 1개 선택 (N5, 단계 4.1 직전)
- [ ] **모바일 앱 base URL 환경 분기** — `--dart-define` vs flavor vs 런타임 입력 (N2, 단계 2.1 직전)
- [ ] **싼 작업 TTL 매핑 표** — BTC/ETH 시그널 등 엔드포인트별 TTL 값 (C1 매핑, 단계 1.3 직전)
- [ ] **콜드 캐시 UX 권장 적용 여부** — 로딩 인디케이터/예상 시간 표시, 종가 스냅샷 폴백 (§7.4, 단계 2.3 직전)
- [ ] **DB 마이그레이션 첫 revision 정책** — Alembic 첫 revision 생성 vs `Base.metadata.create_all` 잔존 (D11 세부, 단계 1.1 직전)
- [ ] **비밀번호 해시 라이브러리** — bcrypt vs argon2 (N4 세부, 단계 1.2 직전)
- [ ] **Worker 익명/인증 라우트 분리 정책** — 종가 조회는 익명, on-demand는 인증 등 (N4 세부, 단계 3.3 직전)
- [ ] **`pg_dump` 백업 정책** — 빈도/보관 기간/외부 스토리지 (§3.1.3, 단계 1.5 직전)
- [ ] **`portfolio.xlsx` SSoT** — 호스트 경로 / R2 prefix / 컨테이너 동봉 (D13)
- [ ] **종가 스냅샷 시점 검증** — 06:30 / 15:35 가 yfinance/pykrx 종가 갱신 시점과 정합한지 (§7.6, 단계 1.4 직전)
- [ ] **drift 감지 자동화 도입 여부** — `scripts/` ↔ `backend/services/` 일치 검증 CI (§7.1 #6)

> v0.4부터는 모든 항목이 단계 1.1 시작을 막지는 않고, 해당 sub-step 직전에 답하면 된다(§6 sub-step 옆 "직전" 표기 참조).

---

## 10. 결정 이력 / 변경 로그

### v0.4 — 2026-05-03
**확정**:
- **N4 인증/접근 제어**: B안(사용자 계정 + JWT) — `users` 테이블 + 회원가입/로그인 라우터 + JWT 미들웨어. Worker는 호스트와 동일 시크릿으로 검증.
- **D8/D12 운영 형태**: docker compose(`api` + `db`) + Caddy 자동 TLS. systemd-only 옵션 탈락.
- **D9 시크릿 위치**: `.env` + `chmod 600` (α 옵션). 시크릿 매니저 도입은 미룸.
- **C4 도메인 구조**: `cbpark.com`(개인 랜딩) / `stock-portfolio.cbpark.com`(웹) / `api-stock-portfolio.cbpark.com`(호스트 백엔드). 도메인 등록처는 미결.

**변경**:
- 머리말 — v0.4 결정 4건 추가, 미결 목록 갱신, 학습 목적 강화 명시
- §4 매트릭스 — D8/D9/D12 ✅ 갱신, §4.1 표에 C4 도메인 항목 추가, §4.2 요약 다시 정리
- §5 N4 — ✅ 확정 + B안 구현 세부(호스트/Worker/모바일) + 수반 위험
- §6 — **전면 재작성**. 4단계를 15개 vertical slice sub-step으로 세분화. 각 sub-step에 Goal/Deliverable/Acceptance/Estimate/Learning Note 5항목 적용
- §9 체크리스트 — N4·D8/D9/D12 제거, 신규 4건 추가(도메인 등록처/비밀번호 해시/Worker 라우트 정책/sub-step 직전 표기)
- §10 — v0.4 항목 신설
- §11 — **신설**. 단계 구분의 아키텍처적 근거(원칙·적용·미룸·트리거·게이트)

**미해결 (사용자 결정 대기)**:
- §9 체크리스트 14개 (v0.3 13개 → 해결 2건 / 신규 3건 → 순증 +1)

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

---

## 11. 단계 구분의 아키텍처적 근거 (학습용 메타 섹션)

> **이 섹션의 목적**: §6의 단계·sub-step 배치가 "왜 그 순서인지"를 일반화 가능한 원칙으로 설명한다. 다른 프로젝트에 적용할 수 있는 사고 방식을 남기는 것이 목표.
>
> **읽는 법**: 11.1 일반 원칙 → 11.2 본 프로젝트 적용 → 11.3 의식적으로 미룬 것 → 11.4 멈춤 트리거 → 11.5 의사결정 게이트.

### 11.1 단계 구분의 일반 원칙 (시니어 아키텍트 사고 방식)

#### (1) Vertical slice 우선 (Horizontal layer 회피)
- **Vertical slice**: 한 sub-step이 끝나면 "한 기능이 사용자 입력부터 응답까지 동작" 하는 얇은 슬라이스가 남는다. 예: §6 단계 1.3 = `/api/screening` 한 라우터를 DB·캐시·스크리너 호출까지 끝까지 한 번에.
- **Horizontal layer (회피)**: "DB 다 만들고 → 라우터 다 만들고 → UI 다 만든다." 마지막에 통합할 때까지 동작 검증이 안 됨.
- **Horizontal 방식의 위험**:
  - 피드백 루프 지연: 첫 사용자 데모가 마지막에야 가능 → 가정 검증이 늦음.
  - 통합 위험 누적: 인터페이스 mismatch 가 마지막에 한꺼번에 터짐.
  - 데모 불가능: 중간 시점에 보여줄 게 없어 이해관계자 신뢰가 떨어짐.
  - 우선순위 변경 비용 증가: 중간에 방향을 바꾸면 만든 layer 가 다 무용지물.
- **Vertical 방식의 보상**:
  - 매 sub-step 종료 시점에 데모 가능한 산출물이 있음 → 단계별 의사결정 게이트(§11.5)가 의미 있음.
  - 가장 위험한 가정을 가장 일찍 검증 가능.
  - 우선순위가 바뀌어도 이미 만든 슬라이스는 계속 동작.

#### (2) Risk-first ordering (가장 불확실한 것을 일찍)
- "확실한 것부터" 가 아니라 **"불확실해서 잘못되면 전체 계획이 무너지는 것"** 부터 검증한다.
- 불확실성의 신호:
  - 새 벤더/신생 서비스 (예: CF Containers — §7.3)
  - 외부 의존성의 동작 보장 부재 (예: yfinance/pykrx 가 컨테이너 안에서도 동작?)
  - 성능 가정 (예: on-demand 5~30초가 사용자에게 받아들여질지)
  - 보안/인증 모델 (잘못 깔면 전체 다시)
- 확실한 것을 먼저 만들면 일은 진척되어 보이지만, 핵심 리스크가 막판에 터지면 그동안 만든 것을 다 버려야 할 수 있다.

#### (3) Reversibility 고려 (Two-way door vs One-way door)
- **One-way door (되돌리기 어려움)**: DB 스키마, 인증 모델, 도메인 구조, 사용자 계정 도입.
  → 이런 결정은 일찍, 신중하게, 충분히 검증 후.
- **Two-way door (되돌리기 쉬움)**: UI 색상, 캐시 TTL 값, 모니터링 채널, 로그 포맷.
  → 일단 정하고 나중에 바꿔도 비용 작음. 미루지 말고 그냥 정함.
- **이 프로젝트 예**:
  - 단계 1.2 인증을 일찍: 사용자 계정 도입은 one-way door (가입한 사용자 데이터 마이그레이션 부담).
  - 단계 1.4 종가 스냅샷 시점 (06:30/15:35) 은 two-way door — 일단 정하고 운영 중 조정.

#### (4) Dependency ordering (B가 A에 의존하면 A 먼저)
- 단순 원칙이지만 자주 어김.
- 예: 단계 2.2 모바일 로그인 화면을 단계 1.2 호스트 인증 라우터 없이 먼저 만들면 mock 으로만 동작 → 통합 시점에 인터페이스 mismatch.
- **의존 그래프를 명시화**: 본 프로젝트의 단계 의존:
  - 단계 1.1 (인프라) → 1.2 (인증) → 1.3 (알고리즘) → 1.4 (스냅샷) → 1.5 (운영)
  - 단계 1 전체 → 단계 2 (모바일이 호스트 호출)
  - 단계 1.2 + 1.3 → 단계 3.3 (Worker 가 동일 인증/캐시 패턴 재사용)

#### (5) Shippable per phase (각 단계는 그 자체로 배포 가능)
- 단계 종료 시점에 "데모 + 멈춰도 무방" 한 상태로 끝나야 함.
- 본 프로젝트 예:
  - 단계 1 종료 = 호스트 백엔드 단독으로 사용 가능 (모바일 앱 없어도 curl 테스트 가능).
  - 단계 2 종료 = 모바일 앱이 출시 가능 (웹 없어도 됨).
  - 단계 3 종료 = 웹이 출시 가능.
  - 단계 4 종료 = 운영 자동화 + 정리 완료.
- **반례**: "단계 X 끝나면 모든 게 반쯤 작동하는데 어느 것도 끝까지 안 됨" → horizontal layer 의 전형적 증상.

#### (6) Operational readiness vs Feature richness 균형
- 초기 단계: 운영 가능성에 비중 (시작/중지/로그/백업/`/health`).
- 후반 단계: 기능 완성도에 비중 (고급 차트, 알림 세분화, 다크모드).
- **이 프로젝트의 적용**: 단계 1.5 에서 "기능 0개 추가, 백업·로그·헬스만 정리" 슬라이스를 일찍 둠. 이게 단계 4로 미뤄지면 단계 2~3 진행 중 호스트 사고 시 복구 불가.

---

### 11.2 본 프로젝트에서 그 원칙이 어떻게 적용됐나

#### (a) 왜 단계 1(호스트 백엔드)이 가장 먼저인가
- **Risk-first**: 인증·DB·캐시 메커니즘이 모든 후속 단계의 기반. 여기서 검증된 패턴을 모바일·웹이 그대로 가져다 씀.
- **단일 진실 코드베이스 검증**: §5 N1 의 `backend/` 단일 소스 정책이 실제로 동작하는지 호스트(단계 1) → 컨테이너(단계 3) 순으로 검증. 단계 1의 Dockerfile 이 단계 3에서 재사용 → drift 위험 감소.
- **Reversibility**: 단계 1에서 결정되는 인증 모델(JWT) 은 one-way door. 단계 2/3의 클라이언트들이 이 모델을 전제로 만들어지므로 단계 1 인증이 흔들리면 단계 2/3 재작업.

#### (b) 왜 단계 2(모바일)가 단계 3(웹) 앞에 오는가
- **사용자 페르소나**: 본 프로젝트의 핵심 사용자는 "장중·장후 폰으로 종목 모니터링" 하는 모바일 사용자라는 가정(§1.3). 핵심 페르소나에 먼저 가치 전달.
- **Risk 분리**: 단계 3은 CF Containers 라는 신생 서비스 리스크가 있음 → 핵심 모바일 가치 전달을 단계 2에서 끝내고, 단계 3은 "추가 채널" 로 분리하면 단계 3 실패 시에도 모바일 서비스는 살아남음.
- **단계 3을 단계 2 앞에 두면 발생할 일**: 모바일 출시가 CF Containers 리스크에 묶임 → 핵심 사용자에게 가치 전달 지연.

#### (c) 왜 단계 1.1에서 컨테이너화를 미리 검증해두는가
- 단계 3.2 의 CF Container 이미지 빌드는 단계 1.1 의 Dockerfile 을 재사용한다는 전제(§5 N1).
- 단계 1.1을 systemd 로 갔다가 단계 3.2 에서 처음 컨테이너화하면 두 환경의 미묘한 차이(환경변수 처리, 파일 경로, 권한)가 단계 3 후반에 터짐 → "단계 1에서 미리 한 보상" 이 단계 3에서 회수됨.

#### (d) 왜 단계 4(운영 정착)가 따로 분리되는가
- 모니터링·알림·백업 자동화는 기능 구현과 인지적 차원이 다르다. 같이 섞으면 두 가지 모두에 집중력이 분산됨.
- 단계 4 가 따로 있어야 "여기서는 운영 부채만 갚는다" 는 명확한 슬롯이 생김. 안 그러면 영원히 미뤄짐("나중에 모니터링 붙일게요" → 평생).
- **단, 단계 1.5 의 최소 운영 슬라이스(백업·헬스)는 단계 4까지 미루지 않음** — 그건 "운영 정착" 이 아니라 "최소 안전망" 이라 단계 1에서 함께.

#### (e) 왜 단계 3.2 가 단계 3 안에서 가장 먼저인가
- CF Containers 가 yfinance/pykrx 를 안전히 돌리는지가 본 프로젝트의 최대 기술 리스크(§7.3).
- 안 되면 §3.2.2 옵션 B 결정을 재검토해야 함 → 단계 3 전체 재설계.
- 따라서 단계 3.1(빈 도메인) → 3.2(컨테이너 검증) 순서로 가장 위험한 것을 둘째에 둠. 첫째(3.1 도메인)는 행정 절차 차원에서 무조건 일찍 시작해야 하므로 1순위.

---

### 11.3 의식적으로 미룬 것들 (Defer, YAGNI 적용)

> **YAGNI (You Aren't Gonna Need It)**: 미래에 필요할 것 같은 기능을 미리 만들지 말라.
> **"Premature optimization is the root of all evil"** — Donald Knuth. 측정 없이 최적화하지 말라.

#### 의식적으로 미룬 항목 + 근거

| 미룬 항목 | 미룬 이유 | 다시 꺼낼 트리거 |
|---|---|---|
| **시크릿 매니저(Vault, AWS Secrets Manager)** | 1인 운영, `.env + chmod 600` 으로 충분. 시크릿 매니저는 운영 부담 추가. | 팀 합류 또는 시크릿 회전 빈도 ↑ 시 |
| **drift 감지 자동화 CI** | 수동 1차 동기화로 시작. 알고리즘 변경 빈도가 높지 않으면 사람 점검으로 충분. | 알고리즘 수정 PR 빈도 월 5회 이상 |
| **다크모드 / 접근성 강화 / i18n** | 핵심 가치 전달이 우선. 사용자 요청 누적 시 추가. | 실제 사용자 요청 누적 |
| **stale-while-revalidate 캐시** | C3 결정으로 콜드 대기 수용. 첫 사용자 이탈률이 측정되기 전에는 복잡도 증가 X. | 이탈률 측정 결과 X% 초과 시 |
| **WebSocket 실시간 푸시 (웹)** | FCM(모바일)으로 충분. 웹 실시간성은 새로고침 누름으로 대체. | 웹 사용자가 실시간성 요청 누적 |
| **사용자별 포트폴리오 SaaS화** | 현재는 개인 사용자 1인 가정. 다중 사용자 SaaS 전환은 별도 결정. | 가입자 100명 초과 또는 명시적 SaaS 전환 결정 |
| **비밀번호 분실/이메일 인증 흐름** | v0.4 N4 범위 외. 단계 2 모바일 출시 후 사용자 피드백으로 추가. | 가입자 첫 로그인 실패 사례 발생 |
| **DB 읽기 복제 / 샤딩** | 호스트 1대, 트래픽 가정 작음(§1.4). 측정 없이 분산 X. | DB CPU 70% 또는 응답 100ms 초과 지속 |
| **Cloudflare Tunnel / Tailscale** | Caddy 자동 TLS + Origin 검사로 충분 가정. | 호스트 IP 노출이 실제 공격받음 |
| **Kubernetes / 오케스트레이션** | 호스트 1대에 docker compose 1개로 충분. | 호스트 N대 운영 또는 무중단 배포 요구 |

#### 미룸의 원칙
- 미룬 것들도 **§7 위험·미해결** 또는 **§9 체크리스트** 에 살아 있어야 함 — 잊혀서는 안 되고, 다만 "지금 안 함" 이 의도적 결정임을 기록.
- "왜 안 만들었어?" 라는 질문에 답이 있어야 한다 — "필요해 보였는데 잊었다" 와 "지금은 X 트리거 전이라 안 만든다" 는 다르다.

---

### 11.4 단계 진행 중 발견하면 일단 멈추는 트리거

각 sub-step 진행 중 다음 신호를 만나면 **다음 sub-step으로 넘어가지 말고 멈춰서 재검토** 한다.

| 트리거 | 의미 | 멈춰서 할 일 |
|---|---|---|
| **Acceptance 미충족** | 검증 기준이 안 나옴 (예: 캐시 응답 > 100ms, 콜드 30초 초과) | 가정 점검 → 설계 변경 vs 기준 완화 결정 |
| **가정 깨짐** | 전제가 틀렸음 발견 (예: yfinance가 컨테이너에서 안 돎) | §3.2.2 옵션 재검토 가능. 영향 범위 평가 후 §10 변경 로그에 기록 |
| **비용 초과** | §1.4 가정 대비 X배 초과 | 비용 분해 → 옵션 다운그레이드 또는 가정 재설정 |
| **벤더 정책 변경** | CF Containers 요금/한도 변경 발표 | §7.3 락인 위험 재평가 |
| **사용자 피드백으로 우선순위 역전** | "이거보다 저게 더 급해요" 가 나옴 | 단계 재배열. 단, 이미 끝낸 슬라이스는 살아남음(vertical slice 의 보상) |
| **단순 진행 속도 < 50% of estimate** | 예상의 두 배 이상 걸림 | 숨은 의존성/학습 곡선 평가. sub-step 더 쪼개기 |

> **멈춤 ≠ 실패**. 멈춤은 학습. 멈춤 없이 끝까지 가서 잘못된 결과를 내는 것이 더 비싸다.

---

### 11.5 단계 종료 시 의사결정 게이트

각 단계 종료 시점에 다음 질문에 명시적으로 답한다 — "다음 단계로 갈까, 멈추고 재설계할까".

#### 게이트 질문 템플릿
1. **이 단계의 모든 sub-step Acceptance 가 충족되었나?**
2. **§7 위험 중 새로 발견된 것이 있나? (있다면 §7 갱신)**
3. **다음 단계의 전제(이 단계의 산출물 중 일부)가 실제로 동작하는가?**
4. **§1.4 비용 가정이 여전히 유효한가?**
5. **사용자가 이 단계 산출물에 만족하는가? (데모 → 피드백)**

#### 게이트 결정 매트릭스
| 1~5번 답 | 결정 |
|---|---|
| 모두 Yes | 다음 단계로 진입 |
| 1~3 No | 미충족 sub-step 재시도. 다음 단계 진입 보류 |
| 4 No (비용 초과) | 옵션 다운그레이드 vs 가정 재설정 결정 |
| 5 No (사용자 불만) | 단계 재배열 또는 추가 sub-step 삽입 |

#### 데이터 기반 판단의 중요성
- 직관 ("괜찮을 것 같다") 으로 게이트를 통과하지 말 것.
- 측정값(메트릭)으로 답하기:
  - 응답 시간(ms), 캐시 적중률(%), 다운타임(분), 비용(USD), 사용자 가입 수, 이탈률(%).
- 측정 안 되는 것은 운영 안 되는 것.

---

### 11.6 본 메타 섹션의 사용법

- 새 sub-step 시작 전 §11.1 원칙을 빠르게 다시 읽기.
- sub-step 진행 중 §11.4 멈춤 트리거에 해당하는 신호가 보이면 즉시 멈춤.
- 단계 종료 시 §11.5 게이트 질문 5개에 명시적으로 답.
- 다른 프로젝트로 옮길 때 §11.1·11.3·11.4·11.5 는 도메인 무관하게 재사용 가능.

> 본 섹션은 결정 사항이 아니라 **사고 방식 기록** 이다. 사용자가 다른 프로젝트에서도 같은 사고를 적용할 수 있도록 하는 것이 목적.