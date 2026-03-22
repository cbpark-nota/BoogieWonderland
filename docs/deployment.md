# 배포 환경 가이드

> 최종 업데이트: 2026-03-23

---

## 배포 환경 개요

```
┌──────────────────────────────────────────────────────────────────┐
│                        배포 환경 3종                              │
├──────────────┬──────────────────┬────────────────────────────────┤
│   서버리스    │   셀프호스팅      │        클라우드 (AWS)           │
│ GitHub Pages │   Docker         │       ECS + RDS                │
├──────────────┼──────────────────┼────────────────────────────────┤
│ 프론트엔드    │ 프론트엔드        │ 프론트엔드                      │
│ (정적 웹)    │ (Nginx 컨테이너)  │ (Nginx 컨테이너 / S3+CF)       │
│              │                  │                                │
│ 백엔드 없음   │ 백엔드           │ 백엔드                          │
│              │ (FastAPI 컨테이너)│ (FastAPI 컨테이너)              │
│              │                  │                                │
│ DB 없음       │ PostgreSQL       │ RDS PostgreSQL                 │
│ (localStorage)│ (Docker)        │ (관리형)                        │
│              │                  │                                │
│ 데이터 수집   │ Collector        │ Collector                      │
│ (GitHub      │ (Docker cron)    │ (ECS Scheduled Task)           │
│  Actions)    │                  │                                │
└──────────────┴──────────────────┴────────────────────────────────┘
```

---

## 디렉토리 구조

```
deploy/
├── .env.example              # 환경변수 템플릿 (모든 환경 공통)
├── local/
│   └── docker-compose.yml    # 로컬 개발: DB만 실행
├── docker/
│   └── docker-compose.yml    # 셀프호스팅: db + backend + frontend + collector
├── aws/
│   ├── docker-compose.yml    # ECS용 (DB 외부 RDS)
│   └── task-definition.json  # ECS Fargate Task 정의
├── serverless/
│   └── (GitHub Actions 워크플로우가 담당)
└── claude-cli/
    └── Dockerfile            # Claude Code CLI 개발 환경용
```

---

## 1. 서버리스 배포 (GitHub Pages)

**용도:** 데모, 프리뷰, 백엔드 없이 스크리닝 결과 확인

**구성:**
- Flutter 웹앱 → GitHub Pages 정적 호스팅
- GitHub Actions cron → 매일 스크리닝 실행 → JSON 생성
- 포트폴리오 → 브라우저 localStorage

**URL:** https://cbpark-nota.github.io/BoogieWonderland/

**배포 방법:** `main` 브랜치 push 시 자동 배포 (GitHub Actions)

**수동 배포:**
```bash
# 워크플로우 수동 트리거
gh workflow run deploy-web.yml
```

**환경변수:**
- `DEPLOY_MODE=serverless` (빌드 시 자동 설정)
- `BASE_HREF=/BoogieWonderland/` (워크플로우에서 설정)

---

## 2. 셀프호스팅 배포 (Docker)

**용도:** 공용 머신, VPS, 온프레미스 서버

**구성:**
- PostgreSQL + FastAPI + Nginx(Flutter) + Collector 4개 컨테이너

**배포 방법:**
```bash
cd deploy/docker

# 1. 환경변수 설정
cp ../.env.example .env
# .env 파일을 열어 비밀번호 등 수정

# 2. 서비스 시작
docker compose up -d

# 3. 확인
docker compose ps
curl http://localhost/api/v1/screening/latest
```

**서비스 URL:**
- 프론트엔드: `http://localhost:80`
- 백엔드 API: `http://localhost:8000`
- 백엔드 문서: `http://localhost:8000/docs`

**로그 확인:**
```bash
docker compose logs -f backend
docker compose logs -f collector
```

**업데이트:**
```bash
git pull
docker compose up -d --build
```

---

## 3. 클라우드 배포 (AWS)

**용도:** 프로덕션, 고가용성

**구성:**
- ECS Fargate: backend + frontend 컨테이너
- RDS PostgreSQL: 관리형 DB
- ALB: 로드밸런서 (라우팅)
- ECR: 컨테이너 이미지 레지스트리
- SSM Parameter Store: 시크릿 관리

**필요 AWS 리소스:**

| 리소스 | 용도 | 예상 비용 (최소) |
|---|---|---|
| ECR (3개 리포) | 이미지 저장 | ~$1/월 |
| RDS (db.t3.micro) | PostgreSQL | ~$15/월 |
| ECS Fargate (0.5 vCPU) | 컨테이너 실행 | ~$10/월 |
| ALB | 로드밸런서 | ~$16/월 |
| **합계** | | **~$42/월** |

**배포 방법:**
```bash
# 1. ECR 리포지토리 생성
aws ecr create-repository --repository-name momentum-backend
aws ecr create-repository --repository-name momentum-frontend
aws ecr create-repository --repository-name momentum-collector

# 2. 이미지 빌드 & 푸시
aws ecr get-login-password | docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.REGION.amazonaws.com
docker build -t momentum-backend ./backend
docker tag momentum-backend:latest ACCOUNT.dkr.ecr.REGION.amazonaws.com/momentum-backend:latest
docker push ACCOUNT.dkr.ecr.REGION.amazonaws.com/momentum-backend:latest

# 3. ECS 서비스 생성 (Task Definition 사용)
aws ecs register-task-definition --cli-input-json file://deploy/aws/task-definition.json
aws ecs create-service --cluster momentum --task-definition momentum-app --desired-count 1

# 4. 환경변수 (SSM Parameter Store)
aws ssm put-parameter --name /momentum/database-url --type SecureString --value "postgresql+asyncpg://..."
```

---

## 4. 로컬 개발 환경

**용도:** 개발, 디버깅

### Mac (Darwin)
```bash
# DB 시작
cd deploy/local && docker compose up -d

# 백엔드 (가상환경)
source .venv/bin/activate
cd backend
APP_DATABASE_URL="postgresql+asyncpg://momentum:momentum@127.0.0.1:5432/momentum" \
APP_DATABASE_URL_SYNC="postgresql://momentum:momentum@127.0.0.1:5432/momentum" \
APP_SCHEDULER_ENABLED=false \
uvicorn app.main:app --reload --port 8000

# 프론트엔드 (FVM)
cd frontend && fvm flutter run -d chrome
```

### 서버리스 모드 (백엔드 불필요)
```bash
# 스크리닝 데이터 생성
python scripts/export_json.py --output frontend/web/data/

# 프론트엔드 실행
cd frontend && fvm flutter run -d chrome --dart-define=DEPLOY_MODE=serverless
```

---

## 환경변수 참조

| 변수 | 기본값 | 용도 |
|---|---|---|
| `POSTGRES_USER` | momentum | DB 사용자 |
| `POSTGRES_PASSWORD` | (필수) | DB 비밀번호 |
| `POSTGRES_DB` | momentum | DB 이름 |
| `APP_DATABASE_URL` | (필수) | SQLAlchemy async 연결 문자열 |
| `APP_SCHEDULER_ENABLED` | true | 배치 스케줄러 활성화 |
| `APP_CORS_ORIGINS` | ["*"] | 허용 오리진 |
| `DEPLOY_MODE` | fullstack | fullstack / serverless |
| `API_URL` | http://localhost:8000 | 프론트엔드 → 백엔드 API URL |
| `BASE_HREF` | / | Flutter 웹 base path |

---

*본 문서는 투자 조언이 아니며, 내부 개발 참고용입니다.*
