import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/vix_etf_data.dart';
import '../services/static_data_source.dart';

// ── VIX ETF 데이터 프로바이더 ────────────────────────────────

final vixEtfProvider = FutureProvider<VixEtfData?>((ref) async {
  try {
    final data = await StaticDataSource().getVixEtfPrices();
    return VixEtfData.fromJson(data);
  } catch (_) {
    return null;
  }
});

// ── VIX 목표값 입력 상태 ────────────────────────────────────

class _TargetVixNotifier extends Notifier<double?> {
  @override
  double? build() => null;

  void set(double? value) => state = value;
}

final targetVixProvider = NotifierProvider<_TargetVixNotifier, double?>(
  _TargetVixNotifier.new,
);
