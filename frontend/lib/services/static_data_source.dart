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
  /// 배포 후 브라우저 캐시로 인한 구 데이터 표시를 방지하기 위해 캐시 버스팅 파라미터 사용
  Future<Map<String, dynamic>> getPortfolio() async {
    final bust = DateTime.now().millisecondsSinceEpoch ~/ 60000; // 1분 단위
    final res = await _dio.get('$_baseDataUrl/portfolio.json?v=$bust');
    return res.data as Map<String, dynamic>;
  }

  /// 사용 가능한 히스토리 날짜 목록 (최근 5일)
  /// history/index.json이 없거나 에러 시 빈 목록 반환
  Future<List<String>> getHistoryDates() async {
    try {
      final res = await _dio.get('$_baseDataUrl/history/index.json');
      final data = res.data as Map<String, dynamic>;
      return List<String>.from(data['dates'] as List);
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
