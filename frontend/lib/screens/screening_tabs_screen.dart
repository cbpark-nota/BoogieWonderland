import 'package:flutter/material.dart';
import 'screening_screen.dart';
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
              Tab(text: 'VIX 매매'),
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
