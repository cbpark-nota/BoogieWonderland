import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/holding.dart';
import '../services/api_client.dart';

final holdingsProvider = AsyncNotifierProvider<HoldingsNotifier, List<Holding>>(
  HoldingsNotifier.new,
);

class HoldingsNotifier extends AsyncNotifier<List<Holding>> {
  @override
  Future<List<Holding>> build() async {
    try {
      final data = await ApiClient().getHoldings();
      return data.map((h) => Holding.fromJson(h)).toList();
    } catch (_) {
      return [];
    }
  }

  Future<void> addHolding(String ticker, double entryPrice) async {
    await ApiClient().addHolding(ticker, entryPrice);
    ref.invalidateSelf();
  }

  Future<void> removeHolding(String ticker) async {
    await ApiClient().removeHolding(ticker);
    ref.invalidateSelf();
  }

  Future<void> refresh() async {
    ref.invalidateSelf();
  }
}

final stopCheckProvider = FutureProvider.family<List<StopCheckResult>, void>((ref, _) async {
  final data = await ApiClient().checkStops();
  final results = data['results'] as List;
  return results.map((r) => StopCheckResult.fromJson(r)).toList();
});

