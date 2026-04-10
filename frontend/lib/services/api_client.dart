import 'package:dio/dio.dart';
import '../config/api_config.dart';

class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  factory ApiClient() => _instance;

  late final Dio dio;

  ApiClient._internal() {
    dio = Dio(BaseOptions(
      baseUrl: ApiConfig.baseUrl,
      connectTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(seconds: 60),
      headers: {'Content-Type': 'application/json'},
    ));
  }

  // Screening
  Future<Map<String, dynamic>> runScreening() async {
    final res = await dio.post('${ApiConfig.screening}/run');
    return res.data;
  }

  Future<Map<String, dynamic>> getLatestScreening() async {
    final res = await dio.get('${ApiConfig.screening}/latest');
    return _unwrapScreeningResponse(res.data);
  }

  Future<Map<String, dynamic>> getScreeningByDate(String date) async {
    final res = await dio.get('${ApiConfig.screening}/history/$date');
    return _unwrapScreeningResponse(res.data);
  }

  Future<List<String>> getScreeningHistoryDates({int days = 30}) async {
    final res = await dio.get(
      '${ApiConfig.screening}/history',
      queryParameters: {'days': days},
    );
    final list = res.data as List;
    return list
        .map((e) => (e as Map<String, dynamic>)['date'] as String)
        .toList();
  }

  Future<List<dynamic>> getScreeningHistory({int limit = 20}) async {
    final res = await dio.get('${ApiConfig.screening}/history', queryParameters: {'limit': limit});
    return res.data;
  }

  /// 백엔드 응답 {date, data: {...}, created_at} 구조를 벗겨 내부 data 반환.
  /// run_date가 없으면 외부 date로 보완한다.
  Map<String, dynamic> _unwrapScreeningResponse(dynamic raw) {
    if (raw is Map<String, dynamic> &&
        raw.containsKey('data') &&
        raw['data'] is Map) {
      final inner = Map<String, dynamic>.from(raw['data'] as Map);
      inner['run_date'] ??= raw['date'];
      return inner;
    }
    return raw as Map<String, dynamic>;
  }

  // Portfolio
  Future<List<dynamic>> getHoldings() async {
    final res = await dio.get(ApiConfig.portfolio);
    return res.data;
  }

  Future<Map<String, dynamic>> addHolding(String ticker, double entryPrice) async {
    final res = await dio.post(ApiConfig.portfolio, data: {
      'ticker': ticker,
      'entry_price': entryPrice,
      'quantity': 1,
    });
    return res.data;
  }

  Future<void> removeHolding(String ticker) async {
    await dio.delete('${ApiConfig.portfolio}/ticker/$ticker');
  }

  Future<Map<String, dynamic>> checkStops() async {
    final res = await dio.post('${ApiConfig.portfolio}/check-stops');
    return res.data;
  }

  // Market
  Future<Map<String, dynamic>> getMarketStatus() async {
    final res = await dio.get('${ApiConfig.market}/status');
    return res.data;
  }

  Future<List<dynamic>> getRebalanceSchedule() async {
    final res = await dio.get('${ApiConfig.market}/rebalance-schedule');
    return res.data;
  }

  // System
  Future<void> refreshData() async {
    await dio.post('${ApiConfig.system}/refresh');
  }

  // Notifications
  Future<void> registerToken(String token, String platform) async {
    await dio.post('${ApiConfig.notifications}/register', data: {
      'token': token,
      'platform': platform,
    });
  }

  Future<void> unregisterToken(String token) async {
    await dio.delete('${ApiConfig.notifications}/register/$token');
  }
}
