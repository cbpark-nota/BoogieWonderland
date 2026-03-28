import 'package:flutter/material.dart';
import '../models/screening_result.dart';

Widget _metric(String label, String value) {
  return Column(
    children: [
      Text(label, style: const TextStyle(fontSize: 11, color: Colors.grey)),
      Text(value,
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
    ],
  );
}

class MarketStatusBanner extends StatelessWidget {
  final MarketStatus status;

  const MarketStatusBanner({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    final isGolden = status.isGoldenCross;
    final color = isGolden ? Colors.green : Colors.red;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(isGolden ? Icons.trending_up : Icons.trending_down,
                  color: color, size: 20),
              const SizedBox(width: 8),
              Text(
                isGolden ? 'SPY Golden Cross' : 'SPY Dead Cross',
                style: TextStyle(
                    fontWeight: FontWeight.bold, color: color, fontSize: 16),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(child: _metric('SPY', '\$${status.spyPrice.toStringAsFixed(1)}')),
              Expanded(child: _metric('20MA', '\$${status.ma20.toStringAsFixed(1)}')),
              Expanded(child: _metric('60MA', '\$${status.ma60.toStringAsFixed(1)}')),
              Expanded(child: _metric('Gap', '${status.gapPct.toStringAsFixed(1)}%')),
            ],
          ),
        ],
      ),
    );
  }
}

class KospiStatusBanner extends StatelessWidget {
  final MarketStatus status;

  const KospiStatusBanner({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    final isGolden = status.kospiIsGoldenCross ?? false;
    final price = status.kospiPrice;
    final ma20 = status.kospiMa20;
    final ma60 = status.kospiMa60;
    final gapPct = status.kospiGapPct;

    if (price == null || ma20 == null || ma60 == null || gapPct == null) {
      return const SizedBox.shrink();
    }

    final color = isGolden ? Colors.green : Colors.red;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(isGolden ? Icons.trending_up : Icons.trending_down,
                  color: color, size: 20),
              const SizedBox(width: 8),
              Text(
                isGolden ? 'KOSPI Golden Cross' : 'KOSPI Dead Cross',
                style: TextStyle(
                    fontWeight: FontWeight.bold, color: color, fontSize: 16),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(child: _metric('KOSPI', price.toStringAsFixed(1))),
              Expanded(child: _metric('20MA', ma20.toStringAsFixed(1))),
              Expanded(child: _metric('60MA', ma60.toStringAsFixed(1))),
              Expanded(child: _metric('Gap', '${gapPct.toStringAsFixed(1)}%')),
            ],
          ),
        ],
      ),
    );
  }
}
