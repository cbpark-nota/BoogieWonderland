class AppConfig {
  static const String deployMode = String.fromEnvironment(
    'DEPLOY_MODE',
    defaultValue: 'fullstack',
  );

  static bool get isServerless => deployMode == 'serverless';

  /// 서버리스 모드에서 정적 JSON 경로
  static const String staticDataPath = 'data';
}
