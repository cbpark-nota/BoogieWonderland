import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/holding.dart';
import '../models/portfolio_data.dart';
import '../models/screening_result.dart';
import '../models/short_squeeze.dart';
import '../services/local_portfolio_service.dart';
import '../services/static_data_source.dart';
import 'portfolio_upload_provider.dart';
import 'screening_provider.dart';
import 'portfolio_provider.dart';

// ── 서버리스 스크리닝 ──────────────────────────────────────────

class ServerlessScreeningNotifier extends ScreeningNotifier {
  final _source = StaticDataSource();

  @override
  Future<ScreeningRun?> build() async {
    try {
      final data = await _source.getLatestScreening();
      return ScreeningRun.fromJson(data);
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() async {
      final data = await _source.getLatestScreening();
      return ScreeningRun.fromJson(data);
    });
  }

  @override
  Future<void> runScreening() async {
    // 서버리스 모드에서는 수동 스크리닝 불가 — 정적 데이터만 제공
  }
}

// ── 서버리스 포트폴리오 ────────────────────────────────────────

class ServerlessHoldingsNotifier extends HoldingsNotifier {
  final _service = LocalPortfolioService();

  @override
  Future<List<Holding>> build() async {
    return _service.getHoldings();
  }

  @override
  Future<void> addHolding(String ticker, double entryPrice) async {
    await _service.addHolding(ticker, entryPrice);
    ref.invalidateSelf();
  }

  @override
  Future<void> removeHolding(String ticker) async {
    await _service.removeHolding(ticker);
    ref.invalidateSelf();
  }

  @override
  Future<void> refresh() async {
    ref.invalidateSelf();
  }
}

// ── 서버리스 시장 상태 ─────────────────────────────────────────
// 스크리닝 JSON에 포함된 market_status를 사용

Future<MarketStatus?> serverlessMarketStatus(Ref ref) async {
  try {
    final data = await StaticDataSource().getLatestScreening();
    final ms = data['market_status'];
    if (ms != null) return MarketStatus.fromJson(ms);
    return null;
  } catch (_) {
    return null;
  }
}

// ── 서버리스 스톱 체크 (정적 데이터 기반) ─────────────────────

Future<List<StopCheckResult>> serverlessStopCheck(Ref ref, void _) async {
  return [];
}

// ── 서버리스 4전략 데이터 (US) ──────────────────────────────────

final strategyDataProvider =
    FutureProvider<StrategyScreeningData?>((ref) async {
  try {
    final data = await StaticDataSource().getStrategies();
    return StrategyScreeningData.fromJson(data);
  } catch (_) {
    return null;
  }
});

// ── 서버리스 4전략 데이터 (KR, v3.2 신규) ──────────────────────

final krStrategyDataProvider =
    FutureProvider<StrategyScreeningData?>((ref) async {
  try {
    final data = await StaticDataSource().getKrStrategies();
    return StrategyScreeningData.fromJson(data);
  } catch (_) {
    return null;
  }
});

// ── 서버리스 포트폴리오 데이터 (엑셀 기반) ───────────────────────
// 우선순위: 사용자 업로드 파일 > 서버 portfolio.json

final portfolioDataProvider = FutureProvider<PortfolioData>((ref) async {
  // 업로드된 포트폴리오가 있으면 즉시 반환
  final uploaded = ref.watch(portfolioUploadProvider);
  if (uploaded != null) return uploaded;

  try {
    final data = await StaticDataSource().getPortfolio();
    return PortfolioData.fromJson(data);
  } catch (_) {
    return PortfolioData.fromJson({
      'updated_at': '',
      'total_invested': 0.0,
      'total_current': 0.0,
      'total_return_pct': 0.0,
      'holdings': [],
    });
  }
});

// ── 숏스퀴즈 데이터 ───────────────────────────────────────────

final shortSqueezeProvider = FutureProvider<ShortSqueezeData?>((ref) async {
  try {
    final data = await StaticDataSource().getShortSqueeze();
    return ShortSqueezeData.fromJson(data);
  } catch (_) {
    return null;
  }
});

// ── 시총 Top 20 (트렌드 모니터링) ─────────────────────────────

final marketCapTop20Provider = FutureProvider<Map<String, dynamic>?>((ref) async {
  try {
    return await StaticDataSource().getMarketCapTop20();
  } catch (_) {
    return null;
  }
});

// ── 히스토리 날짜 목록 ────────────────────────────────────────

final historyDatesProvider = FutureProvider<List<String>>((ref) async {
  return StaticDataSource().getHistoryDates();
});

// ── 선택된 히스토리 날짜 (null = 최신) ────────────────────────

class _SelectedHistoryDateNotifier extends Notifier<String?> {
  @override
  String? build() => null;
}

final selectedHistoryDateProvider =
    NotifierProvider<_SelectedHistoryDateNotifier, String?>(
  _SelectedHistoryDateNotifier.new,
);

// ── 선택된 날짜의 스크리닝 데이터 (US) ────────────────────────

final historyScreeningProvider =
    FutureProvider<StrategyScreeningData?>((ref) async {
  final date = ref.watch(selectedHistoryDateProvider);
  if (date == null) {
    return await ref.watch(strategyDataProvider.future);
  }
  try {
    final data = await StaticDataSource().getScreeningByDate(date);
    return StrategyScreeningData.fromJson(data);
  } catch (_) {
    return null;
  }
});

// ── 선택된 날짜의 스크리닝 데이터 (KR, v3.2 신규) ──────────────

final krHistoryScreeningProvider =
    FutureProvider<StrategyScreeningData?>((ref) async {
  final date = ref.watch(selectedHistoryDateProvider);
  if (date == null) {
    return await ref.watch(krStrategyDataProvider.future);
  }
  try {
    final data = await StaticDataSource().getKrScreeningByDate(date);
    return StrategyScreeningData.fromJson(data);
  } catch (_) {
    return null;
  }
});
