import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/screening_provider.dart';
import '../providers/market_provider.dart';
import '../widgets/market_status_banner.dart';
import '../widgets/btc_signal_widget.dart';
import '../widgets/eth_signal_widget.dart';

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final marketAsync = ref.watch(marketStatusProvider);
    final screeningAsync = ref.watch(screeningProvider);

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(marketStatusProvider);
        await ref.read(screeningProvider.notifier).refresh();
      },
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // 시장 상태
          marketAsync.when(
            data: (status) {
              if (status == null) {
                return const Card(
                  child: Padding(
                    padding: EdgeInsets.all(16),
                    child: Text('시장 데이터를 불러올 수 없습니다'),
                  ),
                );
              }
              return Column(
                children: [
                  MarketStatusBanner(status: status),
                  const SizedBox(height: 8),
                  KospiStatusBanner(status: status),
                ],
              );
            },
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, s) => Text('Error: $e'),
          ),

          const SizedBox(height: 12),

          // BTC V10 시그널
          screeningAsync.when(
            data: (run) {
              final sig = run?.btcSignal;
              if (sig == null) return const SizedBox.shrink();
              return BtcSignalWidget(signal: sig);
            },
            loading: () => const SizedBox.shrink(),
            error: (_, __) => const SizedBox.shrink(),
          ),

          const SizedBox(height: 8),

          // ETH V10 시그널 (BTC 신호 기반 카피 트레이딩)
          screeningAsync.when(
            data: (run) {
              final sig = run?.ethSignal;
              if (sig == null) return const SizedBox.shrink();
              return EthSignalWidget(signal: sig);
            },
            loading: () => const SizedBox.shrink(),
            error: (_, __) => const SizedBox.shrink(),
          ),

          const SizedBox(height: 16),

          // 다음 리밸런싱
          marketAsync.when(
            data: (status) {
              final next = status?.nextRebalance;
              return Card(
                child: ListTile(
                  leading: const Icon(Icons.calendar_today, color: Colors.blue),
                  title: const Text('다음 리밸런싱'),
                  subtitle: Text(next ?? '일정 없음'),
                  trailing: next != null
                      ? Text(_daysUntil(next),
                          style: const TextStyle(
                              fontSize: 18, fontWeight: FontWeight.bold,
                              color: Colors.blue))
                      : null,
                ),
              );
            },
            loading: () => const SizedBox(),
            error: (_, __) => const SizedBox(),
          ),

          const SizedBox(height: 16),

          // TOP 3 미리보기
          const Text('TOP 3',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          screeningAsync.when(
            data: (run) {
              if (run == null || run.results.isEmpty) {
                return const Card(
                  child: Padding(
                    padding: EdgeInsets.all(16),
                    child: Text('스크리닝 결과 없음. 새로고침하세요.'),
                  ),
                );
              }
              final top3 = run.results.take(3).toList();
              return Column(
                children: top3.map((r) => Card(
                  child: ListTile(
                    leading: CircleAvatar(
                      backgroundColor: Colors.amber.shade700,
                      child: Text('${r.rank}',
                          style: const TextStyle(color: Colors.white)),
                    ),
                    title: Text('${r.flag} ${r.ticker}'),
                    subtitle: Text('Score: ${r.score.toStringAsFixed(3)}'),
                    trailing: Text('\$${r.price.toStringAsFixed(2)}',
                        style: const TextStyle(fontWeight: FontWeight.bold)),
                  ),
                )).toList(),
              );
            },
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Text('Error: $e'),
          ),
        ],
      ),
    );
  }

  String _daysUntil(String dateStr) {
    try {
      final target = DateTime.parse(dateStr);
      final days = target.difference(DateTime.now()).inDays;
      if (days < 0) return 'D+${-days}';
      if (days == 0) return 'D-Day';
      return 'D-$days';
    } catch (_) {
      return '';
    }
  }
}
