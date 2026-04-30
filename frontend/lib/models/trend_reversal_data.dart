/// 추세 전환 스크리너 결과 (5MA/120MA 골든크로스 일봉 기준).
///
/// 출력 JSON:
/// ```
/// {
///   "run_id": 20260501,
///   "run_date": "2026-05-01T08:00:00",
///   "total_screened": 517,
///   "total_passed": 25,
///   "results": [ { "rank": 1, "ticker": "...", ... } ]
/// }
/// ```
class TrendReversalResult {
  final int rank;
  final String ticker;
  final String market;
  final String? sector;
  final double score;
  final double price;
  final double? stopPrice;
  final double? stopDistPct;
  final double? atr;
  final double? maShort;
  final double? maLong;

  TrendReversalResult({
    required this.rank,
    required this.ticker,
    required this.market,
    this.sector,
    required this.score,
    required this.price,
    this.stopPrice,
    this.stopDistPct,
    this.atr,
    this.maShort,
    this.maLong,
  });

  factory TrendReversalResult.fromJson(Map<String, dynamic> json) {
    return TrendReversalResult(
      rank: (json['rank'] as num).toInt(),
      ticker: json['ticker'] as String,
      market: (json['market'] as String?) ?? 'US',
      sector: json['sector'] as String?,
      score: (json['score'] as num).toDouble(),
      price: (json['price'] as num).toDouble(),
      stopPrice: (json['stop_price'] as num?)?.toDouble(),
      stopDistPct: (json['stop_dist_pct'] as num?)?.toDouble(),
      atr: (json['atr'] as num?)?.toDouble(),
      maShort: (json['ma_short'] as num?)?.toDouble(),
      maLong: (json['ma_long'] as num?)?.toDouble(),
    );
  }
}

class TrendReversalData {
  final int runId;
  final String runDate;
  final int totalScreened;
  final int totalPassed;
  final List<TrendReversalResult> results;

  TrendReversalData({
    required this.runId,
    required this.runDate,
    required this.totalScreened,
    required this.totalPassed,
    required this.results,
  });

  factory TrendReversalData.fromJson(Map<String, dynamic> json) {
    return TrendReversalData(
      runId: (json['run_id'] as num).toInt(),
      runDate: json['run_date'] as String,
      totalScreened: (json['total_screened'] as num?)?.toInt() ?? 0,
      totalPassed: (json['total_passed'] as num?)?.toInt() ?? 0,
      results: (json['results'] as List? ?? [])
          .map((e) => TrendReversalResult.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  static TrendReversalData empty() => TrendReversalData(
        runId: 0,
        runDate: '',
        totalScreened: 0,
        totalPassed: 0,
        results: const [],
      );
}
