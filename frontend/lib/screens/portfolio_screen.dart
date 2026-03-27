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
  bool _showKrw = true; // true: 원화(₩), false: 달러($)

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
    final portfolioAsync = ref.watch(portfolioDataProvider);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(holdingsProvider.notifier).refresh();
          ref.invalidate(portfolioDataProvider);
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
                // ── 포트폴리오 요약 카드 ──────────────────────────
                portfolioAsync.when(
                  data: (portfolio) => portfolio != null
                      ? _buildSummaryCard(portfolio)
                      : const SizedBox.shrink(),
                  loading: () => const Padding(
                    padding: EdgeInsets.all(16),
                    child: LinearProgressIndicator(),
                  ),
                  error: (_, __) => const SizedBox.shrink(),
                ),
                // ── 헤더 ──────────────────────────────────────────
                Padding(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 16, vertical: 8),
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
                              style: const TextStyle(
                                  fontWeight: FontWeight.bold)),
                          subtitle: Text(
                              '진입가: \$${h.entryPrice.toStringAsFixed(2)}  |  '
                              '날짜: ${h.entryDate}'),
                          trailing: _stopLoaded
                              ? _stopResults.containsKey(h.ticker)
                                  ? StopLossIndicator(
                                      marginPct: _stopResults[h.ticker]!
                                          .marginPct)
                                  : const StopLossIndicator(marginPct: -1)
                              : const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(
                                      strokeWidth: 2),
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

  Widget _buildSummaryCard(PortfolioData portfolio) {
    final isKrw = _showKrw;
    final invested = isKrw
        ? portfolio.totalInvestedKrw
        : portfolio.totalInvestedUsd;
    final current = isKrw
        ? portfolio.totalCurrentKrw
        : portfolio.totalCurrentUsd;
    final returnPct = portfolio.totalReturnPct;
    final profit = current - invested;
    final isPositive = profit >= 0;

    String fmtAmount(double v) {
      if (isKrw) {
        if (v >= 100000000) {
          return '₩${(v / 100000000).toStringAsFixed(1)}억';
        } else if (v >= 10000) {
          return '₩${(v / 10000).toStringAsFixed(0)}만';
        }
        return '₩${v.toStringAsFixed(0)}';
      } else {
        return '\$${v.toStringAsFixed(2)}';
      }
    }

    return Card(
      margin: const EdgeInsets.fromLTRB(16, 16, 16, 4),
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 헤더: 타이틀 + 통화 토글
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('포트폴리오 요약',
                    style: TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold)),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _CurrencyToggleButton(
                      label: '₩',
                      selected: _showKrw,
                      onTap: () => setState(() => _showKrw = true),
                    ),
                    const SizedBox(width: 4),
                    _CurrencyToggleButton(
                      label: '\$',
                      selected: !_showKrw,
                      onTap: () => setState(() => _showKrw = false),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 12),
            // 투자금 / 평가금
            Row(
              children: [
                Expanded(
                  child: _SummaryItem(
                    label: '총 투자금액',
                    value: fmtAmount(invested),
                  ),
                ),
                Expanded(
                  child: _SummaryItem(
                    label: '현재 평가금액',
                    value: fmtAmount(current),
                    valueColor: isPositive ? Colors.red : Colors.blue,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            // 손익 / 수익률
            Row(
              children: [
                Expanded(
                  child: _SummaryItem(
                    label: '손익',
                    value:
                        '${isPositive ? '+' : ''}${fmtAmount(profit)}',
                    valueColor: isPositive ? Colors.red : Colors.blue,
                  ),
                ),
                Expanded(
                  child: _SummaryItem(
                    label: '수익률',
                    value:
                        '${returnPct >= 0 ? '+' : ''}${returnPct.toStringAsFixed(2)}%',
                    valueColor: returnPct >= 0 ? Colors.red : Colors.blue,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            // 환율 정보
            Text(
              '환율 USD/KRW: ${portfolio.usdkrw.toStringAsFixed(0)}원',
              style: const TextStyle(fontSize: 11, color: Colors.grey),
            ),
          ],
        ),
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
                style:
                    TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
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
                final ticker =
                    tickerController.text.trim().toUpperCase();
                final price =
                    double.tryParse(priceController.text.trim());
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

      final breaches =
          data.where((r) => r.eventType == 'BREACH').toList();
      final warnings =
          data.where((r) => r.eventType == 'WARNING').toList();

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

class _CurrencyToggleButton extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _CurrencyToggleButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        decoration: BoxDecoration(
          color: selected ? colorScheme.primary : Colors.transparent,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selected ? colorScheme.primary : Colors.grey,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.bold,
            color: selected ? colorScheme.onPrimary : Colors.grey,
          ),
        ),
      ),
    );
  }
}

class _SummaryItem extends StatelessWidget {
  final String label;
  final String value;
  final Color? valueColor;

  const _SummaryItem({
    required this.label,
    required this.value,
    this.valueColor,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: const TextStyle(fontSize: 11, color: Colors.grey)),
        const SizedBox(height: 2),
        Text(
          value,
          style: TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.bold,
            color: valueColor,
          ),
        ),
      ],
    );
  }
}
