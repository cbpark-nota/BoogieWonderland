/// 시가총액 Top 20 스크리닝 데이터 모델

class MarketCapEntry {
  final int rank;
  final String ticker;
  final String market;
  final double? capBillion; // 억$ 또는 억원 단위
  final bool isNewEntrant;
  final double? currentPrice;
  final double? stopPrice;
  final double? stopDistPct;
  final double? atr;

  MarketCapEntry({
    required this.rank,
    required this.ticker,
    required this.market,
    this.capBillion,
    required this.isNewEntrant,
    this.currentPrice,
    this.stopPrice,
    this.stopDistPct,
    this.atr,
  });

  String get flag => market == 'KR' ? '🇰🇷' : '🇺🇸';
  String get capUnit => market == 'KR' ? '억원' : '억\$';
  String get currencySymbol => market == 'KR' ? '₩' : '\$';

  String get capDisplay {
    if (capBillion == null || capBillion == 0) return 'N/A';
    if (capBillion! >= 10000) {
      return '${(capBillion! / 10000).toStringAsFixed(1)}조 $capUnit';
    }
    return '${capBillion!.toStringAsFixed(0)} $capUnit';
  }
}

class MarketCapData {
  final String runDate;
  final double atrMult;
  final List<MarketCapEntry> usTop20;
  final List<String> usNewEntrants;
  final List<String> usExits;
  final List<MarketCapEntry> krTop20;
  final List<String> krNewEntrants;
  final List<String> krExits;
  final Map<String, AtrStop> atrStops;

  MarketCapData({
    required this.runDate,
    required this.atrMult,
    required this.usTop20,
    required this.usNewEntrants,
    required this.usExits,
    required this.krTop20,
    required this.krNewEntrants,
    required this.krExits,
    required this.atrStops,
  });

  List<MarketCapEntry> get allNewEntrants {
    final us = usTop20.where((e) => e.isNewEntrant).toList();
    final kr = krTop20.where((e) => e.isNewEntrant).toList();
    return [...us, ...kr];
  }

  factory MarketCapData.fromJson(Map<String, dynamic> json) {
    final usMap = json['us'] as Map<String, dynamic>? ?? {};
    final krMap = json['kr'] as Map<String, dynamic>? ?? {};
    final atrStopsMap = json['atr_stops'] as Map<String, dynamic>? ?? {};
    final usNewSet = Set<String>.from(
        (usMap['new_entrants'] as List<dynamic>? ?? []).map((e) => e.toString()));
    final krNewSet = Set<String>.from(
        (krMap['new_entrants'] as List<dynamic>? ?? []).map((e) => e.toString()));
    final usCaps = (usMap['caps'] as Map<String, dynamic>? ?? {});
    final krCaps = (krMap['caps'] as Map<String, dynamic>? ?? {});

    final atrStops = <String, AtrStop>{};
    atrStopsMap.forEach((key, val) {
      if (val != null) {
        atrStops[key] = AtrStop.fromJson(val as Map<String, dynamic>);
      }
    });

    List<MarketCapEntry> buildEntries(
      List<dynamic> top20List,
      Map<String, dynamic> capsMap,
      Set<String> newSet,
      String market,
    ) {
      return top20List.asMap().entries.map((entry) {
        final i = entry.key;
        final ticker = entry.value.toString();
        final stop = atrStops[ticker];
        return MarketCapEntry(
          rank: i + 1,
          ticker: ticker,
          market: market,
          capBillion: (capsMap[ticker] as num?)?.toDouble(),
          isNewEntrant: newSet.contains(ticker),
          currentPrice: stop?.price,
          stopPrice: stop?.stopPrice,
          stopDistPct: stop?.stopDistPct,
          atr: stop?.atr,
        );
      }).toList();
    }

    final usTop20List = usMap['top20'] as List<dynamic>? ?? [];
    final krTop20List = krMap['top20'] as List<dynamic>? ?? [];

    return MarketCapData(
      runDate: json['run_date'] as String? ?? '',
      atrMult: (json['atr_mult'] as num?)?.toDouble() ?? 2.0,
      usTop20: buildEntries(usTop20List, usCaps, usNewSet, 'US'),
      usNewEntrants: usNewSet.toList(),
      usExits: List<String>.from(
          (usMap['exits'] as List<dynamic>? ?? []).map((e) => e.toString())),
      krTop20: buildEntries(krTop20List, krCaps, krNewSet, 'KR'),
      krNewEntrants: krNewSet.toList(),
      krExits: List<String>.from(
          (krMap['exits'] as List<dynamic>? ?? []).map((e) => e.toString())),
      atrStops: atrStops,
    );
  }
}

class AtrStop {
  final double price;
  final double atr;
  final double stopPrice;
  final double stopDistPct;

  AtrStop({
    required this.price,
    required this.atr,
    required this.stopPrice,
    required this.stopDistPct,
  });

  factory AtrStop.fromJson(Map<String, dynamic> json) {
    return AtrStop(
      price: (json['price'] as num).toDouble(),
      atr: (json['atr'] as num).toDouble(),
      stopPrice: (json['stop_price'] as num).toDouble(),
      stopDistPct: (json['stop_dist_pct'] as num).toDouble(),
    );
  }
}
