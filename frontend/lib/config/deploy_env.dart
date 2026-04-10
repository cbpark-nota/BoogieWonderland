/// 배포 환경 구분
///
/// --dart-define=DEPLOY_ENV=serverless  (기본값 — GitHub Pages 정적 배포)
/// --dart-define=DEPLOY_ENV=local       — 로컬 FastAPI 개발 서버
/// --dart-define=DEPLOY_ENV=cloud       — 미래 Cloudflare 배포
enum DeployEnv { serverless, local, cloud }

class DeployConfig {
  static const String _envValue = String.fromEnvironment(
    'DEPLOY_ENV',
    defaultValue: 'serverless',
  );

  static DeployEnv get current => switch (_envValue) {
        'local' => DeployEnv.local,
        'cloud' => DeployEnv.cloud,
        _ => DeployEnv.serverless,
      };

  /// API 베이스 URL. serverless 환경에서는 상대 경로(빈 문자열) 사용.
  static String get apiBaseUrl => switch (current) {
        DeployEnv.serverless => '',
        DeployEnv.local => 'http://localhost:8002',
        DeployEnv.cloud => 'https://api.yourdomain.com',
      };

  /// 정적 JSON 데이터를 사용하는 환경인지 여부
  static bool get useStaticData => current == DeployEnv.serverless;

  /// 백엔드 API 클라이언트를 사용하는 환경인지 여부
  static bool get useApiClient => current != DeployEnv.serverless;
}
