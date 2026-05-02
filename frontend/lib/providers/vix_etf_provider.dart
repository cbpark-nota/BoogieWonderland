import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/vix_etf_data.dart';
import '../services/static_data_source.dart';

final vixEtfDataProvider = FutureProvider<VixEtfData>((ref) async {
  try {
    final data = await StaticDataSource().getVixEtfPrices();
    return VixEtfData.fromJson(data);
  } catch (e) {
    debugPrint('vixEtfDataProvider: fetch failed: $e');
    return VixEtfData.empty;
  }
});
