import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../config/app_config.dart';
import '../models/screening_result.dart';
import '../providers/screening_provider.dart';
import '../providers/market_filter_provider.dart';
import '../providers/serverless_providers.dart';
import '../widgets/stock_card.dart';
import '../theme/app_colors.dart';

// 3전략 세그먼트 버튼 설정
const _kMainStrategies = [
  StrategyType.aggressive,
  StrategyType.balanced,
  StrategyType.conservative,
];

// 세그먼트 버튼에 표시할 짧은 라벨
const _kStrategyShortLabel = {
  StrategyType.aggressive: '공격적',
  StrategyType.balanced: '균형',
  StrategyType.conservative: '보수적',
};

// 세그먼트 버튼에 표시할 파라미터 라벨
const _kStrategyParamLabel = {
  StrategyType.aggressive: 'ATR×1.5 / TOP 15',
  StrategyType.balanced: 'ATR×2.0 / TOP 10',
  StrategyType.conservative: 'ATR×2.5 / TOP 7',
};

class ScreeningScreen extends ConsumerWidget {
  const ScreeningScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (AppConfig.isServerless) {
      return _buildServerlessView(context, ref);
    }
    return _buildFullstackView(context, ref);
  }

  // ── 서버리스 모드: 4전략 탭 ──

  Widget _buildServerlessView(BuildContext context, WidgetRef ref) {
    final filteredAsync = ref.watch(filteredScreeningProvider);
    final sortOrder = ref.watch(sortOrderProvider);

    return Scaffold(
      body: Column(
        children: [
          _buildDateSelector(context, ref),
          _buildStrategySelector(context, ref),
          _buildMarketAndSortRow(context, ref),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async {
                ref.invalidate(strategyDataProvider);
                ref.invalidate(historyScreeningProvider);
                ref.invalidate(historyDatesProvider);
              },
              child: filteredAsync.when(
                data: (result) {
                  if (result == null) return _buildEmpty();
                  return _buildResultList(
                      result.run, result.sr, result.selected, sortOrder);
                },
                loading: () =>
                    const Center(child: CircularProgressIndicator()),
                error: (e, _) => Center(child: Text('오류: $e')),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ── 날짜 선택 바 ──

  Widget _buildDateSelector(BuildContext context, WidgetRef ref) {
    final datesAsync = ref.watch(historyDatesProvider);
    final selectedDate = ref.watch(selectedHistoryDateProvider);

    return datesAsync.when(
      data: (dates) {
        if (dates.isEmpty) return const SizedBox.shrink();
        // 스크리닝 페이지는 최근 5일만 표시 (히스토리는 30일 저장되지만 UI는 5일)
        final displayDates = dates.take(5).toList();
        // null = 최신(오늘) / 5일 범위 밖 날짜 선택 시 최신으로 fallback
        final effectiveDate =
            (selectedDate != null && displayDates.contains(selectedDate))
                ? selectedDate!
                : displayDates.first;
        final idx = displayDates.indexOf(effectiveDate);

        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          color: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.31),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton(
                icon: const Icon(Icons.chevron_left),
                iconSize: 20,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
                onPressed: idx < displayDates.length - 1
                    ? () => ref
                        .read(selectedHistoryDateProvider.notifier)
                        .state = displayDates[idx + 1]
                    : null,
              ),
              const SizedBox(width: 4),
              DropdownButton<String>(
                value: effectiveDate,
                underline: const SizedBox.shrink(),
                isDense: true,
                items: displayDates.map((d) {
                  final isLatest = d == displayDates.first;
                  return DropdownMenuItem(
                    value: d,
                    child: Text(
                      isLatest ? '$d (최신)' : d,
                      style: const TextStyle(fontSize: 13),
                    ),
                  );
                }).toList(),
                onChanged: (d) {
                  ref.read(selectedHistoryDateProvider.notifier).state = d;
                },
              ),
              const SizedBox(width: 4),
              IconButton(
                icon: const Icon(Icons.chevron_right),
                iconSize: 20,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
                onPressed: idx > 0
                    ? () => ref
                        .read(selectedHistoryDateProvider.notifier)
                        .state = displayDates[idx - 1]
                    : null,
              ),
            ],
          ),
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, __) => const SizedBox.shrink(),
    );
  }

  // ── 풀스택 모드: 기존 화면 ──

  Widget _buildFullstackView(BuildContext context, WidgetRef ref) {
    final screeningAsync = ref.watch(screeningProvider);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(screeningProvider.notifier).refresh();
        },
        child: screeningAsync.when(
          data: (run) {
            if (run == null || run.results.isEmpty) return _buildEmpty();
            return _buildResultList(
                run, null, StrategyType.balanced, SortOrder.rank);
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

  // ── 전략 선택 바 (3전략 세그먼트: 공격적/균형/보수적) ──

  Widget _buildStrategySelector(BuildContext context, WidgetRef ref) {
    final selected = ref.watch(selectedStrategyProvider);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      child: Row(
        children: _kMainStrategies.map((st) {
          final isSelected = st == selected;
          return Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 3),
              child: GestureDetector(
                onTap: () =>
                    ref.read(selectedStrategyProvider.notifier).state = st,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  padding:
                      const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
                  decoration: BoxDecoration(
                    color: isSelected
                        ? _chipColor(st)
                        : Theme.of(context)
                            .colorScheme
                            .surfaceContainerHighest
                            .withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: isSelected
                          ? _chipColor(st)
                          : Theme.of(context).colorScheme.outlineVariant,
                      width: isSelected ? 0 : 1,
                    ),
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        _kStrategyShortLabel[st] ?? st.label,
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 13,
                          color: isSelected
                              ? Colors.white
                              : Theme.of(context).colorScheme.onSurface,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        _kStrategyParamLabel[st] ?? st.description,
                        style: TextStyle(
                          fontSize: 10,
                          color: isSelected
                              ? Colors.white.withValues(alpha: 0.85)
                              : AppColors.mutedText,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  // ── 국가 필터 + 정렬 옵션 한 줄 ──

  Widget _buildMarketAndSortRow(BuildContext context, WidgetRef ref) {
    final marketFilter = ref.watch(selectedMarketFilterProvider);
    final sortOrder = ref.watch(sortOrderProvider);
    const countries = [MarketFilter.us, MarketFilter.kr];

    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 0, 8, 6),
      child: Row(
        children: [
          // 국가 필터
          ...countries.map((f) {
            final isSelected = f == marketFilter;
            final label = f == MarketFilter.kr ? '🇰🇷 한국' : '🇺🇸 미국';
            return Padding(
              padding: const EdgeInsets.only(right: 6),
              child: ChoiceChip(
                label: Text(label,
                    style: TextStyle(
                        fontSize: 12,
                        fontWeight:
                            isSelected ? FontWeight.bold : FontWeight.normal)),
                selected: isSelected,
                onSelected: (_) {
                  ref.read(selectedMarketFilterProvider.notifier).state = f;
                  ref.read(selectedHistoryDateProvider.notifier).state = null;
                },
                selectedColor: f == MarketFilter.kr
                    ? AppColors.priceDownStrong
                    : AppColors.infoStrong,
                labelStyle:
                    TextStyle(color: isSelected ? Colors.white : null),
                visualDensity: VisualDensity.compact,
              ),
            );
          }),
          const Spacer(),
          // 정렬 옵션
          _sortButton(
            context: context,
            icon: Icons.format_list_numbered,
            label: '순위',
            isSelected: sortOrder == SortOrder.rank,
            onTap: () => ref.read(sortOrderProvider.notifier).state =
                SortOrder.rank,
          ),
          const SizedBox(width: 4),
          _sortButton(
            context: context,
            icon: Icons.sort_by_alpha,
            label: '알파벳',
            isSelected: sortOrder == SortOrder.alphabetical,
            onTap: () => ref.read(sortOrderProvider.notifier).state =
                SortOrder.alphabetical,
          ),
        ],
      ),
    );
  }

  Widget _sortButton({
    required BuildContext context,
    required IconData icon,
    required String label,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    final color = isSelected
        ? Theme.of(context).colorScheme.primary
        : Theme.of(context).colorScheme.onSurfaceVariant;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: isSelected
              ? Theme.of(context)
                  .colorScheme
                  .primaryContainer
                  .withValues(alpha: 0.6)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(
            color: isSelected
                ? Theme.of(context).colorScheme.primary
                : Theme.of(context).colorScheme.outlineVariant,
            width: 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 14, color: color),
            const SizedBox(width: 3),
            Text(label,
                style: TextStyle(
                    fontSize: 11,
                    fontWeight:
                        isSelected ? FontWeight.bold : FontWeight.normal,
                    color: color)),
          ],
        ),
      ),
    );
  }

  Color _chipColor(StrategyType st) {
    switch (st) {
      case StrategyType.aggressive:
        return AppColors.priceDownMid;
      case StrategyType.balanced:
        return AppColors.infoMid;
      case StrategyType.conservative:
        return AppColors.rankGold;
      case StrategyType.adaptive:
        return AppColors.brandAccentStrong;
    }
  }

  // ── 결과 리스트 ──

  Widget _buildResultList(ScreeningRun run, StrategyResult? sr,
      StrategyType selected, SortOrder sortOrder) {
    if (run.results.isEmpty) return _buildEmpty();

    final sorted = List<ScreeningResult>.from(run.results);
    if (sortOrder == SortOrder.alphabetical) {
      sorted.sort((a, b) => a.ticker.compareTo(b.ticker));
    } else {
      sorted.sort((a, b) => a.rank.compareTo(b.rank));
    }

    return ListView(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('TOP ${run.results.length}',
                  style: const TextStyle(
                      fontSize: 20, fontWeight: FontWeight.bold)),
              Text('${run.totalPassed}/${run.totalScreened} 통과',
                  style: const TextStyle(color: AppColors.mutedText)),
            ],
          ),
        ),
        if (sr != null) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
            child: Row(
              children: [
                _infoChip('ATR ${sr.atrMult}',
                    color: _chipColor(selected)),
                const SizedBox(width: 8),
                _infoChip(sr.rebalFreq,
                    color: _chipColor(selected)),
                if (sr.currentRegime != null) ...[
                  const SizedBox(width: 8),
                  _infoChip('국면: ${sr.currentRegime}',
                      color: AppColors.brandAccentStrong),
                ],
              ],
            ),
          ),
        ],
        ...sorted.map((r) => StockCard(result: r)),
        const SizedBox(height: 80),
      ],
    );
  }

  Widget _infoChip(String text, {Color? color}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color ?? AppColors.dividerLight,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(text,
          style: const TextStyle(fontSize: 11, color: Colors.black)),
    );
  }

  Widget _buildEmpty() {
    return ListView(
      children: const [
        SizedBox(height: 200),
        Center(
          child: Column(
            children: [
              Icon(Icons.search_off, size: 64, color: AppColors.mutedText),
              SizedBox(height: 16),
              Text('스크리닝 결과가 없습니다',
                  style: TextStyle(fontSize: 16, color: AppColors.mutedText)),
            ],
          ),
        ),
      ],
    );
  }
}
