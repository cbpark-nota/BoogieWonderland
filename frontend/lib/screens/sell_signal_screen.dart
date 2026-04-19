import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/screening_result.dart';
import '../providers/serverless_providers.dart';

/// 모멘텀 현재 순위 화면 (공격적 전략 Top 25)
///
/// screening_strategies.json의 aggressive 결과(25개)를 직접 표시한다.
/// stop_price ≤ 현재가인 종목은 "SELL" 마크 표시.
class CurrentRankScreen extends ConsumerWidget {
  const CurrentRankScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncData = ref.watch(strategyDataProvider);

    return Scaffold(
      body: asyncData.when(
        data: (data) {
          if (data == null) return _buildError('데이터를 불러올 수 없습니다.');
          final results =
              data.strategies[StrategyType.aggressive]?.results ?? [];
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(strategyDataProvider),
            child: _buildContent(context, data.runDate, results),
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _buildError('오류: $e'),
      ),
    );
  }

  Widget _buildContent(
      BuildContext context, String runDate, List<ScreeningResult> results) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildHeader(context, runDate, results.length),
        if (results.isEmpty)
          const Expanded(
            child: Center(
              child: Text('데이터가 없습니다.',
                  style: TextStyle(color: Colors.grey)),
            ),
          )
        else
          Expanded(child: _buildTable(context, results)),
      ],
    );
  }

  Widget _buildHeader(
      BuildContext context, String runDate, int count) {
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

  Widget _buildTable(
      BuildContext context, List<ScreeningResult> results) {
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
          rows: results.map((r) => _buildRow(context, r)).toList(),
        ),
      ),
    );
  }

  DataRow _buildRow(BuildContext context, ScreeningResult r) {
    final isSell =
        r.stopPrice != null && r.price <= r.stopPrice!;
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
