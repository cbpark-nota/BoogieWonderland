import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/serverless_providers.dart';
import '../theme/app_colors.dart';

class MarketCapScreen extends ConsumerWidget {
  const MarketCapScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dataAsync = ref.watch(marketCapTop20Provider);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(marketCapTop20Provider),
        child: dataAsync.when(
          data: (data) {
            if (data == null) return _buildEmpty(context);
            return _buildContent(context, data);
          },
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => _buildEmpty(context),
        ),
      ),
    );
  }

  Widget _buildEmpty(BuildContext context) {
    return ListView(
      children: [
        SizedBox(height: MediaQuery.of(context).size.height * 0.4),
        const Center(
          child: Column(
            children: [
              Icon(Icons.bar_chart, size: 64, color: AppColors.mutedText),
              SizedBox(height: 16),
              Text(
                '시총 Top 20 데이터 없음',
                style: TextStyle(fontSize: 16, color: AppColors.mutedText),
              ),
              SizedBox(height: 8),
              Text(
                'GitHub Actions 실행 후 데이터가 생성됩니다.',
                style: TextStyle(fontSize: 13, color: AppColors.mutedText),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildContent(BuildContext context, Map<String, dynamic> data) {
    final rawTop20 = data['top20'] ?? data['results'] ?? [];
    final top20 = (rawTop20 as List).cast<Map<String, dynamic>>();
    final sectorDist = (data['sector_distribution'] as List? ?? [])
        .cast<Map<String, dynamic>>();
    final updatedAt =
        data['updated_at'] as String? ?? data['generated_at'] as String? ?? '';
    final note = data['note'] as String? ?? '';

    final newEntrants = top20
        .where((r) => r['is_new_entrant'] == true)
        .toList();

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // 헤더 카드
        _HeaderCard(updatedAt: updatedAt, note: note),
        const SizedBox(height: 12),

        // 신규 진입 하이라이트
        if (newEntrants.isNotEmpty) ...[
          _NewEntrantsCard(newEntrants: newEntrants),
          const SizedBox(height: 12),
        ],

        // 섹터 분포
        if (sectorDist.isNotEmpty) ...[
          _SectorDistCard(sectorDist: sectorDist, total: top20.length),
          const SizedBox(height: 12),
        ],

        // Top 20 종목 목록
        const Padding(
          padding: EdgeInsets.only(bottom: 8),
          child: Text(
            '시총 Top 20',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
        ),
        ...top20.map(
          (r) => _MarketCapTile(item: r, fallbackEnteredAt: updatedAt),
        ),
        const SizedBox(height: 80),
      ],
    );
  }
}

class _HeaderCard extends StatelessWidget {
  final String updatedAt;
  final String note;

  const _HeaderCard({required this.updatedAt, required this.note});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Card(
      color: colorScheme.primaryContainer.withValues(alpha: 0.4),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.trending_up, color: colorScheme.primary, size: 20),
                const SizedBox(width: 8),
                Text(
                  '시장 트렌드 모니터링',
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.bold,
                    color: colorScheme.primary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              note.isNotEmpty ? note : '매매 전략이 아닌 시장 트렌드 모니터링 참고 도구입니다.',
              style: TextStyle(
                fontSize: 12,
                color: colorScheme.onSurfaceVariant,
                height: 1.4,
              ),
            ),
            if (updatedAt.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                '업데이트: ${updatedAt.length >= 10 ? updatedAt.substring(0, 10) : updatedAt}',
                style: TextStyle(
                  fontSize: 11,
                  color: colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _NewEntrantsCard extends StatelessWidget {
  final List<Map<String, dynamic>> newEntrants;

  const _NewEntrantsCard({required this.newEntrants});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: AppColors.amberSubtle,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(
                  Icons.new_releases_outlined,
                  color: AppColors.amber,
                  size: 18,
                ),
                const SizedBox(width: 6),
                Text(
                  '신규 Top 20 진입 (${newEntrants.length}개)',
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                    color: AppColors.amber,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: newEntrants.map((r) {
                final ticker = r['ticker'] as String? ?? '';
                final sector = r['sector'] as String? ?? '';
                return Chip(
                  backgroundColor: AppColors.amberLight,
                  label: Text(
                    '$ticker ($sector)',
                    style: const TextStyle(fontSize: 12),
                  ),
                  padding: EdgeInsets.zero,
                );
              }).toList(),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectorDistCard extends StatelessWidget {
  final List<Map<String, dynamic>> sectorDist;
  final int total;

  const _SectorDistCard({required this.sectorDist, required this.total});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  Icons.pie_chart_outline,
                  color: colorScheme.secondary,
                  size: 18,
                ),
                const SizedBox(width: 6),
                const Text(
                  '섹터 분포',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                ),
              ],
            ),
            const SizedBox(height: 10),
            ...sectorDist.map((s) {
              final sector = s['sector'] as String? ?? '';
              final count = (s['count'] as num?)?.toInt() ?? 0;
              final pct = total > 0 ? count / total : 0.0;
              return Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Expanded(
                          child: Text(
                            sector,
                            style: const TextStyle(fontSize: 12),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        Text(
                          '$count개  ${(pct * 100).toStringAsFixed(0)}%',
                          style: const TextStyle(
                            fontSize: 12,
                            color: AppColors.mutedText,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 3),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(3),
                      child: LinearProgressIndicator(
                        value: pct,
                        minHeight: 6,
                        backgroundColor: colorScheme.surfaceContainerHighest,
                        valueColor: AlwaysStoppedAnimation<Color>(
                          colorScheme.secondary,
                        ),
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}

class _MarketCapTile extends StatelessWidget {
  final Map<String, dynamic> item;
  final String fallbackEnteredAt;

  const _MarketCapTile({required this.item, required this.fallbackEnteredAt});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final rank = (item['rank'] as num?)?.toInt() ?? 0;
    final ticker = item['ticker'] as String? ?? '';
    final mcB =
        ((item['market_cap_b'] ?? item['market_cap']) as num?)?.toDouble() ?? 0;
    final sector = item['sector'] as String? ?? '';
    final isNew = item['is_new_entrant'] == true;
    final enteredAt = (item['entered_at'] as String?)?.trim();
    final displayEnteredAt = enteredAt?.isNotEmpty == true
        ? enteredAt!
        : _dateOnly(fallbackEnteredAt);

    return Card(
      margin: const EdgeInsets.only(bottom: 6),
      color: isNew ? AppColors.amberSubtle : colorScheme.surfaceContainerLowest,
      child: ListTile(
        dense: true,
        leading: SizedBox(
          width: 32,
          child: Text(
            '#$rank',
            style: TextStyle(
              fontWeight: FontWeight.bold,
              fontSize: 14,
              color: rank <= 3 ? colorScheme.primary : AppColors.mutedText,
            ),
            textAlign: TextAlign.center,
          ),
        ),
        title: Row(
          children: [
            Text(
              ticker,
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
            ),
            if (isNew) ...[
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                decoration: BoxDecoration(
                  color: AppColors.amber,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Text(
                  'NEW',
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                ),
              ),
            ],
          ],
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              sector,
              style: const TextStyle(fontSize: 11, color: AppColors.mutedText),
            ),
            const SizedBox(height: 2),
            Text(
              displayEnteredAt.isEmpty
                  ? 'Top 20 진입일 기록 없음'
                  : 'Top 20 진입: $displayEnteredAt',
              style: const TextStyle(fontSize: 11, color: AppColors.mutedText),
            ),
          ],
        ),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(
              '\$${_formatBillion(mcB)}',
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
            ),
            const Text(
              '시총(B)',
              style: TextStyle(fontSize: 10, color: AppColors.mutedText),
            ),
          ],
        ),
      ),
    );
  }

  String _formatBillion(double b) {
    if (b >= 1000) {
      return '${(b / 1000).toStringAsFixed(1)}T';
    }
    return '${b.toStringAsFixed(0)}B';
  }

  String _dateOnly(String value) {
    if (value.length >= 10) {
      return value.substring(0, 10);
    }
    return value;
  }
}
