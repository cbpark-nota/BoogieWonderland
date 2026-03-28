class ScreeningResult {
  final int rank;
  final String ticker;
  final String market;
  final String? name;
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
    this.name,
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
      name: json['name'] as String?,
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

  ScreeningResult copyWith({int? rank}) {
    return ScreeningResult(
      rank: rank ?? this.rank,
      ticker: ticker,
      market: market,
      name: name,
      sector: sector,
      score: score,
      weightPct: weightPct,
      price: price,
      adx: adx,
      rsi: rsi,
      ret3m: ret3m,
      stopPrice: stopPrice,
      stopDistPct: stopDistPct,
      atr: atr,
    );
  }

  String get flag => market == 'KR' ? '🇰🇷' : '🇺🇸';
  String get displayName => (market == 'KR' && name != null) ? name! : ticker;
  String get currencySymbol => market == 'KR' ? '₩' : '\$';
}

class BtcSignal {
  final String signal; // "buy" | "hold"
  final double? price;
  final String reason;
  final String strategy;
  final String timestamp;
  final String? regime;

  BtcSignal({
    required this.signal,
    this.price,
    required this.reason,
    required this.strategy,
    required this.timestamp,
    this.regime,
  });

  factory BtcSignal.fromJson(Map<String, dynamic> json) {
    return BtcSignal(
      signal: json['signal'] ?? 'hold',
      price: (json['price'] as num?)?.toDouble(),
      reason: json['reason'] ?? '',
      strategy: json['strategy'] ?? 'V10',
      timestamp: json['timestamp'] ?? '',
      regime: json['regime'],
    );
  }
}

class MarketStatus {
  final double spyPrice;
  final bool isGoldenCross;
  final double ma20;
  final double ma60;
  final double gapPct;
  final String? nextRebalance;
  final double? kospiPrice;
  final bool? kospiIsGoldenCross;
  final double? kospiMa20;
  final double? kospiMa60;
  final double? kospiGapPct;

  MarketStatus({
    required this.spyPrice,
    required this.isGoldenCross,
    required this.ma20,
    required this.ma60,
    required this.gapPct,
    this.nextRebalance,
    this.kospiPrice,
    this.kospiIsGoldenCross,
    this.kospiMa20,
    this.kospiMa60,
    this.kospiGapPct,
  });

  factory MarketStatus.fromJson(Map<String, dynamic> json) {
    return MarketStatus(
      spyPrice: (json['spy_price'] as num).toDouble(),
      isGoldenCross: json['is_golden_cross'] ?? false,
      ma20: (json['ma20'] as num).toDouble(),
      ma60: (json['ma60'] as num).toDouble(),
      gapPct: (json['gap_pct'] as num).toDouble(),
      nextRebalance: json['next_rebalance'],
      kospiPrice: (json['kospi_price'] as num?)?.toDouble(),
      kospiIsGoldenCross: json['kospi_golden_cross'] as bool?,
      kospiMa20: (json['kospi_ma20'] as num?)?.toDouble(),
      kospiMa60: (json['kospi_ma60'] as num?)?.toDouble(),
      kospiGapPct: (json['kospi_gap_pct'] as num?)?.toDouble(),
    );
  }
}

class ScreeningRun {
  final int runId;
  final String runDate;
  final MarketStatus? marketStatus;
  final BtcSignal? btcSignal;
  final int totalScreened;
  final int totalPassed;
  final List<ScreeningResult> results;

  ScreeningRun({
    required this.runId,
    required this.runDate,
    this.marketStatus,
    this.btcSignal,
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
      btcSignal: json['btc_signal'] != null
          ? BtcSignal.fromJson(json['btc_signal'] as Map<String, dynamic>)
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
  aggressive('aggressive', '공격적', 'ATR 1.5 / 주간 / TOP15'),
  balanced('balanced', '균형형', 'ATR 2.0 / 격주 / TOP10'),
  conservative('conservative', '보수적', 'ATR 2.5 / 월간 / TOP7'),
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
