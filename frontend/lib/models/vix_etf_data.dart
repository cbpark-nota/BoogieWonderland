/// VIX ETF 가격 데이터 모델

class VixEtfData {
  final String runDate;
  final double vix;
  final double svxy;
  final double svix;

  VixEtfData({
    required this.runDate,
    required this.vix,
    required this.svxy,
    required this.svix,
  });

  factory VixEtfData.fromJson(Map<String, dynamic> json) {
    return VixEtfData(
      runDate: json['run_date'] as String? ?? '',
      vix:     (json['vix']  as num?)?.toDouble() ?? 0.0,
      svxy:    (json['svxy'] as num?)?.toDouble() ?? 0.0,
      svix:    (json['svix'] as num?)?.toDouble() ?? 0.0,
    );
  }

  /// VIX 목표값에서 SVXY 이론가 계산
  /// R = (targetVix - vix) / vix
  /// SVXY_fair = svxy × (1 - 0.5 × R)
  double svxyFair(double targetVix) {
    final r = (targetVix - vix) / vix;
    return svxy * (1 - 0.5 * r);
  }

  /// VIX 목표값에서 SVIX 이론가 계산
  /// SVIX_fair = svix × (1 - R)
  double svixFair(double targetVix) {
    final r = (targetVix - vix) / vix;
    return svix * (1 - r);
  }
}
