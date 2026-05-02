import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'config/deploy_env.dart';
import 'models/screening_result.dart';
import 'providers/screening_provider.dart';
import 'providers/portfolio_provider.dart';
import 'providers/market_provider.dart';
import 'providers/serverless_providers.dart';
import 'services/api_client.dart';
import 'screens/dashboard_screen.dart';
import 'screens/portfolio_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/screening_tabs_screen.dart';
import 'screens/strategy_guide_tabs_screen.dart';
import 'screens/market_cap_screen.dart';

enum _DrawerDestination {
  dashboard,
  screening,
  screeningMomentum,
  screeningTrendReversal,
  screeningShortSqueeze,
  screeningVix,
  portfolio,
  strategy,
  marketCap,
}

void main() {
  if (DeployConfig.useStaticData) {
    runApp(
      ProviderScope(
        overrides: [
          screeningProvider.overrideWith(() => ServerlessScreeningNotifier()),
          holdingsProvider.overrideWith(() => ServerlessHoldingsNotifier()),
          marketStatusProvider.overrideWith(serverlessMarketStatus),
          stopCheckProvider.overrideWith(serverlessStopCheck),
        ],
        child: const MomentumApp(),
      ),
    );
  } else {
    runApp(
      ProviderScope(
        overrides: [
          // fullstack 모드: 백엔드 API에서 전략 데이터 로드
          strategyDataProvider.overrideWith((ref) async {
            try {
              final data = await ApiClient().getLatestScreening();
              return StrategyScreeningData.fromJson(data);
            } catch (e) {
              debugPrint('strategyDataProvider(fullstack): latest screening fetch failed: $e');
              return null;
            }
          }),
          historyScreeningProvider.overrideWith((ref) async {
            final date = ref.watch(selectedHistoryDateProvider);
            try {
              final Map<String, dynamic> data;
              if (date == null) {
                data = await ApiClient().getLatestScreening();
              } else {
                data = await ApiClient().getScreeningByDate(date);
              }
              return StrategyScreeningData.fromJson(data);
            } catch (e) {
              debugPrint('historyScreeningProvider(fullstack, date=$date): fetch failed: $e');
              return null;
            }
          }),
          historyDatesProvider.overrideWith((ref) async {
            try {
              return await ApiClient().getScreeningHistoryDates(days: 30);
            } catch (e) {
              debugPrint('historyDatesProvider(fullstack): fetch failed: $e');
              return [];
            }
          }),
        ],
        child: const MomentumApp(),
      ),
    );
  }
}

class MomentumApp extends StatelessWidget {
  const MomentumApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Stock Screener',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: Colors.blue,
        useMaterial3: true,
        brightness: Brightness.light,
      ),
      darkTheme: ThemeData(
        colorSchemeSeed: Colors.blue,
        useMaterial3: true,
        brightness: Brightness.dark,
      ),
      themeMode: ThemeMode.system,
      home: const MainNavigation(),
    );
  }
}

class MainNavigation extends StatefulWidget {
  const MainNavigation({super.key});

  @override
  State<MainNavigation> createState() => _MainNavigationState();
}

class _MainNavigationState extends State<MainNavigation> {
  _DrawerDestination _currentDestination = _DrawerDestination.dashboard;
  final _scaffoldKey = GlobalKey<ScaffoldState>();

  void _selectMenu(_DrawerDestination destination) {
    setState(() => _currentDestination = destination);
    _scaffoldKey.currentState?.closeDrawer();
  }

  String get _title {
    switch (_currentDestination) {
      case _DrawerDestination.dashboard:
        return 'Dashboard';
      case _DrawerDestination.screening:
      case _DrawerDestination.screeningMomentum:
        return '모멘텀';
      case _DrawerDestination.screeningTrendReversal:
        return '추세 전환';
      case _DrawerDestination.screeningShortSqueeze:
        return '숏 스퀴즈';
      case _DrawerDestination.screeningVix:
        return 'VIX 매매';
      case _DrawerDestination.portfolio:
        return 'Portfolio';
      case _DrawerDestination.strategy:
        return 'Strategy';
      case _DrawerDestination.marketCap:
        return '트렌드 분석';
    }
  }

  Widget get _currentScreen {
    switch (_currentDestination) {
      case _DrawerDestination.dashboard:
        return const DashboardScreen();
      case _DrawerDestination.screening:
      case _DrawerDestination.screeningMomentum:
        return const ScreeningTabsScreen.withIndex(
          key: ValueKey('screening-momentum'),
          initialIndex: 0,
        );
      case _DrawerDestination.screeningTrendReversal:
        return const ScreeningTabsScreen.withIndex(
          key: ValueKey('screening-trend-reversal'),
          initialIndex: 1,
        );
      case _DrawerDestination.screeningShortSqueeze:
        return const ScreeningTabsScreen.withIndex(
          key: ValueKey('screening-short-squeeze'),
          initialIndex: 2,
        );
      case _DrawerDestination.screeningVix:
        return const ScreeningTabsScreen.withIndex(
          key: ValueKey('screening-vix'),
          initialIndex: 3,
        );
      case _DrawerDestination.portfolio:
        return const PortfolioScreen();
      case _DrawerDestination.strategy:
        return const StrategyGuideTabsScreen();
      case _DrawerDestination.marketCap:
        return const MarketCapScreen();
    }
  }

  Widget _menuTile({
    required _DrawerDestination destination,
    required String label,
    required IconData icon,
    IconData? selectedIcon,
    String? subtitle,
    bool isIndented = false,
  }) {
    final colorScheme = Theme.of(context).colorScheme;
    final isSelected = _currentDestination == destination;
    return ListTile(
      contentPadding: EdgeInsets.only(left: isIndented ? 36 : 16, right: 16),
      leading: Icon(
        isSelected ? (selectedIcon ?? icon) : icon,
        color: isSelected ? colorScheme.primary : null,
      ),
      title: Text(
        label,
        style: TextStyle(
          color: isSelected ? colorScheme.primary : null,
          fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
        ),
      ),
      subtitle: subtitle == null
          ? null
          : Text(subtitle, style: const TextStyle(fontSize: 11)),
      selected: isSelected,
      onTap: () => _selectMenu(destination),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      key: _scaffoldKey,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.menu),
          tooltip: '메뉴 열기',
          onPressed: () => _scaffoldKey.currentState?.openDrawer(),
        ),
        title: Text(_title),
        actions: [
          IgnorePointer(
            child: Opacity(
              opacity: 0,
              child: IconButton(
                icon: const Icon(Icons.settings),
                onPressed: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (ctx) => Scaffold(
                        appBar: AppBar(
                          leading: IconButton(
                            icon: const Icon(Icons.arrow_back_ios),
                            onPressed: () => Navigator.pop(ctx),
                          ),
                          title: const Text('설정'),
                        ),
                        body: const SettingsScreen(),
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
        ],
      ),
      drawer: Drawer(
        child: ListView(
          padding: EdgeInsets.zero,
          children: [
            DrawerHeader(
              decoration: BoxDecoration(color: colorScheme.primary),
              child: Text(
                'Stock Screener',
                style: TextStyle(
                  color: colorScheme.onPrimary,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
            _menuTile(
              destination: _DrawerDestination.dashboard,
              label: 'Dashboard',
              icon: Icons.dashboard_outlined,
              selectedIcon: Icons.dashboard,
            ),
            _menuTile(
              destination: _DrawerDestination.screening,
              label: 'Screening',
              icon: Icons.search_outlined,
              selectedIcon: Icons.search,
            ),
            _menuTile(
              destination: _DrawerDestination.screeningMomentum,
              label: '모멘텀',
              icon: Icons.trending_up_outlined,
              selectedIcon: Icons.trending_up,
              isIndented: true,
            ),
            _menuTile(
              destination: _DrawerDestination.screeningTrendReversal,
              label: '추세 전환',
              icon: Icons.swap_vert_outlined,
              selectedIcon: Icons.swap_vert,
              isIndented: true,
            ),
            _menuTile(
              destination: _DrawerDestination.screeningShortSqueeze,
              label: '숏 스퀴즈',
              icon: Icons.compress_outlined,
              selectedIcon: Icons.compress,
              isIndented: true,
            ),
            _menuTile(
              destination: _DrawerDestination.screeningVix,
              label: 'VIX 매매',
              icon: Icons.show_chart_outlined,
              selectedIcon: Icons.show_chart,
              isIndented: true,
            ),
            _menuTile(
              destination: _DrawerDestination.portfolio,
              label: 'Portfolio',
              icon: Icons.account_balance_wallet_outlined,
              selectedIcon: Icons.account_balance_wallet,
            ),
            _menuTile(
              destination: _DrawerDestination.strategy,
              label: 'Strategy',
              icon: Icons.auto_stories_outlined,
              selectedIcon: Icons.auto_stories,
            ),
            const Divider(),
            _menuTile(
              destination: _DrawerDestination.marketCap,
              label: '트렌드 분석',
              icon: Icons.bar_chart_outlined,
              selectedIcon: Icons.bar_chart,
              subtitle: '시총 Top 20 모니터링',
            ),
          ],
        ),
      ),
      body: _currentScreen,
    );
  }
}
