class PortfolioHolding {
  final String ticker;
  final String name;
  final String market;
  final double? entryPrice;
  final double? currentPrice;
  final double shares;
  final String entryDate;
  final double? stopLoss;
  final double? targetPrice;
  final String memo;
  final double? invested;
  final double? currentValue;
  final double? returnPct;
  final double? weightPct;
  final bool stopTriggered;
  final double? investedKrw;
  final double? currentValueKrw;
  final double? investedUsd;
  final double? currentValueUsd;

  PortfolioHolding({
    required this.ticker,
    required this.name,
    required this.market,
    this.entryPrice,
    this.currentPrice,
    required this.shares,
    required this.entryDate,
    this.stopLoss,
    this.targetPrice,
    required this.memo,
    this.invested,
    this.currentValue,
    this.returnPct,
    this.weightPct,
    required this.stopTriggered,
    this.investedKrw,
    this.currentValueKrw,
    this.investedUsd,
    this.currentValueUsd,
  });

  factory PortfolioHolding.fromJson(Map<String, dynamic> json) {
    return PortfolioHolding(
      ticker: json['ticker'] as String,
      name: json['name'] as String? ?? json['ticker'] as String,
      market: json['market'] as String? ?? 'US',
      entryPrice: (json['entry_price'] as num?)?.toDouble(),
      currentPrice: (json['current_price'] as num?)?.toDouble(),
      shares: (json['shares'] as num?)?.toDouble() ?? 0,
      entryDate: json['entry_date'] as String? ?? '',
      stopLoss: (json['stop_loss'] as num?)?.toDouble(),
      targetPrice: (json['target_price'] as num?)?.toDouble(),
      memo: json['memo'] as String? ?? '',
      invested: (json['invested'] as num?)?.toDouble(),
      currentValue: (json['current_value'] as num?)?.toDouble(),
      returnPct: (json['return_pct'] as num?)?.toDouble(),
      weightPct: (json['weight_pct'] as num?)?.toDouble(),
      stopTriggered: json['stop_triggered'] as bool? ?? false,
      investedKrw: (json['invested_krw'] as num?)?.toDouble(),
      currentValueKrw: (json['current_value_krw'] as num?)?.toDouble(),
      investedUsd: (json['invested_usd'] as num?)?.toDouble(),
      currentValueUsd: (json['current_value_usd'] as num?)?.toDouble(),
    );
  }

  bool get isKr => market == 'KR';
  String get currencySymbol => isKr ? '₩' : '\$';

  String formatPrice(double? price) {
    if (price == null) return '-';
    if (isKr) {
      return '₩${price.toStringAsFixed(0).replaceAllMapped(RegExp(r'(\d)(?=(\d{3})+$)'), (m) => '${m[1]},')}';
    }
    return '\$${price.toStringAsFixed(2)}';
  }
}

class PortfolioData {
  final String updatedAt;
  final double totalInvested;
  final double totalCurrent;
  final double totalReturnPct;
  final double usdkrw;
  final double totalInvestedKrw;
  final double totalCurrentKrw;
  final double totalInvestedUsd;
  final double totalCurrentUsd;
  final List<PortfolioHolding> holdings;

  PortfolioData({
    required this.updatedAt,
    required this.totalInvested,
    required this.totalCurrent,
    required this.totalReturnPct,
    required this.usdkrw,
    required this.totalInvestedKrw,
    required this.totalCurrentKrw,
    required this.totalInvestedUsd,
    required this.totalCurrentUsd,
    required this.holdings,
  });

  factory PortfolioData.fromJson(Map<String, dynamic> json) {
    final list = (json['holdings'] as List? ?? [])
        .map((h) => PortfolioHolding.fromJson(h as Map<String, dynamic>))
        .toList();
    final er = json['exchange_rate'] as Map<String, dynamic>? ?? {};
    // total_invested_krw 없으면 total_invested로 fallback (하위 호환)
    final investedKrw = (json['total_invested_krw'] as num?)?.toDouble()
        ?? (json['total_invested'] as num?)?.toDouble()
        ?? 0;
    final currentKrw = (json['total_current_krw'] as num?)?.toDouble()
        ?? (json['total_current'] as num?)?.toDouble()
        ?? 0;
    return PortfolioData(
      updatedAt: json['updated_at'] as String? ?? '',
      totalInvested: (json['total_invested'] as num?)?.toDouble() ?? 0,
      totalCurrent: (json['total_current'] as num?)?.toDouble() ?? 0,
      totalReturnPct: (json['total_return_pct'] as num?)?.toDouble() ?? 0,
      usdkrw: (er['usdkrw'] as num?)?.toDouble() ?? 1380.0,
      totalInvestedKrw: investedKrw,
      totalCurrentKrw: currentKrw,
      totalInvestedUsd: (json['total_invested_usd'] as num?)?.toDouble() ?? 0,
      totalCurrentUsd: (json['total_current_usd'] as num?)?.toDouble() ?? 0,
      holdings: list,
    );
  }

  bool get isEmpty => holdings.isEmpty;
}
