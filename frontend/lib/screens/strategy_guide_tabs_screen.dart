import 'package:flutter/material.dart';
import 'strategy_guide_screen.dart';
import 'trend_reversal_strategy_guide_screen.dart';
import 'short_squeeze_strategy_guide_screen.dart';
import 'vix_strategy_guide_screen.dart';
import 'crypto_strategy_guide_screen.dart';

class StrategyGuideTabsScreen extends StatelessWidget {
  const StrategyGuideTabsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 5,
      child: Column(
        children: [
          TabBar(
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            tabs: const [
              Tab(text: '모멘텀'),
              Tab(text: '추세 전환'),
              Tab(text: '숏 스퀴즈'),
              Tab(text: 'VIX 매매'),
              Tab(text: 'BTC / ETH'),
            ],
            labelStyle: const TextStyle(fontWeight: FontWeight.bold),
            unselectedLabelStyle: const TextStyle(fontWeight: FontWeight.normal),
          ),
          const Expanded(
            child: TabBarView(
              children: [
                StrategyGuideScreen(),
                TrendReversalStrategyGuideScreen(),
                ShortSqueezeStrategyGuideScreen(),
                VixStrategyGuideScreen(),
                CryptoStrategyGuideScreen(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
