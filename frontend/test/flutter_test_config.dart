import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

/// 픽셀 허용 오차를 적용하는 golden 비교자.
/// CI 환경(Ubuntu)에서 폰트 렌더링 차이로 인한 소폭 픽셀 차이를 허용한다.
class _TolerantGoldenComparator extends LocalFileComparator {
  static const double _thresholdPercent = 2.0;

  _TolerantGoldenComparator(super.testFile);

  @override
  Future<bool> compare(Uint8List imageBytes, Uri golden) async {
    try {
      return await super.compare(imageBytes, golden);
    } on FlutterError catch (e) {
      // 에러 메시지에서 diff 퍼센트 추출 (예: "Pixel test failed, 0.83%, ...")
      final match = RegExp(r'([\d.]+)%').firstMatch(e.message);
      if (match != null) {
        final diffPct = double.tryParse(match.group(1) ?? '') ?? 100.0;
        if (diffPct < _thresholdPercent) {
          return true;
        }
      }
      rethrow;
    }
  }
}

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  final current = goldenFileComparator as LocalFileComparator;
  goldenFileComparator = _TolerantGoldenComparator(
    Uri.file('${current.basedir.toFilePath()}placeholder.dart'),
  );
  await testMain();
}
