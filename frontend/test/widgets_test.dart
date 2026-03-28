// widgets_test.dart
// 테스트 대상: StockCard, StopLossIndicator, MarketStatusBanner, KospiStatusBanner 위젯
//
// 검증 내용:
//   - 각 위젯이 올바른 데이터를 화면에 렌더링하는지
//   - 조건별 UI 상태(골든크로스/데드크로스, 스톱로스 위험도 색상 등)
//   - 경계값(marginPct=0, KOSPI 필드 null 등) 처리

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:momentum_app/models/screening_result.dart';
import 'package:momentum_app/widgets/stock_card.dart';
import 'package:momentum_app/widgets/stop_loss_indicator.dart';
import 'package:momentum_app/widgets/market_status_banner.dart';

// 위젯 테스트용 래퍼: MaterialApp으로 감싸서 MediaQuery/Theme 제공
Widget _wrap(Widget child) {
  return MaterialApp(home: Scaffold(body: child));
}

// ========================================
// 테스트용 ScreeningResult 헬퍼
// ========================================
ScreeningResult _makeResult({
  int rank = 1,
  String ticker = 'AAPL',
  String market = 'US',
  String? name,
  String sector = 'Technology',
  double score = 0.85,
  double weightPct = 10.0,
  double price = 180.0,
  double? adx = 30.0,
  double? rsi = 60.0,
  double? ret3m = 0.12,
  double? stopPrice = 165.0,
  double? stopDistPct = -8.3,
  double? atr,
}) {
  return ScreeningResult(
    rank: rank,
    ticker: ticker,
    market: market,
    name: name,
    sector: sector,
    score: score,
    weightPct: weightPct,
    price: price,
    adx: adx,
    rsi: rsi,
    ret3m: ret3m,
    stopPrice: stopPrice,
    stopDistPct: stopDistPct,
    atr: atr,
  );
}

void main() {
  // ========================================
  // 1. StockCard 위젯 테스트
  // ========================================
  group('StockCard', () {
    // 입력: rank=1, ticker='AAPL', market='US', score=0.85, weightPct=10.0
    // 출력: 티커명, 점수, 비중이 화면에 표시됨
    testWidgets('US 종목 기본 정보가 표시된다', (tester) async {
      await tester.pumpWidget(_wrap(StockCard(result: _makeResult())));

      // 티커 (flag + ticker)
      expect(find.textContaining('AAPL'), findsOneWidget);
      // 점수
      expect(find.textContaining('0.850'), findsOneWidget);
      // 비중
      expect(find.textContaining('10.0%'), findsOneWidget);
      // 섹터
      expect(find.textContaining('Technology'), findsOneWidget);
    });

    // 입력: rank=1 ~ 3
    // 출력: 순위 번호가 표시됨
    testWidgets('1~3위는 순위 번호가 표시된다', (tester) async {
      for (int r = 1; r <= 3; r++) {
        await tester.pumpWidget(_wrap(StockCard(result: _makeResult(rank: r))));
        expect(find.text('$r'), findsOneWidget);
      }
    });

    // 입력: market='KR', ticker='005930', name='삼성전자'
    // 출력: 한국어 종목명이 표시되고 KR 플래그(🇰🇷)가 포함됨
    testWidgets('KR 종목은 한글 이름과 KR 플래그가 표시된다', (tester) async {
      await tester.pumpWidget(
        _wrap(
          StockCard(
            result: _makeResult(
              ticker: '005930',
              market: 'KR',
              name: '삼성전자',
              price: 72500,
            ),
          ),
        ),
      );

      // KR 종목은 name을 displayName으로 사용
      expect(find.textContaining('삼성전자'), findsOneWidget);
      // 플래그 확인
      expect(find.textContaining('🇰🇷'), findsOneWidget);
    });

    // 입력: market='US' (name 없음)
    // 출력: US 플래그(🇺🇸)와 ticker가 표시됨
    testWidgets('US 종목은 US 플래그가 표시된다', (tester) async {
      await tester.pumpWidget(_wrap(StockCard(result: _makeResult())));

      expect(find.textContaining('🇺🇸'), findsOneWidget);
    });

    // 입력: adx=30.5, rsi=60.2, ret3m=0.123
    // 출력: 지표값이 포맷에 맞게 표시됨
    testWidgets('ADX, RSI, 3M 지표가 표시된다', (tester) async {
      await tester.pumpWidget(
        _wrap(
          StockCard(
            result: _makeResult(adx: 30.5, rsi: 60.2, ret3m: 0.123),
          ),
        ),
      );

      expect(find.text('30.5'), findsOneWidget); // ADX
      expect(find.text('60.2'), findsOneWidget); // RSI
      expect(find.textContaining('12.3%'), findsOneWidget); // 3M: 0.123 * 100
    });

    // 입력: adx=null, rsi=null, ret3m=null
    // 출력: '-' 표시
    testWidgets('지표가 null이면 하이픈이 표시된다', (tester) async {
      await tester.pumpWidget(
        _wrap(
          StockCard(
            result: _makeResult(
              adx: null,
              rsi: null,
              ret3m: null,
              stopPrice: null,
            ),
          ),
        ),
      );

      // '-'가 여러 개 (ADX, RSI, 3M, Stop 각각)
      expect(find.text('-'), findsWidgets);
    });

    // 입력: KR 종목, price=72500
    // 출력: '₩72500' (소수 없음)
    testWidgets('KR 종목 가격은 소수점 없이 표시된다', (tester) async {
      await tester.pumpWidget(
        _wrap(
          StockCard(
            result: _makeResult(
              ticker: '005930',
              market: 'KR',
              price: 72500,
              stopPrice: 70000,
            ),
          ),
        ),
      );

      // KR 가격 포맷: ₩72500
      expect(find.textContaining('₩72500'), findsOneWidget);
    });

    // 입력: US 종목, price=145.20
    // 출력: '$145.20' (소수 2자리)
    testWidgets('US 종목 가격은 소수점 2자리로 표시된다', (tester) async {
      await tester.pumpWidget(
        _wrap(StockCard(result: _makeResult(price: 145.20))),
      );

      expect(find.textContaining('\$145.20'), findsOneWidget);
    });
  });

  // ========================================
  // 2. StopLossIndicator 위젯 테스트
  // ========================================
  group('StopLossIndicator', () {
    // 입력: marginPct=10.0 (스톱로스로부터 10% 여유)
    // 출력: '10.0%' 텍스트가 녹색으로 표시
    testWidgets('marginPct >= 5이면 퍼센트 텍스트가 표시된다', (tester) async {
      await tester.pumpWidget(
        _wrap(const StopLossIndicator(marginPct: 10.0)),
      );

      expect(find.text('10.0%'), findsOneWidget);
    });

    // 입력: marginPct=2.5 (위험 구간: 0~5%)
    // 출력: '2.5%' 텍스트가 주황색으로 표시
    testWidgets('marginPct 0~5 사이이면 퍼센트 텍스트가 표시된다', (tester) async {
      await tester.pumpWidget(
        _wrap(const StopLossIndicator(marginPct: 2.5)),
      );

      expect(find.text('2.5%'), findsOneWidget);
    });

    // 입력: marginPct=0.0 (스톱로스 경계)
    // 출력: 'BREACH' 텍스트가 빨간색으로 표시
    testWidgets('marginPct=0이면 BREACH가 표시된다', (tester) async {
      await tester.pumpWidget(
        _wrap(const StopLossIndicator(marginPct: 0.0)),
      );

      expect(find.text('BREACH'), findsOneWidget);
    });

    // 입력: marginPct=-3.5 (스톱로스 이하)
    // 출력: 'BREACH' 텍스트가 표시됨
    testWidgets('marginPct 음수이면 BREACH가 표시된다', (tester) async {
      await tester.pumpWidget(
        _wrap(const StopLossIndicator(marginPct: -3.5)),
      );

      expect(find.text('BREACH'), findsOneWidget);
    });

    // 입력: marginPct=4.9 (위험 구간 최상단)
    // 출력: '4.9%' 텍스트 표시 (BREACH 아님)
    testWidgets('marginPct=4.9이면 퍼센트 텍스트가 표시된다', (tester) async {
      await tester.pumpWidget(
        _wrap(const StopLossIndicator(marginPct: 4.9)),
      );

      expect(find.text('4.9%'), findsOneWidget);
      expect(find.text('BREACH'), findsNothing);
    });
  });

  // ========================================
  // 3. MarketStatusBanner 위젯 테스트
  // ========================================
  group('MarketStatusBanner', () {
    final goldenCrossStatus = MarketStatus(
      spyPrice: 523.4,
      isGoldenCross: true,
      ma20: 510.2,
      ma60: 498.5,
      gapPct: 2.35,
      nextRebalance: '2026-04-04',
    );

    final deadCrossStatus = MarketStatus(
      spyPrice: 480.0,
      isGoldenCross: false,
      ma20: 490.0,
      ma60: 510.0,
      gapPct: -3.92,
    );

    // 입력: isGoldenCross=true인 MarketStatus
    // 출력: 'SPY Golden Cross' 텍스트 표시, trending_up 아이콘 표시
    testWidgets('골든크로스 상태에서 Golden Cross 텍스트가 표시된다', (tester) async {
      await tester.pumpWidget(
        _wrap(MarketStatusBanner(status: goldenCrossStatus)),
      );

      expect(find.text('SPY Golden Cross'), findsOneWidget);
      expect(find.byIcon(Icons.trending_up), findsOneWidget);
    });

    // 입력: isGoldenCross=false인 MarketStatus
    // 출력: 'SPY Dead Cross' 텍스트 표시, trending_down 아이콘 표시
    testWidgets('데드크로스 상태에서 Dead Cross 텍스트가 표시된다', (tester) async {
      await tester.pumpWidget(
        _wrap(MarketStatusBanner(status: deadCrossStatus)),
      );

      expect(find.text('SPY Dead Cross'), findsOneWidget);
      expect(find.byIcon(Icons.trending_down), findsOneWidget);
    });

    // 입력: spyPrice=523.4, ma20=510.2, ma60=498.5, gapPct=2.35
    // 출력: 각 수치가 화면에 표시됨
    testWidgets('SPY 가격과 이동평균 수치가 표시된다', (tester) async {
      await tester.pumpWidget(
        _wrap(MarketStatusBanner(status: goldenCrossStatus)),
      );

      expect(find.textContaining('523.4'), findsOneWidget); // SPY Price
      expect(find.textContaining('510.2'), findsOneWidget); // 20MA
      expect(find.textContaining('498.5'), findsOneWidget); // 60MA
      expect(find.textContaining('2.4%'), findsOneWidget);  // Gap (toStringAsFixed(1))
    });
  });

  // ========================================
  // 4. KospiStatusBanner 위젯 테스트
  // ========================================
  group('KospiStatusBanner', () {
    // 입력: KOSPI 필드가 있는 MarketStatus
    // 출력: 'KOSPI Golden Cross' 또는 'KOSPI Dead Cross' 텍스트 표시
    testWidgets('KOSPI 필드 있을 때 배너가 표시된다', (tester) async {
      final status = MarketStatus(
        spyPrice: 523.4,
        isGoldenCross: true,
        ma20: 510.2,
        ma60: 498.5,
        gapPct: 2.35,
        kospiPrice: 2550.0,
        kospiIsGoldenCross: true,
        kospiMa20: 2520.0,
        kospiMa60: 2480.0,
        kospiGapPct: 2.82,
      );

      await tester.pumpWidget(_wrap(KospiStatusBanner(status: status)));

      expect(find.text('KOSPI Golden Cross'), findsOneWidget);
      expect(find.textContaining('2550'), findsOneWidget);
    });

    // 입력: KOSPI 데드크로스 상태
    // 출력: 'KOSPI Dead Cross' 텍스트 표시
    testWidgets('KOSPI 데드크로스 상태에서 Dead Cross 텍스트가 표시된다', (tester) async {
      final status = MarketStatus(
        spyPrice: 480.0,
        isGoldenCross: false,
        ma20: 490.0,
        ma60: 510.0,
        gapPct: -3.92,
        kospiPrice: 2400.0,
        kospiIsGoldenCross: false,
        kospiMa20: 2420.0,
        kospiMa60: 2460.0,
        kospiGapPct: -2.44,
      );

      await tester.pumpWidget(_wrap(KospiStatusBanner(status: status)));

      expect(find.text('KOSPI Dead Cross'), findsOneWidget);
      expect(find.byIcon(Icons.trending_down), findsOneWidget);
    });

    // 입력: kospiPrice=null (KOSPI 필드 없음)
    // 출력: 빈 위젯 (SizedBox.shrink) — 배너가 표시되지 않음
    testWidgets('KOSPI 필드 없을 때 아무것도 표시되지 않는다', (tester) async {
      final status = MarketStatus(
        spyPrice: 450.0,
        isGoldenCross: true,
        ma20: 440.0,
        ma60: 420.0,
        gapPct: 4.76,
        // kospiPrice 등 없음
      );

      await tester.pumpWidget(_wrap(KospiStatusBanner(status: status)));

      expect(find.text('KOSPI Golden Cross'), findsNothing);
      expect(find.text('KOSPI Dead Cross'), findsNothing);
    });
  });
}
