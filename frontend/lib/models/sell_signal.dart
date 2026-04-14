class SellSignal {
  final String ticker;
  final double currentPrice;
  final double stopPrice;
  final double peakPrice;
  final int rank;
  final String entryDate;
  final String sellTriggeredDate;
  final List<String> sellReasons;
  final int daysRemaining;

  const SellSignal({
    required this.ticker,
    required this.currentPrice,
    required this.stopPrice,
    required this.peakPrice,
    required this.rank,
    required this.entryDate,
    required this.sellTriggeredDate,
    required this.sellReasons,
    required this.daysRemaining,
  });

  bool get isStopLoss => sellReasons.contains('stop_loss');
  bool get isRankOut => sellReasons.contains('rank_out');
  bool get isBoth => isStopLoss && isRankOut;

  factory SellSignal.fromJson(Map<String, dynamic> json) {
    return SellSignal(
      ticker: json['ticker'] as String,
      currentPrice: (json['current_price'] as num).toDouble(),
      stopPrice: (json['stop_price'] as num).toDouble(),
      peakPrice: (json['peak_price'] as num).toDouble(),
      rank: json['rank'] as int,
      entryDate: json['entry_date'] as String,
      sellTriggeredDate: json['sell_triggered_date'] as String,
      sellReasons: List<String>.from(json['sell_reasons'] as List),
      daysRemaining: json['days_remaining'] as int,
    );
  }
}

class SellSignalData {
  final String updatedAt;
  final List<SellSignal> signals;

  const SellSignalData({
    required this.updatedAt,
    required this.signals,
  });

  factory SellSignalData.fromJson(Map<String, dynamic> json) {
    return SellSignalData(
      updatedAt: json['updated_at'] as String? ?? '',
      signals: (json['signals'] as List? ?? [])
          .map((e) => SellSignal.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
