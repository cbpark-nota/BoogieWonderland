import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/screening_result.dart';
import '../services/static_data_source.dart';
import 'serverless_providers.dart';

// ── 리밸런싱 주기 ─────────────────────────────────────────────

enum RebalanceMode {
  aggressive('공격적', '매주 금요일'),
  balanced('균형', '격주 금요일'),
  conservative('보수적', '월말 영업일');

  final String label;
  final String description;
  const RebalanceMode(this.label, this.description);
}

// ── 리밸런싱 신호 모델 ────────────────────────────────────────

class RebalanceSignal {
  final String? rebalanceDate;
  final Set<String> screeningTickers;

  const RebalanceSignal({this.rebalanceDate, required this.screeningTickers});

  /// 해당 티커가 스크리닝에 없으면 true → 매도 검토
  bool shouldSell(String ticker) =>
      rebalanceDate != null && !screeningTickers.contains(ticker);
}

// ── 날짜 계산 헬퍼 ─────────────────────────────────────────────

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

// ── 선택된 리밸런싱 주기 ──────────────────────────────────────

class _RebalanceModeNotifier extends Notifier<RebalanceMode> {
  @override
  RebalanceMode build() => RebalanceMode.conservative;
}

final selectedRebalanceModeProvider =
    NotifierProvider<_RebalanceModeNotifier, RebalanceMode>(
  _RebalanceModeNotifier.new,
);

// ── 리밸런싱 기준일 매도 신호 ─────────────────────────────────

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
  } catch (e) {
    debugPrint('rebalanceSignalProvider($dateStr): screening fetch failed: $e');
    return RebalanceSignal(rebalanceDate: dateStr, screeningTickers: {});
  }
});
