import 'package:dio/dio.dart';

/// 서버리스 모드 데이터 소스
/// GitHub Pages에 배포된 정적 JSON 파일을 읽는다.
class StaticDataSource {
  static final StaticDataSource _instance = StaticDataSource._internal();
  factory StaticDataSource() => _instance;

  late final Dio _dio;

  StaticDataSource._internal() {
    _dio = Dio(BaseOptions(
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 10),
    ));
  }

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

  /// 사용 가능한 히스토리 날짜 목록 (최근 5일, KST 기준 주말 제외)
  /// history/index.json이 없거나 에러 시 빈 목록 반환
  Future<List<String>> getHistoryDates() async {
    try {
      final res = await _dio.get('$_baseDataUrl/history/index.json');
      final data = res.data as Map<String, dynamic>;
      final dates = List<String>.from(data['dates'] as List);
      // KST 기준 주말(토=6, 일=7) 제외: 날짜 문자열은 YYYY-MM-DD 형식으로 KST 날짜
      return dates.where((d) {
        final dt = DateTime.parse(d);
        return dt.weekday < 6;
      }).toList();
    } catch (_) {
      return [];
    }
  }

  /// 특정 날짜의 스크리닝 결과 (history/{date}.json)
  Future<Map<String, dynamic>> getScreeningByDate(String date) async {
    final res = await _dio.get('$_baseDataUrl/history/$date.json');
    return res.data as Map<String, dynamic>;
  }
}
