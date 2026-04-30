import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/trend_reversal_data.dart';
import '../providers/market_filter_provider.dart' show SortOrder;
import '../providers/trend_reversal_provider.dart';

/// 추세 전환 화면 — 5MA / 120MA 일봉 골든크로스 후보 Top 25
///
/// 백테스트(`backtest_5w_120w_cross.py`)의 5W/120W 전략을 일봉으로 적용.
/// 매수 방식은 v3.3과 동일 (격주 리밸런싱 + 트레일링 스톱).
class TrendReversalScreen extends ConsumerWidget {
  const TrendReversalScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncData = ref.watch(trendReversalDataProvider);
    final market = ref.watch(trendReversalMarketProvider);
    final sortOrder = ref.watch(trendReversalSortProvider);

    return Scaffold(
      body: asyncData.when(
        data: (data) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(trendReversalDataProvider),
          child: _buildContent(context, ref, data, market, sortOrder),
        ),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _buildError('오류: $e'),
      ),
    );
  }

  Widget _buildContent(
    BuildContext context,
    WidgetRef ref,
    TrendReversalData data,
    TrendReversalMarket market,
    SortOrder sortOrder,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildHeader(context, data),
        _buildToggleRow(context, ref, market, sortOrder),
        if (data.results.isEmpty)
          const Expanded(
            child: Center(
              child: Text('데이터가 없습니다.',
                  style: TextStyle(color: Colors.grey)),
            ),
          )
        else
          Expanded(
            child: _buildTable(context, data.results, sortOrder),
          ),
      ],
    );
  }

  Widget _buildHeader(BuildContext context, TrendReversalData data) {
    final dateStr = data.runDate.length >= 10
        ? data.runDate.substring(0, 10)
        : data.runDate;
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            '추세 전환 TOP ${data.results.length}',
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

  Widget _buildToggleRow(
    BuildContext context,
    WidgetRef ref,
    TrendReversalMarket market,
    SortOrder sortOrder,
  ) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 0, 8, 6),
      child: Row(
        children: [
          // 시장 토글: 🇺🇸 / 🇰🇷
          _segChip(
            context: context,
            label: '🇺🇸 미국',
            isSelected: market == TrendReversalMarket.us,
            onTap: () => ref
                .read(trendReversalMarketProvider.notifier)
                .state = TrendReversalMarket.us,
          ),
          const SizedBox(width: 4),
          _segChip(
            context: context,
            label: '🇰🇷 한국',
            isSelected: market == TrendReversalMarket.kr,
            onTap: () => ref
                .read(trendReversalMarketProvider.notifier)
                .state = TrendReversalMarket.kr,
          ),
          const Spacer(),
          // 정렬 토글
          _segChip(
            context: context,
            icon: Icons.format_list_numbered,
            label: '순위',
            isSelected: sortOrder == SortOrder.rank,
            onTap: () => ref
                .read(trendReversalSortProvider.notifier)
                .state = SortOrder.rank,
          ),
          const SizedBox(width: 4),
          _segChip(
            context: context,
            icon: Icons.sort_by_alpha,
            label: 'A→Z',
            isSelected: sortOrder == SortOrder.alphabetical,
            onTap: () => ref
                .read(trendReversalSortProvider.notifier)
                .state = SortOrder.alphabetical,
          ),
        ],
      ),
    );
  }

  Widget _segChip({
    required BuildContext context,
    String? label,
    IconData? icon,
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
            if (icon != null) ...[
              Icon(icon, size: 14, color: color),
              const SizedBox(width: 3),
            ],
            if (label != null)
              Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight:
                      isSelected ? FontWeight.bold : FontWeight.normal,
                  color: color,
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildTable(
    BuildContext context,
    List<TrendReversalResult> results,
    SortOrder sortOrder,
  ) {
    final sorted = List<TrendReversalResult>.from(results);
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

  DataRow _buildRow(BuildContext context, TrendReversalResult r) {
    final isSell = r.stopPrice != null && r.price <= r.stopPrice!;
    final colorScheme = Theme.of(context).colorScheme;
    final rowColor = isSell
        ? WidgetStateProperty.all(
            colorScheme.error.withValues(alpha: 0.10),
          )
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
    final pct = stopDistPct * 100;
    final isWarning = !isSell && pct.abs() < 3.0;
    final color = isSell
        ? colorScheme.error
        : (isWarning ? Colors.orange.shade400 : null);
    return Text(
      '${pct.toStringAsFixed(1)}%',
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
