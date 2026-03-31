import 'package:flutter_test/flutter_test.dart';
import 'package:momentum_app/models/screening_result.dart';
import 'package:momentum_app/models/holding.dart';

void main() {
  // ========================================
  // 1. ScreeningResult.fromJson 테스트
  // ========================================
  group('ScreeningResult.fromJson', () {
    test('모든 필드가 정상적으로 파싱된다', () {
      final json = {
        'rank': 1,
        'ticker': 'AAPL',
        'market': 'US',
        'sector': 'Technology',
        'score': 95.5,
        'weight_pct': 10.0,
        'price': 180.25,
        'adx': 30.5,
        'rsi': 65.2,
        'ret_3m': 12.3,
        'stop_price': 170.0,
        'stop_dist_pct': -5.7,
        'atr': 3.2,
      };

      final result = ScreeningResult.fromJson(json);

      expect(result.rank, 1);
      expect(result.ticker, 'AAPL');
      expect(result.market, 'US');
      expect(result.sector, 'Technology');
      expect(result.score, 95.5);
      expect(result.weightPct, 10.0);
      expect(result.price, 180.25);
      expect(result.adx, 30.5);
      expect(result.rsi, 65.2);
      expect(result.ret3m, 12.3);
      expect(result.stopPrice, 170.0);
      expect(result.stopDistPct, -5.7);
      expect(result.atr, 3.2);
    });

    test('nullable 필드가 null일 때 정상 처리된다', () {
      final json = {
        'rank': 2,
        'ticker': 'MSFT',
        'market': 'US',
        'sector': 'Technology',
        'score': 88.0,
        'weight_pct': 8.0,
        'price': 350.0,
        'adx': null,
        'rsi': null,
        'ret_3m': null,
        'stop_price': null,
        'stop_dist_pct': null,
        'atr': null,
      };

      final result = ScreeningResult.fromJson(json);

      expect(result.adx, isNull);
      expect(result.rsi, isNull);
      expect(result.ret3m, isNull);
      expect(result.stopPrice, isNull);
      expect(result.stopDistPct, isNull);
      expect(result.atr, isNull);
    });

    test('nullable 필드가 JSON에 없을 때 null로 처리된다', () {
      final json = {
        'rank': 3,
        'ticker': 'GOOG',
        'market': 'US',
        'sector': 'Communication',
        'score': 80.0,
        'weight_pct': 7.0,
        'price': 140.0,
      };

      final result = ScreeningResult.fromJson(json);

      expect(result.adx, isNull);
      expect(result.rsi, isNull);
      expect(result.ret3m, isNull);
    });

    test('market이 KR일 때 flag가 🇰🇷이다', () {
      final json = {
        'rank': 1,
        'ticker': '005930',
        'market': 'KR',
        'sector': '반도체',
        'score': 90.0,
        'weight_pct': 15.0,
        'price': 70000.0,
      };

      final result = ScreeningResult.fromJson(json);
      expect(result.flag, '🇰🇷');
    });

    test('market이 US일 때 flag가 🇺🇸이다', () {
      final json = {
        'rank': 1,
        'ticker': 'AAPL',
        'market': 'US',
        'sector': 'Technology',
        'score': 90.0,
        'weight_pct': 10.0,
        'price': 180.0,
      };

      final result = ScreeningResult.fromJson(json);
      expect(result.flag, '🇺🇸');
    });

    test('market이 없을 때 기본값 US로 설정되고 flag가 🇺🇸이다', () {
      final json = {
        'rank': 1,
        'ticker': 'TSLA',
        'sector': 'Automotive',
        'score': 70.0,
        'weight_pct': 5.0,
        'price': 250.0,
      };

      final result = ScreeningResult.fromJson(json);
      expect(result.market, 'US');
      expect(result.flag, '🇺🇸');
    });

    test('score가 int로 들어와도 double로 변환된다', () {
      final json = {
        'rank': 1,
        'ticker': 'NVDA',
        'market': 'US',
        'sector': 'Technology',
        'score': 85,
        'weight_pct': 12,
        'price': 500,
      };

      final result = ScreeningResult.fromJson(json);
      expect(result.score, isA<double>());
      expect(result.score, 85.0);
      expect(result.weightPct, 12.0);
      expect(result.price, 500.0);
    });
  });

  // ========================================
  // 2. MarketStatus.fromJson 테스트
  // ========================================
  group('MarketStatus.fromJson', () {
    test('정상 파싱된다', () {
      final json = {
        'spy_price': 450.5,
        'is_golden_cross': true,
        'ma20': 440.0,
        'ma60': 420.0,
        'gap_pct': 4.76,
        'next_rebalance': '2026-04-01',
      };

      final status = MarketStatus.fromJson(json);

      expect(status.spyPrice, 450.5);
      expect(status.isGoldenCross, true);
      expect(status.ma20, 440.0);
      expect(status.ma60, 420.0);
      expect(status.gapPct, 4.76);
      expect(status.nextRebalance, '2026-04-01');
    });

    test('nextRebalance가 null일 때 정상 처리된다', () {
      final json = {
        'spy_price': 450.0,
        'is_golden_cross': true,
        'ma20': 440.0,
        'ma60': 420.0,
        'gap_pct': 4.0,
        'next_rebalance': null,
      };

      final status = MarketStatus.fromJson(json);
      expect(status.nextRebalance, isNull);
    });

    test('is_golden_cross가 null일 때 false 기본값이다', () {
      final json = {
        'spy_price': 400.0,
        'is_golden_cross': null,
        'ma20': 410.0,
        'ma60': 420.0,
        'gap_pct': -2.38,
      };

      final status = MarketStatus.fromJson(json);
      expect(status.isGoldenCross, false);
    });

    test('is_golden_cross 키가 없을 때 false 기본값이다', () {
      final json = {
        'spy_price': 400.0,
        'ma20': 410.0,
        'ma60': 420.0,
        'gap_pct': -2.38,
      };

      final status = MarketStatus.fromJson(json);
      expect(status.isGoldenCross, false);
    });
  });

  // ========================================
  // 3. ScreeningRun.fromJson 테스트
  // ========================================
  group('ScreeningRun.fromJson', () {
    test('전체 구조가 정상 파싱된다 (market_status + results 리스트)', () {
      final json = {
        'run_id': 42,
        'run_date': '2026-03-22',
        'market_status': {
          'spy_price': 450.0,
          'is_golden_cross': true,
          'ma20': 440.0,
          'ma60': 420.0,
          'gap_pct': 4.76,
          'next_rebalance': '2026-04-01',
        },
        'total_screened': 500,
        'total_passed': 10,
        'results': [
          {
            'rank': 1,
            'ticker': 'AAPL',
            'market': 'US',
            'sector': 'Technology',
            'score': 95.0,
            'weight_pct': 10.0,
            'price': 180.0,
          },
          {
            'rank': 2,
            'ticker': 'MSFT',
            'market': 'US',
            'sector': 'Technology',
            'score': 90.0,
            'weight_pct': 8.0,
            'price': 350.0,
          },
        ],
      };

      final run = ScreeningRun.fromJson(json);

      expect(run.runId, 42);
      expect(run.runDate, '2026-03-22');
      expect(run.marketStatus, isNotNull);
      expect(run.marketStatus!.spyPrice, 450.0);
      expect(run.marketStatus!.isGoldenCross, true);
      expect(run.totalScreened, 500);
      expect(run.totalPassed, 10);
      expect(run.results.length, 2);
      expect(run.results[0].ticker, 'AAPL');
      expect(run.results[1].ticker, 'MSFT');
    });

    test('market_status가 null일 때 정상 처리된다', () {
      final json = {
        'run_id': 43,
        'run_date': '2026-03-22',
        'market_status': null,
        'total_screened': 100,
        'total_passed': 5,
        'results': [],
      };

      final run = ScreeningRun.fromJson(json);
      expect(run.marketStatus, isNull);
    });

    test('results가 빈 리스트일 때 정상 처리된다', () {
      final json = {
        'run_id': 44,
        'run_date': '2026-03-22',
        'market_status': null,
        'total_screened': 0,
        'total_passed': 0,
        'results': [],
      };

      final run = ScreeningRun.fromJson(json);
      expect(run.results, isEmpty);
      expect(run.totalScreened, 0);
      expect(run.totalPassed, 0);
    });

    test('total_screened/total_passed가 없을 때 기본값 0이다', () {
      final json = {
        'run_id': 45,
        'run_date': '2026-03-22',
        'results': [],
      };

      final run = ScreeningRun.fromJson(json);
      expect(run.totalScreened, 0);
      expect(run.totalPassed, 0);
    });
  });

  // ========================================
  // 4. Holding.fromJson 테스트
  // ========================================
  group('Holding.fromJson', () {
    test('정상 파싱된다', () {
      final json = {
        'id': 1,
        'ticker': 'AAPL',
        'entry_price': 150.0,
        'entry_date': '2026-01-15',
        'peak_price': 185.0,
        'is_active': true,
      };

      final holding = Holding.fromJson(json);

      expect(holding.id, 1);
      expect(holding.ticker, 'AAPL');
      expect(holding.entryPrice, 150.0);
      expect(holding.entryDate, '2026-01-15');
      expect(holding.peakPrice, 185.0);
      expect(holding.isActive, true);
    });

    test('is_active가 null일 때 true 기본값이다', () {
      final json = {
        'id': 2,
        'ticker': 'MSFT',
        'entry_price': 300.0,
        'entry_date': '2026-02-01',
        'peak_price': 360.0,
        'is_active': null,
      };

      final holding = Holding.fromJson(json);
      expect(holding.isActive, true);
    });

    test('is_active 키가 없을 때 true 기본값이다', () {
      final json = {
        'id': 3,
        'ticker': 'GOOG',
        'entry_price': 130.0,
        'entry_date': '2026-03-01',
        'peak_price': 145.0,
      };

      final holding = Holding.fromJson(json);
      expect(holding.isActive, true);
    });

    test('is_active가 false일 때 false이다', () {
      final json = {
        'id': 4,
        'ticker': 'TSLA',
        'entry_price': 200.0,
        'entry_date': '2025-12-01',
        'peak_price': 280.0,
        'is_active': false,
      };

      final holding = Holding.fromJson(json);
      expect(holding.isActive, false);
    });
  });

  // ========================================
  // 5. StopCheckResult.fromJson 테스트
  // ========================================
  group('StopCheckResult.fromJson', () {
    test('BREACH 이벤트가 정상 파싱된다', () {
      final json = {
        'ticker': 'AAPL',
        'current_price': 145.0,
        'stop_price': 150.0,
        'margin_pct': -3.33,
        'event_type': 'BREACH',
      };

      final result = StopCheckResult.fromJson(json);

      expect(result.ticker, 'AAPL');
      expect(result.currentPrice, 145.0);
      expect(result.stopPrice, 150.0);
      expect(result.marginPct, -3.33);
      expect(result.eventType, 'BREACH');
    });

    test('WARNING 이벤트가 정상 파싱된다', () {
      final json = {
        'ticker': 'MSFT',
        'current_price': 305.0,
        'stop_price': 300.0,
        'margin_pct': 1.67,
        'event_type': 'WARNING',
      };

      final result = StopCheckResult.fromJson(json);

      expect(result.eventType, 'WARNING');
      expect(result.currentPrice, 305.0);
    });

    test('eventType이 null일 때 정상 처리된다', () {
      final json = {
        'ticker': 'GOOG',
        'current_price': 140.0,
        'stop_price': 120.0,
        'margin_pct': 16.67,
        'event_type': null,
      };

      final result = StopCheckResult.fromJson(json);
      expect(result.eventType, isNull);
    });

    test('event_type 키가 없을 때 null이다', () {
      final json = {
        'ticker': 'NVDA',
        'current_price': 500.0,
        'stop_price': 450.0,
        'margin_pct': 11.11,
      };

      final result = StopCheckResult.fromJson(json);
      expect(result.eventType, isNull);
    });
  });

  // ========================================
  // 6. StrategyType enum 테스트
  // ========================================
  group('StrategyType enum', () {
    test('aggressive 전략의 key, label, description이 올바르다', () {
      expect(StrategyType.aggressive.key, 'aggressive');
      expect(StrategyType.aggressive.label, '공격적');
      expect(StrategyType.aggressive.description, 'ATR 1.5 / 주간 / TOP15');
    });

    test('balanced 전략의 key, label, description이 올바르다', () {
      expect(StrategyType.balanced.key, 'balanced');
      expect(StrategyType.balanced.label, '균형형');
      expect(StrategyType.balanced.description, 'ATR 2.0 / 격주 / TOP10');
    });

    test('conservative 전략의 key, label, description이 올바르다', () {
      expect(StrategyType.conservative.key, 'conservative');
      expect(StrategyType.conservative.label, '보수적');
      expect(StrategyType.conservative.description, 'ATR 2.5 / 월간 / TOP7');
    });

    test('adaptive 전략의 key, label, description이 올바르다', () {
      expect(StrategyType.adaptive.key, 'adaptive');
      expect(StrategyType.adaptive.label, '적응형');
      expect(StrategyType.adaptive.description, '국면별 동적 전환');
    });

    test('StrategyType.values에 4가지 전략이 존재한다', () {
      expect(StrategyType.values.length, 4);
    });
  });

  // ========================================
  // 7. StrategyScreeningData.fromJson 테스트
  // ========================================
  group('StrategyScreeningData.fromJson', () {
    Map<String, dynamic> _buildStrategyJson({
      String label = '공격적',
      double atrMult = 2.0,
      String rebalFreq = 'weekly',
      int totalScreened = 500,
      int totalPassed = 10,
      List<Map<String, dynamic>>? results,
      String? regimeLabel,
    }) {
      return {
        'label': label,
        'atr_mult': atrMult,
        'rebal_freq': rebalFreq,
        'total_screened': totalScreened,
        'total_passed': totalPassed,
        'results': results ??
            [
              {
                'rank': 1,
                'ticker': 'AAPL',
                'market': 'US',
                'sector': 'Tech',
                'score': 95.0,
                'weight_pct': 10.0,
                'price': 180.0,
              }
            ],
        if (regimeLabel != null) 'regime_label': regimeLabel,
      };
    }

    test('4전략 결과가 정상 파싱된다', () {
      final json = {
        'run_id': 100,
        'run_date': '2026-03-22',
        'market_status': {
          'spy_price': 450.0,
          'is_golden_cross': true,
          'ma20': 440.0,
          'ma60': 420.0,
          'gap_pct': 4.76,
        },
        'strategies': {
          'aggressive': _buildStrategyJson(
            label: '공격적',
            atrMult: 2.0,
            rebalFreq: 'weekly',
          ),
          'balanced': _buildStrategyJson(
            label: '균형형',
            atrMult: 2.5,
            rebalFreq: 'biweekly',
          ),
          'conservative': _buildStrategyJson(
            label: '보수적',
            atrMult: 3.5,
            rebalFreq: 'monthly',
          ),
          'adaptive': _buildStrategyJson(
            label: '적응형',
            atrMult: 2.5,
            rebalFreq: 'dynamic',
            regimeLabel: 'bull',
          ),
        },
      };

      final data = StrategyScreeningData.fromJson(json);

      expect(data.runId, 100);
      expect(data.runDate, '2026-03-22');
      expect(data.marketStatus, isNotNull);
      expect(data.strategies.length, 4);
      expect(data.strategies[StrategyType.aggressive], isNotNull);
      expect(data.strategies[StrategyType.balanced], isNotNull);
      expect(data.strategies[StrategyType.conservative], isNotNull);
      expect(data.strategies[StrategyType.adaptive], isNotNull);
      expect(data.strategies[StrategyType.aggressive]!.label, '공격적');
      expect(data.strategies[StrategyType.balanced]!.atrMult, 2.5);
      expect(data.strategies[StrategyType.conservative]!.rebalFreq, 'monthly');
    });

    test('toScreeningRun 변환이 올바르게 동작한다', () {
      final json = {
        'run_id': 101,
        'run_date': '2026-03-22',
        'market_status': {
          'spy_price': 450.0,
          'is_golden_cross': true,
          'ma20': 440.0,
          'ma60': 420.0,
          'gap_pct': 4.76,
        },
        'strategies': {
          'aggressive': _buildStrategyJson(
            totalScreened: 500,
            totalPassed: 10,
          ),
        },
      };

      final data = StrategyScreeningData.fromJson(json);
      final run = data.toScreeningRun(StrategyType.aggressive);

      expect(run.runId, 101);
      expect(run.runDate, '2026-03-22');
      expect(run.marketStatus, isNotNull);
      expect(run.totalScreened, 500);
      expect(run.totalPassed, 10);
      expect(run.results.length, 1);
      expect(run.results[0].ticker, 'AAPL');
    });

    test('toScreeningRun에서 존재하지 않는 전략은 빈 결과를 반환한다', () {
      final json = {
        'run_id': 102,
        'run_date': '2026-03-22',
        'strategies': {
          'aggressive': _buildStrategyJson(),
        },
      };

      final data = StrategyScreeningData.fromJson(json);
      final run = data.toScreeningRun(StrategyType.conservative);

      expect(run.totalScreened, 0);
      expect(run.totalPassed, 0);
      expect(run.results, isEmpty);
    });

    test('currentRegime 필드가 적응형 전략에서 올바르게 파싱된다', () {
      final json = {
        'run_id': 103,
        'run_date': '2026-03-22',
        'strategies': {
          'adaptive': _buildStrategyJson(
            label: '적응형',
            atrMult: 2.5,
            rebalFreq: 'dynamic',
            regimeLabel: 'bull',
          ),
        },
      };

      final data = StrategyScreeningData.fromJson(json);
      expect(
          data.strategies[StrategyType.adaptive]!.currentRegime, 'bull');
    });

    test('market_status가 null일 때 정상 처리된다', () {
      final json = {
        'run_id': 104,
        'run_date': '2026-03-22',
        'market_status': null,
        'strategies': {
          'aggressive': _buildStrategyJson(),
        },
      };

      final data = StrategyScreeningData.fromJson(json);
      expect(data.marketStatus, isNull);
    });
  });

  // ========================================
  // 8. StrategyResult.fromJson 테스트
  // ========================================
  group('StrategyResult.fromJson', () {
    test('정상 파싱된다', () {
      final json = {
        'label': '공격적',
        'atr_mult': 2.0,
        'rebal_freq': 'weekly',
        'total_screened': 500,
        'total_passed': 10,
        'results': [
          {
            'rank': 1,
            'ticker': 'AAPL',
            'market': 'US',
            'sector': 'Technology',
            'score': 95.0,
            'weight_pct': 10.0,
            'price': 180.0,
          },
        ],
        'regime_label': 'bull',
      };

      final result = StrategyResult.fromJson(json);

      expect(result.label, '공격적');
      expect(result.atrMult, 2.0);
      expect(result.rebalFreq, 'weekly');
      expect(result.totalScreened, 500);
      expect(result.totalPassed, 10);
      expect(result.results.length, 1);
      expect(result.results[0].ticker, 'AAPL');
      expect(result.currentRegime, 'bull');
    });

    test('currentRegime(regime_label)이 null일 때 null이다', () {
      final json = {
        'label': '균형형',
        'atr_mult': 2.5,
        'rebal_freq': 'biweekly',
        'total_screened': 300,
        'total_passed': 8,
        'results': [],
      };

      final result = StrategyResult.fromJson(json);
      expect(result.currentRegime, isNull);
    });

    test('label과 rebal_freq가 없을 때 빈 문자열 기본값이다', () {
      final json = {
        'atr_mult': 3.5,
        'total_screened': 200,
        'total_passed': 5,
        'results': [],
      };

      final result = StrategyResult.fromJson(json);
      expect(result.label, '');
      expect(result.rebalFreq, '');
    });

    test('results가 빈 리스트일 때 정상 처리된다', () {
      final json = {
        'label': '보수적',
        'atr_mult': 3.5,
        'rebal_freq': 'monthly',
        'total_screened': 0,
        'total_passed': 0,
        'results': [],
      };

      final result = StrategyResult.fromJson(json);
      expect(result.results, isEmpty);
    });
  });
}
