import 'dart:typed_data';

/// 비웹 환경용 다운로드 스텁 (no-op)
void triggerFileDownload(Uint8List bytes, String filename) {
  // 웹이 아닌 환경에서는 지원하지 않음
}
