import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/short_squeeze_result.dart';
import '../services/static_data_source.dart';

// ── 숏스퀴즈 데이터 프로바이더 ──────────────────────────────

final shortSqueezeProvider = FutureProvider<ShortSqueezeData?>((ref) async {
  try {
    final data = await StaticDataSource().getShortSqueeze();
    return ShortSqueezeData.fromJson(data);
  } catch (e) {
    debugPrint('shortSqueezeProvider: fetch failed: $e');
    return null;
  }
});

// ── 마켓 필터 상태 ─────────────────────────────────────────

enum ShortSqueezeMarketFilter { all, us, kr }

class _MarketFilterNotifier extends Notifier<ShortSqueezeMarketFilter> {
  @override
  ShortSqueezeMarketFilter build() => ShortSqueezeMarketFilter.all;

  void set(ShortSqueezeMarketFilter filter) => state = filter;
}

final shortSqueezeMarketFilterProvider =
    NotifierProvider<_MarketFilterNotifier, ShortSqueezeMarketFilter>(
  _MarketFilterNotifier.new,
);

// ── 필터링된 결과 ─────────────────────────────────────────

final filteredShortSqueezeProvider =
    Provider<AsyncValue<List<ShortSqueezeResult>>>((ref) {
  final dataAsync = ref.watch(shortSqueezeProvider);
  final filter = ref.watch(shortSqueezeMarketFilterProvider);

  return dataAsync.when(
    data: (data) {
      if (data == null) return const AsyncValue.data([]);
      final results = switch (filter) {
        ShortSqueezeMarketFilter.us  => data.usResults,
        ShortSqueezeMarketFilter.kr  => data.krResults,
        ShortSqueezeMarketFilter.all => data.allResults,
      };
      return AsyncValue.data(results);
    },
    loading: () => const AsyncValue.loading(),
    error:   (e, s) => AsyncValue.error(e, s),
  );
});
