import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/trend_reversal_data.dart';
import '../providers/market_filter_provider.dart' show SortOrder;
import '../services/static_data_source.dart';

/// 추세 전환 화면 — 시장(US/KR) 토글
enum TrendReversalMarket { us, kr }

class _TrendReversalMarketNotifier extends Notifier<TrendReversalMarket> {
  @override
  TrendReversalMarket build() => TrendReversalMarket.us;
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
  final key = market == TrendReversalMarket.us ? 'us' : 'kr';
  try {
    final data = await StaticDataSource().getTrendReversal(key);
    return TrendReversalData.fromJson(data);
  } catch (_) {
    return TrendReversalData.empty();
  }
});
