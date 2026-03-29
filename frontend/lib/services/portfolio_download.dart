/// 플랫폼별 파일 다운로드 헬퍼
/// - 웹: dart:html Blob URL 방식
/// - 비웹: no-op (stub)
export '_portfolio_download_stub.dart'
    if (dart.library.html) '_portfolio_download_web.dart';
