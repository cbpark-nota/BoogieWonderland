import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/holding.dart';
import '../models/portfolio_data.dart';
import '../models/screening_result.dart';
import '../services/local_portfolio_service.dart';
import '../services/static_data_source.dart';
import 'screening_provider.dart';
import 'portfolio_provider.dart';

// ── 서버리스 스크리닝 ──────────────────────────────────────

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

// ── 서버리스 포트폴리오 ────────────────────────────────────

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

// ── 서버리스 시장 상태 ─────────────────────────────────────
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

// ── 서버리스 스톱 체크 (정적 데이터 기반) ────────────────────

Future<List<StopCheckResult>> serverlessStopCheck(Ref ref, void _) async {
  return [];
}

// ── 서버리스 4전략 데이터 ──────────────────────────────────

final strategyDataProvider =
    FutureProvider<StrategyScreeningData?>((ref) async {
  try {
    final data = await StaticDataSource().getStrategies();
    return StrategyScreeningData.fromJson(data);
  } catch (_) {
    return null;
  }
});

// ── 서버리스 포트폴리오 데이터 (엑셀 기반) ──────────────────────

final portfolioDataProvider = FutureProvider<PortfolioData>((ref) async {
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

// ── 히스토리 날짜 목록 ──────────────────────────────────────

final historyDatesProvider = FutureProvider<List<String>>((ref) async {
  return StaticDataSource().getHistoryDates();
});

// ── 선택된 히스토리 날짜 (null = 최신) ─────────────────────

final selectedHistoryDateProvider = StateProvider<String?>((ref) => null);

// ── 선택된 날짜의 스크리닝 데이터 ──────────────────────────

final historyScreeningProvider =
    FutureProvider<StrategyScreeningData?>((ref) async {
  final date = ref.watch(selectedHistoryDateProvider);
  if (date == null) {
    // 최신 데이터 사용
    return ref.watch(strategyDataProvider).valueOrNull;
  }
  try {
    final data = await StaticDataSource().getScreeningByDate(date);
    return StrategyScreeningData.fromJson(data);
  } catch (_) {
    return null;
  }
});
