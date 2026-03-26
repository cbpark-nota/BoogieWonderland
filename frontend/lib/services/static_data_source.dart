import 'package:dio/dio.dart';

/// 서버리스 모드 데이터 소스
/// GitHub Pages에 배포된 정적 JSON 파일을 읽는다.
class StaticDataSource {
  final Dio _dio = Dio(BaseOptions(
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 10),
  ));

  String get _baseDataUrl => 'data';

  /// 하위 호환: 균형형 기본 결과
  Future<Map<String, dynamic>> getLatestScreening() async {
    final res = await _dio.get('$_baseDataUrl/screening_latest.json');
    return res.data as Map<String, dynamic>;
  }

  /// 4전략 전체 결과
  Future<Map<String, dynamic>> getStrategies() async {
    final res = await _dio.get('$_baseDataUrl/screening_strategies.json');
    return res.data as Map<String, dynamic>;
  }

  /// 엑셀 기반 포트폴리오 데이터
  Future<Map<String, dynamic>> getPortfolio() async {
    final res = await _dio.get('$_baseDataUrl/portfolio.json');
    return res.data as Map<String, dynamic>;
  }
}
