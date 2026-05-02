import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/screening_result.dart';
import '../services/api_client.dart';

final marketStatusProvider = FutureProvider<MarketStatus?>((ref) async {
  try {
    final data = await ApiClient().getMarketStatus();
    return MarketStatus.fromJson(data);
  } catch (e) {
    debugPrint('marketStatusProvider: fetch failed: $e');
    return null;
  }
});
