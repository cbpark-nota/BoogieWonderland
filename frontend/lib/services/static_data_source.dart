import 'package:dio/dio.dart';

/// 서버리스 모드 데이터 소스
/// GitHub Pages에 배포된 정적 JSON 파일을 읽는다.
class StaticDataSource {
  static final StaticDataSource _instance = StaticDataSource._internal();

  factory StaticDataSource() => _instance;

  StaticDataSource._internal();

  final Dio _dio = Dio(
    BaseOptions(
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 10),
    ),
  );

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

  /// 숏스퀴즈 최신 결과
  Future<Map<String, dynamic>> getShortSqueeze() async {
    final res = await _dio.get('$_baseDataUrl/short_squeeze_latest.json');
    return res.data as Map<String, dynamic>;
  }

  /// 시총 Top 20 트렌드 데이터 (market_cap.json)
  Future<Map<String, dynamic>> getMarketCapTop20() async {
    try {
      final res = await _dio.get('$_baseDataUrl/market_cap.json');
      return res.data as Map<String, dynamic>;
    } catch (_) {
      final fallback = await _dio.get('$_baseDataUrl/market_cap_latest.json');
      return fallback.data as Map<String, dynamic>;
    }
  }

  /// VIX/SVXY/SVIX 현재가 (vix_etf_prices.json)
  Future<Map<String, dynamic>> getVixEtfPrices() async {
    final bust = DateTime.now().millisecondsSinceEpoch ~/ 60000;
    final res = await _dio.get('$_baseDataUrl/vix_etf_prices.json?v=$bust');
    return res.data as Map<String, dynamic>;
  }

  /// 추세 전환 후보 (5MA/120MA 일봉 골든크로스)
  /// market: 'us' | 'kr'
  Future<Map<String, dynamic>> getTrendReversal(String market) async {
    final bust = DateTime.now().millisecondsSinceEpoch ~/ 60000;
    final res = await _dio
        .get('$_baseDataUrl/trend_reversal_$market.json?v=$bust');
    return res.data as Map<String, dynamic>;
  }

  // ── v3.2 KR 분리 스크리닝 ─────────────────────────────────

  /// KR 4전략 전체 결과 (screening_kr_strategies.json)
  Future<Map<String, dynamic>> getKrStrategies() async {
    final res = await _dio.get('$_baseDataUrl/screening_kr_strategies.json');
    return res.data as Map<String, dynamic>;
  }

  /// 특정 날짜의 KR 스크리닝 결과 — history/{date}.json의 kr_strategies 키 사용
  Future<Map<String, dynamic>> getKrScreeningByDate(String date) async {
    final res = await _dio.get('$_baseDataUrl/history/$date.json');
    final data = res.data as Map<String, dynamic>;
    // kr_strategies 키를 strategies 키로 리매핑하여 StrategyScreeningData.fromJson 호환
    return {...data, 'strategies': data['kr_strategies'] ?? {}};
  }

}
