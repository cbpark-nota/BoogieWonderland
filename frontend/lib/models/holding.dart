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
      entryDate: json['entry_date'],
      peakPrice: (json['peak_price'] as num).toDouble(),
      isActive: json['is_active'] ?? true,
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
