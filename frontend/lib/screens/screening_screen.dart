import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../config/app_config.dart';
import '../models/screening_result.dart';
import '../providers/screening_provider.dart';
import '../providers/serverless_providers.dart';
import '../widgets/stock_card.dart';

class ScreeningScreen extends ConsumerStatefulWidget {
  const ScreeningScreen({super.key});

  @override
  ConsumerState<ScreeningScreen> createState() => _ScreeningScreenState();
}

enum _MarketFilter { all, kr, us }

class _ScreeningScreenState extends ConsumerState<ScreeningScreen> {
  StrategyType _selected = StrategyType.balanced;
  _MarketFilter _marketFilter = _MarketFilter.all;

  @override
  Widget build(BuildContext context) {
    // 서버리스 모드: 4전략 데이터 사용
    if (AppConfig.isServerless) {
      return _buildServerlessView();
    }
    // 풀스택 모드: 기존 단일 스크리닝
    return _buildFullstackView();
  }

  // ── 서버리스 모드: 4전략 탭 ──

  Widget _buildServerlessView() {
    final strategyAsync = ref.watch(strategyDataProvider);

    return Scaffold(
      body: Column(
        children: [
          _buildStrategySelector(),
          _buildMarketFilter(),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async {
                ref.invalidate(strategyDataProvider);
              },
              child: strategyAsync.when(
                data: (data) {
                  if (data == null) return _buildEmpty();
                  final run = data.toScreeningRun(_selected);
                  final sr = data.strategies[_selected];
                  return _buildResultList(_filterRun(run), sr);
                },
                loading: () =>
                    const Center(child: CircularProgressIndicator()),
                error: (e, _) => Center(child: Text('오류: $e')),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ── 풀스택 모드: 기존 화면 ──

  Widget _buildFullstackView() {
    final screeningAsync = ref.watch(screeningProvider);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(screeningProvider.notifier).refresh();
        },
        child: screeningAsync.when(
          data: (run) {
            if (run == null || run.results.isEmpty) return _buildEmpty();
            return _buildResultList(run, null);
          },
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text('오류: $e')),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('스크리닝 실행 중...')),
          );
          await ref.read(screeningProvider.notifier).runScreening();
        },
        icon: const Icon(Icons.play_arrow),
        label: const Text('스크리닝'),
      ),
    );
  }

  // ── 전략 선택 바 ──

  Widget _buildStrategySelector() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: StrategyType.values.map((st) {
            final isSelected = st == _selected;
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: ChoiceChip(
                label: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(st.label,
                        style: TextStyle(
                            fontWeight:
                                isSelected ? FontWeight.bold : FontWeight.normal,
                            fontSize: 13)),
                    Text(st.description,
                        style: TextStyle(
                            fontSize: 10,
                            color: isSelected
                                ? Theme.of(context).colorScheme.onPrimary
                                : Colors.grey)),
                  ],
                ),
                selected: isSelected,
                onSelected: (_) => setState(() => _selected = st),
                selectedColor: _chipColor(st),
                labelStyle: TextStyle(
                    color:
                        isSelected ? Colors.white : null),
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _buildMarketFilter() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Row(
        children: _MarketFilter.values.map((f) {
          final isSelected = f == _marketFilter;
          final label = switch (f) {
            _MarketFilter.all => '전체',
            _MarketFilter.kr => '🇰🇷 한국',
            _MarketFilter.us => '🇺🇸 미국',
          };
          return Padding(
            padding: const EdgeInsets.only(right: 8),
            child: ChoiceChip(
              label: Text(label,
                  style: TextStyle(
                      fontSize: 12,
                      fontWeight: isSelected ? FontWeight.bold : FontWeight.normal)),
              selected: isSelected,
              onSelected: (_) => setState(() => _marketFilter = f),
              selectedColor: Colors.teal.shade600,
              labelStyle: TextStyle(color: isSelected ? Colors.white : null),
            ),
          );
        }).toList(),
      ),
    );
  }

  ScreeningRun _filterRun(ScreeningRun run) {
    if (_marketFilter == _MarketFilter.all) return run;
    final marketCode = _marketFilter == _MarketFilter.kr ? 'KR' : 'US';
    final filtered = run.results
        .where((r) => r.market == marketCode)
        .toList();
    final reranked = filtered.asMap().entries.map((e) {
      final r = e.value;
      return ScreeningResult(
        rank: e.key + 1,
        ticker: r.ticker,
        market: r.market,
        name: r.name,
        sector: r.sector,
        score: r.score,
        weightPct: r.weightPct,
        price: r.price,
        adx: r.adx,
        rsi: r.rsi,
        ret3m: r.ret3m,
        stopPrice: r.stopPrice,
        stopDistPct: r.stopDistPct,
        atr: r.atr,
      );
    }).toList();
    return ScreeningRun(
      runId: run.runId,
      runDate: run.runDate,
      marketStatus: run.marketStatus,
      btcSignal: run.btcSignal,
      totalScreened: run.totalScreened,
      totalPassed: run.totalPassed,
      results: reranked,
    );
  }

  Color _chipColor(StrategyType st) {
    switch (st) {
      case StrategyType.aggressive:
        return Colors.red.shade600;
      case StrategyType.balanced:
        return Colors.blue.shade600;
      case StrategyType.conservative:
        return Colors.amber.shade700;
      case StrategyType.adaptive:
        return Colors.purple.shade600;
    }
  }

  // ── 결과 리스트 ──

  Widget _buildResultList(ScreeningRun run, StrategyResult? sr) {
    if (run.results.isEmpty) return _buildEmpty();

    return ListView(
      key: ValueKey(_selected.key),
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('TOP ${run.results.length}',
                  style: const TextStyle(
                      fontSize: 20, fontWeight: FontWeight.bold)),
              Text('${run.totalPassed}/${run.totalScreened} 통과',
                  style: const TextStyle(color: Colors.grey)),
            ],
          ),
        ),
        if (sr != null) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
            child: Row(
              children: [
                _infoChip('ATR ${sr.atrMult}',
                    color: _chipColor(_selected)),
                const SizedBox(width: 8),
                _infoChip(sr.rebalFreq,
                    color: _chipColor(_selected)),
                if (sr.currentRegime != null) ...[
                  const SizedBox(width: 8),
                  _infoChip('국면: ${sr.currentRegime}',
                      color: Colors.purple.shade600),
                ],
              ],
            ),
          ),
        ],
        ...run.results.map((r) => StockCard(result: r)),
        const SizedBox(height: 80),
      ],
    );
  }

  Widget _infoChip(String text, {Color? color}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color ?? Colors.grey.shade200,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(text,
          style: const TextStyle(fontSize: 11, color: Colors.black)),
    );
  }

  Widget _buildEmpty() {
    return ListView(
      children: const [
        SizedBox(height: 200),
        Center(
          child: Column(
            children: [
              Icon(Icons.search_off, size: 64, color: Colors.grey),
              SizedBox(height: 16),
              Text('스크리닝 결과가 없습니다',
                  style: TextStyle(fontSize: 16, color: Colors.grey)),
            ],
          ),
        ),
      ],
    );
  }
}
