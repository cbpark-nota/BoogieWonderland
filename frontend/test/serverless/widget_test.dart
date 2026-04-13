// widget_test.dart
// 테스트 대상: MomentumApp 전체 앱 렌더링
//
// 검증 내용:
//   - 앱 초기 렌더링 시 Dashboard 화면과 Drawer 메뉴 아이콘이 표시되는지
//   - Settings 아이콘이 AppBar에 표시되는지
//
// 주의: 이 앱은 BottomNavigationBar가 아닌 Drawer 기반 네비게이션을 사용합니다.
//   'Screening', 'Portfolio' 레이블은 Drawer 안에 있으며,
//   Drawer를 열기 전에는 위젯 트리에서 찾을 수 없습니다.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:momentum_app/main.dart';
import 'package:momentum_app/providers/screening_provider.dart';
import 'package:momentum_app/providers/market_provider.dart';
import 'package:momentum_app/providers/rebalance_provider.dart';
import 'package:momentum_app/providers/serverless_providers.dart';
import 'package:momentum_app/models/screening_result.dart';
import 'package:momentum_app/models/portfolio_data.dart';

/// DEPLOY_ENV 기본값이 serverless로 변경됨에 따라
/// IndexedStack이 모든 화면을 pre-build할 때 네트워크 호출을 막기 위한 공통 overrides.
List<dynamic> _serverlessOverrides() => [
      portfolioDataProvider.overrideWith((ref) async => PortfolioData.fromJson({})),
      historyDatesProvider.overrideWith((ref) async => []),
      strategyDataProvider.overrideWith((ref) async => null),
      rebalanceSignalProvider.overrideWith(
          (ref) async => const RebalanceSignal(screeningTickers: {})),
    ];

void main() {
  // 입력: Mock provider로 앱 렌더링
  // 출력: AppBar 타이틀 'Dashboard'와 Drawer 메뉴 아이콘(햄버거) 표시
  testWidgets('App renders with drawer navigation', (WidgetTester tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          marketStatusProvider.overrideWith((ref) async => null),
          screeningProvider.overrideWith(() => _MockScreeningNotifier()),
          ..._serverlessOverrides(),
        ],
        child: const MomentumApp(),
      ),
    );
    await tester.pump();

    // AppBar 타이틀과 Drawer 메뉴 아이콘이 표시된다
    expect(find.text('Dashboard'), findsOneWidget);
    expect(find.byIcon(Icons.menu), findsOneWidget);
  });

  // 입력: Mock provider로 앱 렌더링
  // 출력: Settings 아이콘이 AppBar에 표시됨
  testWidgets('Settings icon is present', (WidgetTester tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          marketStatusProvider.overrideWith((ref) async => null),
          screeningProvider.overrideWith(() => _MockScreeningNotifier()),
          ..._serverlessOverrides(),
        ],
        child: const MomentumApp(),
      ),
    );
    await tester.pump();

    expect(find.byIcon(Icons.settings), findsOneWidget);
  });
}

class _MockScreeningNotifier extends ScreeningNotifier {
  @override
  Future<ScreeningRun?> build() async => null;
}
