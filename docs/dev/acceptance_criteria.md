# 구현 단계별 Acceptance Criteria

## Phase 1: 백엔드 코어

### 1.1 프로젝트 스캐폴딩 + DB 설정
- [x] `backend/` 디렉토리에 FastAPI 프로젝트 생성 (`pyproject.toml`, uv 사용)
- [x] `backend/app/main.py`에서 FastAPI 앱 생성, `GET /health` 응답 확인
- [x] `docker-compose.yml`로 PostgreSQL 컨테이너 실행 가능
- [x] SQLAlchemy 모델 정의 (stocks, screening_runs, screening_results, holdings, stop_loss_events, rebalance_schedule, device_tokens, notification_log)
- [x] 앱 시작 시 `Base.metadata.create_all`로 자동 테이블 생성 (Alembic 대체)
- [x] `uvicorn`으로 서버 기동 후 `/health` 엔드포인트 200 응답 확인

### 1.2 서비스 레이어 (알고리즘 추출)
- [x] `screener_v3.py`의 핵심 함수를 `backend/app/services/screener.py`에 추출
  - `download_tickers()`, `calc_indicators()`, `screen_stock()`, `rank_stocks()`, `calc_position_weights()`, `check_market()`, `run_screening()`
- [x] `monitor.py`의 핵심 함수를 `backend/app/services/monitor.py`에 추출
  - `calc_atr_stop_for_ticker()`, `check_stop_loss()`
- [x] 각 서비스 함수가 print 대신 데이터를 return하는 구조로 변환
- [x] 서비스 함수 단위 테스트 5개 작성 및 통과

### 1.3 스크리닝 API
- [x] `POST /api/v1/screening/run` — 스크리닝 실행, DB 저장, 결과 반환
- [x] `GET /api/v1/screening/latest` — 최신 스크리닝 결과 조회
- [x] `GET /api/v1/screening/history` — 과거 스크리닝 이력 목록
- [x] `GET /api/v1/screening/{run_id}` — 특정 실행 결과 조회
- [x] 응답 스키마에 rank, ticker, score, weight_pct, price, adx, rsi, ret_3m, stop_price, stop_dist_pct 포함
- [x] 스크리닝 통과 종목이 0개일 때 빈 배열 반환 (에러 아님)

### 1.4 포트폴리오 API
- [x] `GET /api/v1/portfolio/holdings` — 활성 보유 종목 목록
- [x] `POST /api/v1/portfolio/holdings` — 종목 추가 (ticker + entry_price)
- [x] `DELETE /api/v1/portfolio/holdings/{ticker}` — 종목 제거
- [x] `POST /api/v1/portfolio/check-stops` — 전 종목 스톱로스 체크, 결과 반환
- [x] 동일 종목 중복 추가 시 409 Conflict 반환
- [x] 존재하지 않는 종목 삭제 시 404 반환

### 1.5 시장 상태 API
- [x] `GET /api/v1/market/status` — SPY 가격, 골든/데드크로스, MA50, MA200, 다음 리밸런싱일
- [x] `GET /api/v1/market/rebalance-schedule` — 향후 6개월 리밸런싱 일정
- [x] `POST /api/v1/system/refresh` — 수동 데이터 갱신 트리거

---

## Phase 2: 스케줄러 + 알림

### 2.1 스케줄러
- [x] APScheduler가 FastAPI lifespan에 통합
- [x] 일간 스크리닝 스케줄 (미국장 마감 후) 등록 확인
- [x] 일간 스톱로스 체크 스케줄 (미국장, 한국장 마감 후) 등록 확인
- [x] 리밸런싱 리마인더 스케줄 (2일 전) 등록 확인
- [x] `GET /api/v1/system/status` — 스케줄러 상태, 마지막 실행 시각 조회

### 2.2 알림 (FCM)
- [x] `POST /api/v1/notifications/register` — FCM 디바이스 토큰 등록
- [x] `DELETE /api/v1/notifications/register/{token}` — 토큰 해제
- [x] `GET /api/v1/notifications/history` — 알림 발송 이력
- [x] 스톱로스 이탈 시 STOP_BREACH 알림 발송 (firebase-admin)
- [x] 리밸런싱 2일 전 REBALANCE 알림 발송
- [x] 알림 발송 기록이 notification_log 테이블에 저장

---

## Phase 3: Flutter 앱

### 3.1 프로젝트 스캐폴딩
- [x] `frontend/` 에 Flutter 프로젝트 생성
- [x] 의존성 추가: dio, flutter_riverpod
- [x] 3탭 BottomNavigationBar 구조 (대시보드, 스크리닝, 포트폴리오)
- [x] API 클라이언트 (`dio` 기반) 구현, base URL 설정 가능
- [ ] Android, iOS, Web 빌드 성공 (빌드 환경 필요)

### 3.2 대시보드 화면
- [x] 시장 상태 배너 (골든/데드크로스, SPY 가격)
- [x] 다음 리밸런싱일 카운트다운 표시
- [x] 최신 TOP 3 종목 미리보기
- [x] 수동 새로고침 버튼 (Pull-to-refresh)

### 3.3 스크리닝 화면
- [x] TOP 10 종목 리스트 (순위, 티커, 점수, 비중, 가격, 스톱가)
- [x] Pull-to-refresh로 수동 스크리닝 트리거
- [x] 로딩/빈 상태 처리
- [x] FAB으로 스크리닝 실행

### 3.4 포트폴리오 화면
- [x] 보유 종목 리스트 (진입가, 날짜)
- [x] 스톱 근접도 인디케이터 (초록/노랑/빨강)
- [x] 종목 추가 (하단 시트: 티커 + 진입가)
- [x] 스와이프로 종목 삭제
- [x] 수동 스톱 체크 버튼

### 3.5 푸시 알림
- [x] 백엔드 FCM 발송 로직 구현 (firebase-admin)
- [x] 프론트엔드 토큰 등록 API 클라이언트 구현
- [ ] FCM 실제 연동 (Firebase 프로젝트 생성 필요)

---

## Phase 4: 폴리시

### 4.1 에러 처리 + UX
- [x] 로딩 스피너 (CircularProgressIndicator)
- [x] 빈 상태 아이콘 + 안내 메시지
- [x] 다크 모드 지원 (ThemeMode.system)

### 4.2 배포
- [x] docker-compose로 백엔드 + DB 한 번에 기동
- [x] 환경변수로 DB URL, FCM 키 등 설정 가능
- [ ] Flutter 웹 빌드 배포 (빌드 환경 필요)

---

## 테스트 결과

- 백엔드 단위 테스트: 5/5 통과
- Flutter 위젯 테스트: 2/2 통과
- Flutter 정적 분석: 에러 0개 (info 1개)
