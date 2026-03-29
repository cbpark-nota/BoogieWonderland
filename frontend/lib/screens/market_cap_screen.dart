import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/market_cap_data.dart';
import '../providers/market_cap_provider.dart';

class MarketCapScreen extends ConsumerStatefulWidget {
  const MarketCapScreen({super.key});

  @override
  ConsumerState<MarketCapScreen> createState() => _MarketCapScreenState();
}

enum _MarketFilter { all, us, kr }

class _MarketCapScreenState extends ConsumerState<MarketCapScreen> {
  _MarketFilter _filter = _MarketFilter.all;
  bool _showNewOnly = false;

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(marketCapProvider);

    return Scaffold(
      body: async.when(
        data: (data) {
          if (data == null) return _buildEmpty();
          return _buildContent(data);
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
              const SizedBox(height: 8),
              Text('데이터 없음\n(market_cap.json 미생성)',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.grey)),
              const SizedBox(height: 12),
              TextButton.icon(
                onPressed: () => ref.invalidate(marketCapProvider),
                icon: const Icon(Icons.refresh),
                label: const Text('새로고침'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildContent(MarketCapData data) {
    final allEntries = [
      if (_filter != _MarketFilter.kr) ...data.usTop20,
      if (_filter != _MarketFilter.us) ...data.krTop20,
    ];
    final entries = _showNewOnly
        ? allEntries.where((e) => e.isNewEntrant).toList()
        : allEntries;
    final newCount = data.allNewEntrants.length;

    return Column(
      children: [
        _buildHeader(data, newCount),
        _buildFilterBar(),
        Expanded(
          child: RefreshIndicator(
            onRefresh: () async => ref.invalidate(marketCapProvider),
            child: entries.isEmpty
                ? _buildEmptyFiltered()
                : ListView.builder(
                    padding: const EdgeInsets.only(bottom: 16),
                    itemCount: entries.length,
                    itemBuilder: (ctx, i) => _buildEntryCard(ctx, entries[i]),
                  ),
          ),
        ),
      ],
    );
  }

  Widget _buildHeader(MarketCapData data, int newCount) {
    final colorScheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
      child: Row(
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '시총 Top 20',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold),
              ),
              Text(
                '업데이트: ${data.runDate}',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Colors.grey),
              ),
            ],
          ),
          const Spacer(),
          if (newCount > 0)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.orange.shade700,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                '★ 신규 $newCount종목',
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 12,
                    fontWeight: FontWeight.bold),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildFilterBar() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      child: Row(
        children: [
          // 시장 필터
          ..._MarketFilter.values.map((f) {
            final label = switch (f) {
              _MarketFilter.all => '전체',
              _MarketFilter.us => '🇺🇸 US',
              _MarketFilter.kr => '🇰🇷 KR',
            };
            final isSelected = f == _filter;
            return Padding(
              padding: const EdgeInsets.only(right: 6),
              child: ChoiceChip(
                label: Text(label,
                    style: TextStyle(
                        fontSize: 12,
                        fontWeight:
                            isSelected ? FontWeight.bold : FontWeight.normal)),
                selected: isSelected,
                onSelected: (_) => setState(() => _filter = f),
                selectedColor: Colors.teal.shade600,
                labelStyle: TextStyle(color: isSelected ? Colors.white : null),
              ),
            );
          }),
          const Spacer(),
          // 신규만 보기 토글
          FilterChip(
            label: const Text('신규만', style: TextStyle(fontSize: 12)),
            selected: _showNewOnly,
            onSelected: (v) => setState(() => _showNewOnly = v),
            selectedColor: Colors.orange.shade600,
            labelStyle:
                TextStyle(color: _showNewOnly ? Colors.white : null),
          ),
        ],
      ),
    );
  }

  Widget _buildEntryCard(BuildContext context, MarketCapEntry entry) {
    final isNew = entry.isNewEntrant;
    final colorScheme = Theme.of(context).colorScheme;

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      elevation: isNew ? 3 : 1,
      color: isNew ? Colors.orange.shade50 : null,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: isNew
            ? BorderSide(color: Colors.orange.shade400, width: 1.5)
            : BorderSide.none,
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        child: Row(
          children: [
            // 순위
            SizedBox(
              width: 32,
              child: Text(
                '${entry.rank}',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: entry.rank <= 3
                      ? Colors.amber.shade700
                      : colorScheme.onSurface.withValues(alpha: 0.6),
                ),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(width: 8),
            // 국기 + 티커
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(entry.flag, style: const TextStyle(fontSize: 14)),
                      const SizedBox(width: 4),
                      Text(
                        entry.ticker,
                        style: const TextStyle(
                            fontWeight: FontWeight.bold, fontSize: 14),
                      ),
                      if (isNew) ...[
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 6, vertical: 1),
                          decoration: BoxDecoration(
                            color: Colors.orange.shade700,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: const Text(
                            'NEW',
                            style: TextStyle(
                                color: Colors.white,
                                fontSize: 10,
                                fontWeight: FontWeight.bold),
                          ),
                        ),
                      ],
                    ],
                  ),
                  if (entry.capBillion != null && entry.capBillion! > 0)
                    Text(
                      entry.capDisplay,
                      style: TextStyle(
                          fontSize: 11,
                          color: colorScheme.onSurface.withValues(alpha: 0.6)),
                    ),
                ],
              ),
            ),
            // 가격 + 스톱로스
            if (entry.currentPrice != null)
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    '${entry.currencySymbol}${_formatPrice(entry.currentPrice!, entry.market)}',
                    style: const TextStyle(
                        fontWeight: FontWeight.w600, fontSize: 13),
                  ),
                  if (entry.stopPrice != null && entry.stopDistPct != null)
                    Text(
                      '스톱 ${entry.stopDistPct!.toStringAsFixed(1)}%',
                      style: TextStyle(
                          fontSize: 11,
                          color: entry.stopDistPct! < 5
                              ? Colors.red.shade400
                              : Colors.grey),
                    ),
                ],
              ),
          ],
        ),
      ),
    );
  }

  String _formatPrice(double price, String market) {
    if (market == 'KR') {
      if (price >= 1000) return price.toStringAsFixed(0);
      return price.toStringAsFixed(0);
    }
    if (price >= 1000) return price.toStringAsFixed(0);
    return price.toStringAsFixed(2);
  }

  Widget _buildEmpty() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.bar_chart, size: 64, color: Colors.grey),
          const SizedBox(height: 12),
          Text(
            '시총 Top 20 데이터 없음',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                color: Colors.grey),
          ),
          const SizedBox(height: 8),
          const Text(
            'python scripts/export_json.py --market-cap\n을 실행해 데이터를 생성하세요.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey, fontSize: 13),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyFiltered() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.search_off, size: 48, color: Colors.grey),
          const SizedBox(height: 8),
          Text(
            _showNewOnly ? '신규 진입 종목이 없습니다' : '해당 시장 데이터 없음',
            style: const TextStyle(color: Colors.grey),
          ),
        ],
      ),
    );
  }
}
