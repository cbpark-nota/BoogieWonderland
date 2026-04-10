import 'dart:typed_data';

import 'package:excel/excel.dart';

import '../models/portfolio_data.dart';

/// xlsx 파싱·생성·내보내기 서비스 (클라이언트 사이드 전용)
class PortfolioXlsxService {
  static const int maxFileSizeBytes = 1 * 1024 * 1024; // 1MB

  // 영문/한글 컬럼 별칭 매핑
  static const Map<String, String> _colAliases = {
    'ticker': 'ticker', '티커': 'ticker',
    'name': 'name', '종목명': 'name',
    'market': 'market', '시장': 'market', '시장(us/kr)': 'market',
    'entry_price': 'entry_price', '진입가': 'entry_price',
    'shares': 'shares', '주수': 'shares',
    'entry_date': 'entry_date', '진입일': 'entry_date',
    'stop_loss': 'stop_loss', '스톱로스': 'stop_loss',
    'target_price': 'target_price', '목표가': 'target_price',
    'memo': 'memo', '메모': 'memo',
  };

  static const List<String> _headerKr = [
    '티커', '종목명', '시장(US/KR)', '진입가', '주수',
    '진입일', '스톱로스', '목표가', '메모',
  ];

  // ── xlsx → PortfolioData 파싱 ──────────────────────────────

  PortfolioData parseXlsx(Uint8List bytes) {
    if (bytes.length > maxFileSizeBytes) {
      throw Exception('파일 크기가 너무 큽니다 (최대 1MB)');
    }

    final excel = Excel.decodeBytes(bytes.toList());

    // 'Portfolio' 시트 우선, 없으면 첫 번째 시트
    Sheet? sheet;
    for (final name in excel.tables.keys) {
      if (name.toLowerCase() == 'portfolio') {
        sheet = excel.tables[name];
        break;
      }
    }
    sheet ??= excel.tables.values.firstOrNull;

    if (sheet == null || sheet.rows.isEmpty) {
      throw Exception('유효한 시트를 찾을 수 없습니다');
    }

    final rows = sheet.rows;

    // 헤더 행 → 컬럼 인덱스 맵
    final colMap = <String, int>{};
    final headerRow = rows[0];
    for (var i = 0; i < headerRow.length; i++) {
      final raw = headerRow[i]?.value?.toString().trim().toLowerCase() ?? '';
      final normalized = _colAliases[raw];
      if (normalized != null) colMap[normalized] = i;
    }

    if (!colMap.containsKey('ticker')) {
      throw Exception('티커(ticker) 컬럼을 찾을 수 없습니다');
    }

    final holdings = <PortfolioHolding>[];

    for (var r = 1; r < rows.length; r++) {
      final row = rows[r];

      String? getStr(String key) {
        final idx = colMap[key];
        if (idx == null || idx >= row.length) return null;
        final v = row[idx]?.value?.toString().trim();
        return (v == null || v.isEmpty) ? null : v;
      }

      double? getNum(String key) {
        final s = getStr(key);
        if (s == null) return null;
        return double.tryParse(s.replaceAll(',', ''));
      }

      final ticker = getStr('ticker');
      if (ticker == null) continue;

      final market = (getStr('market') ?? 'US').toUpperCase();
      final shares = getNum('shares') ?? 0.0;
      final entryPrice = getNum('entry_price');
      final invested =
          (entryPrice != null && shares > 0) ? entryPrice * shares : null;

      holdings.add(PortfolioHolding(
        ticker: ticker,
        name: getStr('name') ?? ticker,
        market: market,
        entryPrice: entryPrice,
        currentPrice: null,
        shares: shares,
        entryDate: getStr('entry_date') ?? '',
        stopLoss: getNum('stop_loss'),
        targetPrice: getNum('target_price'),
        memo: getStr('memo') ?? '',
        invested: invested,
        currentValue: null,
        returnPct: null,
        weightPct: null,
        stopTriggered: false,
        investedKrw: null,
        currentValueKrw: null,
        investedUsd: null,
        currentValueUsd: null,
        atrStop: null,
        atrStopDistPct: null,
        atrStopTriggered: false,
      ));
    }

    if (holdings.isEmpty) {
      throw Exception('포트폴리오 종목이 없습니다');
    }

    // 비중(%) 계산
    final totalInvested =
        holdings.fold<double>(0.0, (s, h) => s + (h.invested ?? 0.0));

    final holdingsWithWeight = holdings.map((h) {
      final w = (totalInvested > 0 && h.invested != null)
          ? (h.invested! / totalInvested * 100)
          : null;
      return PortfolioHolding(
        ticker: h.ticker,
        name: h.name,
        market: h.market,
        entryPrice: h.entryPrice,
        currentPrice: null,
        shares: h.shares,
        entryDate: h.entryDate,
        stopLoss: h.stopLoss,
        targetPrice: h.targetPrice,
        memo: h.memo,
        invested: h.invested,
        currentValue: null,
        returnPct: null,
        weightPct: w,
        stopTriggered: false,
        investedKrw: null,
        currentValueKrw: null,
        investedUsd: null,
        currentValueUsd: null,
        atrStop: null,
        atrStopDistPct: null,
        atrStopTriggered: false,
      );
    }).toList();

    return PortfolioData(
      updatedAt: DateTime.now().toIso8601String(),
      totalInvested: totalInvested,
      totalCurrent: totalInvested,
      totalReturnPct: 0.0,
      usdkrw: 1380.0,
      totalInvestedKrw: 0.0,
      totalCurrentKrw: 0.0,
      totalInvestedUsd: 0.0,
      totalCurrentUsd: 0.0,
      holdings: holdingsWithWeight,
    );
  }

  // ── 템플릿 xlsx 생성 ────────────────────────────────────────

  Uint8List generateTemplate() {
    final excel = Excel.createExcel();
    excel.rename('Sheet1', 'Portfolio');
    final sheet = excel['Portfolio'];

    // 헤더 행
    for (var i = 0; i < _headerKr.length; i++) {
      sheet
          .cell(CellIndex.indexByColumnRow(columnIndex: i, rowIndex: 0))
          .value = TextCellValue(_headerKr[i]);
    }

    // 예시 US 종목
    final exampleUs = [
      'AAPL', 'Apple Inc.', 'US', '180.00', '10',
      '2024-01-15', '160.00', '220.00', '모멘텀 진입',
    ];
    for (var i = 0; i < exampleUs.length; i++) {
      sheet
          .cell(CellIndex.indexByColumnRow(columnIndex: i, rowIndex: 1))
          .value = TextCellValue(exampleUs[i]);
    }

    // 예시 KR 종목
    final exampleKr = [
      '005930.KS', '삼성전자', 'KR', '75000', '100',
      '2024-01-20', '68000', '95000', '반도체 강세',
    ];
    for (var i = 0; i < exampleKr.length; i++) {
      sheet
          .cell(CellIndex.indexByColumnRow(columnIndex: i, rowIndex: 2))
          .value = TextCellValue(exampleKr[i]);
    }

    return Uint8List.fromList(excel.encode()!);
  }

  // ── PortfolioData → xlsx 내보내기 ──────────────────────────

  Uint8List exportPortfolio(PortfolioData portfolio) {
    final excel = Excel.createExcel();
    excel.rename('Sheet1', 'Portfolio');
    final sheet = excel['Portfolio'];

    final headers = [
      ..._headerKr,
      '현재가', '수익률(%)', 'ATR스톱', '비중(%)',
    ];
    for (var i = 0; i < headers.length; i++) {
      sheet
          .cell(CellIndex.indexByColumnRow(columnIndex: i, rowIndex: 0))
          .value = TextCellValue(headers[i]);
    }

    for (var r = 0; r < portfolio.holdings.length; r++) {
      final h = portfolio.holdings[r];
      final data = [
        h.ticker,
        h.name,
        h.market,
        h.entryPrice?.toString() ?? '',
        h.shares.toString(),
        h.entryDate,
        h.stopLoss?.toString() ?? '',
        h.targetPrice?.toString() ?? '',
        h.memo,
        h.currentPrice?.toString() ?? '',
        h.returnPct?.toStringAsFixed(2) ?? '',
        h.atrStop?.toString() ?? '',
        h.weightPct?.toStringAsFixed(2) ?? '',
      ];
      for (var i = 0; i < data.length; i++) {
        sheet
            .cell(
                CellIndex.indexByColumnRow(columnIndex: i, rowIndex: r + 1))
            .value = TextCellValue(data[i]);
      }
    }

    return Uint8List.fromList(excel.encode()!);
  }
}
