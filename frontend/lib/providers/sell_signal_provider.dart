import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/sell_signal.dart';
import '../services/static_data_source.dart';

final sellSignalProvider = FutureProvider<SellSignalData?>((ref) async {
  try {
    final data = await StaticDataSource().getSellSignals();
    return SellSignalData.fromJson(data);
  } on DioException catch (e) {
    // 404: 파일이 아직 생성되지 않음 → 빈 상태로 표시
    if (e.response?.statusCode == 404) {
      return const SellSignalData(updatedAt: '', signals: []);
    }
    return null;
  } catch (_) {
    return null;
  }
});
