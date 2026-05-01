# 프론트엔드(Flutter Web) 종합 코드 리뷰 — 2026-05-01

리뷰 대상: `frontend/` 디렉터리 (lib + test + web + pubspec.yaml)
리뷰 관점: 시니어 프론트엔드 엔지니어 + Flutter 베테랑
독자: 프론트엔드를 잘 모르는 프로젝트 오너 → 각 항목의 의미부터 설명한다

---

## 0. 한 줄 요약

> **"기능은 충분히 동작하고, JSON 파싱·테스트·라이트한 상태관리는 평균 이상이다.
> 다만 (1) 화면 파일이 1,000줄을 넘는 거대 위젯, (2) 접근성·국제화·디자인 시스템 부재,
> (3) 디자인 토큰 하드코딩 폭주, (4) 성능에 직결되는 ListView·rebuild 패턴, (5) 풀스택/서버리스 두 갈래 분기 정리"
> 이 다섯 가지가 가장 큰 부채다.**

세부 평점(상/중/하) 분포: **상 3, 중 6, 하 6**. 즉 절반 가까이가 손볼 가치가 있다.

프로젝트는 Flutter 3.11+ Material 3, Riverpod 3.x, Dio 5.x, GitHub Pages 정적 배포라는 모던한 스택이고
서버리스 모드(`DEPLOY_ENV=serverless`)가 메인 진입점이다. 풀스택 모드 코드(API 클라이언트 + 백엔드)는 dead code에 가까운
"잠재 분기"로 남아 있어 실제 배포 형상과 코드 베이스의 정합성을 떨어뜨린다.

---

## 검토 항목별 평가

각 항목은 다음 5단으로 정리한다.
1. **이게 뭐야?** — 비전공자용 한 줄 설명
2. **왜 중요해?** — 안 챙기면 어떤 손실이 있는지
3. **현재 상태** — 이 프로젝트의 실제 사례(파일/라인)
4. **평점** — 상/중/하
5. **개선 제안** — 실행 가능한 다음 액션

---

### 1. 아키텍처 / 레이어 분리

**이게 뭐야?**
앱 코드를 "화면(screens) / 재사용 부품(widgets) / 상태 관리(providers) / 데이터 모델(models) / 외부 통신(services)"
처럼 책임별로 갈라놓는 것. 잘 나눠 두면 한 군데를 고칠 때 다른 곳이 안 깨진다.

**왜 중요해?**
경계가 흐려지면 화면 코드 안에 통신·계산·UI 로직이 한꺼번에 섞여 버그 추적이 어려워지고
같은 코드를 여러 화면에 복붙하기 시작한다.

**현재 상태**
- `lib/` 디렉터리 분할은 **표준 패턴(screens / widgets / providers / models / services / config)**을 잘 따라가고 있다 → 첫인상은 좋다.
- 그러나 실제로는 **screens 내부에 위젯·계산 로직이 다 들어 있다.**
  - [strategy_guide_screen.dart](frontend/lib/screens/strategy_guide_screen.dart) — **1,132줄**
  - [crypto_strategy_guide_screen.dart](frontend/lib/screens/crypto_strategy_guide_screen.dart) — **1,065줄**
  - [portfolio_screen.dart](frontend/lib/screens/portfolio_screen.dart) — **1,035줄** (`_SummaryCard`, `_WeightChart`, `_HoldingsList`, `_HoldingCard`, `_PriceChip`, `_AtrStopRow`, `_RebalanceModeSelector`, `_UploadToolbar`, `_ToolbarButton`, `_CurrencyToggle`, `_ToggleBtn`, `_MetricTile` 등 12개 이상의 private 위젯이 한 파일에 동거)
  - [vix_strategy_guide_screen.dart:970](frontend/lib/screens/vix_strategy_guide_screen.dart) — **970줄**
- 같은 `_metric` 함수가 [stock_card.dart:106](frontend/lib/widgets/stock_card.dart) 와 [market_status_banner.dart:4](frontend/lib/widgets/market_status_banner.dart) 에 거의 그대로 두 번 정의돼 있다.
- 같은 BTC/ETH 시그널 위젯 ([btc_signal_widget.dart](frontend/lib/widgets/btc_signal_widget.dart), [eth_signal_widget.dart](frontend/lib/widgets/eth_signal_widget.dart))은 **거의 100% 동일한 로직**(라벨만 BTC↔ETH)을 두 파일에 복제하고 있다.
- `widgets/` 디렉터리에는 5개 파일만 있어, "재사용 위젯" 슬롯이 사실상 비어 있다 — 위젯 추출이 전혀 일어나지 않았다는 신호.
- `services/portfolio_xlsx_service.dart`는 비즈니스 로직(콤마 제거 + 통화 계산)을 service에 두면서도, 같은 통화 계산이 [portfolio_data.dart:80](frontend/lib/models/portfolio_data.dart) `formatPrice`에도 들어가 있어 책임이 모호하다.

**평점: 중 (B-)**
폴더 구조의 외형은 표준 그대로지만, 내부 위젯 추출과 중복 제거가 안 되어 "구조만 있고 모듈은 없는" 상태.

**개선 제안**
1. **800줄 이상 화면을 분할.** 한 화면 = `<screen_name>/` 폴더 + 화면 파일 + 그 화면이 사용하는 sub-widget 파일들.
2. **위젯 라이브러리화.** `_metric`, `_PriceChip`, `_infoChip`, `_StatusPill` 등 작은 부품을 `widgets/atoms/` 또는 별도 파일로 빼고, BTC/ETH 시그널은 단일 `CryptoSignalCard`로 통합 (라벨·테마만 prop).
3. 가이드 스크린(strategy_guide, vix_strategy_guide, ...)은 **데이터 정의(JSON-like)** 와 **렌더링 컴포넌트**를 분리. 1,000줄짜리 const tree는 전형적인 "정적 콘텐츠를 코드로 박은" 안티패턴이다 → `assets/strategy_guide.json`으로 빼고 `StrategyGuideRenderer`가 읽도록.

---

### 2. 상태 관리 (Riverpod)

**이게 뭐야?**
"이 화면은 지금 어떤 데이터를 보고 있나"를 관리하는 도구. Riverpod는 Flutter 진영에서 Provider/Bloc과 함께 가장 널리 쓰이는 상태 라이브러리.

**왜 중요해?**
Provider 종류 선택을 잘못하면 (1) 같은 데이터를 여러 번 로드하거나, (2) 화면 전환 시 메모리에 데이터가 영구히 남거나, (3) 빌드 폭주가 일어난다.

**현재 상태**
- **버전**: `flutter_riverpod: ^3.3.1` (최신 메이저 라인) — 좋다.
- **Provider 선택**:
  - `FutureProvider` 다수 ([serverless_providers.dart](frontend/lib/providers/serverless_providers.dart) 9개) — 단발성 비동기 로드는 적절.
  - `AsyncNotifierProvider` 사용 ([screening_provider.dart:5](frontend/lib/providers/screening_provider.dart), [portfolio_provider.dart:5](frontend/lib/providers/portfolio_provider.dart)) — `refresh()` 같은 메서드가 필요한 곳에 알맞게 선택.
  - `NotifierProvider` 로 단순 enum 토글 관리 — 적절.
  - 옛날식 `StateProvider`는 안 쓰고 모두 `Notifier`로 통일 → 좋다.
- **AsyncValue 처리**: `data/loading/error` 3분기 처리가 일관됨 ([dashboard_screen.dart:26-46](frontend/lib/screens/dashboard_screen.dart), [screening_screen.dart:62-71](frontend/lib/screens/screening_screen.dart)).
- **문제 1 — 중복 정의**: `shortSqueezeProvider`가 두 곳에 **동시에** 정의돼 있다.
  - [providers/short_squeeze_provider.dart:7](frontend/lib/providers/short_squeeze_provider.dart)
  - [providers/serverless_providers.dart:138](frontend/lib/providers/serverless_providers.dart)
  → import 순서에 따라 어느 것이 쓰이는지 헷갈리고, 한쪽만 고치면 silent regression 위험.
- **문제 2 — autoDispose 부재**: `FutureProvider.autoDispose`는 [trend_reversal_provider.dart:38](frontend/lib/providers/trend_reversal_provider.dart) **딱 한 곳**에만 적용. 나머지 11개 FutureProvider는 한 번 로드하면 앱 종료까지 메모리에 남는다. 서버리스 모드는 Cache-friendly이긴 하나, 히스토리 30일 분이 모두 메모리에 누적될 수 있음.
- **문제 3 — 캐시 버스팅이 메모이제이션과 충돌**: [static_data_source.dart:36](frontend/lib/services/static_data_source.dart)에서 `?v=${ms~/60000}` 캐시 버스팅을 쓰는데, FutureProvider가 자동 캐싱이라 1분이 지나도 provider가 invalidate되기 전에는 새 값을 못 받는다 → 의도와 결과가 어긋남.
- **문제 4 — `ref.read` vs `ref.watch`**: `ref.watch` 37회, `ref.read` 12회로 비율은 양호. 다만 [screening_screen.dart:108](frontend/lib/screens/screening_screen.dart) `ref.read(...).state = displayDates[idx + 1]` 같이 Riverpod 3.x에서는 `notifier.set()` 패턴을 권장하는 직접 `state =` 할당이 다수 잔존.

**평점: 중 (B)**
Riverpod 사용 자체는 깔끔. 다만 중복 provider, autoDispose 누락, 캐시 모델의 모호함은 정리 필요.

**개선 제안**
1. `serverless_providers.dart`의 `shortSqueezeProvider` **삭제**, `short_squeeze_provider.dart`의 것만 사용.
2. 데이터형 `FutureProvider`에 `.autoDispose` 적용 (또는 명시적으로 keep하고 싶은 것에만 keepAlive).
3. 캐시 버스팅(`?v=...`) 제거하고, "수동 새로고침 시 `ref.invalidate(...)`" 패턴으로 통일. 1분 간격 자동 갱신이 필요하면 `Stream.periodic` + `StreamProvider`.
4. `ref.read(provider.notifier).state = X` → `notifier.setX(X)` 패턴으로 마이그레이션.
5. `riverpod_lint`/`custom_lint` 도입(자동으로 위 안티패턴을 잡아줌).

---

### 3. 렌더링 성능

**이게 뭐야?**
화면이 갱신될 때 얼마나 적은 리소스로 그릴 수 있는가. Flutter는 위젯 트리를 매 프레임 다시 만드는 모델이라, 잘못 짜면 60fps가 30fps로 떨어진다.

**왜 중요해?**
모바일/저사양 기기에서 끊김이 생기고, 웹에서는 첫 페인트가 느려지고 메모리 사용량이 올라간다.

**현재 상태**
- **`const` 사용**은 1,167회로 많이 박혀 있어 **rebuild 비용 절감의 베이스라인**은 갖춰져 있다.
- **그러나 `ListView.builder` 사용은 단 1회**, 일반 `ListView()` (children eager-build)가 17회.
  - [screening_screen.dart:389](frontend/lib/screens/screening_screen.dart)에서는 종목 리스트를 `ListView(children: [..., ...sorted.map(...)])` 방식으로 그린다 — TOP 25개라 큰 문제는 아니나, history나 트렌드 분석 데이터가 50+로 늘면 즉시 병목.
  - [strategy_guide_screen.dart:9](frontend/lib/screens/strategy_guide_screen.dart) 같은 1,000줄짜리 정적 카드 모음을 `ListView(children: [...])`로 그리는 건 일종의 잠재적 메모리 폭탄.
- **불필요한 리빌드 위험**:
  - [main.dart:122-143](frontend/lib/main.dart) `_currentScreen` getter는 setState로 destination이 바뀔 때마다 새 위젯 인스턴스를 생성. `IndexedStack` + 캐싱 기반이 아니라서 화면 전환 시 상태(스크롤 위치, 검색어, 필터)가 매번 초기화된다. `ScreeningTabsScreen.withIndex(key: ValueKey(...))`로 의도적으로 새 인스턴스를 만들고 있는데, 이는 **의도된 디자인이지만 사용자 입장에서는 "탭 갈아낄 때마다 리셋되는" 불편**으로 이어진다.
  - `_AtrStopRow`, `_WeightChart` 내 `LayoutBuilder` 사용 → 매 빌드마다 layout 재측정. 큰 보유 종목 리스트가 들어오면 누적 코스트.
- **`itemExtent`/`cacheExtent`/`Key` 사용은 0회.** 가변 높이 카드를 ListView.builder로 바꾸면서 itemExtent를 정해 두면 스크롤 점프가 사라지지만 현재는 미적용.
- **이미지/자산이 없어 첫 페인트는 가벼운 편** — 자산 부담은 거의 0.

**평점: 중 (B-)**
TOP 25 종목 수준에서는 체감 안 되지만, 히스토리/풀유니버스로 데이터가 늘면 곧장 병목. 지금 손쉽게 대비 가능한 단계.

**개선 제안**
1. 모든 데이터 기반 리스트를 `ListView.builder` + `itemExtent`(또는 `prototypeItem`)로 전환.
2. 가이드/정적 카드 화면은 `SliverList` + `SliverChildBuilderDelegate`로 lazy 화.
3. `MainNavigation`에 `IndexedStack`을 도입해 탭 간 상태 보존(스크롤 위치, 필터)을 살리거나, 의도적으로 리셋하려면 그 의도를 코드 주석으로 명시.
4. 큰 화면을 작은 위젯으로 쪼개고 그 위젯에 `const` + `super.key`를 부여 → Flutter가 자체 리빌드 스킵 가능.
5. Flutter DevTools Performance/Repaint Rainbow를 한 번 돌려 hotspot 확인.

---

### 4. 네트워크 / 데이터 로딩

**이게 뭐야?**
서버에서 JSON을 가져오는 부분. 성공 케이스만큼 실패 케이스(타임아웃·404·파싱 실패) 처리가 중요하다.

**왜 중요해?**
GitHub Pages가 일시 다운되거나 사용자가 와이파이가 끊겨도 앱이 "그냥 멍"하지 않게 해야 한다.

**현재 상태**
- HTTP 클라이언트 추상화: `Dio` 싱글턴 두 개([api_client.dart:5](frontend/lib/services/api_client.dart), [static_data_source.dart:6](frontend/lib/services/static_data_source.dart))로 분리 — 좋다.
- 타임아웃: `connectTimeout: 30s, receiveTimeout: 60s` (api_client) / `10s/10s` (static_data_source) — 정적 JSON에 30s/60s는 과도, 10s/10s는 무난.
- **에러 처리 패턴은 거의 모든 곳이 `catch (_)` 로 빈 fallback**:
  - [api_client.dart:53](frontend/lib/services/api_client.dart) `_unwrapScreeningResponse` 외엔 모두 `try { ... } catch (_) { return null; }` 또는 `return [];`
  - 25곳에서 `catch (_)`로 에러를 **삼키고** 있음(`grep -rn "catch (_)" lib | wc -l` → 25).
  - 결과적으로 사용자는 "데이터가 없습니다"만 보고, 개발자는 어디서 에러가 났는지 알 길이 없다 (debugPrint도 0회).
- 재시도(retry) 로직: **없음**. Dio interceptor도 없음.
- 빈 상태 UI: 일부 화면([screening_screen.dart:441-457](frontend/lib/screens/screening_screen.dart), [portfolio_screen.dart:42](frontend/lib/screens/portfolio_screen.dart))은 빈 상태를 잘 다루지만, [trend_reversal_screen.dart:46](frontend/lib/screens/trend_reversal_screen.dart) 등 일부는 `'데이터가 없습니다'` 텍스트만.
- 로딩 상태 UI: `CircularProgressIndicator`만 사용. 스켈레톤 UI 없음 → "처음 보는 사용자가 5초간 빈 동그라미만" 보는 시간이 길다.
- 캐싱: HTTP 캐시 헤더 의존(브라우저 캐시) + 일부 `?v=timestamp` 캐시 버스팅. 일관된 전략 없음.

**평점: 하 (C)**
"성공 시"는 작동하지만 실패 관측 가능성과 사용자 피드백이 약하다.

**개선 제안**
1. **Dio Interceptor**로 (a) 에러 로깅, (b) 지수 백오프 재시도(2회), (c) HTTP 5xx → 사용자 친화 메시지 변환 추가.
2. `catch (_)` 대신 `catch (e, st) { debugPrint('...'); return null; }` 또는 `Sentry` / `FirebaseCrashlytics` 같은 원격 로깅 도입.
3. 모든 화면에 `loading → 스켈레톤`, `error → 재시도 버튼이 있는 에러 카드`, `empty → 친절 안내` 3종 세트를 의무화. 공통 `AsyncValueRenderer<T>` 위젯 도입을 추천.
4. `connectTimeout`을 정적 JSON 기준 5–10s로 단축, 백엔드 호출은 15s 정도로 통일.

---

### 5. null 안전성 / 타입 안전성

**이게 뭐야?**
"값이 없을 수 있다(null)"를 안전하게 다루는 능력. Dart는 sound null safety를 강제하지만, `as`/`!`로 빠져나갈 구멍은 늘 있다.

**왜 중요해?**
JSON 키가 빠지거나 타입이 바뀌었을 때(=백엔드가 살짝 바뀌었을 때) 런타임에서만 터지는 크래시의 80%가 여기서 나온다.

**현재 상태**
- 강제 언래핑(`!`): 약 20회 — Flutter 표준 대비 적은 편.
- `as Map<String, dynamic>` 캐스트: **35회**. JSON 파싱이 모두 손코딩이라 캐스트가 빈번.
- `dynamic` 사용: `List<dynamic>`(api_client.dart, screening_provider 등) 다수.
- **`json_serializable`/`freezed` 미사용** (pubspec/lock 모두 검색 결과 없음).
  - 모든 모델이 손으로 `fromJson`을 작성 → 늘어날수록 typo 위험. 예: [screening_result.dart:36](frontend/lib/models/screening_result.dart) `json['rank']`처럼 키가 cast 없이 들어가 있고, 이때 `int?`가 와도 `dynamic→int` 암시 변환에 의존.
- `historyDates` 파싱: [static_data_source.dart:46](frontend/lib/services/static_data_source.dart) `data['dates'] as List` → `List<String>.from(...)` — 안전.
- 한편 `screeningResult.fromJson`의 `score: (json['score'] as num).toDouble()`은 `score`가 누락되면 즉시 크래시. 다른 nullable 필드(`adx`, `rsi`)는 `as num?`로 잘 막혀 있어 일관성이 균일하지 않음.
- 모델은 **immutable**(final 필드 + ctor)로 잘 잡혀 있고, equality/hashCode/copyWith는 [screening_result.dart:53](frontend/lib/models/screening_result.dart)에 부분적으로만(rank만 가능) 존재 — 비교/캐싱 시 문제 가능.

**평점: 중 (B-)**
nullable 처리는 평균적이지만 codegen 미사용으로 인한 사람손 부채가 누적 중.

**개선 제안**
1. **`freezed` + `json_serializable`** 도입. 14개 모델 파일 중 절반(screening_result, portfolio_data, market_cap_data, vix_etf_data, trend_reversal_data, short_squeeze*)을 codegen으로 옮기면 `fromJson`/`copyWith`/`==`/`hashCode`가 공짜로 따라온다.
2. 필수 필드(`rank`, `ticker`, `score` 등)에도 `as num?` + `?? 0` 또는 `tryParse`형 안전 변환 적용.
3. JSON 키 누락 시의 동작을 **모델 단위 단위 테스트**로 못 박기 — 이미 [test/portfolio_model_test.dart](frontend/test/portfolio_model_test.dart) 등이 모범 사례이므로 다른 모델로 확장.

---

### 6. 테마 / 디자인 시스템

**이게 뭐야?**
색·간격·폰트·둥근 모서리 같은 디자인 토큰을 한 곳에서 관리하는 체계. 다크모드/리디자인이 자유로워진다.

**왜 중요해?**
하드코딩된 `Colors.red.shade600`은 다크모드에서 가독성을 박살내고, 브랜드 색을 바꾸려면 100군데를 고쳐야 한다.

**현재 상태**
- `ThemeData`는 [main.dart:91-100](frontend/lib/main.dart)에서 `colorSchemeSeed: Colors.blue` + `useMaterial3: true` + light/dark + `ThemeMode.system`. 베이스라인은 OK.
- **그러나 코드베이스에서 `Colors.<X>` 직접 참조가 318회**. 즉 각 화면이 자기 마음대로 색을 결정.
  - 빨간/녹색은 "오를 때/내릴 때"를 의미하지만, 어디는 `Colors.red`, 어디는 `Colors.red.shade600`, 어디는 `Color(0xFFEF5350)` 식으로 셰이드가 다 다름.
  - 다크모드에서 "0.08 alpha 위에 grey 글씨"가 거의 안 읽힘.
- `AnimatedContainer`/`Container.decoration` 안의 `borderRadius: BorderRadius.circular(N)` — 6, 8, 10, 12, 14가 무작위로 혼재. 디자인 일관성 부재.
- `withOpacity` / `withValues` / `withAlpha`가 93회 — Flutter 3.27+의 `withValues` 권장 마이그레이션은 일부 진행, 일부 미진행 (혼용).
- 폰트 사이즈(10, 11, 12, 13, 14, 15, 16, 18, 20)가 모든 화면에 매직 넘버로 박혀 있음 → **의도적 위계가 없는 마이크로타이포그래피**.
- 텍스트 스타일 토큰 미사용. `Theme.of(context).textTheme.bodyMedium` 같은 호출은 거의 안 보임 (`116`회 `Theme.of` 중 대부분 `colorScheme` 접근).
- Custom theme extension(`ThemeExtension<AppColors>`) 도입 흔적 없음.

**평점: 하 (C-)**
"동작은 하지만 손댈 때마다 100군데가 바뀌어야 하는" 가장 위험한 영역.

**개선 제안**
1. `lib/theme/app_tokens.dart`에 `AppColors`, `AppSpacing`, `AppRadius`, `AppTypography` 토큰 클래스 정의(또는 `ThemeExtension` 활용).
2. 의미 있는 색을 토큰화: `success`, `warning`, `danger`, `regimeBull`, `regimeBear`, `marketUs`, `marketKr` 등. 318개의 `Colors.X`를 모두 토큰 참조로 바꾸기 전, 가장 자주 등장하는 10개부터 토큰화하면 80% 효과.
3. 다크모드에서 한 번 클릭하며 가독성 점검(`/* TODO: dark contrast */` 라벨링).
4. 디자인 시스템 storybook 대안으로 `widgetbook` 또는 직접 만든 "갤러리 화면"을 도입.

---

### 7. 반응형 / 레이아웃

**이게 뭐야?**
화면이 좁아지거나 넓어졌을 때 깨지지 않고 자연스럽게 변하는 능력. Flutter Web은 모바일 사파리부터 4K 모니터까지 한 번에 노출된다.

**왜 중요해?**
"PC에서는 멀쩡한데 폰에서 글자가 잘려요"는 사용자가 가장 빨리 알아채는 버그.

**현재 상태**
- `MediaQuery` 사용: **3회만**. [portfolio_screen.dart:47](frontend/lib/screens/portfolio_screen.dart)의 `MediaQuery.of(context).size.height * 0.5` 정도.
- `LayoutBuilder` 사용: **2회** ([portfolio_screen.dart:530](frontend/lib/screens/portfolio_screen.dart) WeightChart, ATR Stop bar).
- **반응형 분기 코드(데스크톱/태블릿/모바일) 사실상 없음.** 이는 의도적일 수도 있지만, 데스크톱에서 좌측 Drawer + 메인 영역으로 펼치는 일반적인 패턴(`NavigationRail` / `NavigationDrawer` 자동 분기)이 미적용.
- [portfolio_screen.dart:355-372](frontend/lib/screens/portfolio_screen.dart) Summary Card의 `Row(children: 3 Expanded)` 구조 — 좁은 폰에서 "총 투자금액"이 ₩X.X억 / "현재 평가금액" 등이 두 줄로 줄바꿈 시 카드 높이 점프.
- `Wrap`/`Flexible`/`AspectRatio` 활용은 1~2회 수준 — overflow 위험 신호.
- 큰 가이드 화면들은 그냥 `ListView` + `Padding(16)` 조합 — 데스크톱에서는 가운데 영역만 쓰고 양쪽이 비어 보임 (max-width 제약 부재).
- TabBar(`isScrollable: true`)는 OK ([screening_tabs_screen.dart:21](frontend/lib/screens/screening_tabs_screen.dart)).

**평점: 중 (B-)**
좁은 모바일 화면이 가장 위험. 데스크톱/태블릿은 "그냥 늘어나는" 정도로 못 박힘.

**개선 제안**
1. 화면 폭 기반 분기 헬퍼 (`Breakpoint.isCompact / .isMedium / .isExpanded`) 도입. Material 3 가이드의 600/840/1200 dp 기준 권장.
2. 콘텐츠 영역에 `ConstrainedBox(maxWidth: 1024)` + `Center` 적용 (특히 가이드 스크린).
3. Summary Card 같은 좁은 영역 Row를 `Wrap(spacing, runSpacing)`로 전환.
4. 모바일/태블릿/데스크톱 각 1번씩 클릭해 보면서 발견되는 overflow 항목을 PR로 정리.

---

### 8. 접근성 (a11y)

**이게 뭐야?**
시각장애·색각이상·키보드 사용자도 쓸 수 있게 만드는 것. 스크린리더 라벨, 색 대비, 포커스 이동 등을 챙긴다.

**왜 중요해?**
한국 기준으로도 공공기관/금융 앱은 WCAG 2.1 AA가 사실상 표준. 일반 앱이라도 노년/저시력 사용자 비율을 무시할 수 없다.

**현재 상태**
- **`Semantics` 위젯 사용 0회**.
- 아이콘 버튼은 `IconButton(tooltip: '메뉴 열기')`처럼 일부만 tooltip이 달림 ([main.dart:218](frontend/lib/main.dart)).
- 색만으로 의미를 전달하는 케이스 다수: 빨간 = 매도, 녹색 = 매수, 주황 = 위험 — 색각이상자에게 정보가 사라진다. 아이콘이 함께 들어 있어 부분적으로는 보완되지만 원칙적으로 미흡.
- 클릭 영역이 작은 케이스: [screening_screen.dart:130](frontend/lib/screens/screening_screen.dart)의 `IconButton(iconSize: 20, padding: EdgeInsets.zero, constraints: const BoxConstraints())` — 터치 타겟 44px 미만. 모바일 a11y 위반.
- `GestureDetector` 다수 사용([screening_screen.dart:198](frontend/lib/screens/screening_screen.dart) 등) — semantic role이 비어 있어 스크린리더가 "그냥 박스"로 인식.
- `excludeFromSemantics`/`MergeSemantics` 미사용.
- 키보드 네비게이션: Material 위젯의 기본 포커스만 의존, 커스텀 GestureDetector 영역은 키보드로 도달 불가.

**평점: 하 (C-)**
가장 약한 영역. 공공·금융 출시 시 즉시 결격 사유.

**개선 제안**
1. 모든 정보성 카드에 `Semantics(label: '...')` 추가 (특히 SPY 골든크로스 배너, BTC 시그널 카드).
2. 색 + 아이콘 + 텍스트 = 3중 인코딩 강제(현재 일부만 적용).
3. `GestureDetector`를 `InkWell`/`OutlinedButton`/`FilledButton`으로 대체 (기본 포커스/스플래시/세만틱이 따라온다).
4. 터치 타겟 최소 48×48 dp 보장.
5. Flutter DevTools Accessibility tab으로 1회 점검 후 주요 누락 PR 정리.

---

### 9. 국제화 (i18n)

**이게 뭐야?**
앱 텍스트를 한국어/영어/일본어 등으로 갈아끼울 수 있게 만드는 것. `intl` 패키지 + `MaterialApp.localizationsDelegates`로 처리.

**왜 중요해?**
한 번이라도 해외 출시/B2B 협업이 들어오면 "코드 안에 한국어 박혀 있어요"는 즉시 결격.

**현재 상태**
- pubspec에 `intl: ^0.20.2` **선언은 돼 있음** — 그러나 `lib/` 안에서 `package:intl` 임포트 0회.
- `Localizations`/`AppLocalizations`/`S.of(context)` 사용 0회.
- `MaterialApp`에 `localizationsDelegates` / `supportedLocales` 미설정 → 메뉴 등에서 영어 fallback 발생 (예: 날짜 선택기, 숫자 포맷).
- 한국어/영어가 한 코드에 혼재:
  - [main.dart:122-143](frontend/lib/main.dart) 메뉴 타이틀이 'Dashboard'(영) / '모멘텀'(한) / 'Portfolio'(영) / 'Strategy'(영) / '트렌드 분석'(한) **혼용**.
  - 백테스트 결과 카드 안에는 'CAGR' 'MDD' '샤프' 같은 영문 약어가 자연스럽게 섞임 — 이건 OK.
- 통화/숫자 포맷이 손코딩: [holding.dart](frontend/lib/models/holding.dart) 없음, [portfolio_data.dart:80](frontend/lib/models/portfolio_data.dart) `formatPrice`에서 `RegExp(r'(\d)(?=(\d{3})+$)')`로 수동 콤마 — `intl.NumberFormat`을 쓰면 한 줄.
- 날짜 포맷: [trend_reversal_screen.dart:60](frontend/lib/screens/trend_reversal_screen.dart) `data.runDate.substring(0, 10)` 식 손가공.

**평점: 하 (C)**
도구는 들여놨으면서 안 쓰는 상태. 한국어/영어 혼재가 사용자 입장에서 이상해 보이기 시작.

**개선 제안**
1. `MaterialApp`에 `localizationsDelegates` 추가 + `supportedLocales: [Locale('ko'), Locale('en')]`.
2. ARB 기반 `intl_translation`(또는 `slang` 패키지) 도입. 우선 한국어만 ARB로 모은 뒤 영어를 부분 추가.
3. 메뉴 타이틀 통일: 모두 한국어 또는 모두 영어로. 현재의 혼용은 디자인 가이드 부재 신호.
4. `NumberFormat.currency(locale: 'ko_KR', symbol: '₩', decimalDigits: 0)` / `'en_US'` 로 통화 포맷을 한 함수로.
5. `DateFormat.yMd(locale)` 도입.

---

### 10. 테스트

**이게 뭐야?**
코드 변경 시 자동으로 "예전에 잘 돌던 것이 안 깨지는지" 확인하는 안전망.

**왜 중요해?**
테스트가 없으면 작은 수정에도 회귀가 누적되어, 결국 누구도 손대기 무서운 코드가 된다.

**현재 상태**
- 파일 수: 7개 테스트 파일 / 57 dart 파일 = **테스트 비율 ~12%**. 모델 테스트가 두텁고, 위젯 테스트가 4개.
- 모델 테스트가 매우 잘 짜여 있음:
  - [test/portfolio_model_test.dart](frontend/test/portfolio_model_test.dart) (484줄, 30+ 케이스)
  - [test/shared/models_test.dart](frontend/test/shared/models_test.dart) (722줄)
  - [test/shared/portfolio_data_test.dart](frontend/test/shared/portfolio_data_test.dart) (509줄)
  → JSON 파싱 nullable/edge case 커버리지 우수. **이 코드베이스에서 가장 잘 되어 있는 부분.**
- 위젯 테스트 [test/shared/widgets_test.dart](frontend/test/shared/widgets_test.dart) (363줄) — `StockCard`/`StopLossIndicator`/`MarketStatusBanner`/`KospiStatusBanner` 4종 커버.
- 골든 테스트 [test/serverless/screenshot_test.dart](frontend/test/serverless/screenshot_test.dart) — Dashboard/Screening/Portfolio + Dark 모드 4장. CI 폰트 차이를 위한 [flutter_test_config.dart](frontend/test/flutter_test_config.dart) `_TolerantGoldenComparator`(2% 임계) 도입 — **세련된 처리**.
- **그러나 통합 테스트(`integration_test/`)는 없음**. 화면 전환/RefreshIndicator/FilePicker 흐름 검증 부재.
- 모킹 전략: `_MockScreeningNotifier extends ScreeningNotifier` 식의 직접 상속 + `overrideWith` — 깔끔하나 mockito/mocktail 도입은 안 함(필요성 낮음).
- Provider override가 [test/serverless/widget_test.dart:25](frontend/test/serverless/widget_test.dart)에서 4종 강제 — 좋은 패턴.
- 테스트 안 되는 부분: 거대 화면(strategy_guide_screen 1132줄, crypto_strategy_guide_screen 1065줄)은 위젯 테스트 0건.

**평점: 상 (B+)**
이 코드베이스에서 가장 빛나는 영역. 다만 화면 위젯 테스트와 통합 테스트가 적다는 약점.

**개선 제안**
1. `integration_test/` 추가: 앱 시작 → Drawer 열기 → 모멘텀 화면 → 종목 카드 표시까지 1개 시나리오만 있어도 PR 안전성이 크게 오름.
2. 거대 화면을 1번 항목 제안대로 분할한 뒤, 각 sub-widget에 위젯 테스트 한두 개 추가.
3. 골든 테스트를 좁은/넓은 화면 두 종으로 늘려 반응형 회귀 방지.
4. CI에 `flutter test --coverage` + lcov 리포트 → PR 코멘트 자동화.

---

### 11. 번들 / 빌드 최적화

**이게 뭐야?**
사용자에게 보내는 JS/Wasm 묶음 크기와 첫 로딩 시간. Flutter Web은 기본 5–10 MB가 흔해서 신경을 안 쓰면 모바일에서 첫 진입이 5초 이상 걸린다.

**왜 중요해?**
GitHub Pages는 캐시가 동작하지만 첫 방문자는 풀 다운로드. 모바일 LTE 환경에서 이탈률이 급증한다.

**현재 상태**
- pubspec 의존성: `dio`, `flutter_riverpod`, `intl`, `shared_preferences`, `excel`, `file_picker`, `cupertino_icons` — **간결**. 비필수 패키지 거의 없음.
- 그러나 **`excel: ^4.0.6`은 무겁다.** xlsx 파싱/생성에 약 200KB+ 추가됨. 포트폴리오 업로드/다운로드 한 번에만 쓰이므로 deferred loading 후보 1순위.
- `file_picker: ^8.1.7` 마찬가지.
- `intl`은 들여놨지만 안 씀 → tree-shaking으로 빠지긴 하지만 도입 시 사용 시작.
- **deferred imports / lazy loading: 0회.** Flutter Web은 `import '...' deferred as foo;` + `await foo.loadLibrary();`를 지원.
- web 빌드 옵션: [.github/workflows/deploy-web.yml](.github/workflows/deploy-web.yml) → `_screening-deploy.yml`로 위임 (확인 필요). HTML/CanvasKit 렌더러 명시 없음 — Flutter 3.x default(자동 선택)로 동작. CanvasKit는 ~2MB, HTML은 ~0.5MB지만 폰트 렌더링 차이.
- Asset: pubspec `assets:` 섹션은 모두 주석 — 비어 있음. 이미지/폰트 자산 부담 0.
- `web/index.html`: Flutter 기본 그대로. SEO/OG 메타 없음.
- favicon 있음(`web/index.html:28`).

**평점: 중 (B-)**
의존성은 간결하나 특정 패키지(excel, file_picker)가 무거워서 Lazy 화 여지 큼.

**개선 제안**
1. `excel` + `file_picker`를 deferred import로 전환 — Portfolio 화면 진입 시에만 로드. 첫 페인트 ~300KB 절감 예상.
2. `flutter build web --wasm`(Flutter 3.22+) 시도 — Wasm 렌더러로 첫 로드/스크롤 성능 모두 개선.
3. `--source-maps` + `flutter build web --analyze-size`로 bundle 분석 1회 실시.
4. `web/index.html`에 OG/Twitter 카드 메타 + 한국어 description + theme-color 추가.

---

### 12. 에러 처리 / 사용자 피드백

**이게 뭐야?**
실패가 일어났을 때 "왜 안 되는지", "다음에 뭘 해야 하는지"를 사용자에게 보여주는 것.

**왜 중요해?**
실패 자체보다 "조용히 실패"가 더 큰 신뢰 손실을 만든다.

**현재 상태**
- `try/catch` 30곳, 그중 **`catch (_)` (변수 없는 swallow)가 25곳**. 사실상 거의 모든 catch가 silent.
- `print`/`debugPrint` 잔존: **0회** — 디버그 출력은 깨끗.
- `ScaffoldMessenger.of(context).showSnackBar` 사용 사례:
  - [portfolio_screen.dart:133, 149, 159, 172, 182](frontend/lib/screens/portfolio_screen.dart) — 업로드 성공/실패에 일관된 SnackBar.
  - [settings_screen.dart:33](frontend/lib/screens/settings_screen.dart) — 푸시 토글 실패 시 SnackBar.
  - [screening_screen.dart:175](frontend/lib/screens/screening_screen.dart) — 풀스택 모드에서 "스크리닝 실행 중..." 안내.
- 일관성: `backgroundColor: Colors.red`(실패) / `Colors.green`(성공) — 일관됨.
- 그러나 데이터 로드 실패는 거의 모든 화면에서 `Center(child: Text('오류: $e'))` 또는 빈 카드. 사용자가 **재시도할 방법이 없다.**
- [main.dart:223-247](frontend/lib/main.dart) AppBar `IgnorePointer + Opacity(0)`로 설정 버튼을 숨겨놓은 코드 — **dead UI**가 보이지 않게 가려진 채 트리에 남아 있음. 이런 잔재는 "왜 비활성?"의 신호 없이 남아 다음 개발자를 혼란시킴.

**평점: 중 (B-)**
사용자 액션(업로드/토글)에서는 양호, 데이터 로드 실패에서는 약함.

**개선 제안**
1. `catch (_) → catch (e, st) { /* 로깅 */ }`로 일괄 마이그레이션 + Sentry/Crashlytics 도입.
2. 모든 `error: (e, _) => ...` 경로에 **재시도 버튼**을 가진 공통 위젯(`ErrorRetryView`).
3. SnackBar를 글로벌 헬퍼(`showSuccess(context, msg)` / `showError(context, msg)`)로 통일.
4. [main.dart:223-247](frontend/lib/main.dart) IgnorePointer/Opacity 설정 버튼 dead-UI **삭제**. 진짜 비활성이라면 주석 + TODO만 남기고 위젯 트리에서 빼기.

---

### 13. 코드 품질

**이게 뭐야?**
네이밍, 매직 넘버, 함수/파일 길이, 중복, 주석 등 "사람이 읽고 고치기 쉬운 코드"의 기본기.

**왜 중요해?**
이게 뭉치면 결국 모든 이슈 해결 속도가 절반으로 떨어진다.

**현재 상태**
- 파일 길이 분포(상위 5개 모두 800줄+):
  - [strategy_guide_screen.dart:1132](frontend/lib/screens/strategy_guide_screen.dart)
  - [crypto_strategy_guide_screen.dart:1065](frontend/lib/screens/crypto_strategy_guide_screen.dart)
  - [portfolio_screen.dart:1035](frontend/lib/screens/portfolio_screen.dart)
  - [vix_strategy_guide_screen.dart:970](frontend/lib/screens/vix_strategy_guide_screen.dart)
  - [trend_reversal_strategy_guide_screen.dart:829](frontend/lib/screens/trend_reversal_strategy_guide_screen.dart)
  → 일반 가이드(>500줄)를 상회. 분할 필요.
- 매직 넘버: 사이즈/패딩/색 셰이드/임계값이 거의 모든 위젯에 직접 박힘. 예: [portfolio_screen.dart:483](frontend/lib/screens/portfolio_screen.dart) `_colors = [10가지 hex]`, [portfolio_screen.dart:830-844](frontend/lib/screens/portfolio_screen.dart) ATR distPct 임계 `<= 3`, `<= 7` 직접 박힘.
- 중복:
  - `_metric` 함수 [stock_card.dart:106](frontend/lib/widgets/stock_card.dart) ↔ [market_status_banner.dart:4](frontend/lib/widgets/market_status_banner.dart) — 거의 동일.
  - [btc_signal_widget.dart](frontend/lib/widgets/btc_signal_widget.dart) ↔ [eth_signal_widget.dart](frontend/lib/widgets/eth_signal_widget.dart) — 100% 복제. 클래스명·라벨만 다름.
  - 콤마 포맷 정규식 `RegExp(r'(\d)(?=(\d{3})+$)')`이 [btc_signal_widget.dart:16](frontend/lib/widgets/btc_signal_widget.dart), [eth_signal_widget.dart:18](frontend/lib/widgets/eth_signal_widget.dart), [portfolio_data.dart:83](frontend/lib/models/portfolio_data.dart) 3곳에 흩어짐.
- 데드 코드:
  - [main.dart:226-247](frontend/lib/main.dart) `IgnorePointer + Opacity(0)`로 숨겨진 설정 버튼 + Navigator.push 분기.
  - [providers/serverless_providers.dart:138](frontend/lib/providers/serverless_providers.dart) 중복 `shortSqueezeProvider`.
- 라벨 정합 깨짐:
  - [screening_screen.dart:25-28](frontend/lib/screens/screening_screen.dart) `_kStrategyParamLabel`은 'ATR×1.5 / TOP 15', 'TOP 10', 'TOP 7'을 표시.
  - 그러나 v3.3에서 모든 전략 `top_n=25`로 통일됐고 [screening_result.dart:226-229](frontend/lib/models/screening_result.dart) enum description은 'TOP25'.
  - → **UI 라벨이 실제 데이터와 다름.** 사용자는 "TOP 15"라고 보고 25개 종목을 본다.
- 주석 품질: 상단에 한국어로 "왜"를 적어둔 모듈 주석이 좋음 ([rebalance_provider.dart:43](frontend/lib/providers/rebalance_provider.dart) 격주 기준일 등). 다만 화면 단 위젯 내부 주석은 거의 없음 — 1,000줄 화면 안에서 길을 잃기 쉬움.
- 파일별 import 순서: 일관되지 않음 (dart → package → relative 컨벤션 일부만 적용).
- 네이밍은 한/영 혼용: enum value `aggressive` (영) vs label `'공격적'`(한) — UX적으로는 자연스럽지만 enum/필드 모두 한 언어로 통일하는 컨벤션 강화 필요.

**평점: 중 (C+)**
거대 화면 + 매직 넘버 + 중복 + 라벨 정합 깨짐이 누적된 상태. 위험한 단계는 아니지만 손볼 가치 큼.

**개선 제안**
1. 1,000줄 화면 분해 (1번 항목과 동일).
2. 매직 넘버를 const 상수로: `const _atrDangerThreshold = 3.0;` 같은 것을 파일 상단 또는 `models/`로.
3. 중복 위젯 통합 (BTC/ETH → `CryptoSignalCard`).
4. **라벨 정합 깨짐(TOP15/10/7) 즉시 수정** — 가장 사용자에게 영향이 큰 버그.
5. `dart fix --apply` + `dart format` CI 강제.

---

### 14. 린팅 / 정적 분석

**이게 뭐야?**
"이런 패턴은 위험하다"를 컴파일 단계에서 잡아주는 자동 검사.

**왜 중요해?**
강하게 묶을수록 PR 리뷰 시간이 줄고, 신규 인원이 잘못된 패턴을 쓸 확률이 떨어진다.

**현재 상태**
- [analysis_options.yaml](frontend/analysis_options.yaml) — **flutter_lints 기본 그대로, 추가 룰 0개**.
  ```yaml
  include: package:flutter_lints/flutter.yaml
  linter:
    rules:
      # avoid_print: false
      # prefer_single_quotes: true
  ```
- `analyzer.errors` / `analyzer.exclude` / `language.strict-casts` 미설정.
- `// ignore_for_file:` 1회만 등장 ([_portfolio_download_web.dart:1](frontend/lib/services/_portfolio_download_web.dart) `avoid_web_libraries_in_flutter`).
- `riverpod_lint`, `custom_lint`, `very_good_analysis`, `lints_dart` 같은 강화 규칙 미사용.

**평점: 하 (C)**
"기본만 켜져 있는" 상태. 잡아낼 수 있는 것을 안 잡고 있다.

**개선 제안**
1. `analysis_options.yaml`을 강화:
   ```yaml
   include: package:flutter_lints/flutter.yaml
   analyzer:
     language:
       strict-casts: true
       strict-inference: true
       strict-raw-types: true
     errors:
       missing_required_param: error
       missing_return: error
       todo: ignore
   linter:
     rules:
       - prefer_single_quotes
       - prefer_const_constructors
       - prefer_const_literals_to_create_immutables
       - require_trailing_commas
       - sort_pub_dependencies
       - unawaited_futures
       - use_super_parameters
       - avoid_dynamic_calls
   ```
2. `dev_dependencies`에 `custom_lint: ^0.x` + `riverpod_lint: ^2.x` 추가.
3. CI에 `flutter analyze` 추가 (이미 있다면 fatal-warnings 옵션 켜기).

---

### 15. 웹 특화 이슈

**이게 뭐야?**
Flutter Web만의 한계와 모범 패턴. 모바일과 다르게 SEO·텍스트 선택·라우팅·렌더러 선택이 추가 고려 사항.

**왜 중요해?**
Flutter Web의 알려진 함정에 걸리면 "사파리에서만 안 됨", "구글에서 검색이 안 됨" 등 탐지 어려운 문제가 생긴다.

**현재 상태**
- 렌더러: 명시 없음 → Flutter 3.11 default (모바일 사파리는 HTML, 데스크톱은 CanvasKit). Wasm 도입 안 됨.
- 라우팅: `Navigator.push`만 1회 사용([main.dart:229](frontend/lib/main.dart)), 그것도 dead UI 안. 메인 네비는 `setState + IndexedStack 없는 _currentScreen` 패턴 → **URL이 바뀌지 않는다.** 즉:
  - 사용자가 특정 화면을 북마크할 수 없다.
  - 브라우저 뒤로 가기는 앱을 닫음.
  - 새로고침하면 항상 Dashboard로 돌아간다.
- SEO:
  - [web/index.html:18](frontend/web/index.html) `<meta name="description" content="A new Flutter project.">` — Flutter 기본값 그대로. **검색 엔진에 노출 시 부정적.**
  - `<title>momentum_app</title>` — 앱 이름 그대로. 한국어 타이틀 미적용.
  - OG 태그/Twitter 카드 없음.
  - manifest.json 확인 필요 (기본일 가능성 높음).
- 텍스트 선택: Flutter Web의 디폴트로 `SelectableText`를 의도적으로 쓴 흔적 없음 → 카피가 안 되는 텍스트가 많을 것.
- 파일 다운로드: [_portfolio_download_web.dart](frontend/lib/services/_portfolio_download_web.dart) `dart:html` Blob URL 패턴 — 적절. 다만 `dart:html`은 deprecated 경로(Flutter 3.x), `package:web` + `dart:js_interop`로 마이그레이션 권장.
- PWA: `web/manifest.json` 존재하지만 favicon만 등록. install/오프라인 미지원.
- base href: GitHub Pages에서 `/BoogieWonderland/` 서브경로 ([deploy-web.yml:14](.github/workflows/deploy-web.yml)) — 적절.
- Flutter 텍스트 텍스트 선택/접근성 한계: 많은 GestureDetector가 키보드/포커스 미지원 (8번 항목과 중복).

**평점: 하 (C-)**
URL 라우팅 부재가 가장 큰 문제. 웹앱이라기보다 "웹에서 도는 모바일 앱" 수준에 머무름.

**개선 제안**
1. **`go_router`(또는 `auto_route`) 도입.** `/dashboard`, `/screening/momentum`, `/portfolio` 같은 URL을 도입하면 북마크/공유가 가능해지고 새로고침 시 화면 보존 가능.
2. SEO 메타 정비: 한국어 타이틀, description, OG 카드, JSON-LD `WebApplication` 스키마 추가.
3. `dart:html` → `package:web` 마이그레이션 (Flutter 3.22+).
4. `flutter build web --wasm` 도입 검토 (모든 CanvasKit 사용처에 호환).
5. `SelectableText`로 종목명/티커 등 사용자가 카피하고 싶을 만한 영역 변경.
6. 간단한 PWA 등록(install prompt) — 사용자가 홈 화면에 추가 가능하게.

---

## 우선순위 액션 아이템 Top 10

영향도(High/Medium/Low) = 사용자/유지보수에 미치는 영향
공수 = 예상 작업량 (S=반나절, M=1–2일, L=1주+)
리스크 = 이 일을 할 때 다른 곳에 미칠 영향(Low가 좋다)

| # | 액션 | 영향도 | 공수 | 리스크 | 근거(섹션) |
|---|---|---|---|---|---|
| 1 | **TOP 15/10/7 잘못된 라벨을 TOP 25로 정정** ([screening_screen.dart:25-28](frontend/lib/screens/screening_screen.dart)) | High | S | Low | §13 |
| 2 | **중복 `shortSqueezeProvider` 제거** ([serverless_providers.dart:138](frontend/lib/providers/serverless_providers.dart) 삭제) | High | S | Low | §2, §13 |
| 3 | **`go_router` 도입 + URL 라우팅** (북마크·뒤로가기·새로고침 동작) | High | M | Medium | §15 |
| 4 | **`analysis_options.yaml` 강화** + `riverpod_lint` 추가 → 자동으로 향후 안티패턴 차단 | High | S | Low | §14 |
| 5 | **`catch (_)` → `catch (e, st)` + 원격 로깅(Sentry)** + 공통 ErrorRetryView 위젯 | High | M | Low | §4, §12 |
| 6 | **`freezed` + `json_serializable`** 도입, 14개 모델 중 핵심 6개 마이그레이션 | High | M | Low | §5 |
| 7 | **거대 화면 분할** (1,000줄+ 4개 화면을 sub-widget 파일로 추출) | Medium | L | Medium | §1, §13 |
| 8 | **디자인 토큰 시스템** (`AppColors`/`AppSpacing`/`AppTypography`) + 가장 많이 쓰는 색 10개부터 토큰화 | Medium | M | Low | §6 |
| 9 | **i18n 토대 구축** (`localizationsDelegates` + ARB 한국어 시작 + `NumberFormat`/`DateFormat` 일괄 적용) | Medium | M | Low | §9 |
| 10 | **번들 다이어트** (`excel`/`file_picker` deferred import + `flutter build web --wasm` 실험) | Medium | M | Medium | §11 |

**보너스(차순위)**: 접근성 Semantics 패스 1회(§8) · `ListView.builder` 마이그레이션(§3) · IndexedStack 도입(§3) · IgnorePointer dead UI 삭제(§12).

---

## 프론트엔드 지식이 없는 사용자가 이 보고서를 보고 가장 먼저 무엇을 해야 하나?

**한 가지만 시키시려면, 위 표의 1번과 2번을 같은 PR로 묶어 처리하세요.**
"라벨이 실제 데이터와 다른 버그 수정"은 사용자가 즉시 영향을 받는 신뢰성 문제이고, "중복 provider 제거"는 다음 누가 코드를 만져도 안 헷갈리도록 해두는 위생 작업입니다. 둘 다 5분~30분짜리 변경이고 회귀 위험이 거의 없습니다. 이 두 개만 닫혀도 "코드 베이스의 거짓말"이 사라져, 이후 어떤 리팩터링을 해도 검증 기준이 깨끗해집니다. 그다음으로는 4번(린트 강화) → 5번(에러 핸들링/원격 로깅) → 3번(URL 라우팅) 순서로, "기반을 다지고 → 관측 가능성을 확보하고 → 사용자 경험을 끌어올리는" 흐름을 권장합니다. 거대 화면 분할(7번)이나 디자인 토큰화(8번)는 매력적이지만 한 번에 손대면 PR이 비대해지므로, 위 우선순위를 닫은 뒤 1주짜리 작업으로 별도 슬롯을 잡는 편이 안전합니다.

---

## 부록: 코드 메트릭 한눈에

```
파일 수
  lib/.dart                : 50
  test/.dart               : 7
  total                    : 57

파일 길이 상위 5
  strategy_guide_screen.dart           : 1132
  crypto_strategy_guide_screen.dart    : 1065
  portfolio_screen.dart                : 1035
  vix_strategy_guide_screen.dart       :  970
  trend_reversal_strategy_guide_screen :  829

패턴 카운트
  Colors.* 직접 참조             : 318
  Theme.of(context)              : 116
  withOpacity/withValues/Alpha   :  93
  ref.watch                      :  37
  ref.read                       :  12
  as Map<String, dynamic> 캐스트 :  35
  try { ... }                    :  30
  catch (_)                      :  25  ← swallow
  ListView(  (eager)             :  17
  ListView.builder               :   1
  ! 강제 언래핑                  : ~20
  Semantics                      :   0
  print/debugPrint               :   0
  freezed/json_serializable      :   0
  Localizations/AppLocalizations :   0
  deferred import                :   0

의존성
  flutter_riverpod  ^3.3.1
  dio               ^5.9.2
  intl              ^0.20.2  (선언만 / 미사용)
  shared_preferences ^2.5.4
  excel             ^4.0.6   (무거움 — deferred 후보)
  file_picker       ^8.1.7   (무거움 — deferred 후보)
  flutter_lints     ^6.0.0   (룰 강화 미적용)
```

```
배포
  GitHub Pages /BoogieWonderland/  via .github/workflows/deploy-web.yml
  base_href: '/BoogieWonderland/'
  렌더러: Flutter default (CanvasKit/HTML 자동)
  라우팅: setState 기반 (URL 미반영)
```

---

*작성: Claude (시니어 프론트엔드 검토 페르소나) — 2026-05-01*
*분석 대상 커밋: `db0b540` 시점의 `frontend/` 트리*
*코드 수정 없음 — 분석/보고서만.*
