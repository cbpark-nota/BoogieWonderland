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
    final historyAsync = ref.watch(historyScreeningProvider);

    return Column(
      children: [
        _buildDateSelector(),
        _buildStrategySelector(),
        _buildMarketFilter(),
        Expanded(
          child: RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(strategyDataProvider);
              ref.invalidate(historyScreeningProvider);
              ref.invalidate(historyDatesProvider);
            },
            child: historyAsync.when(
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
    );
  }

  // ── 날짜 선택 바 ──

  Widget _buildDateSelector() {
    final datesAsync = ref.watch(historyDatesProvider);
    final selectedDate = ref.watch(selectedHistoryDateProvider);

    return datesAsync.when(
      data: (dates) {
        if (dates.isEmpty) return const SizedBox.shrink();
        // 스크리닝 페이지는 최근 5일만 표시 (히스토리는 30일 저장되지만 UI는 5일)
        final displayDates = dates.take(5).toList();
        // null = 최신(오늘) / 5일 범위 밖 날짜 선택 시 최신으로 fallback
        final effectiveDate =
            (selectedDate != null && displayDates.contains(selectedDate))
                ? selectedDate!
                : displayDates.first;
        final idx = displayDates.indexOf(effectiveDate);

        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          color: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.31),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton(
                icon: const Icon(Icons.chevron_left),
                iconSize: 20,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
                onPressed: idx < displayDates.length - 1
                    ? () => ref
                        .read(selectedHistoryDateProvider.notifier)
                        .state = displayDates[idx + 1]
                    : null,
              ),
              const SizedBox(width: 4),
              DropdownButton<String>(
                value: effectiveDate,
                underline: const SizedBox.shrink(),
                isDense: true,
                items: displayDates.map((d) {
                  final isLatest = d == displayDates.first;
                  return DropdownMenuItem(
                    value: d,
                    child: Text(
                      isLatest ? '$d (최신)' : d,
                      style: const TextStyle(fontSize: 13),
                    ),
                  );
                }).toList(),
                onChanged: (d) {
                  ref.read(selectedHistoryDateProvider.notifier).state = d;
                },
              ),
              const SizedBox(width: 4),
              IconButton(
                icon: const Icon(Icons.chevron_right),
                iconSize: 20,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
                onPressed: idx > 0
                    ? () => ref
                        .read(selectedHistoryDateProvider.notifier)
                        .state = displayDates[idx - 1]
                    : null,
              ),
            ],
          ),
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, __) => const SizedBox.shrink(),
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
    final reranked = filtered.asMap().entries
        .map((e) => e.value.copyWith(rank: e.key + 1))
        .toList();
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
          style: TextStyle(
            fontSize: 11,
            color: color != null
                ? Colors.white
                : Theme.of(context).colorScheme.onSurface,
          )),
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
