import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/short_squeeze_result.dart';
import '../providers/short_squeeze_provider.dart';

class ShortSqueezeScreen extends ConsumerWidget {
  const ShortSqueezeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      body: Column(
        children: [
          _MarketFilterBar(),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async => ref.invalidate(shortSqueezeProvider),
              child: _ResultList(),
            ),
          ),
        ],
      ),
    );
  }
}

// ── 마켓 필터 탭 ────────────────────────────────────────────

class _MarketFilterBar extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(shortSqueezeMarketFilterProvider);
    final notifier = ref.read(shortSqueezeMarketFilterProvider.notifier);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: SegmentedButton<ShortSqueezeMarketFilter>(
        segments: const [
          ButtonSegment(
            value: ShortSqueezeMarketFilter.all,
            label: Text('전체'),
            icon: Icon(Icons.public, size: 16),
          ),
          ButtonSegment(
            value: ShortSqueezeMarketFilter.us,
            label: Text('🇺🇸 US'),
          ),
          ButtonSegment(
            value: ShortSqueezeMarketFilter.kr,
            label: Text('🇰🇷 KR'),
          ),
        ],
        selected: {filter},
        onSelectionChanged: (s) => notifier.set(s.first),
        style: const ButtonStyle(
          visualDensity: VisualDensity.compact,
        ),
      ),
    );
  }
}

// ── 결과 리스트 ─────────────────────────────────────────────

class _ResultList extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filteredAsync = ref.watch(filteredShortSqueezeProvider);
    final dataAsync = ref.watch(shortSqueezeProvider);

    return filteredAsync.when(
      data: (results) {
        if (results.isEmpty) {
          return _buildEmpty(context);
        }
        // 상단 요약 정보 추출
        final data = dataAsync.asData?.value;
        return ListView.builder(
          padding: const EdgeInsets.only(bottom: 16),
          itemCount: results.length + 1,
          itemBuilder: (context, index) {
            if (index == 0) {
              return _SummaryHeader(data: data);
            }
            return _ShortSqueezeCard(result: results[index - 1]);
          },
        );
      },
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 48, color: Colors.grey),
            const SizedBox(height: 8),
            Text('데이터 로드 실패\n$e',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.grey)),
          ],
        ),
      ),
    );
  }

  Widget _buildEmpty(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.compress_outlined,
              size: 64,
              color: Theme.of(context).colorScheme.primary.withAlpha(100)),
          const SizedBox(height: 12),
          const Text('스크리닝 데이터 없음',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w500)),
          const SizedBox(height: 4),
          const Text('조건을 통과한 종목이 없거나 데이터가 아직 없습니다.',
              style: TextStyle(color: Colors.grey, fontSize: 13)),
        ],
      ),
    );
  }
}

// ── 상단 요약 헤더 ──────────────────────────────────────────

class _SummaryHeader extends StatelessWidget {
  final ShortSqueezeData? data;

  const _SummaryHeader({this.data});

  @override
  Widget build(BuildContext context) {
    if (data == null) return const SizedBox.shrink();
    final colorScheme = Theme.of(context).colorScheme;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
      child: Card(
        color: colorScheme.primaryContainer,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.compress_outlined,
                      color: colorScheme.onPrimaryContainer, size: 18),
                  const SizedBox(width: 6),
                  Text(
                    '숏스퀴즈 스크리닝',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: colorScheme.onPrimaryContainer,
                    ),
                  ),
                  const Spacer(),
                  Text(
                    _formatDate(data!.runDate),
                    style: TextStyle(
                        fontSize: 11,
                        color: colorScheme.onPrimaryContainer.withAlpha(180)),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _summaryItem(
                    label: 'US 통과',
                    value: '${data!.totalUsPassed}개',
                    sub: '/ ${data!.totalUsScreened}개 스크리닝',
                    color: colorScheme.onPrimaryContainer,
                  ),
                  Container(
                    width: 1,
                    height: 32,
                    color: colorScheme.onPrimaryContainer.withAlpha(50),
                  ),
                  _summaryItem(
                    label: 'KR 통과',
                    value: '${data!.totalKrPassed}개',
                    sub: '/ ${data!.totalKrScreened}개 스크리닝',
                    color: colorScheme.onPrimaryContainer,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _summaryItem({
    required String label,
    required String value,
    required String sub,
    required Color color,
  }) {
    return Column(
      children: [
        Text(label, style: TextStyle(fontSize: 11, color: color.withAlpha(180))),
        Text(value,
            style: TextStyle(
                fontWeight: FontWeight.bold, fontSize: 18, color: color)),
        Text(sub, style: TextStyle(fontSize: 10, color: color.withAlpha(150))),
      ],
    );
  }

  String _formatDate(String iso) {
    try {
      final dt = DateTime.parse(iso);
      return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-'
          '${dt.day.toString().padLeft(2, '0')}';
    } catch (_) {
      return iso;
    }
  }
}

// ── 종목 카드 ───────────────────────────────────────────────

class _ShortSqueezeCard extends StatelessWidget {
  final ShortSqueezeResult result;

  const _ShortSqueezeCard({required this.result});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final score = result.squeezeScore;

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            // 1행: 순위 + 종목명 + 점수
            Row(
              children: [
                _RankBadge(rank: result.rank, score: score),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${result.flag} ${result.displayName}',
                        style: const TextStyle(
                            fontWeight: FontWeight.bold, fontSize: 15),
                      ),
                      Text(
                        result.market == 'KR'
                            ? '${result.ticker} · ${result.sector}'
                            : result.sector,
                        style:
                            const TextStyle(fontSize: 11, color: Colors.grey),
                      ),
                    ],
                  ),
                ),
                // 점수 게이지
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    const Text('Squeeze Score',
                        style: TextStyle(fontSize: 10, color: Colors.grey)),
                    Text(
                      score.toStringAsFixed(1),
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 20,
                        color: _scoreColor(score, colorScheme),
                      ),
                    ),
                  ],
                ),
              ],
            ),
            const Divider(height: 14),
            // 2행: 핵심 지표
            result.market == 'US'
                ? _UsMetrics(result: result)
                : _KrMetrics(result: result),
          ],
        ),
      ),
    );
  }

  Color _scoreColor(double score, ColorScheme cs) {
    if (score >= 70) return Colors.red.shade600;
    if (score >= 40) return Colors.orange.shade700;
    return cs.primary;
  }
}

class _RankBadge extends StatelessWidget {
  final int rank;
  final double score;

  const _RankBadge({required this.rank, required this.score});

  @override
  Widget build(BuildContext context) {
    final color = score >= 70
        ? Colors.red.shade700
        : score >= 40
            ? Colors.orange.shade700
            : Colors.blue;

    return Container(
      width: 32,
      height: 32,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Center(
        child: Text(
          '$rank',
          style: const TextStyle(
              color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13),
        ),
      ),
    );
  }
}

// ── US 지표 행 ──────────────────────────────────────────────

class _UsMetrics extends StatelessWidget {
  final ShortSqueezeResult result;

  const _UsMetrics({required this.result});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceAround,
      children: [
        _metric(
          'SI%Float',
          result.siPctFloat != null
              ? '${result.siPctFloat!.toStringAsFixed(1)}%'
              : '-',
          highlight: (result.siPctFloat ?? 0) >= 20,
        ),
        _metric(
          'DTC',
          result.daysToCover != null
              ? '${result.daysToCover!.toStringAsFixed(1)}일'
              : '-',
          highlight: (result.daysToCover ?? 0) >= 10,
        ),
        _metric(
          'CTB',
          result.ctbRate != null
              ? '${result.ctbRate!.toStringAsFixed(1)}%'
              : '-',
          highlight: (result.ctbRate ?? 0) >= 10,
        ),
        _metric(
          'Vol5x',
          result.volRatio5d != null
              ? '${result.volRatio5d!.toStringAsFixed(1)}x'
              : '-',
          highlight: (result.volRatio5d ?? 0) >= 2.0,
        ),
        _metric(
          'Price',
          result.price != null
              ? '\$${result.price!.toStringAsFixed(2)}'
              : '-',
        ),
      ],
    );
  }

  Widget _metric(String label, String value, {bool highlight = false}) {
    return Column(
      children: [
        Text(label,
            style: const TextStyle(fontSize: 10, color: Colors.grey)),
        Text(
          value,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: highlight ? Colors.red.shade700 : null,
          ),
        ),
      ],
    );
  }
}

// ── KR 지표 행 ──────────────────────────────────────────────

class _KrMetrics extends StatelessWidget {
  final ShortSqueezeResult result;

  const _KrMetrics({required this.result});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceAround,
      children: [
        _metric(
          '잔고비율',
          result.siPct != null
              ? '${result.siPct!.toStringAsFixed(2)}%'
              : '-',
          highlight: (result.siPct ?? 0) >= 3.0,
        ),
        _metric(
          '공매도Vol',
          result.volRatio5dShort != null
              ? '${result.volRatio5dShort!.toStringAsFixed(1)}x'
              : '-',
          highlight: (result.volRatio5dShort ?? 0) >= 2.0,
        ),
        _metric(
          '전체Vol',
          result.volRatio5d != null
              ? '${result.volRatio5d!.toStringAsFixed(1)}x'
              : '-',
          highlight: (result.volRatio5d ?? 0) >= 2.0,
        ),
        _metric(
          '현재가',
          result.price != null
              ? '₩${result.price!.toStringAsFixed(0).replaceAllMapped(
                    RegExp(r'(\d)(?=(\d{3})+$)'),
                    (m) => '${m[1]},',
                  )}'
              : '-',
        ),
      ],
    );
  }

  Widget _metric(String label, String value, {bool highlight = false}) {
    return Column(
      children: [
        Text(label,
            style: const TextStyle(fontSize: 10, color: Colors.grey)),
        Text(
          value,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: highlight ? Colors.red.shade700 : null,
          ),
        ),
      ],
    );
  }
}
