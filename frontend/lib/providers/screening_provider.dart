import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/screening_result.dart';
import '../services/api_client.dart';

final screeningProvider = AsyncNotifierProvider<ScreeningNotifier, ScreeningRun?>(
  ScreeningNotifier.new,
);

class ScreeningNotifier extends AsyncNotifier<ScreeningRun?> {
  @override
  Future<ScreeningRun?> build() async {
    try {
      final data = await ApiClient().getLatestScreening();
      return ScreeningRun.fromJson(data);
    } catch (e) {
      debugPrint('ScreeningNotifier: latest screening fetch failed: $e');
      return null;
    }
  }

  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() async {
      final data = await ApiClient().getLatestScreening();
      return ScreeningRun.fromJson(data);
    });
  }

  Future<void> runScreening() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() async {
      final data = await ApiClient().runScreening();
      return ScreeningRun.fromJson(data);
    });
  }
}

final screeningHistoryProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  final data = await ApiClient().getScreeningHistory();
  return data.cast<Map<String, dynamic>>();
});
