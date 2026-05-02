import 'package:flutter/material.dart';
import '../models/screening_result.dart';
import '../theme/app_colors.dart';

class StockCard extends StatelessWidget {
  final ScreeningResult result;

  const StockCard({super.key, required this.result});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            Row(
              children: [
                // 순위
                Container(
                  width: 28,
                  height: 28,
                  decoration: BoxDecoration(
                    color: _rankColor(result.rank),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Center(
                    child: Text('${result.rank}',
                        style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                            fontSize: 13)),
                  ),
                ),
                const SizedBox(width: 10),
                // 종목명/티커 + 섹터
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${result.flag} ${result.displayName}',
                          style: const TextStyle(
                              fontWeight: FontWeight.bold, fontSize: 15)),
                      Text(
                        result.market == 'KR'
                            ? '${result.ticker} · ${result.sector}'
                            : result.sector,
                        style: const TextStyle(
                            fontSize: 11, color: AppColors.mutedText),
                      ),
                    ],
                  ),
                ),
                // 점수 + 비중
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Text('Score',
                            style: TextStyle(
                                fontSize: 11, color: AppColors.mutedText)),
                        const SizedBox(width: 4),
                        Text(result.score.toStringAsFixed(3),
                            style: const TextStyle(
                                fontWeight: FontWeight.bold, fontSize: 15)),
                      ],
                    ),
                    Text('${result.weightPct.toStringAsFixed(1)}%',
                        style: const TextStyle(
                            fontSize: 12, color: AppColors.info)),
                  ],
                ),
              ],
            ),
            const Divider(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _metric('Price', '${result.currencySymbol}${result.price.toStringAsFixed(result.market == 'KR' ? 0 : 2)}'),
                _metric('ADX', result.adx?.toStringAsFixed(1) ?? '-'),
                _metric('RSI', result.rsi?.toStringAsFixed(1) ?? '-'),
                _metric('3M',
                    result.ret3m != null
                        ? '${(result.ret3m! * 100).toStringAsFixed(1)}%'
                        : '-'),
                _metric('Stop',
                    result.stopPrice != null
                        ? '${result.currencySymbol}${result.stopPrice!.toStringAsFixed(result.market == 'KR' ? 0 : 2)}'
                        : '-'),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Color _rankColor(int rank) {
    if (rank <= 3) return AppColors.rankGold;
    if (rank <= 7) return AppColors.info;
    return AppColors.mutedText;
  }

  Widget _metric(String label, String value) {
    return Column(
      children: [
        Text(label,
            style: const TextStyle(fontSize: 10, color: AppColors.mutedText)),
        Text(value,
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500)),
      ],
    );
  }
}
