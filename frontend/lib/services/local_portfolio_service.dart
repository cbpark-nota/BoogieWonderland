import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/holding.dart';

/// 서버리스 모드에서 localStorage 기반 포트폴리오 관리
class LocalPortfolioService {
  static const _key = 'serverless_holdings';

  Future<List<Holding>> getHoldings() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null) return [];
    final list = jsonDecode(raw) as List;
    return list.map((h) => Holding.fromJson(h)).toList();
  }

  Future<void> addHolding(String ticker, double entryPrice) async {
    final prefs = await SharedPreferences.getInstance();
    final holdings = await getHoldings();
    final nextId =
        holdings.isEmpty ? 1 : holdings.map((h) => h.id).reduce((a, b) => a > b ? a : b) + 1;
    final now = DateTime.now().toIso8601String().substring(0, 10);
    holdings.add(Holding(
      id: nextId,
      ticker: ticker.toUpperCase(),
      entryPrice: entryPrice,
      entryDate: now,
      peakPrice: entryPrice,
      isActive: true,
    ));
    await prefs.setString(_key, jsonEncode(holdings.map(_toJson).toList()));
  }

  Future<void> removeHolding(String ticker) async {
    final prefs = await SharedPreferences.getInstance();
    final holdings = await getHoldings();
    holdings.removeWhere((h) => h.ticker == ticker);
    await prefs.setString(_key, jsonEncode(holdings.map(_toJson).toList()));
  }

  Map<String, dynamic> _toJson(Holding h) => {
        'id': h.id,
        'ticker': h.ticker,
        'entry_price': h.entryPrice,
        'entry_date': h.entryDate,
        'peak_price': h.peakPrice,
        'is_active': h.isActive,
      };
}
