class ApiConfig {
  static const String baseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://localhost:8002',
  );

  static const String screening = '/api/screening';
  static const String portfolio = '/api/portfolio';
  static const String market = '/api/v1/market';
  static const String notifications = '/api/v1/notifications';
  static const String system = '/api/v1/system';
}
