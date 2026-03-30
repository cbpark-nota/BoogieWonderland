# TEST_GUIDE.md — 테스트 가이드

## 목차
1. [Flutter 테스트 실행 방법](#flutter-테스트-실행-방법)
2. [테스트 파일 목록](#테스트-파일-목록)
3. [기능별 검증 내용](#기능별-검증-내용)
4. [Python 기능 설명 (수동 검증)](#python-기능-설명-수동-검증)

---

## Flutter 테스트 실행 방법

```bash
# 전체 테스트 실행
cd frontend
fvm flutter test

# 특정 파일 테스트
fvm flutter test test/portfolio_model_test.dart
fvm flutter test test/models_test.dart
fvm flutter test test/widget_test.dart

# 골든 파일 업데이트 (로컬 기준)
fvm flutter test test/screenshot_test.dart --update-goldens
```

---

## 테스트 파일 목록

| 파일 | 범주 | 설명 |
|------|------|------|
| `frontend/test/portfolio_model_test.dart` | 모델 단위 | **신규** — PortfolioHolding/PortfolioData 모델 검증 (ATR 스톱, 환율, 가격 포맷) |
| `frontend/test/models_test.dart` | 모델 단위 | ScreeningResult, MarketStatus, ScreeningRun, StrategyScreeningData 등 파싱 검증 |
| `frontend/test/widget_test.dart` | 위젯 통합 | 앱 렌더링, Drawer, Settings 아이콘 표시 여부 |
| `frontend/test/screenshot_test.dart` | 스크린샷/골든 | 스크리닝·포트폴리오·대시보드 화면 시각적 회귀 테스트 |

---

## 기능별 검증 내용

### 1. ATR 스톱로스 표시 (`portfolio_model_test.dart`)

**관련 코드**
- Python: `scripts/export_json.py` — `_calc_atr_stop()`
- Flutter 모델: `frontend/lib/models/portfolio_data.dart` — `PortfolioHolding.atrStop / atrStopDistPct / atrStopTriggered`
- Flutter 위젯: `frontend/lib/screens/portfolio_screen.dart` — `_AtrStopRow`

**검증 항목**

| 테스트 이름 | 입력 | 확인 동작 |
|-------------|------|-----------|
| ATR 필드 정상 파싱 | `atr_stop: 175.5, atr_stop_dist_pct: 5.2` | 필드가 올바른 타입·값으로 파싱됨 |
| null 필드 처리 | `atr_stop: null` | atrStop=null → 위젯에서 ATR 섹션 미표시 |
| 키 부재 시 기본값 | atr_stop 키 없음 | null/false 기본값 적용 |
| atrStopTriggered=true | `atr_stop_triggered: true` | true로 파싱 → 위젯에서 "추세 이탈" 상태 |
| 추세 이탈 조건 | `atr_stop_dist_pct: -1.5` | distPct ≤ 0 → 위젯에서 🔴 "추세 이탈" |
| 위험 구간 조건 | `atr_stop_dist_pct: 2.8` | 0 < distPct ≤ 3 → 위젯에서 🔴 "위험 X%" |
| 주의 구간 조건 | `atr_stop_dist_pct: 5.5` | 3 < distPct ≤ 7 → 위젯에서 🟠 "주의 X%" |
| 안전 구간 조건 | `atr_stop_dist_pct: 12.0` | distPct > 7 → 위젯에서 🟢 "안전 X%" |
| int → double 변환 | `atr_stop: 170, atr_stop_dist_pct: 8` | double 타입으로 변환됨 |

**`_AtrStopRow` 위젯 상태 판단 로직 (portfolio_screen.dart:569)**

```dart
if (triggered || distPct <= 0)  → "추세 이탈" (빨간색)
else if (distPct <= 3)          → "위험 X%"  (빨간색)
else if (distPct <= 7)          → "주의 X%"  (주황색)
else                            → "안전 X%"  (초록색)
```

진행바: `distPct`를 0~20% 범위로 정규화 → `barFill = distPct.clamp(0, 20) / 20`

---

### 2. 환율 조회 수정 (`portfolio_model_test.dart`)

**관련 코드**
- Python: `scripts/export_json.py` — `fetch_usdkrw()`
  - `.squeeze()` 적용으로 DataFrame → Series 변환 보장
  - 실패 시 기본값 `1380.0` 반환
- Flutter 모델: `PortfolioData.fromJson()` — `exchange_rate.usdkrw` 처리

**검증 항목**

| 테스트 이름 | 입력 | 확인 동작 |
|-------------|------|-----------|
| 정상 환율 파싱 | `exchange_rate: {usdkrw: 1350.5}` | 1350.5로 파싱됨 |
| null 환율 처리 | `exchange_rate: {usdkrw: null}` | 기본값 1380.0 적용 |
| exchange_rate 키 없음 | exchange_rate 키 미포함 | 기본값 1380.0 적용 |
| int 타입 환율 | `usdkrw: 1380` | double 1380.0으로 변환됨 |

> **참고**: Python `fetch_usdkrw()`는 yfinance 조회 실패 시 `1380.0`을 반환하므로
> 실제 JSON에 null이 기록되는 경우는 드물지만, Dart 측에서 방어적으로 처리한다.

---

### 3. NaN 데이터 정규화 (`_sanitize_nan`)

**관련 코드**: `scripts/export_json.py:903` — `_sanitize_nan(obj)`

이 기능은 Python 서버 측 로직으로 Flutter 단위 테스트 대상이 아님.
`save_history()` 호출 전 JSON 직렬화 전에 float NaN/Inf → None 변환을 수행.

**동작 원리**
```python
def _sanitize_nan(obj):
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj
```

**Flutter 측 영향**: null 값은 `(json['field'] as num?)?.toDouble()` 패턴으로
안전하게 처리되며, 위젯에서 `-` 또는 기본값으로 표시된다.

---

### 4. 주말 필터링

**관련 코드**: `.github/workflows/daily-screening.yml`

```yaml
schedule:
  - cron: '0 19 * * 1-5'  # UTC 19:00, 월~금만 실행 (주말 제외)
  - cron: '0 23 * * 1-5'  # UTC 23:00, 월~금만 실행
```

주말 필터링은 GitHub Actions 크론 스케줄로 처리된다.
토·일에는 스크리닝이 실행되지 않으므로 history/index.json에 주말 날짜가 포함되지 않음.
따라서 스크리닝 페이지의 날짜 선택기에도 주말이 표시되지 않는다.

> Flutter 단위 테스트로 검증할 별도 로직 없음 (인프라 레벨 제어).

---

### 5. 과거 스크리닝 데이터 백업 (`save_history`)

**관련 코드**: `scripts/export_json.py:915` — `save_history(output_dir, output, now, keep_days=5)`

이 기능은 Python 서버 측 로직으로 Flutter 단위 테스트 대상이 아님.

**동작 원리**
1. `history/{today}.json` 저장 (NaN 정규화 적용)
2. 기존 히스토리 파일 NaN 재정규화
3. `keep_days`(기본 5일) 초과 파일 삭제
4. `history/index.json` 업데이트 (최신 날짜 목록)

**Flutter 측 영향**: `StaticDataSource.getHistoryDates()` → `history/index.json`에서
최근 5일치 날짜를 읽어 스크리닝 페이지의 날짜 선택기에 표시.

---

### 6. `--date` / `--batch-dates` 옵션

**관련 코드**: `scripts/export_json.py` — argparse

특정 날짜 또는 여러 날짜를 지정하여 히스토리 데이터를 일괄 생성할 수 있는 CLI 옵션.
Python 실행 옵션이므로 Flutter 테스트 대상이 아님.

---

## Python 기능 설명 (수동 검증)

Python 기능(`_sanitize_nan`, `save_history`, `fetch_usdkrw`, `_calc_atr_stop`)은
현재 Flutter 테스트 스위트에 포함되지 않는다.
수동 검증 방법:

```bash
# 가상환경 활성화 (Mac)
source .venv/bin/activate

# 스크리닝 JSON 생성 (기본 동작)
python scripts/export_json.py --output frontend/web/data/

# 포트폴리오만 재생성
python scripts/export_json.py --portfolio-only

# 출력 확인 (NaN 없는 유효한 JSON)
python -c "import json; json.load(open('frontend/web/data/screening_strategies.json')); print('JSON 유효')"
python -c "import json; json.load(open('frontend/web/data/history/index.json')); print('index.json 유효')"
```

---

## 테스트 커버리지 요약

| 기능 | Flutter 단위 테스트 | 위젯/통합 테스트 | Python 테스트 |
|------|---------------------|------------------|----------------|
| ATR 스톱로스 모델 파싱 | ✅ `portfolio_model_test.dart` | 📷 `screenshot_test.dart` | — |
| ATR 스톱 상태 조건 (임계값) | ✅ `portfolio_model_test.dart` | 📷 `screenshot_test.dart` | — |
| 환율 null 처리 | ✅ `portfolio_model_test.dart` | — | — |
| KRW/USD 금액 필드 | ✅ `portfolio_model_test.dart` | — | — |
| formatPrice() | ✅ `portfolio_model_test.dart` | — | — |
| 스크리닝 모델 파싱 | ✅ `models_test.dart` | — | — |
| 앱 기본 렌더링 | — | ✅ `widget_test.dart` | — |
| NaN 정규화 (`_sanitize_nan`) | — | — | 수동 검증 |
| 히스토리 백업 (`save_history`) | — | — | 수동 검증 |
| 환율 조회 (`fetch_usdkrw`) | — | — | 수동 검증 |
| ATR 스톱 계산 (`_calc_atr_stop`) | — | — | 수동 검증 |
| 주말 필터링 | — | — | 인프라(cron) 레벨 |
