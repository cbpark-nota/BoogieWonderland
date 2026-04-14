import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/sell_signal.dart';
import '../services/static_data_source.dart';

final sellSignalProvider = FutureProvider<SellSignalData?>((ref) async {
  try {
    final data = await StaticDataSource().getSellSignals();
    return SellSignalData.fromJson(data);
  } catch (_) {
    return null;
  }
});
