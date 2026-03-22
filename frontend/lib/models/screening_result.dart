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

/// 전략 유형
enum StrategyType {
  aggressive('aggressive', '공격적', 'ATR 2.0 / 주간'),
  balanced('balanced', '균형형', 'ATR 2.5 / 격주'),
  conservative('conservative', '보수적', 'ATR 3.5 / 월간'),
  adaptive('adaptive', '적응형', '국면별 동적 전환');

  final String key;
  final String label;
  final String description;

  const StrategyType(this.key, this.label, this.description);
}

/// 4전략 스크리닝 결과를 담는 모델
class StrategyScreeningData {
  final int runId;
  final String runDate;
  final MarketStatus? marketStatus;
  final Map<StrategyType, StrategyResult> strategies;

  StrategyScreeningData({
    required this.runId,
    required this.runDate,
    this.marketStatus,
    required this.strategies,
  });

  factory StrategyScreeningData.fromJson(Map<String, dynamic> json) {
    final strategiesJson = json['strategies'] as Map<String, dynamic>;
    final ms = json['market_status'] != null
        ? MarketStatus.fromJson(json['market_status'])
        : null;

    final strategies = <StrategyType, StrategyResult>{};
    for (final st in StrategyType.values) {
      final sJson = strategiesJson[st.key];
      if (sJson != null) {
        strategies[st] = StrategyResult.fromJson(sJson);
      }
    }

    return StrategyScreeningData(
      runId: json['run_id'],
      runDate: json['run_date'],
      marketStatus: ms,
      strategies: strategies,
    );
  }

  /// 특정 전략의 ScreeningRun 변환 (기존 위젯 호환)
  ScreeningRun toScreeningRun(StrategyType type) {
    final sr = strategies[type];
    return ScreeningRun(
      runId: runId,
      runDate: runDate,
      marketStatus: marketStatus,
      totalScreened: sr?.totalScreened ?? 0,
      totalPassed: sr?.totalPassed ?? 0,
      results: sr?.results ?? [],
    );
  }
}

class StrategyResult {
  final String label;
  final double atrMult;
  final String rebalFreq;
  final int totalScreened;
  final int totalPassed;
  final List<ScreeningResult> results;
  final String? currentRegime;

  StrategyResult({
    required this.label,
    required this.atrMult,
    required this.rebalFreq,
    required this.totalScreened,
    required this.totalPassed,
    required this.results,
    this.currentRegime,
  });

  factory StrategyResult.fromJson(Map<String, dynamic> json) {
    return StrategyResult(
      label: json['label'] ?? '',
      atrMult: (json['atr_mult'] as num).toDouble(),
      rebalFreq: json['rebal_freq'] ?? '',
      totalScreened: json['total_screened'] ?? 0,
      totalPassed: json['total_passed'] ?? 0,
      results: (json['results'] as List)
          .map((r) => ScreeningResult.fromJson(r))
          .toList(),
      currentRegime: json['regime_label'],
    );
  }
}
