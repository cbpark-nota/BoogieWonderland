import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/short_squeeze.dart';
import '../providers/serverless_providers.dart';

class ShortSqueezeScreen extends ConsumerWidget {
  const ShortSqueezeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dataAsync = ref.watch(shortSqueezeProvider);

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(shortSqueezeProvider),
      child: dataAsync.when(
        data: (data) {
          if (data == null || data.results.isEmpty) {
            return _buildEmpty();
          }
          return _buildContent(context, data);
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('오류: $e')),
      ),
    );
  }

  Widget _buildContent(BuildContext context, ShortSqueezeData data) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _buildHeader(context, data),
        const SizedBox(height: 12),
        ...data.results.asMap().entries.map(
              (e) => _buildCard(context, e.key + 1, e.value),
            ),
        const SizedBox(height: 80),
      ],
    );
  }

  Widget _buildHeader(BuildContext context, ShortSqueezeData data) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.compress, color: Colors.orange),
                const SizedBox(width: 8),
                Text(
                  '숏스퀴즈 후보 ${data.totalCandidates}종목',
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.bold),
                ),
                if (data.isSample) ...[
                  const SizedBox(width: 8),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: Colors.amber.shade700,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Text('샘플',
                        style: TextStyle(fontSize: 10, color: Colors.white)),
                  ),
                ],
              ],
            ),
            if (data.criteriaDescription.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(data.criteriaDescription,
                  style: const TextStyle(fontSize: 12, color: Colors.grey)),
            ],
            if (data.generatedAt.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text('업데이트: ${data.generatedAt.replaceFirst('T', ' ')}',
                  style: const TextStyle(fontSize: 11, color: Colors.grey)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildCard(
      BuildContext context, int rank, ShortSqueezeResult result) {
    final change5dColor =
        result.change5dPct >= 0 ? Colors.green.shade400 : Colors.red.shade400;
    final change1dColor =
        result.change1dPct >= 0 ? Colors.green.shade400 : Colors.red.shade400;

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 16,
                  backgroundColor: Colors.orange.shade700,
                  child: Text('$rank',
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.bold)),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(result.ticker,
                          style: const TextStyle(
                              fontSize: 15, fontWeight: FontWeight.bold)),
                      Text(result.name,
                          style: const TextStyle(
                              fontSize: 12, color: Colors.grey)),
                    ],
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text('\$${result.price.toStringAsFixed(2)}',
                        style: const TextStyle(
                            fontSize: 15, fontWeight: FontWeight.bold)),
                    Text(result.sector,
                        style:
                            const TextStyle(fontSize: 10, color: Colors.grey)),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                _statChip('공매도 비율', '${result.shortFloatPct.toStringAsFixed(1)}%',
                    Colors.red.shade700),
                const SizedBox(width: 8),
                _statChip('커버 일수', '${result.daysToCover.toStringAsFixed(1)}일',
                    Colors.blue.shade700),
                const SizedBox(width: 8),
                _statChip('거래량비',
                    '${result.volumeRatio.toStringAsFixed(1)}x', Colors.purple.shade700),
              ],
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                _changeChip('1일', result.change1dPct, change1dColor),
                const SizedBox(width: 8),
                _changeChip('5일', result.change5dPct, change5dColor),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _statChip(String label, String value, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Column(
        children: [
          Text(label, style: const TextStyle(fontSize: 9, color: Colors.grey)),
          Text(value,
              style: TextStyle(
                  fontSize: 12, fontWeight: FontWeight.bold, color: color)),
        ],
      ),
    );
  }

  Widget _changeChip(String period, double pct, Color color) {
    final sign = pct >= 0 ? '+' : '';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        '$period: $sign${pct.toStringAsFixed(1)}%',
        style:
            TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: color),
      ),
    );
  }

  Widget _buildEmpty() {
    return ListView(
      children: const [
        SizedBox(height: 200),
        Center(
          child: Column(
            children: [
              Icon(Icons.compress, size: 64, color: Colors.grey),
              SizedBox(height: 16),
              Text('숏스퀴즈 데이터가 없습니다',
                  style: TextStyle(fontSize: 16, color: Colors.grey)),
            ],
          ),
        ),
      ],
    );
  }
}
