import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/screening_provider.dart';
import '../widgets/stock_card.dart';

class ScreeningScreen extends ConsumerWidget {
  const ScreeningScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final screeningAsync = ref.watch(screeningProvider);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(screeningProvider.notifier).refresh();
        },
        child: screeningAsync.when(
          data: (run) {
            if (run == null || run.results.isEmpty) {
              return const Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.search_off, size: 64, color: Colors.grey),
                    SizedBox(height: 16),
                    Text('스크리닝 결과가 없습니다',
                        style: TextStyle(fontSize: 16, color: Colors.grey)),
                    SizedBox(height: 8),
                    Text('아래 버튼을 눌러 스크리닝을 실행하세요',
                        style: TextStyle(color: Colors.grey)),
                  ],
                ),
              );
            }
            return ListView(
              children: [
                Padding(
                  padding: const EdgeInsets.all(16),
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
                ...run.results.map((r) => StockCard(result: r)),
                const SizedBox(height: 80),
              ],
            );
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
}
