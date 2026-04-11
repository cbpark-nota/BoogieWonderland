import 'package:flutter/material.dart';
import 'strategy_guide_screen.dart';
import 'short_squeeze_strategy_guide_screen.dart';
import 'vix_strategy_guide_screen.dart';

class StrategyGuideTabsScreen extends StatelessWidget {
  const StrategyGuideTabsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Column(
        children: [
          TabBar(
            tabs: const [
              Tab(text: '모멘텀'),
              Tab(text: '숏 스퀴즈'),
              Tab(text: 'VIX 매매'),
            ],
            labelStyle: const TextStyle(fontWeight: FontWeight.bold),
            unselectedLabelStyle: const TextStyle(fontWeight: FontWeight.normal),
          ),
          const Expanded(
            child: TabBarView(
              children: [
                StrategyGuideScreen(),
                ShortSqueezeStrategyGuideScreen(),
                VixStrategyGuideScreen(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
