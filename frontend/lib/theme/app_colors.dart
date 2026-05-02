import 'package:flutter/material.dart';

/// 앱 전역 의미 기반 색상 토큰.
///
/// 가격 등락 컨벤션은 미국식: green = 상승(+), red = 하락(-).
/// 다크모드 정식 대응은 별도 작업 항목이므로 여기서는 라이트 모드 기준
/// MaterialColor 매핑만 정의한다.
abstract class AppColors {
  AppColors._();

  // ── 가격/등락 ────────────────────────────────────────────────
  /// 상승·매수 신호·플러스 수익률.
  ///
  /// MaterialColor 그대로 노출하여 호출 측에서 `.shade300`, `[300]` 등
  /// 셰이드 접근이 필요할 때도 그대로 동작하도록 한다.
  static const MaterialColor priceUp = Colors.green;

  /// 하락·매도 신호·마이너스 수익률.
  static const MaterialColor priceDown = Colors.red;

  /// 가격이 중립이거나 시그널이 비활성일 때.
  static const MaterialColor priceNeutral = Colors.grey;

  /// 강조용(차트 라인, 굵은 라벨).
  static final Color priceUpStrong = Colors.green.shade700;
  static final Color priceDownStrong = Colors.red.shade700;
  static final Color priceUpMid = Colors.green.shade600;
  static final Color priceDownMid = Colors.red.shade600;
  static final Color priceDownSoft = Colors.red.shade400;

  // ── 의미 상태(success / warning / error / info) ───────────────
  /// 성공·완료·확인 메시지(SnackBar 등).
  static const MaterialColor success = Colors.green;

  /// 실패·에러·경고 알림(SnackBar 등).
  static const MaterialColor error = Colors.red;

  /// 주의·임계값 근처·중간 위험.
  static const MaterialColor warning = Colors.orange;

  /// 정보·중립·기본 강조.
  static const MaterialColor info = Colors.blue;

  static final Color warningStrong = Colors.orange.shade700;
  static final Color warningMid = Colors.orange.shade600;
  static final Color warningSoft = Colors.orange.shade400;
  static final Color warningSubtle = Colors.orange.shade200;
  static final Color warningBackground = Colors.orange.shade50;

  static final Color infoStrong = Colors.blue.shade700;
  static final Color infoMid = Colors.blue.shade600;

  // ── UI 장식(텍스트·디바이더·배경) ─────────────────────────────
  /// 보조 텍스트(부제, 캡션) 기본값. `Colors.grey` 별칭.
  static const MaterialColor mutedText = Colors.grey;

  /// 강한 보조 텍스트(라벨, 강조 부제).
  static final Color secondaryText = Colors.grey.shade700;

  /// 약간 강한 보조 텍스트.
  static final Color mutedTextStrong = Colors.grey.shade600;

  /// 플레이스홀더·비활성 텍스트.
  static final Color placeholderText = Colors.grey.shade500;

  /// 디바이더·테두리 기본값.
  static final Color divider = Colors.grey.shade300;
  static final Color dividerLight = Colors.grey.shade200;

  /// 카드/패널 옅은 배경.
  static final Color subtleBackground = Colors.grey.shade100;

  // ── 강조/카테고리 ────────────────────────────────────────────
  /// 보조 브랜드 강조(차트, 카테고리 칩 등).
  static const MaterialColor brandAccent = Colors.purple;
  static final Color brandAccentStrong = Colors.purple.shade600;

  /// 랭킹 1~3위, 메달.
  static final Color rankGold = Colors.amber.shade700;

  /// 황색 보조(노티스, 하이라이트).
  static const MaterialColor amber = Colors.amber;
  static final Color amberSubtle = Colors.amber.shade50;
  static final Color amberLight = Colors.amber.shade100;
  static final Color amberDeep = Colors.amber.shade900;

  /// 인디고 강조(보조 차트, 헤더).
  static final Color indigo = Colors.indigo.shade600;
}
