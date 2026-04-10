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

// ── 리밸런싱 주기 ──────────────────────────────────────────

enum RebalanceMode {
  aggressive('공격적', '매주 금요일'),
  balanced('균형', '격주 금요일'),
  conservative('보수적', '월말 영업일');

  final String label;
  final String description;
  const RebalanceMode(this.label, this.description);
}

// ── 리밸런싱 신호 모델 ────────────────────────────────────

class RebalanceSignal {
  final String? rebalanceDate;
  final Set<String> screeningTickers;

  const RebalanceSignal({this.rebalanceDate, required this.screeningTickers});

  /// 해당 티커가 스크리닝에 없으면 true → 매도 검토
  bool shouldSell(String ticker) =>
      rebalanceDate != null && !screeningTickers.contains(ticker);
}

// ── 날짜 계산 헬퍼 ────────────────────────────────────────

DateTime _lastFriday(DateTime date) {
  // Friday = weekday 5. 오늘 포함 가장 최근 금요일
  final daysBack = (date.weekday - 5) % 7;
  return DateTime(date.year, date.month, date.day)
      .subtract(Duration(days: daysBack));
}

DateTime _lastBiweeklyFriday(DateTime date) {
  final lastFri = _lastFriday(date);
  // 기준 격주 금요일: 2025-01-03
  final ref = DateTime(2025, 1, 3);
  final daysDiff = lastFri.difference(ref).inDays;
  final remainder = daysDiff % 14;
  if (remainder == 0) return lastFri;
  return lastFri.subtract(Duration(days: remainder));
}

DateTime _lastMonthEndBusinessDay(DateTime today) {
  // 이번 달 말일
  final curMonthEnd = DateTime(today.year, today.month + 1, 0);
  var d = curMonthEnd;
  while (d.weekday == DateTime.saturday || d.weekday == DateTime.sunday) {
    d = d.subtract(const Duration(days: 1));
  }
  // 아직 이번 달 말 영업일이 오지 않았으면 전 달 사용
  if (d.isAfter(today)) {
    final prevMonthEnd = DateTime(today.year, today.month, 0);
    d = prevMonthEnd;
    while (d.weekday == DateTime.saturday || d.weekday == DateTime.sunday) {
      d = d.subtract(const Duration(days: 1));
    }
  }
  return d;
}

DateTime _calcTargetRebalanceDate(RebalanceMode mode, DateTime today) {
  switch (mode) {
    case RebalanceMode.aggressive:
      return _lastFriday(today);
    case RebalanceMode.balanced:
      return _lastBiweeklyFriday(today);
    case RebalanceMode.conservative:
      return _lastMonthEndBusinessDay(today);
  }
}

String _dateToStr(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-'
    '${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

/// 가용 날짜 중 target 이하인 가장 최근 날짜 반환
String? _findClosestDate(DateTime target, List<String> availableDates) {
  if (availableDates.isEmpty) return null;
  final targetStr = _dateToStr(target);
  for (final d in availableDates) {
    // availableDates는 내림차순 정렬
    if (d.compareTo(targetStr) <= 0) return d;
  }
  return null;
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

// ── 숏스퀴즈 데이터 ────────────────────────────────────────

final shortSqueezeProvider = FutureProvider<ShortSqueezeData?>((ref) async {
  try {
    final data = await StaticDataSource().getShortSqueeze();
    return ShortSqueezeData.fromJson(data);
  } catch (_) {
    return null;
  }
});

// ── 시총 Top 20 (트렌드 모니터링) ────────────────────────────

final marketCapTop20Provider = FutureProvider<Map<String, dynamic>?>((ref) async {
  try {
    return await StaticDataSource().getMarketCapTop20();
  } catch (_) {
    return null;
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

// ── 선택된 리밸런싱 주기 ──────────────────────────────────

class _RebalanceModeNotifier extends Notifier<RebalanceMode> {
  @override
  RebalanceMode build() => RebalanceMode.conservative;
}

final selectedRebalanceModeProvider =
    NotifierProvider<_RebalanceModeNotifier, RebalanceMode>(
  _RebalanceModeNotifier.new,
);

// ── 리밸런싱 기준일 매도 신호 ─────────────────────────────

final rebalanceSignalProvider =
    FutureProvider<RebalanceSignal>((ref) async {
  final mode = ref.watch(selectedRebalanceModeProvider);
  final dates = await ref.watch(historyDatesProvider.future);

  final today = DateTime.now();
  final targetDate = _calcTargetRebalanceDate(mode, today);
  final dateStr = _findClosestDate(targetDate, dates);

  if (dateStr == null) {
    return const RebalanceSignal(screeningTickers: {});
  }

  try {
    final data = await StaticDataSource().getScreeningByDate(dateStr);
    final strategyData = StrategyScreeningData.fromJson(data);

    final StrategyType strategyType;
    if (mode == RebalanceMode.aggressive) {
      strategyType = StrategyType.aggressive;
    } else if (mode == RebalanceMode.balanced) {
      strategyType = StrategyType.balanced;
    } else {
      strategyType = StrategyType.conservative;
    }

    final sr = strategyData.strategies[strategyType];
    final tickers = sr?.results.map((r) => r.ticker).toSet() ?? <String>{};

    return RebalanceSignal(rebalanceDate: dateStr, screeningTickers: tickers);
  } catch (_) {
    return RebalanceSignal(rebalanceDate: dateStr, screeningTickers: {});
  }
});
