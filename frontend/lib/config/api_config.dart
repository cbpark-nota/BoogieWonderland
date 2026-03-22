class ApiConfig {
  static const String baseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://localhost:8000',
  );

  static const String screening = '/api/v1/screening';
  static const String portfolio = '/api/v1/portfolio';
  static const String market = '/api/v1/market';
  static const String notifications = '/api/v1/notifications';
  static const String system = '/api/v1/system';
}
