import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/sell_signal.dart';
import '../providers/sell_signal_provider.dart';

class SellSignalScreen extends ConsumerWidget {
  const SellSignalScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncData = ref.watch(sellSignalProvider);

    return Scaffold(
      body: asyncData.when(
        data: (data) {
          if (data == null) return _buildError('데이터를 불러올 수 없습니다.');
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(sellSignalProvider),
            child: _buildContent(context, data),
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _buildError('오류: $e'),
      ),
    );
  }

  Widget _buildContent(BuildContext context, SellSignalData data) {
    final signals = data.signals;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildHeader(context, data),
        if (signals.isEmpty)
          Expanded(child: _buildEmpty())
        else
          Expanded(child: _buildTable(context, signals)),
      ],
    );
  }

  Widget _buildHeader(BuildContext context, SellSignalData data) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            '매도 신호 ${data.signals.length}건',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          if (data.updatedAt.isNotEmpty)
            Text(
              data.updatedAt,
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
        ],
      ),
    );
  }

  Widget _buildTable(BuildContext context, List<SellSignal> signals) {
    // 정렬: sell_triggered_date 최신순, 같으면 days_remaining 오름차순
    final sorted = [...signals]
      ..sort((a, b) {
        final dc = b.sellTriggeredDate.compareTo(a.sellTriggeredDate);
        if (dc != 0) return dc;
        return a.daysRemaining.compareTo(b.daysRemaining);
      });

    return SingleChildScrollView(
      scrollDirection: Axis.vertical,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columnSpacing: 16,
          headingRowHeight: 40,
          dataRowMinHeight: 48,
          dataRowMaxHeight: 64,
          columns: const [
            DataColumn(label: Text('티커', style: TextStyle(fontWeight: FontWeight.bold))),
            DataColumn(label: Text('현재가', style: TextStyle(fontWeight: FontWeight.bold)), numeric: true),
            DataColumn(label: Text('스톱로스', style: TextStyle(fontWeight: FontWeight.bold)), numeric: true),
            DataColumn(label: Text('순위', style: TextStyle(fontWeight: FontWeight.bold)), numeric: true),
            DataColumn(label: Text('신호', style: TextStyle(fontWeight: FontWeight.bold))),
            DataColumn(label: Text('발생일', style: TextStyle(fontWeight: FontWeight.bold))),
            DataColumn(label: Text('남은일', style: TextStyle(fontWeight: FontWeight.bold)), numeric: true),
          ],
          rows: sorted.map((s) => _buildRow(context, s)).toList(),
        ),
      ),
    );
  }

  DataRow _buildRow(BuildContext context, SellSignal s) {
    final isSell = s.sellReasons.isNotEmpty;
    final rowColor = isSell
        ? WidgetStateProperty.all(Colors.red.shade50)
        : null;

    return DataRow(
      color: rowColor,
      cells: [
        DataCell(
          Text(
            s.ticker,
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
          ),
        ),
        DataCell(Text(_formatPrice(s.currentPrice))),
        DataCell(
          Text(
            _formatPrice(s.stopPrice),
            style: TextStyle(
              color: s.currentPrice <= s.stopPrice ? Colors.red.shade700 : null,
              fontWeight: s.currentPrice <= s.stopPrice ? FontWeight.bold : null,
            ),
          ),
        ),
        DataCell(
          Text(
            s.rank > 25 ? '>25' : '${s.rank}',
            style: TextStyle(
              color: s.rank > 25 ? Colors.orange.shade700 : null,
              fontWeight: s.rank > 25 ? FontWeight.bold : null,
            ),
          ),
        ),
        DataCell(_buildSignalChip(s)),
        DataCell(Text(s.sellTriggeredDate, style: const TextStyle(fontSize: 12))),
        DataCell(
          Text(
            '${s.daysRemaining}일',
            style: TextStyle(
              color: s.daysRemaining == 1 ? Colors.red.shade700 : Colors.grey.shade700,
              fontWeight: s.daysRemaining == 1 ? FontWeight.bold : null,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSignalChip(SellSignal s) {
    final reasons = <String>[];
    if (s.isStopLoss) reasons.add('스톱로스');
    if (s.isRankOut) reasons.add('순위이탈');

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: reasons.map((r) {
        final isStop = r == '스톱로스';
        return Container(
          margin: const EdgeInsets.only(bottom: 2),
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
          decoration: BoxDecoration(
            color: isStop ? Colors.red.shade100 : Colors.orange.shade100,
            borderRadius: BorderRadius.circular(4),
          ),
          child: Text(
            r,
            style: TextStyle(
              fontSize: 10,
              color: isStop ? Colors.red.shade800 : Colors.orange.shade800,
              fontWeight: FontWeight.bold,
            ),
          ),
        );
      }).toList(),
    );
  }

  String _formatPrice(double price) {
    if (price >= 1000) {
      return '\$${price.toStringAsFixed(0)}';
    } else if (price >= 10) {
      return '\$${price.toStringAsFixed(2)}';
    } else {
      return '\$${price.toStringAsFixed(4)}';
    }
  }

  Widget _buildEmpty() {
    return ListView(
      children: const [
        SizedBox(height: 160),
        Center(
          child: Column(
            children: [
              Icon(Icons.check_circle_outline, size: 64, color: Colors.green),
              SizedBox(height: 16),
              Text('현재 매도 신호가 없습니다',
                  style: TextStyle(fontSize: 16, color: Colors.grey)),
              SizedBox(height: 8),
              Text('모든 보유 후보 종목이 정상 범위에 있습니다.',
                  style: TextStyle(fontSize: 13, color: Colors.grey)),
            ],
          ),
        ),
      ],
    );
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
