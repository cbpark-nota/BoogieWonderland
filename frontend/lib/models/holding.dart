class Holding {
  final int id;
  final String ticker;
  final double entryPrice;
  final String entryDate;
  final double peakPrice;
  final bool isActive;

  Holding({
    required this.id,
    required this.ticker,
    required this.entryPrice,
    required this.entryDate,
    required this.peakPrice,
    required this.isActive,
  });

  factory Holding.fromJson(Map<String, dynamic> json) {
    return Holding(
      id: json['id'],
      ticker: json['ticker'],
      entryPrice: (json['entry_price'] as num).toDouble(),
      entryDate: json['entry_date'] ?? '',
      peakPrice: (json['peak_price'] as num? ?? json['current_price'] as num? ?? json['entry_price'] as num).toDouble(),
      isActive: json['is_active'] ?? true,
    );
  }
}

class PortfolioHolding {
  final String ticker;
  final String market;
  final String? name;
  final double entryPrice;
  final double currentPrice;
  final double peakPrice;
  final String entryDate;
  final double retPct;
  final double investedKrw;
  final double currentValueKrw;
  final double investedUsd;
  final double currentValueUsd;

  PortfolioHolding({
    required this.ticker,
    required this.market,
    this.name,
    required this.entryPrice,
    required this.currentPrice,
    required this.peakPrice,
    required this.entryDate,
    required this.retPct,
    required this.investedKrw,
    required this.currentValueKrw,
    required this.investedUsd,
    required this.currentValueUsd,
  });

  factory PortfolioHolding.fromJson(Map<String, dynamic> json) {
    return PortfolioHolding(
      ticker: json['ticker'],
      market: json['market'] ?? 'US',
      name: json['name'],
      entryPrice: (json['entry_price'] as num).toDouble(),
      currentPrice: (json['current_price'] as num).toDouble(),
      peakPrice: (json['peak_price'] as num).toDouble(),
      entryDate: json['entry_date'] ?? '',
      retPct: (json['ret_pct'] as num).toDouble(),
      investedKrw: (json['invested_krw'] as num).toDouble(),
      currentValueKrw: (json['current_value_krw'] as num).toDouble(),
      investedUsd: (json['invested_usd'] as num).toDouble(),
      currentValueUsd: (json['current_value_usd'] as num).toDouble(),
    );
  }
}

class PortfolioData {
  final String runDate;
  final double usdkrw;
  final String exchangeRateUpdatedAt;
  final double totalInvestedKrw;
  final double totalCurrentKrw;
  final double totalReturnPct;
  final double totalInvestedUsd;
  final double totalCurrentUsd;
  final List<PortfolioHolding> holdings;

  PortfolioData({
    required this.runDate,
    required this.usdkrw,
    required this.exchangeRateUpdatedAt,
    required this.totalInvestedKrw,
    required this.totalCurrentKrw,
    required this.totalReturnPct,
    required this.totalInvestedUsd,
    required this.totalCurrentUsd,
    required this.holdings,
  });

  factory PortfolioData.fromJson(Map<String, dynamic> json) {
    final er = json['exchange_rate'] as Map<String, dynamic>? ?? {};
    final rawHoldings = json['holdings'] as List? ?? [];
    return PortfolioData(
      runDate: json['run_date'] ?? '',
      usdkrw: (er['usdkrw'] as num?)?.toDouble() ?? 1380.0,
      exchangeRateUpdatedAt: er['updated_at'] ?? '',
      totalInvestedKrw: (json['total_invested_krw'] as num?)?.toDouble() ?? 0,
      totalCurrentKrw: (json['total_current_krw'] as num?)?.toDouble() ?? 0,
      totalReturnPct: (json['total_return_pct'] as num?)?.toDouble() ?? 0,
      totalInvestedUsd: (json['total_invested_usd'] as num?)?.toDouble() ?? 0,
      totalCurrentUsd: (json['total_current_usd'] as num?)?.toDouble() ?? 0,
      holdings: rawHoldings.map((h) => PortfolioHolding.fromJson(h)).toList(),
    );
  }
}

class StopCheckResult {
  final String ticker;
  final double currentPrice;
  final double stopPrice;
  final double marginPct;
  final String? eventType;

  StopCheckResult({
    required this.ticker,
    required this.currentPrice,
    required this.stopPrice,
    required this.marginPct,
    this.eventType,
  });

  factory StopCheckResult.fromJson(Map<String, dynamic> json) {
    return StopCheckResult(
      ticker: json['ticker'],
      currentPrice: (json['current_price'] as num).toDouble(),
      stopPrice: (json['stop_price'] as num).toDouble(),
      marginPct: (json['margin_pct'] as num).toDouble(),
      eventType: json['event_type'],
    );
  }
}
