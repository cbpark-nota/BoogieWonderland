class ShortSqueezeResult {
  final String ticker;
  final String name;
  final double shortFloatPct;
  final double daysToCover;
  final double price;
  final double change1dPct;
  final double change5dPct;
  final double volumeRatio;
  final double marketCap;
  final String sector;

  const ShortSqueezeResult({
    required this.ticker,
    required this.name,
    required this.shortFloatPct,
    required this.daysToCover,
    required this.price,
    required this.change1dPct,
    required this.change5dPct,
    required this.volumeRatio,
    required this.marketCap,
    required this.sector,
  });

  factory ShortSqueezeResult.fromJson(Map<String, dynamic> json) {
    return ShortSqueezeResult(
      ticker: json['ticker'] as String? ?? '',
      name: json['name'] as String? ?? '',
      shortFloatPct: (json['short_float_pct'] as num? ?? 0).toDouble(),
      daysToCover: (json['days_to_cover'] as num? ?? 0).toDouble(),
      price: (json['price'] as num? ?? 0).toDouble(),
      change1dPct: (json['change_1d_pct'] as num? ?? 0).toDouble(),
      change5dPct: (json['change_5d_pct'] as num? ?? 0).toDouble(),
      volumeRatio: (json['volume_ratio'] as num? ?? 0).toDouble(),
      marketCap: (json['market_cap'] as num? ?? 0).toDouble(),
      sector: json['sector'] as String? ?? '',
    );
  }
}

class ShortSqueezeData {
  final String generatedAt;
  final bool isSample;
  final int totalCandidates;
  final String criteriaDescription;
  final List<ShortSqueezeResult> results;

  const ShortSqueezeData({
    required this.generatedAt,
    required this.isSample,
    required this.totalCandidates,
    required this.criteriaDescription,
    required this.results,
  });

  factory ShortSqueezeData.fromJson(Map<String, dynamic> json) {
    final criteria = json['criteria'] as Map<String, dynamic>? ?? {};
    return ShortSqueezeData(
      generatedAt: json['generated_at'] as String? ?? '',
      isSample: json['is_sample'] as bool? ?? false,
      totalCandidates: (json['total_candidates'] as num? ?? 0).toInt(),
      criteriaDescription: criteria['description'] as String? ?? '',
      results: (json['results'] as List<dynamic>? ?? [])
          .map((e) => ShortSqueezeResult.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
