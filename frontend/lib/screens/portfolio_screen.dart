import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/holding.dart';
import '../providers/portfolio_provider.dart';
import '../widgets/stop_loss_indicator.dart';

class PortfolioScreen extends ConsumerStatefulWidget {
  const PortfolioScreen({super.key});

  @override
  ConsumerState<PortfolioScreen> createState() => _PortfolioScreenState();
}

class _PortfolioScreenState extends ConsumerState<PortfolioScreen> {
  Map<String, StopCheckResult> _stopResults = {};
  bool _stopLoaded = false;

  @override
  void initState() {
    super.initState();
    _loadStopData();
  }

  Future<void> _loadStopData() async {
    try {
      final data = await ref.read(stopCheckProvider(null).future);
      if (mounted) {
        setState(() {
          _stopResults = {for (final r in data) r.ticker: r};
          _stopLoaded = true;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _stopLoaded = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final holdingsAsync = ref.watch(holdingsProvider);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(holdingsProvider.notifier).refresh();
        },
        child: holdingsAsync.when(
          data: (holdings) {
            if (holdings.isEmpty) {
              return const Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.account_balance_wallet_outlined,
                        size: 64, color: Colors.grey),
                    SizedBox(height: 16),
                    Text('보유 종목이 없습니다',
                        style: TextStyle(fontSize: 16, color: Colors.grey)),
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
                      Text('보유 종목 (${holdings.length})',
                          style: const TextStyle(
                              fontSize: 20, fontWeight: FontWeight.bold)),
                      TextButton.icon(
                        onPressed: () => _checkStops(),
                        icon: const Icon(Icons.shield, size: 18),
                        label: const Text('스톱 체크'),
                      ),
                    ],
                  ),
                ),
                ...holdings.map((h) => Dismissible(
                      key: Key(h.ticker),
                      direction: DismissDirection.endToStart,
                      background: Container(
                        color: Colors.red,
                        alignment: Alignment.centerRight,
                        padding: const EdgeInsets.only(right: 16),
                        child: const Icon(Icons.delete, color: Colors.white),
                      ),
                      onDismissed: (_) async {
                        await ref
                            .read(holdingsProvider.notifier)
                            .removeHolding(h.ticker);
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text('${h.ticker} 제거됨')),
                          );
                        }
                      },
                      child: Card(
                        margin: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 4),
                        child: ListTile(
                          title: Text(h.ticker,
                              style:
                                  const TextStyle(fontWeight: FontWeight.bold)),
                          subtitle: Text(
                              '진입가: \$${h.entryPrice.toStringAsFixed(2)}  |  '
                              '날짜: ${h.entryDate}'),
                          trailing: _stopLoaded
                              ? _stopResults.containsKey(h.ticker)
                                  ? StopLossIndicator(
                                      marginPct:
                                          _stopResults[h.ticker]!.marginPct)
                                  : const StopLossIndicator(marginPct: -1)
                              : const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child:
                                      CircularProgressIndicator(strokeWidth: 2),
                                ),
                        ),
                      ),
                    )),
                const SizedBox(height: 80),
              ],
            );
          },
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text('오류: $e')),
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showAddDialog(),
        child: const Icon(Icons.add),
      ),
    );
  }

  void _showAddDialog() {
    final tickerController = TextEditingController();
    final priceController = TextEditingController();

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(ctx).viewInsets.bottom,
          left: 16,
          right: 16,
          top: 16,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('종목 추가',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 16),
            TextField(
              controller: tickerController,
              decoration: const InputDecoration(
                labelText: '티커',
                hintText: 'NVDA',
                border: OutlineInputBorder(),
              ),
              textCapitalization: TextCapitalization.characters,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: priceController,
              decoration: const InputDecoration(
                labelText: '진입가',
                hintText: '130.50',
                border: OutlineInputBorder(),
              ),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () async {
                final ticker = tickerController.text.trim().toUpperCase();
                final price = double.tryParse(priceController.text.trim());
                if (ticker.isEmpty || price == null) return;

                try {
                  await ref
                      .read(holdingsProvider.notifier)
                      .addHolding(ticker, price);
                  if (ctx.mounted) Navigator.pop(ctx);
                } catch (e) {
                  if (ctx.mounted) {
                    ScaffoldMessenger.of(ctx).showSnackBar(
                      SnackBar(content: Text('추가 실패: $e')),
                    );
                  }
                }
              },
              child: const Text('추가'),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }

  void _checkStops() async {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('스톱로스 체크 중...')),
    );
    setState(() => _stopLoaded = false);
    try {
      ref.invalidate(stopCheckProvider(null));
      final data = await ref.read(stopCheckProvider(null).future);
      if (!mounted) return;

      setState(() {
        _stopResults = {for (final r in data) r.ticker: r};
        _stopLoaded = true;
      });

      final breaches = data.where((r) => r.eventType == 'BREACH').toList();
      final warnings = data.where((r) => r.eventType == 'WARNING').toList();

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
              '체크 완료: ${breaches.length}건 이탈, ${warnings.length}건 경고'),
          duration: const Duration(seconds: 3),
        ),
      );
    } catch (e) {
      if (mounted) {
        setState(() => _stopLoaded = true);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('체크 실패: $e')),
        );
      }
    }
  }
}
