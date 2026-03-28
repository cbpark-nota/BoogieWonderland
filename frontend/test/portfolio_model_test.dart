import 'package:flutter_test/flutter_test.dart';
import 'package:momentum_app/models/portfolio_data.dart';

/// PortfolioHolding / PortfolioData 모델 단위 테스트
///
/// 오늘 추가된 기능:
///   1. ATR 스톱로스 필드 (atrStop, atrStopDistPct, atrStopTriggered)
///   2. 환율(usdkrw) null 처리 → 기본값 1380.0
///   3. KRW/USD 이중 금액 필드
///   4. formatPrice(), isKr, currencySymbol 동작
void main() {
  // ══════════════════════════════════════════════════════════
  // 1. PortfolioHolding.fromJson — ATR 스톱로스 필드
  // ══════════════════════════════════════════════════════════
  group('PortfolioHolding.fromJson — ATR 스톱로스 필드', () {
    // 입력: atr_stop, atr_stop_dist_pct, atr_stop_triggered 모두 유효한 값
    // 확인: 각 필드가 올바른 타입·값으로 파싱된다
    test('atrStop / atrStopDistPct / atrStopTriggered 정상 파싱', () {
      final json = {
        'ticker': 'AAPL',
        'name': 'Apple Inc.',
        'market': 'US',
        'shares': 10.0,
        'entry_date': '2026-01-15',
        'memo': '',
        'stop_triggered': false,
        'atr_stop': 175.50,
        'atr_stop_dist_pct': 5.2,
        'atr_stop_triggered': false,
      };
      final h = PortfolioHolding.fromJson(json);

      expect(h.atrStop, 175.50);
      expect(h.atrStopDistPct, 5.2);
      expect(h.atrStopTriggered, false);
    });

    // 입력: atr_stop, atr_stop_dist_pct가 명시적으로 null
    // 확인: 필드가 null로 파싱된다 (위젯에서 ATR 섹션 미표시)
    test('atrStop / atrStopDistPct가 명시적 null이면 null이다', () {
      final json = {
        'ticker': 'MSFT',
        'market': 'US',
        'shares': 5.0,
        'entry_date': '2026-02-01',
        'memo': '',
        'stop_triggered': false,
        'atr_stop': null,
        'atr_stop_dist_pct': null,
      };
      final h = PortfolioHolding.fromJson(json);

      expect(h.atrStop, isNull);
      expect(h.atrStopDistPct, isNull);
    });

    // 입력: atr_stop 관련 키 자체가 JSON에 없는 경우
    // 확인: 기본값 null/false로 처리된다
    test('atr_stop 키가 없으면 null 기본값이 사용된다', () {
      final json = {
        'ticker': 'GOOG',
        'market': 'US',
        'shares': 3.0,
        'entry_date': '2026-03-01',
        'memo': '',
        'stop_triggered': false,
      };
      final h = PortfolioHolding.fromJson(json);

      expect(h.atrStop, isNull);
      expect(h.atrStopDistPct, isNull);
      expect(h.atrStopTriggered, false);
    });

    // 입력: atr_stop_triggered = true (ATR 스톱 이탈 발생)
    // 확인: atrStopTriggered=true로 파싱되어 위젯에서 "추세 이탈" 표시 가능
    test('atrStopTriggered=true일 때 true로 파싱된다', () {
      final json = {
        'ticker': 'TSLA',
        'market': 'US',
        'shares': 2.0,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
        'atr_stop': 180.0,
        'atr_stop_dist_pct': -2.5,
        'atr_stop_triggered': true,
      };
      final h = PortfolioHolding.fromJson(json);

      expect(h.atrStopTriggered, true);
    });

    // 입력: atr_stop_dist_pct가 0 이하 (현재가 < ATR 스톱)
    // 확인: distPct <= 0 조건 → _AtrStopRow에서 "추세 이탈" 상태
    test('atrStopDistPct <= 0이면 추세 이탈 조건을 만족한다', () {
      final json = {
        'ticker': 'NVDA',
        'market': 'US',
        'shares': 5.0,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
        'atr_stop': 200.0,
        'atr_stop_dist_pct': -1.5,
        'atr_stop_triggered': false,
      };
      final h = PortfolioHolding.fromJson(json);

      // _AtrStopRow: triggered || distPct <= 0 → "추세 이탈" (빨간색)
      expect(h.atrStopDistPct!, lessThanOrEqualTo(0));
    });

    // 입력: atr_stop_dist_pct = 2.8 (0 초과, 3 이하)
    // 확인: 위험 구간 조건 만족 → _AtrStopRow에서 "위험 X%" 표시
    test('atrStopDistPct가 0 초과 3 이하이면 위험 구간 조건을 만족한다', () {
      final json = {
        'ticker': 'AMD',
        'market': 'US',
        'shares': 10.0,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
        'atr_stop': 150.0,
        'atr_stop_dist_pct': 2.8,
        'atr_stop_triggered': false,
      };
      final h = PortfolioHolding.fromJson(json);

      // _AtrStopRow: 0 < distPct <= 3 → "위험 X%" (빨간색)
      expect(h.atrStopDistPct!, greaterThan(0));
      expect(h.atrStopDistPct!, lessThanOrEqualTo(3));
    });

    // 입력: atr_stop_dist_pct = 5.5 (3 초과, 7 이하)
    // 확인: 주의 구간 조건 만족 → _AtrStopRow에서 "주의 X%" 표시
    test('atrStopDistPct가 3 초과 7 이하이면 주의 구간 조건을 만족한다', () {
      final json = {
        'ticker': 'META',
        'market': 'US',
        'shares': 3.0,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
        'atr_stop': 400.0,
        'atr_stop_dist_pct': 5.5,
        'atr_stop_triggered': false,
      };
      final h = PortfolioHolding.fromJson(json);

      // _AtrStopRow: 3 < distPct <= 7 → "주의 X%" (주황색)
      expect(h.atrStopDistPct!, greaterThan(3));
      expect(h.atrStopDistPct!, lessThanOrEqualTo(7));
    });

    // 입력: atr_stop_dist_pct = 12.0 (7 초과)
    // 확인: 안전 구간 조건 만족 → _AtrStopRow에서 "안전 X%" 표시
    test('atrStopDistPct가 7 초과이면 안전 구간 조건을 만족한다', () {
      final json = {
        'ticker': 'AMZN',
        'market': 'US',
        'shares': 2.0,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
        'atr_stop': 150.0,
        'atr_stop_dist_pct': 12.0,
        'atr_stop_triggered': false,
      };
      final h = PortfolioHolding.fromJson(json);

      // _AtrStopRow: distPct > 7 → "안전 X%" (초록색)
      expect(h.atrStopDistPct!, greaterThan(7));
    });

    // 입력: atr_stop_dist_pct를 int로 받는 경우 (JSON에서 정수로 올 수 있음)
    // 확인: double로 정상 변환된다
    test('atr_stop_dist_pct가 int로 들어오면 double로 변환된다', () {
      final json = {
        'ticker': 'AAPL',
        'market': 'US',
        'shares': 5.0,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
        'atr_stop': 170,
        'atr_stop_dist_pct': 8,
      };
      final h = PortfolioHolding.fromJson(json);

      expect(h.atrStop, isA<double>());
      expect(h.atrStopDistPct, isA<double>());
      expect(h.atrStop, 170.0);
      expect(h.atrStopDistPct, 8.0);
    });
  });

  // ══════════════════════════════════════════════════════════
  // 2. PortfolioHolding — 가격 포맷팅 (formatPrice)
  // ══════════════════════════════════════════════════════════
  group('PortfolioHolding.formatPrice', () {
    PortfolioHolding _makeHolding(String market) => PortfolioHolding(
          ticker: market == 'KR' ? '005930.KS' : 'AAPL',
          name: market == 'KR' ? '삼성전자' : 'Apple',
          market: market,
          shares: 10,
          entryDate: '2026-01-01',
          memo: '',
          stopTriggered: false,
        );

    // 입력: US 종목, 가격 180.25
    // 확인: "$180.25" 형식으로 출력
    test(r'US 종목 가격은 달러 형식($X.XX)으로 포맷된다', () {
      final h = _makeHolding('US');
      expect(h.formatPrice(180.25), '\$180.25');
    });

    // 입력: KR 종목, 가격 70000
    // 확인: "₩70,000" 형식으로 출력 (3자리 콤마 구분)
    test('KR 종목 가격은 원화 형식(₩X,XXX)으로 포맷된다', () {
      final h = _makeHolding('KR');
      expect(h.formatPrice(70000), '₩70,000');
    });

    // 입력: KR 종목, 1억 이상 가격
    // 확인: 콤마 구분 형식 유지
    test('KR 종목 고액(1백만) 가격도 콤마 구분이 올바르다', () {
      final h = _makeHolding('KR');
      expect(h.formatPrice(1000000), '₩1,000,000');
    });

    // 입력: 가격이 null
    // 확인: "-" 반환 (데이터 없음 표시)
    test('null 가격은 "-"를 반환한다', () {
      final h = _makeHolding('US');
      expect(h.formatPrice(null), '-');
    });

    // 입력: US 종목, 가격 0.5 (소수점 2자리)
    // 확인: "$0.50" 형식 (소수점 2자리 유지)
    test('US 종목 소수점 가격은 2자리로 표시된다', () {
      final h = _makeHolding('US');
      expect(h.formatPrice(0.5), '\$0.50');
    });
  });

  // ══════════════════════════════════════════════════════════
  // 3. PortfolioHolding — 시장 구분 (isKr, currencySymbol)
  // ══════════════════════════════════════════════════════════
  group('PortfolioHolding — 시장 구분', () {
    // 입력: market = 'KR'
    // 확인: isKr=true, currencySymbol='₩'
    test('KR 종목은 isKr=true, currencySymbol=₩이다', () {
      final h = PortfolioHolding.fromJson({
        'ticker': '005930.KS',
        'name': '삼성전자',
        'market': 'KR',
        'shares': 10,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
      });
      expect(h.isKr, true);
      expect(h.currencySymbol, '₩');
    });

    // 입력: market = 'US'
    // 확인: isKr=false, currencySymbol='$'
    test('US 종목은 isKr=false, currencySymbol=\$이다', () {
      final h = PortfolioHolding.fromJson({
        'ticker': 'AAPL',
        'name': 'Apple',
        'market': 'US',
        'shares': 10,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
      });
      expect(h.isKr, false);
      expect(h.currencySymbol, '\$');
    });

    // 입력: market 키 없음 → 기본값 'US'
    // 확인: isKr=false (하위 호환)
    test('market이 없으면 기본값 US로 처리된다', () {
      final h = PortfolioHolding.fromJson({
        'ticker': 'TSLA',
        'shares': 1,
        'entry_date': '2026-01-01',
        'memo': '',
        'stop_triggered': false,
      });
      expect(h.isKr, false);
    });
  });

  // ══════════════════════════════════════════════════════════
  // 4. PortfolioData.fromJson — 환율 및 금액 필드
  // ══════════════════════════════════════════════════════════
  group('PortfolioData.fromJson — 환율(usdkrw)', () {
    // 입력: exchange_rate.usdkrw = 1350.5
    // 확인: 정상 파싱
    test('exchange_rate.usdkrw가 정상적으로 파싱된다', () {
      final json = {
        'updated_at': '2026-03-29T10:00:00',
        'exchange_rate': {'usdkrw': 1350.5},
        'total_invested': 0.0,
        'total_current': 0.0,
        'total_return_pct': 0.0,
        'holdings': [],
      };
      final data = PortfolioData.fromJson(json);
      expect(data.usdkrw, 1350.5);
    });

    // 입력: exchange_rate.usdkrw = null (환율 조회 실패 시 Python에서 None 출력)
    // 확인: 기본값 1380.0으로 fallback (프론트엔드 null 처리)
    test('exchange_rate.usdkrw가 null이면 기본값 1380.0이 사용된다', () {
      final json = {
        'updated_at': '',
        'exchange_rate': {'usdkrw': null},
        'total_invested': 0.0,
        'total_current': 0.0,
        'total_return_pct': 0.0,
        'holdings': [],
      };
      final data = PortfolioData.fromJson(json);
      expect(data.usdkrw, 1380.0);
    });

    // 입력: exchange_rate 키 자체 없음 (구버전 JSON 하위 호환)
    // 확인: 기본값 1380.0 적용
    test('exchange_rate 키 자체가 없으면 기본값 1380.0이 사용된다', () {
      final json = {
        'updated_at': '',
        'total_invested': 0.0,
        'total_current': 0.0,
        'total_return_pct': 0.0,
        'holdings': [],
      };
      final data = PortfolioData.fromJson(json);
      expect(data.usdkrw, 1380.0);
    });

    // 입력: exchange_rate.usdkrw를 int로 전달
    // 확인: double로 변환된다
    test('exchange_rate.usdkrw가 int이면 double로 변환된다', () {
      final json = {
        'updated_at': '',
        'exchange_rate': {'usdkrw': 1380},
        'total_invested': 0.0,
        'total_current': 0.0,
        'total_return_pct': 0.0,
        'holdings': [],
      };
      final data = PortfolioData.fromJson(json);
      expect(data.usdkrw, isA<double>());
      expect(data.usdkrw, 1380.0);
    });
  });

  // ══════════════════════════════════════════════════════════
  // 5. PortfolioData.fromJson — KRW/USD 이중 금액 필드
  // ══════════════════════════════════════════════════════════
  group('PortfolioData.fromJson — KRW/USD 이중 금액', () {
    // 입력: total_invested_krw/usd 모두 있는 최신 JSON
    // 확인: 각 금액 필드가 정확히 파싱된다
    test('total_invested_krw/usd 필드가 정상 파싱된다', () {
      final json = {
        'updated_at': '2026-03-29',
        'exchange_rate': {'usdkrw': 1350.0},
        'total_invested': 10000000.0,
        'total_current': 11000000.0,
        'total_return_pct': 10.0,
        'total_invested_krw': 10000000.0,
        'total_current_krw': 11000000.0,
        'total_invested_usd': 7407.41,
        'total_current_usd': 8148.15,
        'holdings': [],
      };
      final data = PortfolioData.fromJson(json);

      expect(data.totalInvestedKrw, 10000000.0);
      expect(data.totalCurrentKrw, 11000000.0);
      expect(data.totalInvestedUsd, closeTo(7407.41, 0.01));
      expect(data.totalCurrentUsd, closeTo(8148.15, 0.01));
    });

    // 입력: total_invested_krw 없는 구버전 JSON
    // 확인: total_invested 값으로 fallback (하위 호환성)
    test('total_invested_krw 없으면 total_invested로 fallback된다', () {
      final json = {
        'updated_at': '2026-03-29',
        'exchange_rate': {'usdkrw': 1350.0},
        'total_invested': 5000000.0,
        'total_current': 5500000.0,
        'total_return_pct': 10.0,
        'holdings': [],
      };
      final data = PortfolioData.fromJson(json);

      expect(data.totalInvestedKrw, 5000000.0);
      expect(data.totalCurrentKrw, 5500000.0);
    });
  });

  // ══════════════════════════════════════════════════════════
  // 6. PortfolioData.isEmpty
  // ══════════════════════════════════════════════════════════
  group('PortfolioData.isEmpty', () {
    // 입력: holdings가 빈 리스트
    // 확인: isEmpty=true (UI에서 "데이터 없음" 표시)
    test('holdings가 비어 있으면 isEmpty=true이다', () {
      final json = {
        'updated_at': '',
        'total_invested': 0.0,
        'total_current': 0.0,
        'total_return_pct': 0.0,
        'holdings': [],
      };
      final data = PortfolioData.fromJson(json);
      expect(data.isEmpty, true);
    });

    // 입력: holdings에 종목 1개
    // 확인: isEmpty=false, holdings.length=1
    test('holdings가 있으면 isEmpty=false이다', () {
      final json = {
        'updated_at': '2026-03-29',
        'exchange_rate': {'usdkrw': 1350.0},
        'total_invested': 1000.0,
        'total_current': 1100.0,
        'total_return_pct': 10.0,
        'holdings': [
          {
            'ticker': 'AAPL',
            'market': 'US',
            'shares': 5,
            'entry_date': '2026-01-01',
            'memo': '',
            'stop_triggered': false,
          }
        ],
      };
      final data = PortfolioData.fromJson(json);

      expect(data.isEmpty, false);
      expect(data.holdings.length, 1);
      expect(data.holdings.first.ticker, 'AAPL');
    });

    // 입력: ATR 스톱 데이터가 포함된 holding
    // 확인: holding의 atrStop 필드가 PortfolioData를 통해서도 정상 파싱된다
    test('PortfolioData 내 holding의 ATR 스톱 필드가 정상 파싱된다', () {
      final json = {
        'updated_at': '2026-03-29',
        'exchange_rate': {'usdkrw': 1350.0},
        'total_invested': 1000.0,
        'total_current': 1100.0,
        'total_return_pct': 10.0,
        'holdings': [
          {
            'ticker': 'NVDA',
            'name': 'NVIDIA',
            'market': 'US',
            'shares': 5,
            'entry_date': '2026-01-01',
            'memo': '',
            'stop_triggered': false,
            'atr_stop': 850.0,
            'atr_stop_dist_pct': 8.5,
            'atr_stop_triggered': false,
          }
        ],
      };
      final data = PortfolioData.fromJson(json);
      final holding = data.holdings.first;

      expect(holding.atrStop, 850.0);
      expect(holding.atrStopDistPct, 8.5);
      expect(holding.atrStopTriggered, false);
    });
  });
}
