import 'deploy_env.dart';

/// 앱 전역 설정
///
/// [Deprecated] DEPLOY_MODE 환경 변수는 DEPLOY_ENV로 통합되었습니다.
/// 기존 코드와의 호환성을 위해 isServerless는 DeployConfig에 위임합니다.
class AppConfig {
  /// @Deprecated: DEPLOY_MODE는 deprecated. DEPLOY_ENV를 사용하세요.
  /// 호환성 유지를 위해 잔존; DeployConfig.useStaticData에 위임합니다.
  static bool get isServerless => DeployConfig.useStaticData;

  /// 서버리스 모드에서 정적 JSON 경로
  static const String staticDataPath = 'data';
}
