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
    return res.data;
  }

  Future<List<dynamic>> getScreeningHistory({int limit = 20}) async {
    final res = await dio.get('${ApiConfig.screening}/history', queryParameters: {'limit': limit});
    return res.data;
  }

  // Portfolio
  Future<List<dynamic>> getHoldings() async {
    final res = await dio.get('${ApiConfig.portfolio}/holdings');
    return res.data;
  }

  Future<Map<String, dynamic>> addHolding(String ticker, double entryPrice) async {
    final res = await dio.post('${ApiConfig.portfolio}/holdings', data: {
      'ticker': ticker,
      'entry_price': entryPrice,
    });
    return res.data;
  }

  Future<void> removeHolding(String ticker) async {
    await dio.delete('${ApiConfig.portfolio}/holdings/$ticker');
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
