import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/screening_result.dart';
import '../providers/market_filter_provider.dart';
import '../providers/serverless_providers.dart';

// 3전략 세그먼트 설정 (스크리닝 탭과 동일)
const _kStrategies = [
  StrategyType.aggressive,
  StrategyType.balanced,
  StrategyType.conservative,
];

const _kStrategyShortLabel = {
  StrategyType.aggressive: '공격적',
  StrategyType.balanced: '균형',
  StrategyType.conservative: '보수적',
};

const _kStrategyParamLabel = {
  StrategyType.aggressive: 'ATR×1.5 / TOP 25',
  StrategyType.balanced: 'ATR×2.0 / TOP 10',
  StrategyType.conservative: 'ATR×2.5 / TOP 7',
};

/// 모멘텀 현재 순위 화면 (전략별 전체 순위 표시)
///
/// screening_strategies.json의 전략별 결과를 표시한다.
/// stop_price ≤ 현재가인 종목은 "SELL" 마크 표시.
class CurrentRankScreen extends ConsumerWidget {
  const CurrentRankScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncData = ref.watch(strategyDataProvider);
    final selectedStrategy = ref.watch(currentRankStrategyProvider);
    final sortOrder = ref.watch(currentRankSortOrderProvider);

    return Scaffold(
      body: asyncData.when(
        data: (data) {
          if (data == null) return _buildError('데이터를 불러올 수 없습니다.');
          final results = data.strategies[selectedStrategy]?.results ?? [];
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(strategyDataProvider),
            child: _buildContent(
                context, ref, data.runDate, results, selectedStrategy, sortOrder),
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _buildError('오류: $e'),
      ),
    );
  }

  Widget _buildContent(
    BuildContext context,
    WidgetRef ref,
    String runDate,
    List<ScreeningResult> results,
    StrategyType selectedStrategy,
    SortOrder sortOrder,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildHeader(context, runDate, results.length),
        _buildStrategySelector(context, ref, selectedStrategy),
        _buildSortRow(context, ref, sortOrder),
        if (results.isEmpty)
          const Expanded(
            child: Center(
              child: Text('데이터가 없습니다.',
                  style: TextStyle(color: Colors.grey)),
            ),
          )
        else
          Expanded(child: _buildTable(context, results, sortOrder)),
      ],
    );
  }

  Widget _buildHeader(BuildContext context, String runDate, int count) {
    final dateStr =
        runDate.length >= 10 ? runDate.substring(0, 10) : runDate;
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            '모멘텀 순위 TOP $count',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          Text(
            dateStr,
            style: const TextStyle(fontSize: 12, color: Colors.grey),
          ),
        ],
      ),
    );
  }

  // ── 전략 선택 바 (스크리닝 탭과 동일 UI) ──

  Widget _buildStrategySelector(
      BuildContext context, WidgetRef ref, StrategyType selected) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      child: Row(
        children: _kStrategies.map((st) {
          final isSelected = st == selected;
          return Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 3),
              child: GestureDetector(
                onTap: () =>
                    ref.read(currentRankStrategyProvider.notifier).state = st,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  padding:
                      const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
                  decoration: BoxDecoration(
                    color: isSelected
                        ? _chipColor(st)
                        : Theme.of(context)
                            .colorScheme
                            .surfaceContainerHighest
                            .withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: isSelected
                          ? _chipColor(st)
                          : Theme.of(context).colorScheme.outlineVariant,
                      width: isSelected ? 0 : 1,
                    ),
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        _kStrategyShortLabel[st] ?? st.label,
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 13,
                          color: isSelected
                              ? Colors.white
                              : Theme.of(context).colorScheme.onSurface,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        _kStrategyParamLabel[st] ?? st.description,
                        style: TextStyle(
                          fontSize: 10,
                          color: isSelected
                              ? Colors.white.withValues(alpha: 0.85)
                              : Colors.grey,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  // ── 정렬 옵션 바 (스크리닝 탭과 동일 UI) ──

  Widget _buildSortRow(
      BuildContext context, WidgetRef ref, SortOrder sortOrder) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 0, 8, 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          _sortButton(
            context: context,
            icon: Icons.format_list_numbered,
            label: '순위',
            isSelected: sortOrder == SortOrder.rank,
            onTap: () => ref
                .read(currentRankSortOrderProvider.notifier)
                .state = SortOrder.rank,
          ),
          const SizedBox(width: 4),
          _sortButton(
            context: context,
            icon: Icons.sort_by_alpha,
            label: '알파벳',
            isSelected: sortOrder == SortOrder.alphabetical,
            onTap: () => ref
                .read(currentRankSortOrderProvider.notifier)
                .state = SortOrder.alphabetical,
          ),
        ],
      ),
    );
  }

  Widget _sortButton({
    required BuildContext context,
    required IconData icon,
    required String label,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    final color = isSelected
        ? Theme.of(context).colorScheme.primary
        : Theme.of(context).colorScheme.onSurfaceVariant;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: isSelected
              ? Theme.of(context)
                  .colorScheme
                  .primaryContainer
                  .withValues(alpha: 0.6)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(
            color: isSelected
                ? Theme.of(context).colorScheme.primary
                : Theme.of(context).colorScheme.outlineVariant,
            width: 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 14, color: color),
            const SizedBox(width: 3),
            Text(label,
                style: TextStyle(
                    fontSize: 11,
                    fontWeight:
                        isSelected ? FontWeight.bold : FontWeight.normal,
                    color: color)),
          ],
        ),
      ),
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

  Widget _buildTable(
      BuildContext context, List<ScreeningResult> results, SortOrder sortOrder) {
    final sorted = List<ScreeningResult>.from(results);
    if (sortOrder == SortOrder.alphabetical) {
      sorted.sort((a, b) => a.ticker.compareTo(b.ticker));
    } else {
      sorted.sort((a, b) => a.rank.compareTo(b.rank));
    }

    return SingleChildScrollView(
      scrollDirection: Axis.vertical,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columnSpacing: 14,
          headingRowHeight: 40,
          dataRowMinHeight: 48,
          dataRowMaxHeight: 56,
          columns: const [
            DataColumn(
                label: Text('순위',
                    style: TextStyle(fontWeight: FontWeight.bold)),
                numeric: true),
            DataColumn(
                label: Text('티커',
                    style: TextStyle(fontWeight: FontWeight.bold))),
            DataColumn(
                label: Text('현재가',
                    style: TextStyle(fontWeight: FontWeight.bold)),
                numeric: true),
            DataColumn(
                label: Text('스코어',
                    style: TextStyle(fontWeight: FontWeight.bold)),
                numeric: true),
            DataColumn(
                label: Text('스톱가',
                    style: TextStyle(fontWeight: FontWeight.bold)),
                numeric: true),
            DataColumn(
                label: Text('여유%',
                    style: TextStyle(fontWeight: FontWeight.bold)),
                numeric: true),
            DataColumn(
                label: Text('상태',
                    style: TextStyle(fontWeight: FontWeight.bold))),
          ],
          rows: sorted.map((r) => _buildRow(context, r)).toList(),
        ),
      ),
    );
  }

  DataRow _buildRow(BuildContext context, ScreeningResult r) {
    final isSell = r.stopPrice != null && r.price <= r.stopPrice!;
    final colorScheme = Theme.of(context).colorScheme;
    final rowColor = isSell
        ? WidgetStateProperty.all(
            colorScheme.error.withValues(alpha: 0.10))
        : null;

    return DataRow(
      color: rowColor,
      cells: [
        DataCell(Text('${r.rank}',
            style: const TextStyle(fontWeight: FontWeight.bold))),
        DataCell(Text(r.ticker,
            style: const TextStyle(
                fontWeight: FontWeight.bold, fontSize: 13))),
        DataCell(Text(_formatPrice(r.price, r.market))),
        DataCell(Text(r.score.toStringAsFixed(3))),
        DataCell(
          Text(
            r.stopPrice != null
                ? _formatPrice(r.stopPrice!, r.market)
                : '-',
            style: TextStyle(
              color: isSell ? colorScheme.error : null,
              fontWeight: isSell ? FontWeight.bold : null,
            ),
          ),
        ),
        DataCell(_buildDistCell(context, r.stopDistPct, isSell)),
        DataCell(_buildStatusChip(context, isSell)),
      ],
    );
  }

  Widget _buildDistCell(
      BuildContext context, double? stopDistPct, bool isSell) {
    if (stopDistPct == null) return const Text('-');
    final colorScheme = Theme.of(context).colorScheme;
    final isWarning = !isSell && stopDistPct < 3.0;
    final color = isSell
        ? colorScheme.error
        : (isWarning ? Colors.orange.shade400 : null);
    final sign = stopDistPct >= 0 ? '' : '';
    return Text(
      '$sign${stopDistPct.toStringAsFixed(1)}%',
      style: TextStyle(color: color),
    );
  }

  Widget _buildStatusChip(BuildContext context, bool isSell) {
    final colorScheme = Theme.of(context).colorScheme;
    if (!isSell) return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: colorScheme.error.withValues(alpha: 0.20),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        'SELL',
        style: TextStyle(
          fontSize: 11,
          color: colorScheme.error,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }

  String _formatPrice(double price, String market) {
    if (market == 'KR') {
      return '₩${price.toStringAsFixed(0)}';
    }
    if (price >= 1000) {
      return '\$${price.toStringAsFixed(0)}';
    } else if (price >= 10) {
      return '\$${price.toStringAsFixed(2)}';
    } else {
      return '\$${price.toStringAsFixed(4)}';
    }
  }

  Widget _buildError(String message) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.error_outline, size: 48, color: Colors.grey),
          const SizedBox(height: 12),
          Text(message, style: const TextStyle(color: Colors.grey)),
        ],
      ),
    );
  }
}
