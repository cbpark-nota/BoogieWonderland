import 'package:flutter/material.dart';
import 'screening_screen.dart';
import 'short_squeeze_screen.dart';
import 'trend_reversal_screen.dart';
import 'vix_etf_calculator_screen.dart';

class ScreeningTabsScreen extends StatelessWidget {
  final int initialIndex;

  const ScreeningTabsScreen({super.key, this.initialIndex = 0});
  const ScreeningTabsScreen.withIndex({super.key, required this.initialIndex});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 4,
      initialIndex: initialIndex,
      child: Column(
        children: [
          TabBar(
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            tabs: const [
              Tab(text: '모멘텀'),
              Tab(text: '추세 전환'),
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
                ScreeningScreen(),
                TrendReversalScreen(),
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
