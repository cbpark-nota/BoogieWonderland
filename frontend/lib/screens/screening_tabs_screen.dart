import 'package:flutter/material.dart';
import 'screening_screen.dart';
import 'sell_signal_screen.dart' show CurrentRankScreen;
import 'short_squeeze_screen.dart';
import 'vix_etf_calculator_screen.dart';

class ScreeningTabsScreen extends StatelessWidget {
  final int initialIndex;

  const ScreeningTabsScreen({super.key, this.initialIndex = 0});
  const ScreeningTabsScreen.withIndex({super.key, required this.initialIndex});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      initialIndex: initialIndex,
      child: Column(
        children: [
          TabBar(
            tabs: const [
              Tab(text: '모멘텀'),
              Tab(text: '숏 스퀴즈'),
              Tab(text: 'VIX ETF'),
            ],
            labelStyle: const TextStyle(fontWeight: FontWeight.bold),
            unselectedLabelStyle: const TextStyle(
              fontWeight: FontWeight.normal,
            ),
          ),
          const Expanded(
            child: TabBarView(
              children: [
                _MomentumTabScreen(),
                ShortSqueezeScreen(),
                VixEtfCalculatorScreen(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// 모멘텀 탭 내부 2단계 탭: 스크리닝 / 현재 순위
class _MomentumTabScreen extends StatefulWidget {
  const _MomentumTabScreen();

  @override
  State<_MomentumTabScreen> createState() => _MomentumTabScreenState();
}

class _MomentumTabScreenState extends State<_MomentumTabScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Column(
      children: [
        TabBar(
          controller: _tabController,
          indicatorSize: TabBarIndicatorSize.tab,
          dividerColor: colorScheme.outlineVariant,
          labelStyle: const TextStyle(
              fontWeight: FontWeight.bold, fontSize: 13),
          unselectedLabelStyle: const TextStyle(
              fontWeight: FontWeight.normal, fontSize: 13),
          tabs: const [
            Tab(text: '스크리닝'),
            Tab(text: '현재 순위'),
          ],
        ),
        Expanded(
          child: TabBarView(
            controller: _tabController,
            children: const [
              ScreeningScreen(),
              CurrentRankScreen(),
            ],
          ),
        ),
      ],
    );
  }
}
