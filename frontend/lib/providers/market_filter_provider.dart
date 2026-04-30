import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/screening_result.dart';
import 'serverless_providers.dart';

// ── 마켓 필터 enum (국가 선택) ────────────────────────────────
// v3.2: us/kr 두 값만 존재. all 제거됨.
enum MarketFilter { kr, us }

// ── 정렬 순서 enum ─────────────────────────────────────────
enum SortOrder { rank, alphabetical }

class _SortOrderNotifier extends Notifier<SortOrder> {
  @override
  SortOrder build() => SortOrder.rank;
}

final sortOrderProvider =
    NotifierProvider<_SortOrderNotifier, SortOrder>(_SortOrderNotifier.new);

// ── 전략 선택 ────────────────────────────────────────────────

class _SelectedStrategyNotifier extends Notifier<StrategyType> {
  @override
  StrategyType build() => StrategyType.aggressive;
}

final selectedStrategyProvider =
    NotifierProvider<_SelectedStrategyNotifier, StrategyType>(
  _SelectedStrategyNotifier.new,
);

// ── 마켓 필터 선택 ───────────────────────────────────────────

class _SelectedMarketFilterNotifier extends Notifier<MarketFilter> {
  @override
  MarketFilter build() => MarketFilter.us;
}

final selectedMarketFilterProvider =
    NotifierProvider<_SelectedMarketFilterNotifier, MarketFilter>(
  _SelectedMarketFilterNotifier.new,
);

// ── 필터링된 스크리닝 결과 (메모이제이션) ─────────────────────
// marketFilter에 따라 US(historyScreeningProvider) 또는
// KR(krHistoryScreeningProvider) 데이터를 별도 로드.

typedef _FilteredResult = (
  {ScreeningRun run, StrategyResult? sr, StrategyType selected}
);

final filteredScreeningProvider =
    Provider<AsyncValue<_FilteredResult?>>((ref) {
  final marketFilter = ref.watch(selectedMarketFilterProvider);
  final selected = ref.watch(selectedStrategyProvider);

  final isKr = marketFilter == MarketFilter.kr;
  final historyAsync = isKr
      ? ref.watch(krHistoryScreeningProvider)
      : ref.watch(historyScreeningProvider);

  return historyAsync.whenData((data) {
    if (data == null) return null;
    final run = data.toScreeningRun(selected);
    final sr = data.strategies[selected];
    return (run: run, sr: sr, selected: selected);
  });
});
