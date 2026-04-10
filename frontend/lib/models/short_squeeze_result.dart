/// 숏스퀴즈 스크리닝 결과 모델

class ShortSqueezeResult {
  final int rank;
  final String ticker;
  final String market;
  final String? name;
  final String sector;
  final double squeezeScore;
  final double? price;

  // US 지표
  final double? siPctFloat;    // Short Interest % of Float
  final double? daysToCover;   // Days to Cover
  final double? ctbRate;       // Cost to Borrow (%)
  final int? ctbAvailable;     // 가용 주식수
  final double? volRatio5d;    // 5일 거래량 / 20일 평균
  final double? volRatio1d;    // 최근 1일 거래량 / 20일 평균
  final int? sharesShort;      // 공매도 잔량
  final int? floatShares;      // 유통주식수
  final double? shortVolPctAvg;   // FINRA 평균 공매도 거래량 비율
  final double? shortVolTrend;    // FINRA 공매도 거래량 추세
  final int? ftdTotal;         // SEC FTD 합계
  final double? ftdTrend;      // FTD 증가 추세

  // KR 지표
  final int? siBalance;        // 공매도 잔고 (주수)
  final double? siBalanceValue; // 공매도 잔고 금액
  final double? siPct;         // 공매도 잔고 비율 (%)
  final double? shortVolAvg;   // 공매도 거래량 평균
  final double? volRatio5dShort; // 공매도 거래량 비율

  ShortSqueezeResult({
    required this.rank,
    required this.ticker,
    required this.market,
    this.name,
    required this.sector,
    required this.squeezeScore,
    this.price,
    this.siPctFloat,
    this.daysToCover,
    this.ctbRate,
    this.ctbAvailable,
    this.volRatio5d,
    this.volRatio1d,
    this.sharesShort,
    this.floatShares,
    this.shortVolPctAvg,
    this.shortVolTrend,
    this.ftdTotal,
    this.ftdTrend,
    this.siBalance,
    this.siBalanceValue,
    this.siPct,
    this.shortVolAvg,
    this.volRatio5dShort,
  });

  factory ShortSqueezeResult.fromJson(Map<String, dynamic> json) {
    return ShortSqueezeResult(
      rank:         json['rank'] as int,
      ticker:       json['ticker'] as String,
      market:       json['market'] as String? ?? 'US',
      name:         json['name'] as String?,
      sector:       json['sector'] as String? ?? '',
      squeezeScore: (json['squeeze_score'] as num?)?.toDouble() ?? 0.0,
      price:        (json['price'] as num?)?.toDouble(),
      // US
      siPctFloat:   (json['si_pct_float'] as num?)?.toDouble(),
      daysToCover:  (json['days_to_cover'] as num?)?.toDouble(),
      ctbRate:      (json['ctb_rate'] as num?)?.toDouble(),
      ctbAvailable: (json['ctb_available'] as num?)?.toInt(),
      volRatio5d:   (json['vol_ratio_5d'] as num?)?.toDouble(),
      volRatio1d:   (json['vol_ratio_1d'] as num?)?.toDouble(),
      sharesShort:  (json['shares_short'] as num?)?.toInt(),
      floatShares:  (json['float_shares'] as num?)?.toInt(),
      shortVolPctAvg:  (json['short_vol_pct_avg'] as num?)?.toDouble(),
      shortVolTrend:   (json['short_vol_trend'] as num?)?.toDouble(),
      ftdTotal:     (json['ftd_total'] as num?)?.toInt(),
      ftdTrend:     (json['ftd_trend'] as num?)?.toDouble(),
      // KR
      siBalance:      (json['si_balance'] as num?)?.toInt(),
      siBalanceValue: (json['si_balance_value'] as num?)?.toDouble(),
      siPct:          (json['si_pct'] as num?)?.toDouble(),
      shortVolAvg:    (json['short_vol_avg'] as num?)?.toDouble(),
      volRatio5dShort:(json['vol_ratio_5d_short'] as num?)?.toDouble(),
    );
  }

  String get flag => market == 'KR' ? '🇰🇷' : '🇺🇸';
  String get displayName => (market == 'KR' && name != null) ? name! : ticker;
  String get currencySymbol => market == 'KR' ? '₩' : '\$';

  /// 주요 공매도 지표 요약 문자열 (US/KR 구분)
  String get primaryMetricLabel => market == 'KR' ? '잔고비율' : 'SI%Float';
  double? get primaryMetricValue =>
      market == 'KR' ? siPct : siPctFloat;
}

class ShortSqueezeData {
  final int runId;
  final String runDate;
  final Map<String, double> params;
  final int totalUsScreened;
  final int totalKrScreened;
  final int totalUsPassed;
  final int totalKrPassed;
  final List<ShortSqueezeResult> usResults;
  final List<ShortSqueezeResult> krResults;

  ShortSqueezeData({
    required this.runId,
    required this.runDate,
    required this.params,
    required this.totalUsScreened,
    required this.totalKrScreened,
    required this.totalUsPassed,
    required this.totalKrPassed,
    required this.usResults,
    required this.krResults,
  });

  factory ShortSqueezeData.fromJson(Map<String, dynamic> json) {
    final rawParams = json['params'] as Map<String, dynamic>? ?? {};
    final params = rawParams.map(
      (k, v) => MapEntry(k, (v as num).toDouble()),
    );
    return ShortSqueezeData(
      runId:            json['run_id'] as int? ?? 0,
      runDate:          json['run_date'] as String? ?? '',
      params:           params,
      totalUsScreened:  json['total_us_screened'] as int? ?? 0,
      totalKrScreened:  json['total_kr_screened'] as int? ?? 0,
      totalUsPassed:    json['total_us_passed'] as int? ?? 0,
      totalKrPassed:    json['total_kr_passed'] as int? ?? 0,
      usResults: (json['us_results'] as List? ?? [])
          .map((r) => ShortSqueezeResult.fromJson(r as Map<String, dynamic>))
          .toList(),
      krResults: (json['kr_results'] as List? ?? [])
          .map((r) => ShortSqueezeResult.fromJson(r as Map<String, dynamic>))
          .toList(),
    );
  }

  /// US + KR 합산 결과
  List<ShortSqueezeResult> get allResults => [...usResults, ...krResults];
}
