import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'config/app_config.dart';
import 'providers/screening_provider.dart';
import 'providers/portfolio_provider.dart';
import 'providers/market_provider.dart';
import 'providers/serverless_providers.dart';
import 'screens/dashboard_screen.dart';
import 'screens/screening_screen.dart';
import 'screens/portfolio_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/strategy_guide_screen.dart';
import 'screens/market_cap_screen.dart';

void main() {
  if (AppConfig.isServerless) {
    runApp(ProviderScope(
      overrides: [
        screeningProvider.overrideWith(() => ServerlessScreeningNotifier()),
        holdingsProvider.overrideWith(() => ServerlessHoldingsNotifier()),
        marketStatusProvider.overrideWith(serverlessMarketStatus),
        stopCheckProvider.overrideWith(serverlessStopCheck),
      ],
      child: const MomentumApp(),
    ));
  } else {
    runApp(const ProviderScope(child: MomentumApp()));
  }
}

class MomentumApp extends StatelessWidget {
  const MomentumApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Momentum Screener',
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
  int _currentIndex = 0;
  final _scaffoldKey = GlobalKey<ScaffoldState>();

  final _screens = const [
    DashboardScreen(),
    ScreeningScreen(),
    PortfolioScreen(),
  ];

  static const _menuItems = [
    (label: 'Dashboard', icon: Icons.dashboard_outlined, selectedIcon: Icons.dashboard),
    (label: 'Screening', icon: Icons.search_outlined, selectedIcon: Icons.search),
    (label: 'Portfolio', icon: Icons.account_balance_wallet_outlined, selectedIcon: Icons.account_balance_wallet),
  ];

  void _selectMenu(int index) {
    setState(() => _currentIndex = index);
    _scaffoldKey.currentState?.closeDrawer();
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
        title: Text(_menuItems[_currentIndex].label),
        actions: [
          IconButton(
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
        ],
      ),
      drawer: Drawer(
        child: ListView(
          padding: EdgeInsets.zero,
          children: [
            DrawerHeader(
              decoration: BoxDecoration(color: colorScheme.primary),
              child: Text(
                'Momentum Screener',
                style: TextStyle(
                  color: colorScheme.onPrimary,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
            ..._menuItems.asMap().entries.map((entry) {
              final i = entry.key;
              final item = entry.value;
              final isSelected = _currentIndex == i;
              return ListTile(
                leading: Icon(
                  isSelected ? item.selectedIcon : item.icon,
                  color: isSelected ? colorScheme.primary : null,
                ),
                title: Text(
                  item.label,
                  style: TextStyle(
                    color: isSelected ? colorScheme.primary : null,
                    fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                  ),
                ),
                selected: isSelected,
                onTap: () => _selectMenu(i),
              );
            }),
            const Divider(),
            ListTile(
              leading: const Icon(Icons.bar_chart_outlined),
              title: const Text('트렌드 분석'),
              subtitle: const Text('시총 Top 20 모니터링',
                  style: TextStyle(fontSize: 11)),
              onTap: () {
                _scaffoldKey.currentState?.closeDrawer();
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (ctx) => Scaffold(
                      appBar: AppBar(
                        leading: IconButton(
                          icon: const Icon(Icons.arrow_back_ios),
                          onPressed: () => Navigator.pop(ctx),
                        ),
                        title: const Text('트렌드 분석'),
                      ),
                      body: const MarketCapScreen(),
                    ),
                  ),
                );
              },
            ),
            ListTile(
              leading: const Icon(Icons.auto_stories_outlined),
              title: const Text('전략 설명'),
              onTap: () {
                _scaffoldKey.currentState?.closeDrawer();
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (ctx) => Scaffold(
                      appBar: AppBar(
                        leading: IconButton(
                          icon: const Icon(Icons.arrow_back_ios),
                          onPressed: () => Navigator.pop(ctx),
                        ),
                        title: const Text('전략 설명'),
                      ),
                      body: const StrategyGuideScreen(),
                    ),
                  ),
                );
              },
            ),
          ],
        ),
      ),
      body: _screens[_currentIndex],
    );
  }
}
