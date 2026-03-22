import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:momentum_app/main.dart';
import 'package:momentum_app/screens/screening_screen.dart';
import 'package:momentum_app/screens/portfolio_screen.dart';
import 'package:momentum_app/screens/dashboard_screen.dart';
import 'package:momentum_app/providers/screening_provider.dart';
import 'package:momentum_app/providers/market_provider.dart';
import 'package:momentum_app/providers/portfolio_provider.dart';
import 'package:momentum_app/models/screening_result.dart';
import 'package:momentum_app/models/holding.dart';

// 목 데이터
final _mockMarketStatus = MarketStatus(
  spyPrice: 523.40,
  isGoldenCross: true,
  ma50: 510.20,
  ma200: 498.50,
  gapPct: 2.35,
  nextRebalance: '2026-04-04',
);

final _mockScreeningRun = ScreeningRun(
  runId: 1,
  runDate: '2026-03-21',
  marketStatus: _mockMarketStatus,
  totalScreened: 46,
  totalPassed: 8,
  results: [
    ScreeningResult(rank: 1, ticker: 'NVDA', market: 'US', sector: 'Technology', score: 0.921, weightPct: 18.5, price: 142.50, adx: 38.2, rsi: 62.4, ret3m: 0.234, stopPrice: 128.75, stopDistPct: -9.6, atr: 5.50),
    ScreeningResult(rank: 2, ticker: 'AVGO', market: 'US', sector: 'Technology', score: 0.874, weightPct: 15.2, price: 198.30, adx: 35.1, rsi: 58.7, ret3m: 0.185, stopPrice: 182.40, stopDistPct: -8.0, atr: 6.35),
    ScreeningResult(rank: 3, ticker: 'META', market: 'US', sector: 'Communication', score: 0.831, weightPct: 13.8, price: 512.80, adx: 32.5, rsi: 61.2, ret3m: 0.156, stopPrice: 478.90, stopDistPct: -6.6, atr: 13.56),
    ScreeningResult(rank: 4, ticker: 'LLY', market: 'US', sector: 'Health Care', score: 0.795, weightPct: 11.4, price: 845.20, adx: 30.8, rsi: 55.3, ret3m: 0.128, stopPrice: 802.10, stopDistPct: -5.1, atr: 17.24),
    ScreeningResult(rank: 5, ticker: 'MSFT', market: 'US', sector: 'Technology', score: 0.762, weightPct: 10.1, price: 425.60, adx: 28.4, rsi: 54.8, ret3m: 0.098, stopPrice: 405.30, stopDistPct: -4.8, atr: 8.12),
    ScreeningResult(rank: 6, ticker: 'GS', market: 'US', sector: 'Financials', score: 0.718, weightPct: 8.7, price: 562.40, adx: 27.1, rsi: 53.2, ret3m: 0.076, stopPrice: 538.80, stopDistPct: -4.2, atr: 9.44),
    ScreeningResult(rank: 7, ticker: '005930.KS', market: 'KR', sector: 'Technology', score: 0.685, weightPct: 7.5, price: 72500, adx: 26.3, rsi: 52.1, ret3m: 0.065, stopPrice: 69200, stopDistPct: -4.6, atr: 1320),
    ScreeningResult(rank: 8, ticker: 'CAT', market: 'US', sector: 'Industrials', score: 0.654, weightPct: 6.8, price: 378.90, adx: 25.7, rsi: 51.4, ret3m: 0.054, stopPrice: 361.20, stopDistPct: -4.7, atr: 7.08),
  ],
);

final _mockHoldings = [
  Holding(id: 1, ticker: 'NVDA', entryPrice: 130.50, entryDate: '2026-03-10', peakPrice: 145.20, isActive: true),
  Holding(id: 2, ticker: 'META', entryPrice: 495.00, entryDate: '2026-03-12', peakPrice: 515.80, isActive: true),
  Holding(id: 3, ticker: 'LLY', entryPrice: 820.00, entryDate: '2026-03-14', peakPrice: 848.50, isActive: true),
];

class _MockScreeningNotifier extends ScreeningNotifier {
  @override
  Future<ScreeningRun?> build() async => _mockScreeningRun;
}

class _MockHoldingsNotifier extends HoldingsNotifier {
  @override
  Future<List<Holding>> build() async => _mockHoldings;
}

Widget _wrapPhone(Widget child) {
  return ProviderScope(
    overrides: [
      marketStatusProvider.overrideWith((ref) async => _mockMarketStatus),
      screeningProvider.overrideWith(() => _MockScreeningNotifier()),
      holdingsProvider.overrideWith(() => _MockHoldingsNotifier()),
    ],
    child: MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: Colors.blue,
        useMaterial3: true,
        brightness: Brightness.light,
      ),
      home: MediaQuery(
        data: const MediaQueryData(size: Size(390, 844)), // iPhone 14 size
        child: child,
      ),
    ),
  );
}

void main() {
  testWidgets('Screenshot: Dashboard', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(390 * 3, 844 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(_wrapPhone(
      const Scaffold(
        appBar: _FakeAppBar(title: 'Dashboard'),
        body: DashboardScreen(),
        bottomNavigationBar: _FakeNavBar(selected: 0),
      ),
    ));
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/dashboard.png'),
    );
  });

  testWidgets('Screenshot: Screening', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(390 * 3, 844 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(_wrapPhone(
      const Scaffold(
        appBar: _FakeAppBar(title: 'Screening'),
        body: ScreeningScreen(),
        bottomNavigationBar: _FakeNavBar(selected: 1),
      ),
    ));
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/screening.png'),
    );
  });

  testWidgets('Screenshot: Portfolio', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(390 * 3, 844 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(_wrapPhone(
      const Scaffold(
        appBar: _FakeAppBar(title: 'Portfolio'),
        body: PortfolioScreen(),
        bottomNavigationBar: _FakeNavBar(selected: 2),
      ),
    ));
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/portfolio.png'),
    );
  });

  testWidgets('Screenshot: Dashboard Dark', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(390 * 3, 844 * 3);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          marketStatusProvider.overrideWith((ref) async => _mockMarketStatus),
          screeningProvider.overrideWith(() => _MockScreeningNotifier()),
          holdingsProvider.overrideWith(() => _MockHoldingsNotifier()),
        ],
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: ThemeData(
            colorSchemeSeed: Colors.blue,
            useMaterial3: true,
            brightness: Brightness.dark,
          ),
          home: const MediaQuery(
            data: MediaQueryData(size: Size(390, 844)),
            child: Scaffold(
              appBar: _FakeAppBar(title: 'Dashboard'),
              body: DashboardScreen(),
              bottomNavigationBar: _FakeNavBar(selected: 0),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/dashboard_dark.png'),
    );
  });
}

class _FakeAppBar extends StatelessWidget implements PreferredSizeWidget {
  final String title;
  const _FakeAppBar({required this.title});

  @override
  Widget build(BuildContext context) {
    return AppBar(
      title: Text(title),
      actions: [
        IconButton(icon: const Icon(Icons.settings), onPressed: () {}),
      ],
    );
  }

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);
}

class _FakeNavBar extends StatelessWidget {
  final int selected;
  const _FakeNavBar({required this.selected});

  @override
  Widget build(BuildContext context) {
    return NavigationBar(
      selectedIndex: selected,
      onDestinationSelected: (_) {},
      destinations: const [
        NavigationDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: 'Dashboard'),
        NavigationDestination(icon: Icon(Icons.search_outlined), selectedIcon: Icon(Icons.search), label: 'Screening'),
        NavigationDestination(icon: Icon(Icons.account_balance_wallet_outlined), selectedIcon: Icon(Icons.account_balance_wallet), label: 'Portfolio'),
      ],
    );
  }
}
