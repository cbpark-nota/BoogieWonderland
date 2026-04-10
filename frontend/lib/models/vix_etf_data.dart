/// VIX ETF 이론가 계산기용 데이터 모델

class VixEtfData {
  final String updatedAt;
  final double? vixCurrent;
  final double? vixPrevClose;
  final double? svxyPrice;
  final double? svxyPrevClose;
  final double? svixPrice;
  final double? svixPrevClose;

  const VixEtfData({
    required this.updatedAt,
    this.vixCurrent,
    this.vixPrevClose,
    this.svxyPrice,
    this.svxyPrevClose,
    this.svixPrice,
    this.svixPrevClose,
  });

  factory VixEtfData.fromJson(Map<String, dynamic> json) {
    final vix = json['vix'] as Map<String, dynamic>? ?? {};
    final svxy = json['svxy'] as Map<String, dynamic>? ?? {};
    final svix = json['svix'] as Map<String, dynamic>? ?? {};

    return VixEtfData(
      updatedAt: json['updated_at'] as String? ?? '',
      vixCurrent: (vix['current'] as num?)?.toDouble(),
      vixPrevClose: (vix['prev_close'] as num?)?.toDouble(),
      svxyPrice: (svxy['current_price'] as num?)?.toDouble(),
      svxyPrevClose: (svxy['prev_close'] as num?)?.toDouble(),
      svixPrice: (svix['current_price'] as num?)?.toDouble(),
      svixPrevClose: (svix['prev_close'] as num?)?.toDouble(),
    );
  }

  /// SVXY 이론가: prevClose × (1 - 0.5 × R)
  double? svxyTheoretical(double r) {
    if (svxyPrevClose == null) return null;
    return svxyPrevClose! * (1 - 0.5 * r);
  }

  /// SVIX 이론가: prevClose × (1 - R)
  double? svixTheoretical(double r) {
    if (svixPrevClose == null) return null;
    return svixPrevClose! * (1 - r);
  }

  /// SVXY 현재가 대비 괴리율 (이론가 기준)
  double? svxyDeviation(double r) {
    final theoretical = svxyTheoretical(r);
    if (theoretical == null || svxyPrice == null || theoretical == 0) return null;
    return (svxyPrice! - theoretical) / theoretical * 100;
  }

  /// SVIX 현재가 대비 괴리율 (이론가 기준)
  double? svixDeviation(double r) {
    final theoretical = svixTheoretical(r);
    if (theoretical == null || svixPrice == null || theoretical == 0) return null;
    return (svixPrice! - theoretical) / theoretical * 100;
  }

  /// VIX 목표값 → R 계산 (근사: ΔVIXFutures ≈ ΔVIX)
  double? rFromTargetVix(double targetVix) {
    if (vixCurrent == null || vixCurrent == 0) return null;
    return (targetVix - vixCurrent!) / vixCurrent!;
  }

  static const VixEtfData empty = VixEtfData(updatedAt: '');
}
