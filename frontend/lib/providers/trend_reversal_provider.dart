import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/trend_reversal_data.dart';
import '../services/static_data_source.dart';

/// 추세 전환 화면 — 시장(통합/US/KR) 토글
///
/// 백테스트 [3-3] 통합(US+KR) 시나리오가 최우수 성과(CAGR +89.8%, MDD -2.7%,
/// 샤프 4.15)였으므로 기본값을 ALL로 설정.
enum TrendReversalMarket { all, us, kr }

/// 추세 전환 정렬 — recent(최근 돌파순) / gap(스코어 내림차순) / alphabetical
///
/// 스크리너 JSON은 cross_days_ago 오름차순으로 미리 정렬되어 있으므로
/// `recent`는 데이터 순서를 그대로 사용한다.
enum TrendReversalSort { recent, gap, alphabetical }

class _TrendReversalMarketNotifier extends Notifier<TrendReversalMarket> {
  @override
  TrendReversalMarket build() => TrendReversalMarket.all;
}

final trendReversalMarketProvider =
    NotifierProvider<_TrendReversalMarketNotifier, TrendReversalMarket>(
  _TrendReversalMarketNotifier.new,
);

class _TrendReversalSortNotifier extends Notifier<TrendReversalSort> {
  @override
  TrendReversalSort build() => TrendReversalSort.recent;
}

final trendReversalSortProvider =
    NotifierProvider<_TrendReversalSortNotifier, TrendReversalSort>(
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
