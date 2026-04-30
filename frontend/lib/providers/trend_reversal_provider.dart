import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/trend_reversal_data.dart';
import '../providers/market_filter_provider.dart' show SortOrder;
import '../services/static_data_source.dart';

/// 추세 전환 화면 — 시장(통합/US/KR) 토글
///
/// 백테스트 [3-3] 통합(US+KR) 시나리오가 최우수 성과(CAGR +89.8%, MDD -2.7%,
/// 샤프 4.15)였으므로 기본값을 ALL로 설정.
enum TrendReversalMarket { all, us, kr }

class _TrendReversalMarketNotifier extends Notifier<TrendReversalMarket> {
  @override
  TrendReversalMarket build() => TrendReversalMarket.all;
}

final trendReversalMarketProvider =
    NotifierProvider<_TrendReversalMarketNotifier, TrendReversalMarket>(
  _TrendReversalMarketNotifier.new,
);

class _TrendReversalSortNotifier extends Notifier<SortOrder> {
  @override
  SortOrder build() => SortOrder.rank;
}

final trendReversalSortProvider =
    NotifierProvider<_TrendReversalSortNotifier, SortOrder>(
  _TrendReversalSortNotifier.new,
);

final trendReversalDataProvider =
    FutureProvider.autoDispose<TrendReversalData>((ref) async {
  final market = ref.watch(trendReversalMarketProvider);
  final key = switch (market) {
    TrendReversalMarket.all => 'all',
    TrendReversalMarket.us => 'us',
    TrendReversalMarket.kr => 'kr',
  };
  try {
    final data = await StaticDataSource().getTrendReversal(key);
    return TrendReversalData.fromJson(data);
  } catch (_) {
    return TrendReversalData.empty();
  }
});
