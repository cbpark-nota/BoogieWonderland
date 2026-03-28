# 테스트 가이드 (TEST_GUIDE.md)

> 이 문서는 Momentum Stock Screener 앱의 Flutter 테스트 파일 위치, 검증 기능, 실행 방법을 설명합니다.

---

## 테스트 파일 목록

| 파일 | 위치 | 테스트 수 | 설명 |
|------|------|-----------|------|
| `models_test.dart` | `frontend/test/` | 33개 | 핵심 데이터 모델 파싱 |
| `portfolio_data_test.dart` | `frontend/test/` | 22개 | 포트폴리오·BTC 모델 파싱 |
| `widget_test.dart` | `frontend/test/` | 2개 | 앱 전체 렌더링 |
| `widgets_test.dart` | `frontend/test/` | 23개 | 개별 위젯 렌더링 |
| `screenshot_test.dart` | `frontend/test/` | 4개 | 스크린샷 Golden 비교 |

---

## 각 테스트 파일 상세

---

### 1. `frontend/test/models_test.dart` — 핵심 데이터 모델 파싱 테스트

**검증하는 기능:**

JSON 응답 → Dart 데이터 모델 변환(파싱)이 올바르게 동작하는지 검증합니다.

| 테스트 그룹 | 검증 내용 |
|------------|---------|
| `ScreeningResult.fromJson` | 스크리닝 종목 데이터 파싱, nullable 필드 처리, KR/US 시장 구분, 숫자 타입 변환 |
| `MarketStatus.fromJson` | SPY/KOSPI 시장 상태 파싱, 골든크로스 기본값 |
| `ScreeningRun.fromJson` | 스크리닝 실행 결과 전체 구조 파싱 |
| `Holding.fromJson` | 포트폴리오 보유 종목 파싱, is_active 기본값 |
| `StopCheckResult.fromJson` | 스톱로스 체크 결과 파싱 (BREACH, WARNING) |
| `StrategyType enum` | 4개 전략(공격적/균형형/보수적/적응형) 속성 값 검증 |
| `StrategyScreeningData.fromJson` | 4전략 통합 데이터 파싱, toScreeningRun 변환 |
| `StrategyResult.fromJson` | 개별 전략 결과 파싱, regime 라벨 |

**입력/출력 요약:**
- 입력: `Map<String, dynamic>` 형태의 JSON 딕셔너리
- 출력: 각 Dart 클래스 인스턴스 (필드값 검증)

---

### 2. `frontend/test/portfolio_data_test.dart` — 포트폴리오·BTC 모델 파싱 테스트

**검증하는 기능:**

포트폴리오 데이터와 BTC 시그널 모델 파싱, 통화 포맷, 엣지 케이스를 검증합니다.

| 테스트 그룹 | 검증 내용 |
|------------|---------|
| `PortfolioHolding.fromJson` | KR/US 종목 파싱, ATR 스톱로스 필드, 스톱 트리거 상태, formatPrice 통화 포맷 |
| `PortfolioData.fromJson` | 포트폴리오 전체 집계값, 환율 필드, holdings 리스트, isEmpty |
| `BtcSignal.fromJson` | BTC 매수/홀드 시그널, price/regime nullable 필드, 기본값 처리 |
| `MarketStatus KOSPI 필드` | KOSPI 가격/이동평균/골든크로스 파싱, 필드 없을 때 null |

**입력/출력 요약:**
- 입력: `Map<String, dynamic>` JSON 딕셔너리
- 출력: PortfolioHolding/PortfolioData/BtcSignal 인스턴스 (필드 및 포맷 검증)

**주요 엣지 케이스:**
- KR 종목 `name` 없으면 `ticker`로 fallback
- `exchange_rate` 없으면 usdkrw 기본값 1380.0
- `total_invested_krw` 없으면 `total_invested`로 fallback (하위 호환)
- KR 포맷: `₩72,500` (천 단위 콤마, 소수 없음)
- US 포맷: `$145.20` (소수 2자리)

---

### 3. `frontend/test/widget_test.dart` — 앱 전체 렌더링 테스트

**검증하는 기능:**

앱 진입점(MomentumApp)이 올바르게 렌더링되는지 검증합니다.

| 테스트 이름 | 검증 내용 |
|------------|---------|
| `App renders with drawer navigation` | 초기 AppBar 타이틀 'Dashboard'와 Drawer 메뉴 아이콘(☰) 표시 여부 |
| `Settings icon is present` | Settings 아이콘이 AppBar에 표시되는지 여부 |

**입력/출력 요약:**
- 입력: Mock ScreeningNotifier (null 반환), Mock marketStatusProvider (null 반환)
- 출력: 'Dashboard' 텍스트, `Icons.menu`, `Icons.settings` 아이콘이 위젯 트리에 존재함

> **참고:** 이 앱은 BottomNavigationBar가 아닌 Drawer 기반 네비게이션을 사용합니다.
> 'Screening', 'Portfolio' 레이블은 Drawer 안에 있어 기본 상태에서는 찾을 수 없습니다.

---

### 4. `frontend/test/widgets_test.dart` — 개별 위젯 렌더링 테스트

**검증하는 기능:**

각 재사용 위젯이 조건에 따라 올바른 UI를 렌더링하는지 검증합니다.

| 테스트 그룹 | 검증 내용 |
|------------|---------|
| `StockCard` | 종목 정보 표시, KR/US 플래그, 지표(ADX/RSI/3M) 포맷, null 지표 하이픈 처리, 통화 포맷 |
| `StopLossIndicator` | marginPct 값에 따른 BREACH/경고/안전 상태 텍스트, 경계값(0, 음수) 처리 |
| `MarketStatusBanner` | Golden Cross/Dead Cross 텍스트, trending_up/down 아이콘, 수치 포맷 |
| `KospiStatusBanner` | KOSPI 데이터 있을 때 배너 표시, 없을 때 빈 위젯 반환 |

**StopLossIndicator 조건:**
- `marginPct <= 0` → `BREACH` (빨간색)
- `0 < marginPct < 5` → `X.X%` (주황색)
- `marginPct >= 5` → `X.X%` (녹색)

**입력/출력 요약:**
- 입력: ScreeningResult / double / MarketStatus 객체
- 출력: 조건에 맞는 텍스트, 아이콘이 위젯 트리에 표시됨

---

### 5. `frontend/test/screenshot_test.dart` — 스크린샷 Golden 파일 비교 테스트

**검증하는 기능:**

앱 화면(Dashboard, Screening, Portfolio, Dashboard Dark)의 픽셀 수준 렌더링이 기준 이미지와 일치하는지 검증합니다.

| 테스트 이름 | Golden 파일 |
|------------|------------|
| Screenshot: Dashboard | `frontend/test/goldens/dashboard.png` |
| Screenshot: Screening | `frontend/test/goldens/screening.png` |
| Screenshot: Portfolio | `frontend/test/goldens/portfolio.png` |
| Screenshot: Dashboard Dark | `frontend/test/goldens/dashboard_dark.png` |

> **주의:** 이 테스트는 환경(OS, 해상도)마다 결과가 달라질 수 있습니다.
> Golden 파일은 Ubuntu CI 환경에서 생성됩니다. 로컬(Mac)에서는 픽셀 차이로 실패할 수 있습니다.

---

## 테스트 실행 방법

### 사전 준비
```bash
# 프로젝트 루트에서
cd frontend
```

### 전체 테스트 실행 (스크린샷 제외)
```bash
fvm flutter test test/models_test.dart test/portfolio_data_test.dart test/widget_test.dart test/widgets_test.dart
```

### 전체 테스트 실행 (스크린샷 포함)
```bash
fvm flutter test
```

### 특정 파일만 실행
```bash
# 모델 테스트만
fvm flutter test test/models_test.dart

# 포트폴리오 모델 테스트만
fvm flutter test test/portfolio_data_test.dart

# 위젯 테스트만
fvm flutter test test/widgets_test.dart
```

### Golden 파일 갱신 (스크린샷 업데이트 시)
```bash
fvm flutter test test/screenshot_test.dart --update-goldens
```

---

## 테스트 결과 요약

| 파일 | 상태 | 테스트 수 |
|------|------|-----------|
| `models_test.dart` | ✅ 통과 | 33개 |
| `portfolio_data_test.dart` | ✅ 통과 | 22개 |
| `widget_test.dart` | ✅ 통과 | 2개 |
| `widgets_test.dart` | ✅ 통과 | 23개 |
| **합계** | **✅ 80개 모두 통과** | **80개** |

> 스크린샷 테스트(`screenshot_test.dart`)는 CI(Ubuntu) 환경에서만 정상 통과됩니다.

---

## 주요 수정 이력

| 파일 | 수정 내용 |
|------|---------|
| `models_test.dart` | `ma50`/`ma200` → `ma20`/`ma60` 필드명 오타 수정 (모델과 불일치) |
| `models_test.dart` | `StrategyType` description 기댓값 수정 (ATR/TOP 값 오타) |
| `widget_test.dart` | BottomNavigationBar 기반 → Drawer 기반 네비게이션 테스트로 수정 |
