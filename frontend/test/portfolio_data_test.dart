// portfolio_data_test.dart
// 테스트 대상: PortfolioHolding, PortfolioData, BtcSignal 데이터 모델
//
// 검증 내용:
//   - JSON → Dart 모델 파싱이 올바르게 동작하는지
//   - nullable 필드의 기본값 처리
//   - KR/US 마켓별 통화 포맷
//   - 포트폴리오 집계값(총 투자금액, 수익률 등) 파싱
//   - ATR 스톱로스 필드 파싱
//   - BTC 시그널 파싱

import 'package:flutter_test/flutter_test.dart';
import 'package:momentum_app/models/portfolio_data.dart';
import 'package:momentum_app/models/screening_result.dart';

void main() {
  // ========================================
  // 1. PortfolioHolding.fromJson 테스트
  // ========================================
  group('PortfolioHolding.fromJson', () {
    // 입력: 모든 필드가 채워진 US 종목 JSON
    // 출력: 각 필드가 올바르게 파싱된 PortfolioHolding 객체
    test('US 종목 모든 필드가 정상 파싱된다', () {
      final json = {
        'ticker': 'NVDA',
        'name': 'NVIDIA Corporation',
        'market': 'US',
        'entry_price': 130.50,
        'current_price': 145.20,
        'shares': 10.0,
        'entry_date': '2026-03-10',
        'stop_loss': 120.0,
        'target_price': 160.0,
        'memo': '모멘텀 진입',
        'invested': 1305.0,
        'current_value': 1452.0,
        'return_pct': 11.26,
        'weight_pct': 15.0,
        'stop_triggered': false,
        'invested_krw': 1800000.0,
        'current_value_krw': 2003760.0,
        'invested_usd': 1305.0,
        'current_value_usd': 1452.0,
        'atr_stop': 128.75,
        'atr_stop_dist_pct': -11.3,
        'atr_stop_triggered': false,
      };

      final holding = PortfolioHolding.fromJson(json);

      // 기본 필드
      expect(holding.ticker, 'NVDA');
      expect(holding.name, 'NVIDIA Corporation');
      expect(holding.market, 'US');
      expect(holding.entryPrice, 130.50);
      expect(holding.currentPrice, 145.20);
      expect(holding.shares, 10.0);
      expect(holding.entryDate, '2026-03-10');
      expect(holding.stopLoss, 120.0);
      expect(holding.targetPrice, 160.0);
      expect(holding.memo, '모멘텀 진입');
      // 집계 필드
      expect(holding.invested, 1305.0);
      expect(holding.currentValue, 1452.0);
      expect(holding.returnPct, 11.26);
      expect(holding.weightPct, 15.0);
      expect(holding.stopTriggered, false);
      // 환율 변환 필드
      expect(holding.investedKrw, 1800000.0);
      expect(holding.currentValueKrw, 2003760.0);
      expect(holding.investedUsd, 1305.0);
      expect(holding.currentValueUsd, 1452.0);
      // ATR 스톱로스 필드
      expect(holding.atrStop, 128.75);
      expect(holding.atrStopDistPct, -11.3);
      expect(holding.atrStopTriggered, false);
    });

    // 입력: KR 종목 JSON (name 없음, market=KR)
    // 출력: name이 ticker로 fallback, 통화기호가 ₩
    test('KR 종목에서 name이 없으면 ticker로 fallback된다', () {
      final json = {
        'ticker': '005930',
        'market': 'KR',
        'entry_price': 68000.0,
        'current_price': 72000.0,
        'shares': 5.0,
        'entry_date': '2026-03-01',
        'memo': '',
        'stop_triggered': false,
      };

      final holding = PortfolioHolding.fromJson(json);

      expect(holding.ticker, '005930');
      expect(holding.name, '005930'); // ticker로 fallback
      expect(holding.isKr, true);
      expect(holding.currencySymbol, '₩');
    });

    // 입력: US 종목 JSON
    // 출력: isKr=false, currencySymbol='$'
    test('US 종목 currencySymbol이 \$이다', () {
      final json = {
        'ticker': 'AAPL',
        'market': 'US',
        'shares': 1.0,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
      };

      final holding = PortfolioHolding.fromJson(json);

      expect(holding.isKr, false);
      expect(holding.currencySymbol, '\$');
    });

    // 입력: market 필드 없는 JSON
    // 출력: market 기본값 'US'
    test('market 필드 없을 때 기본값 US이다', () {
      final json = {
        'ticker': 'TSLA',
        'shares': 2.0,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
      };

      final holding = PortfolioHolding.fromJson(json);

      expect(holding.market, 'US');
      expect(holding.isKr, false);
    });

    // 입력: stop_triggered=true, atr_stop_triggered=true인 JSON
    // 출력: stopTriggered=true, atrStopTriggered=true
    test('스톱로스 트리거 상태가 올바르게 파싱된다', () {
      final json = {
        'ticker': 'AAPL',
        'market': 'US',
        'shares': 1.0,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': true,
        'atr_stop_triggered': true,
      };

      final holding = PortfolioHolding.fromJson(json);

      expect(holding.stopTriggered, true);
      expect(holding.atrStopTriggered, true);
    });

    // 입력: atr_stop_triggered 키 없는 JSON
    // 출력: atrStopTriggered 기본값 false
    test('atr_stop_triggered 없을 때 기본값 false이다', () {
      final json = {
        'ticker': 'MSFT',
        'market': 'US',
        'shares': 1.0,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
      };

      final holding = PortfolioHolding.fromJson(json);

      expect(holding.atrStopTriggered, false);
    });

    // 입력: price=null인 KR 종목
    // 출력: formatPrice(null) = '-'
    test('formatPrice(null)은 하이픈을 반환한다', () {
      final json = {
        'ticker': '000660',
        'market': 'KR',
        'shares': 3.0,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
      };

      final holding = PortfolioHolding.fromJson(json);

      expect(holding.formatPrice(null), '-');
    });

    // 입력: KR 종목의 formatPrice(72500)
    // 출력: '₩72,500' (천 단위 콤마, 소수 없음)
    test('KR 종목 formatPrice는 원화 형식으로 표시된다', () {
      final json = {
        'ticker': '005930',
        'market': 'KR',
        'shares': 1.0,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
      };

      final holding = PortfolioHolding.fromJson(json);

      expect(holding.formatPrice(72500.0), '₩72,500');
    });

    // 입력: US 종목의 formatPrice(145.20)
    // 출력: '$145.20' (소수 2자리)
    test('US 종목 formatPrice는 달러 형식으로 표시된다', () {
      final json = {
        'ticker': 'NVDA',
        'market': 'US',
        'shares': 1.0,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
      };

      final holding = PortfolioHolding.fromJson(json);

      expect(holding.formatPrice(145.20), '\$145.20');
    });
  });

  // ========================================
  // 2. PortfolioData.fromJson 테스트
  // ========================================
  group('PortfolioData.fromJson', () {
    // 입력: holdings 2개 포함된 완전한 포트폴리오 JSON
    // 출력: 집계값과 holdings 리스트가 올바르게 파싱됨
    test('전체 포트폴리오 데이터가 정상 파싱된다', () {
      final json = {
        'updated_at': '2026-03-28',
        'total_invested': 5000.0,
        'total_current': 5500.0,
        'total_return_pct': 10.0,
        'total_invested_krw': 6900000.0,
        'total_current_krw': 7590000.0,
        'total_invested_usd': 5000.0,
        'total_current_usd': 5500.0,
        'exchange_rate': {'usdkrw': 1380.0},
        'holdings': [
          {
            'ticker': 'NVDA',
            'name': 'NVIDIA',
            'market': 'US',
            'shares': 10.0,
            'entry_date': '2026-03-10',
            'memo': '',
            'stop_triggered': false,
          },
          {
            'ticker': 'META',
            'name': 'Meta',
            'market': 'US',
            'shares': 5.0,
            'entry_date': '2026-03-12',
            'memo': '',
            'stop_triggered': false,
          },
        ],
      };

      final portfolio = PortfolioData.fromJson(json);

      expect(portfolio.updatedAt, '2026-03-28');
      expect(portfolio.totalInvested, 5000.0);
      expect(portfolio.totalCurrent, 5500.0);
      expect(portfolio.totalReturnPct, 10.0);
      expect(portfolio.totalInvestedKrw, 6900000.0);
      expect(portfolio.totalCurrentKrw, 7590000.0);
      expect(portfolio.totalInvestedUsd, 5000.0);
      expect(portfolio.totalCurrentUsd, 5500.0);
      expect(portfolio.usdkrw, 1380.0);
      expect(portfolio.holdings.length, 2);
      expect(portfolio.holdings[0].ticker, 'NVDA');
      expect(portfolio.holdings[1].ticker, 'META');
      expect(portfolio.isEmpty, false);
    });

    // 입력: holdings 빈 리스트인 JSON
    // 출력: isEmpty = true
    test('holdings가 빈 리스트일 때 isEmpty가 true이다', () {
      final json = {
        'updated_at': '',
        'total_invested': 0.0,
        'total_current': 0.0,
        'total_return_pct': 0.0,
        'holdings': [],
      };

      final portfolio = PortfolioData.fromJson(json);

      expect(portfolio.isEmpty, true);
      expect(portfolio.holdings, isEmpty);
    });

    // 입력: exchange_rate 없는 JSON
    // 출력: usdkrw 기본값 1380.0
    test('exchange_rate 없을 때 usdkrw 기본값 1380.0이다', () {
      final json = {
        'updated_at': '',
        'total_invested': 0.0,
        'total_current': 0.0,
        'total_return_pct': 0.0,
        'holdings': [],
      };

      final portfolio = PortfolioData.fromJson(json);

      expect(portfolio.usdkrw, 1380.0);
    });

    // 입력: total_invested_krw 없지만 total_invested 있는 JSON (하위 호환)
    // 출력: totalInvestedKrw = total_invested 값 (fallback)
    test('total_invested_krw 없을 때 total_invested로 fallback된다', () {
      final json = {
        'updated_at': '',
        'total_invested': 3000.0,
        'total_current': 3300.0,
        'total_return_pct': 10.0,
        'exchange_rate': {'usdkrw': 1380.0},
        'holdings': [],
      };

      final portfolio = PortfolioData.fromJson(json);

      // heuristic: 구버전 JSON 구조 호환성
      expect(portfolio.totalInvestedKrw, 3000.0);
    });

    // 입력: holdings가 null인 JSON
    // 출력: holdings = []로 처리되어 isEmpty = true
    test('holdings가 null일 때 빈 리스트로 처리된다', () {
      final json = {
        'updated_at': '',
        'total_invested': 0.0,
        'total_current': 0.0,
        'total_return_pct': 0.0,
        'holdings': null,
      };

      final portfolio = PortfolioData.fromJson(json);

      expect(portfolio.holdings, isEmpty);
      expect(portfolio.isEmpty, true);
    });
  });

  // ========================================
  // 3. BtcSignal.fromJson 테스트
  // ========================================
  group('BtcSignal.fromJson', () {
    // 입력: 완전한 BTC 매수 시그널 JSON
    // 출력: 모든 필드가 올바르게 파싱됨
    test('BTC 매수 시그널이 정상 파싱된다', () {
      final json = {
        'signal': 'buy',
        'price': 68500.0,
        'reason': '스퀴즈 모멘텀 상승 돌파',
        'strategy': 'V10',
        'timestamp': '2026-03-28T09:00:00',
        'regime': 'bull',
      };

      final signal = BtcSignal.fromJson(json);

      expect(signal.signal, 'buy');
      expect(signal.price, 68500.0);
      expect(signal.reason, '스퀴즈 모멘텀 상승 돌파');
      expect(signal.strategy, 'V10');
      expect(signal.timestamp, '2026-03-28T09:00:00');
      expect(signal.regime, 'bull');
    });

    // 입력: signal=hold, price=null, regime=null인 JSON
    // 출력: signal='hold', price=null, regime=null
    test('hold 시그널에서 price와 regime이 null이어도 정상 처리된다', () {
      final json = {
        'signal': 'hold',
        'price': null,
        'reason': '추세 없음',
        'strategy': 'V10',
        'timestamp': '2026-03-28T09:00:00',
        'regime': null,
      };

      final signal = BtcSignal.fromJson(json);

      expect(signal.signal, 'hold');
      expect(signal.price, isNull);
      expect(signal.regime, isNull);
    });

    // 입력: signal 키 없는 JSON (기본값 확인)
    // 출력: signal='hold' (기본값)
    test('signal 키가 없을 때 기본값 hold이다', () {
      final json = {
        'reason': '',
        'strategy': 'V10',
        'timestamp': '2026-03-28T09:00:00',
      };

      final signal = BtcSignal.fromJson(json);

      expect(signal.signal, 'hold');
    });

    // 입력: strategy 키 없는 JSON
    // 출력: strategy='V10' (기본값)
    test('strategy 키가 없을 때 기본값 V10이다', () {
      final json = {
        'signal': 'buy',
        'reason': '테스트',
        'timestamp': '2026-03-28T09:00:00',
      };

      final signal = BtcSignal.fromJson(json);

      expect(signal.strategy, 'V10');
    });

    // 입력: reason, timestamp 키 없는 JSON
    // 출력: reason='', timestamp='' (빈 문자열 기본값)
    test('reason, timestamp 없을 때 빈 문자열이다', () {
      final json = {
        'signal': 'hold',
      };

      final signal = BtcSignal.fromJson(json);

      expect(signal.reason, '');
      expect(signal.timestamp, '');
    });
  });

  // ========================================
  // 4. MarketStatus KOSPI 필드 테스트
  // ========================================
  group('MarketStatus KOSPI 필드', () {
    // 입력: KOSPI 필드가 포함된 완전한 시장 상태 JSON
    // 출력: KOSPI 관련 모든 필드가 올바르게 파싱됨
    test('KOSPI 필드가 포함된 시장 상태가 정상 파싱된다', () {
      final json = {
        'spy_price': 523.4,
        'is_golden_cross': true,
        'ma20': 510.2,
        'ma60': 498.5,
        'gap_pct': 2.35,
        'kospi_price': 2550.0,
        'kospi_golden_cross': true,
        'kospi_ma20': 2520.0,
        'kospi_ma60': 2480.0,
        'kospi_gap_pct': 2.82,
      };

      final status = MarketStatus.fromJson(json);

      expect(status.kospiPrice, 2550.0);
      expect(status.kospiIsGoldenCross, true);
      expect(status.kospiMa20, 2520.0);
      expect(status.kospiMa60, 2480.0);
      expect(status.kospiGapPct, 2.82);
    });

    // 입력: KOSPI 필드 없는 JSON (US only)
    // 출력: KOSPI 필드 모두 null
    test('KOSPI 필드 없을 때 모두 null이다', () {
      final json = {
        'spy_price': 450.0,
        'is_golden_cross': true,
        'ma20': 440.0,
        'ma60': 420.0,
        'gap_pct': 4.76,
      };

      final status = MarketStatus.fromJson(json);

      expect(status.kospiPrice, isNull);
      expect(status.kospiIsGoldenCross, isNull);
      expect(status.kospiMa20, isNull);
      expect(status.kospiMa60, isNull);
      expect(status.kospiGapPct, isNull);
    });

    // 입력: KOSPI Dead Cross 상태 JSON
    // 출력: kospiIsGoldenCross = false
    test('KOSPI Dead Cross 상태가 올바르게 파싱된다', () {
      final json = {
        'spy_price': 450.0,
        'is_golden_cross': false,
        'ma20': 440.0,
        'ma60': 460.0,
        'gap_pct': -4.35,
        'kospi_price': 2400.0,
        'kospi_golden_cross': false,
        'kospi_ma20': 2380.0,
        'kospi_ma60': 2450.0,
        'kospi_gap_pct': -2.86,
      };

      final status = MarketStatus.fromJson(json);

      expect(status.isGoldenCross, false);
      expect(status.kospiIsGoldenCross, false);
      expect(status.gapPct, -4.35);
      expect(status.kospiGapPct, -2.86);
    });
  });
}
