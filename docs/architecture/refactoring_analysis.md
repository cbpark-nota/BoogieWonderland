# 리팩토링 분석 보고서 (v3.2 기준)

> 분석 기준일: 2026-04-11  
> 대상 브랜치: develop (v3.2 — 한미 분리 스크리닝, 숏스퀴즈, VIX ETF 계산기 등 반영)

---

## 우선순위 Top 10 리팩토링 항목

| # | 항목 | 위치 | 심각도 |
|---|------|------|--------|
| 1 | 백엔드 서비스가 프로덕션과 완전히 분리된 구식 하드코딩 유니버스 사용 | `backend/app/services/screener.py:10-52` | 🔴 |
| 2 | `market_cap_provider.dart` — 존재하지 않는 메서드 호출 + 완전 미사용 데드 파일 | `frontend/lib/providers/market_cap_provider.dart` | 🔴 |
| 3 | 백엔드 스크리너가 `scripts/screener/screener_v3.py`의 알고리즘을 중복 구현 | `backend/app/services/screener.py` vs `scripts/screener/screener_v3.py` | 🔴 |
| 4 | `screener_v3_kr.py`의 `_safe_float()` 미사용 함수 + `export_json.py`의 `safe_float()`와 중복 | `screener_v3_kr.py:32-40`, `export_json.py:57-63` | 🟡 |
| 5 | `serverless_providers.dart` 단일 파일 397줄에 너무 많은 책임 혼재 | `frontend/lib/providers/serverless_providers.dart` | 🟡 |
| 6 | `MarketFilter.all` enum 값이 실질적으로 `us`와 동일하게 동작 (dead branch) | `serverless_providers.dart:51-55` | 🟡 |
| 7 | `rebalanceSignalProvider` 내 RebalanceMode→StrategyType 수동 매핑 중복 | `serverless_providers.dart:381-387` | 🟡 |
| 8 | `screener_v3_kr.py`가 `sc.ALL_UNIVERSE`를 직접 교체 후 복원하는 전역 상태 mutation | `screener_v3_kr.py:210-233` | 🟡 |
| 9 | `backend/app/services/screener.py` 예외 처리 전부 `except Exception: pass` (로그 없음) | `screener.py:98-99, 104` | 🟡 |
| 10 | 스크리닝 상수(가중치, 임계값)가 `scripts/`와 `backend/` 간 이중 정의 | `scripts/screener/screener_v3.py:77-83` vs `backend/app/services/screener.py:78-84` | 🟡 |

---

## 백엔드 / 스크립트 분석

### B-1. 백엔드 유니버스가 구식 하드코딩 목록 🔴

**파일**: `backend/app/services/screener.py:10-52`

```python
US_UNIVERSE = {
    "NVDA":"Technology","AAPL":"Technology",  # ... 약 40개 하드코딩
}
KR_UNIVERSE = {
    "005930.KS":"Technology", ...  # 17개 하드코딩
}
```

**문제**: CLAUDE.md 규칙 7("주식 백테스트 시에는 항상 풀 유니버스로 수행한다. 하드코딩된 축소 유니버스는 절대 사용하지 않는다")을 위반한다. `scripts/screener/screener_v3.py`는 `core/constants.py`에서 동적 수집 함수를 사용하지만, 백엔드는 v3 이전의 구식 목록을 독립적으로 유지한다. `core/constants.py`의 `US_UNIVERSE`/`KR_UNIVERSE`와 이미 정의가 있는데 백엔드가 이를 import하지 않고 자체 정의를 사용한다.

**개선 방향**: `backend/app/services/screener.py`에서 `US_UNIVERSE`, `KR_UNIVERSE`, `ALL_UNIVERSE`, `SECTOR_ETF` 정의를 제거하고 `core/constants.py`에서 import한다.

---

### B-2. 백엔드 스크리너 알고리즘 중복 구현 🔴

**파일**: `backend/app/services/screener.py` vs `scripts/screener/screener_v3.py`

**문제**: `backend/app/services/screener.py`는 `scripts/screener/screener_v3.py`와 동일한 함수들을 별도로 재구현한다:
- `calc_indicators()` — 동일 (backend:108-122 vs scripts:110-155)
- `count_hh_hl_swing()` — 동일 (backend:125-135 vs scripts:129-138)
- `screen_stock()` / `screen()` — 동일 로직 (backend:138+ vs scripts:185+)
- `rank_stocks()` — 동일 (별도 구현)

또한 백엔드의 `SCORE_WEIGHTS`가 스크립트와 불일치한다:
- scripts: `adx=0.30, ret3m=0.20, ret12m=0.20, sector=0.20, vol_stab=0.10`
- backend: 동일 딕셔너리 키이나 주석 상태 불일치

**개선 방향**: 백엔드 서비스가 `scripts/screener/screener_v3.py`를 직접 import하거나, `core/screening_engine.py`로 공통 모듈을 분리한다.

---

### B-3. `screener_v3_kr.py` — `_safe_float()` 미사용 함수 🟡

**파일**: `scripts/screener/screener_v3_kr.py:32-40`

```python
def _safe_float(val, ndigits=2):
    import math
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, ndigits)
    except (TypeError, ValueError):
        return None
```

**문제**: 이 함수는 파일 내 어디서도 사용되지 않는다. `export_json.py`의 `safe_float()`(57-63줄)과 기능이 동일한 중복 함수다. `screener_v3_kr.py` 내부에서는 `sc.rank_stocks()` 등 screener_v3 함수를 그대로 사용하기 때문에 별도 safe_float이 필요 없다.

**개선 방향**: `_safe_float()` 삭제. 공통으로 필요하다면 `core/utils.py`에 단일 구현.

---

### B-4. `screener_v3_kr.py` — 전역 상태 직접 변조 🟡

**파일**: `scripts/screener/screener_v3_kr.py:210-233`

```python
orig_all = dict(sc.ALL_UNIVERSE)
sc.ALL_UNIVERSE.clear()
sc.ALL_UNIVERSE.update(kr_sectors)
# ... 스크리닝 실행 ...
sc.ALL_UNIVERSE.clear()
sc.ALL_UNIVERSE.update(orig_all)
```

**문제**: `screener_v3` 모듈의 전역 딕셔너리를 직접 교체 후 복원한다. 비동기/스레드 환경에서 경쟁 조건(race condition)이 발생할 수 있다. `export_json.py`에서 US/KR 스크리닝을 순차 실행할 때는 괜찮지만, 구조적으로 취약하다.

**개선 방향**: `run_kr_screening()` 함수 시그니처에 `universe: dict` 파라미터를 추가하고, 내부에서 `sc.screen(df_ind, universe=...)` 형태로 전달한다. 전역 상태 변조를 제거한다.

---

### B-5. 예외 처리에 로그 누락 🟡

**파일**: `backend/app/services/screener.py:98-99, 104`

```python
except Exception:
    pass  # 라인 99

except Exception:
    return {}  # 라인 104, 로그 없음
```

**문제**: `scripts/screener/screener_v3.py`는 `logging.debug()`라도 남기지만, 백엔드 서비스는 모든 예외를 무시한다. 다운로드 실패 시 빈 결과가 정상 결과처럼 반환되어 디버깅이 불가능하다.

**개선 방향**: 최소한 `logging.warning("download_tickers failed: %s", e)` 추가.

---

### B-6. `export_json.py` — 스크리닝 상수와 스크립트 상수 이중 관리 🟡

**파일**: `scripts/export_json.py:49-54`

```python
STRATEGIES = {
    "aggressive":   {"atr_mult": 1.5, ...},
    "balanced":     {"atr_mult": 2.0, ...},
    "conservative": {"atr_mult": 2.5, ...},
    "adaptive":     {"atr_mult": 2.0, ...},
}
```

**문제**: 이 전략 정의가 `screener_v3.py`의 `ATR_MULT_*` 상수와 이중으로 관리된다. ATR 승수 변경 시 두 곳을 수정해야 한다.

**개선 방향**: `core/constants.py`에 `STRATEGIES` 딕셔너리를 이동하고 두 파일에서 import.

---

### B-7. `screener_v3.py` — download 실패를 DEBUG 레벨로만 로깅 🟢

**파일**: `scripts/screener/screener_v3.py:99, 105`

```python
logging.debug("screener_v3 download: %s 슬라이스 실패 — %s", t, e)
```

**문제**: 프로덕션 로그 레벨에서 보이지 않아 데이터 손실을 감지하기 어렵다.

**개선 방향**: `logging.warning()`으로 상향.

---

### B-8. `screener_v3_kr.py` — `pykrx` import 반복 🟢

**파일**: `scripts/screener/screener_v3_kr.py:59, 110, 137`

```python
from pykrx import stock as pkstock  # 함수 호출마다 3회 반복
```

**문제**: 파일 상단에서 한 번만 import하면 되는데 각 함수 내부에서 반복 import한다. 성능상 큰 문제는 없지만 (Python이 모듈 캐싱을 하므로) 코드 명확성이 떨어진다.

**개선 방향**: 파일 상단에서 `try/except ImportError`로 한 번만 import.

---

## 프론트엔드 분석

### F-1. `market_cap_provider.dart` — 데드 파일 (존재하지 않는 메서드 + 미사용) 🔴

**파일**: `frontend/lib/providers/market_cap_provider.dart`

```dart
final marketCapProvider = FutureProvider<MarketCapData?>((ref) async {
  try {
    final data = await StaticDataSource().getMarketCap(); // ← 이 메서드 없음!
    return MarketCapData.fromJson(data);
  } catch (_) {
    return null;
  }
});
```

**문제**:
1. `StaticDataSource`에 `getMarketCap()` 메서드가 없다 (실제 메서드명은 `getMarketCapTop20()`).
2. `MarketCapScreen`은 이 provider를 전혀 사용하지 않는다 — `serverless_providers.dart`의 `marketCapTop20Provider`를 사용한다.
3. 이 파일은 완전한 데드 코드이며, 빌드는 통과하지만 런타임에서 항상 예외를 던진다.

**개선 방향**: `market_cap_provider.dart` 파일 삭제. `MarketCapScreen`이 이미 `serverless_providers.dart`의 `marketCapTop20Provider`를 올바르게 사용 중.

---

### F-2. `MarketFilter.all` enum 값 — Dead Branch 🟡

**파일**: `frontend/lib/providers/serverless_providers.dart:15, 51-55`

```dart
enum MarketFilter { all, kr, us }

// filteredScreeningProvider 내부:
final isKr = marketFilter == MarketFilter.kr;
final historyAsync = isKr
    ? ref.watch(krHistoryScreeningProvider)
    : ref.watch(historyScreeningProvider);  // all과 us 모두 여기로 떨어짐
```

**문제**: `MarketFilter.all`과 `MarketFilter.us`가 동일한 데이터를 반환한다. v3.2에서 `all` 필터의 의미가 "US + KR 혼합"이어야 할 텐데 실제로는 US와 동일하게 동작한다. 또한 기본값이 `MarketFilter.us`로 설정되어 있어 `all`은 사실상 사용되지 않는다.

**개선 방향**: `MarketFilter.all`을 제거하고 `enum MarketFilter { us, kr }`로 단순화하거나, `all`의 의미를 US+KR 통합 뷰로 실제 구현한다.

---

### F-3. `serverless_providers.dart` 단일 파일에 너무 많은 책임 🟡

**파일**: `frontend/lib/providers/serverless_providers.dart` (397줄)

**문제**: 단일 파일에 다음이 혼재한다:
- `MarketFilter` enum (도메인 타입)
- `RebalanceMode` enum + `RebalanceSignal` 모델 (도메인 타입)
- 날짜 계산 헬퍼 4개 함수 (`_lastFriday`, `_lastBiweeklyFriday` 등)
- 서버리스 Notifier 클래스들 (`ServerlessScreeningNotifier`, `ServerlessHoldingsNotifier`)
- 데이터 providers 10개 이상 (`strategyDataProvider`, `krStrategyDataProvider`, `portfolioDataProvider`, `shortSqueezeProvider`, `marketCapTop20Provider` 등)
- 히스토리/날짜 선택 providers

**개선 방향**:
```
providers/
  rebalance_provider.dart     # RebalanceMode, RebalanceSignal, 날짜 계산
  history_provider.dart       # historyDates, historyScreening, selectedDate
  serverless_notifiers.dart   # ServerlessScreeningNotifier, ServerlessHoldingsNotifier
  market_data_providers.dart  # shortSqueeze, marketCap, marketStatus
  (기존 serverless_providers.dart는 import/re-export 파사드로 유지)
```

---

### F-4. `rebalanceSignalProvider` — RebalanceMode→StrategyType 수동 매핑 🟡

**파일**: `frontend/lib/providers/serverless_providers.dart:381-387`

```dart
final StrategyType strategyType;
if (mode == RebalanceMode.aggressive) {
  strategyType = StrategyType.aggressive;
} else if (mode == RebalanceMode.balanced) {
  strategyType = StrategyType.balanced;
} else {
  strategyType = StrategyType.conservative;
}
```

**문제**: `RebalanceMode`와 `StrategyType`의 값이 1:1 대응임에도 수동 if-chain으로 매핑한다. `RebalanceMode`가 추가되거나 변경될 때 이 코드를 찾아서 수정해야 한다.

**개선 방향**: `RebalanceMode` enum에 `toStrategyType()` 메서드를 추가하거나 Map을 사용.

```dart
StrategyType get strategyType => switch (this) {
  RebalanceMode.aggressive => StrategyType.aggressive,
  RebalanceMode.balanced => StrategyType.balanced,
  RebalanceMode.conservative => StrategyType.conservative,
};
```

---

### F-5. `StaticDataSource` — `getKrScreeningByDate`의 데이터 리매핑 🟡

**파일**: `frontend/lib/services/static_data_source.dart:83-91`

```dart
Future<Map<String, dynamic>> getKrScreeningByDate(String date) async {
  final res = await _dio.get('$_baseDataUrl/history/$date.json');
  final data = res.data as Map<String, dynamic>;
  return {
    ...data,
    'strategies': data['kr_strategies'] ?? {},  // 키 리매핑
  };
}
```

**문제**: `history/{date}.json`은 `getScreeningByDate()`와 `getKrScreeningByDate()` 모두 동일 파일을 요청한다. 두 번의 HTTP 요청이 동일 URL에 발생할 수 있다 (UI가 날짜 선택 시 US+KR 모두 watch하는 경우). 또한 `strategies` 키를 강제로 `kr_strategies`로 오버라이드하는 방식은 데이터 구조가 변경될 때 조용히 실패한다.

**개선 방향**: 단일 요청으로 US/KR 모두 가져오는 `getScreeningDataByDate(date)` 메서드를 사용하고, 상위에서 키를 선택하도록 분리.

---

### F-6. `screening_screen.dart` — 서버리스/풀스택 분기 코드 중복 🟡

**파일**: `frontend/lib/screens/screening_screen.dart:14-18`

```dart
if (AppConfig.isServerless) {
  return _buildServerlessView(context, ref);
}
return _buildFullstackView(context, ref);
```

**문제**: `screening_screen.dart`에 서버리스 뷰와 풀스택 뷰가 함께 있고, 두 `_build*` 메서드가 일부 위젯 빌더(`_buildDateSelector`, `_buildStrategySelector` 등)를 공유하면서 코드가 복잡하다. 파일 전체 길이가 늘어날수록 관리가 어려워진다.

**개선 방향**: `screening_screen_serverless.dart` / `screening_screen_fullstack.dart`로 분리하고 `main.dart` 또는 라우터에서 조건 분기.

---

### F-7. `MarketCapScreen` — `Map<String, dynamic>` 직접 파싱 🟡

**파일**: `frontend/lib/screens/market_cap_screen.dart:49-53`

```dart
final top20 = (data['top20'] as List? ?? [])
    .cast<Map<String, dynamic>>();
final sectorDist = (data['sector_distribution'] as List? ?? [])
    .cast<Map<String, dynamic>>();
```

**문제**: `marketCapTop20Provider`가 `Map<String, dynamic>`을 반환하기 때문에 화면에서 직접 JSON 구조를 파싱한다. `market_cap_data.dart`에 `MarketCapData` 모델이 이미 정의되어 있음에도 활용되지 않는다.

**개선 방향**: `marketCapTop20Provider`를 `FutureProvider<MarketCapData?>`로 교체 (또는 `market_cap_provider.dart`의 broken provider를 수정)하고, `MarketCapScreen`에서 모델을 직접 사용.

---

### F-8. `screening_provider.dart` — 에러 무시 🟡

**파일**: `frontend/lib/providers/screening_provider.dart:15-17`

```dart
} catch (_) {
  return null;
}
```

`serverless_providers.dart` 전반에도 동일 패턴:
```dart
} catch (_) {
  return null;  // 어떤 에러인지 전혀 알 수 없음
}
```

**문제**: 모든 예외를 무시하고 null을 반환한다. 네트워크 오류인지, JSON 파싱 오류인지, 잘못된 URL인지 구별 불가능. 디버깅 시 원인 파악이 어렵다.

**개선 방향**: 최소한 `debugPrint()`로 예외 로깅. 필요시 Sentry/Crashlytics 연동.

---

### F-9. `strategy_guide_tabs_screen.dart` — `ScreeningTabsScreen`과 유사한 탭 구조 중복 🟢

**파일**: `frontend/lib/screens/strategy_guide_tabs_screen.dart`, `frontend/lib/screens/screening_tabs_screen.dart`

**문제**: 두 파일 모두 `DefaultTabController` + `TabBar` + `TabBarView` 구조의 거의 동일한 탭 래퍼 코드를 반복한다.

**개선 방향**: `TabsScreen` 제너릭 위젯 추출 (tabs: `List<(String label, Widget screen)>`).

---

### F-10. 모델 파일들 — `fromJson` 내부에 비즈니스 로직 혼재 🟢

**파일**: `frontend/lib/models/market_cap_data.dart:86-108`

```dart
List<MarketCapEntry> buildEntries(
  List<dynamic> top20List,
  Map<String, dynamic> capsMap,
  Set<String> newSet,
  String market,
) {
  return top20List.asMap().entries.map((entry) { ... }).toList();
}
```

**문제**: `fromJson` 팩토리 내부에 `buildEntries`라는 로컬 함수가 정의되어 있다. 복잡한 변환 로직이 생성자에 혼재하여 테스트가 어렵다.

**개선 방향**: `buildEntries`를 `static` 메서드로 분리하거나 별도 파서 클래스 도입.

---

## 테스트 커버리지 부족

### T-1. 핵심 스크리닝 함수 유닛 테스트 없음 🟡

**관련 모듈**: `scripts/screener/screener_v3.py`, `scripts/screener/screener_v3_kr.py`

**문제**: `calc_indicators()`, `screen()`, `rank_stocks()`, `calc_position_weights()`에 대한 유닛 테스트가 없다. 백테스트 스크립트가 통합 테스트 역할을 하지만, 개별 함수의 경계값 처리 (NaN, 빈 데이터프레임, 60일 미만 데이터)를 검증하지 않는다.

**개선 방향**: `tests/test_screener_v3.py` 작성 (`pytest`). 특히 `screen()` 함수에 대한 mock 데이터 기반 테스트.

### T-2. `export_json.py` 통합 테스트 없음 🟢

**문제**: JSON 내보내기 파이프라인 전체를 검증하는 테스트가 없다. 출력 JSON 스키마 변경 시 Flutter 앱과의 호환성 깨짐을 사전에 감지할 수 없다.

**개선 방향**: `tests/test_export_json.py` — mock 데이터로 출력 JSON의 스키마/필드 존재 여부 검증.

---

## 요약

| 심각도 | 항목 수 | 주요 파일 |
|--------|---------|-----------|
| 🔴 높음 | 3 | `backend/app/services/screener.py`, `market_cap_provider.dart` |
| 🟡 중간 | 12 | `serverless_providers.dart`, `screener_v3_kr.py`, `screening_screen.dart` 등 |
| 🟢 낮음 | 4 | 탭 위젯 중복, pykrx import 반복, 로그 레벨 등 |

**즉시 수정 권장 (🔴)**:
1. `market_cap_provider.dart` 삭제 — 데드 코드 + 존재하지 않는 메서드 호출
2. `backend/app/services/screener.py` 유니버스를 `core/constants.py`에서 import
3. 백엔드-스크립트 알고리즘 중복 제거 계획 수립
