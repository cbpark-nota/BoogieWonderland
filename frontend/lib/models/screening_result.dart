class ScreeningResult {
  final int rank;
  final String ticker;
  final String market;
  final String sector;
  final double score;
  final double weightPct;
  final double price;
  final double? adx;
  final double? rsi;
  final double? ret3m;
  final double? stopPrice;
  final double? stopDistPct;
  final double? atr;

  ScreeningResult({
    required this.rank,
    required this.ticker,
    required this.market,
    required this.sector,
    required this.score,
    required this.weightPct,
    required this.price,
    this.adx,
    this.rsi,
    this.ret3m,
    this.stopPrice,
    this.stopDistPct,
    this.atr,
  });

  factory ScreeningResult.fromJson(Map<String, dynamic> json) {
    return ScreeningResult(
      rank: json['rank'],
      ticker: json['ticker'],
      market: json['market'] ?? 'US',
      sector: json['sector'] ?? '',
      score: (json['score'] as num).toDouble(),
      weightPct: (json['weight_pct'] as num).toDouble(),
      price: (json['price'] as num).toDouble(),
      adx: (json['adx'] as num?)?.toDouble(),
      rsi: (json['rsi'] as num?)?.toDouble(),
      ret3m: (json['ret_3m'] as num?)?.toDouble(),
      stopPrice: (json['stop_price'] as num?)?.toDouble(),
      stopDistPct: (json['stop_dist_pct'] as num?)?.toDouble(),
      atr: (json['atr'] as num?)?.toDouble(),
    );
  }

  String get flag => market == 'KR' ? '🇰🇷' : '🇺🇸';
}

class MarketStatus {
  final double spyPrice;
  final bool isGoldenCross;
  final double ma50;
  final double ma200;
  final double gapPct;
  final String? nextRebalance;

  MarketStatus({
    required this.spyPrice,
    required this.isGoldenCross,
    required this.ma50,
    required this.ma200,
    required this.gapPct,
    this.nextRebalance,
  });

  factory MarketStatus.fromJson(Map<String, dynamic> json) {
    return MarketStatus(
      spyPrice: (json['spy_price'] as num).toDouble(),
      isGoldenCross: json['is_golden_cross'] ?? false,
      ma50: (json['ma50'] as num).toDouble(),
      ma200: (json['ma200'] as num).toDouble(),
      gapPct: (json['gap_pct'] as num).toDouble(),
      nextRebalance: json['next_rebalance'],
    );
  }
}

class ScreeningRun {
  final int runId;
  final String runDate;
  final MarketStatus? marketStatus;
  final int totalScreened;
  final int totalPassed;
  final List<ScreeningResult> results;

  ScreeningRun({
    required this.runId,
    required this.runDate,
    this.marketStatus,
    required this.totalScreened,
    required this.totalPassed,
    required this.results,
  });

  factory ScreeningRun.fromJson(Map<String, dynamic> json) {
    return ScreeningRun(
      runId: json['run_id'],
      runDate: json['run_date'],
      marketStatus: json['market_status'] != null
          ? MarketStatus.fromJson(json['market_status'])
          : null,
      totalScreened: json['total_screened'] ?? 0,
      totalPassed: json['total_passed'] ?? 0,
      results: (json['results'] as List)
          .map((r) => ScreeningResult.fromJson(r))
          .toList(),
    );
  }
}
