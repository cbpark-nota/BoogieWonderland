import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/holding.dart';
import '../models/portfolio_data.dart';
import '../models/screening_result.dart';
import '../services/local_portfolio_service.dart';
import '../services/static_data_source.dart';
import 'screening_provider.dart';
import 'portfolio_provider.dart';

// ── 마켓 필터 enum (screening_screen에서 이동) ──────────────

enum MarketFilter { all, kr, us }

// ── 선택 상태 providers ────────────────────────────────────

class _SelectedStrategyNotifier extends Notifier<StrategyType> {
  @override
  StrategyType build() => StrategyType.balanced;
}

final selectedStrategyProvider =
    NotifierProvider<_SelectedStrategyNotifier, StrategyType>(
  _SelectedStrategyNotifier.new,
);

class _SelectedMarketFilterNotifier extends Notifier<MarketFilter> {
  @override
  MarketFilter build() => MarketFilter.all;
}

final selectedMarketFilterProvider =
    NotifierProvider<_SelectedMarketFilterNotifier, MarketFilter>(
  _SelectedMarketFilterNotifier.new,
);

// ── 필터링된 스크리닝 결과 (메모이제이션) ────────────────────
// historyScreeningProvider, selectedStrategyProvider,
// selectedMarketFilterProvider 중 하나라도 변경될 때만 재계산된다.

typedef _FilteredResult = ({ScreeningRun run, StrategyResult? sr, StrategyType selected});

final filteredScreeningProvider =
    Provider<AsyncValue<_FilteredResult?>>((ref) {
  final historyAsync = ref.watch(historyScreeningProvider);
  final selected = ref.watch(selectedStrategyProvider);
  final marketFilter = ref.watch(selectedMarketFilterProvider);

  return historyAsync.whenData((data) {
    if (data == null) return null;
    final run = data.toScreeningRun(selected);
    final sr = data.strategies[selected];
    return (run: _applyMarketFilter(run, marketFilter), sr: sr, selected: selected);
  });
});

ScreeningRun _applyMarketFilter(ScreeningRun run, MarketFilter marketFilter) {
  if (marketFilter == MarketFilter.all) return run;
  final marketCode = marketFilter == MarketFilter.kr ? 'KR' : 'US';
  final filtered =
      run.results.where((r) => r.market == marketCode).toList();
  final reranked = filtered.asMap().entries.map((e) {
    final r = e.value;
    return ScreeningResult(
      rank: e.key + 1,
      ticker: r.ticker,
      market: r.market,
      name: r.name,
      sector: r.sector,
      score: r.score,
      weightPct: r.weightPct,
      price: r.price,
      adx: r.adx,
      rsi: r.rsi,
      ret3m: r.ret3m,
      stopPrice: r.stopPrice,
      stopDistPct: r.stopDistPct,
      atr: r.atr,
    );
  }).toList();
  return ScreeningRun(
    runId: run.runId,
    runDate: run.runDate,
    marketStatus: run.marketStatus,
    btcSignal: run.btcSignal,
    totalScreened: run.totalScreened,
    totalPassed: run.totalPassed,
    results: reranked,
  );
}

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

class _SelectedHistoryDateNotifier extends Notifier<String?> {
  @override
  String? build() => null;
}

final selectedHistoryDateProvider =
    NotifierProvider<_SelectedHistoryDateNotifier, String?>(
  _SelectedHistoryDateNotifier.new,
);

// ── 선택된 날짜의 스크리닝 데이터 ──────────────────────────

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
