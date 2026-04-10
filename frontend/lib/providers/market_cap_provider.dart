import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/market_cap_data.dart';
import '../services/static_data_source.dart';

/// 시총 Top 20 스크리닝 데이터 프로바이더
final marketCapProvider = FutureProvider<MarketCapData?>((ref) async {
  try {
    final data = await StaticDataSource().getMarketCap();
    return MarketCapData.fromJson(data);
  } catch (_) {
    return null;
  }
});
