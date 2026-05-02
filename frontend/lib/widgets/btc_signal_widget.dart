import 'package:flutter/material.dart';
import '../models/screening_result.dart';
import '../theme/app_colors.dart';

class BtcSignalWidget extends StatelessWidget {
  final BtcSignal signal;

  const BtcSignalWidget({super.key, required this.signal});

  @override
  Widget build(BuildContext context) {
    final isBuy = signal.signal == 'buy';
    final color = isBuy ? AppColors.priceUp : AppColors.mutedText;
    final icon = isBuy ? Icons.arrow_upward : Icons.remove;
    final label = isBuy ? '매수' : '관망';
    final priceStr = signal.price != null
        ? '\$${signal.price!.toStringAsFixed(0).replaceAllMapped(RegExp(r'(\d)(?=(\d{3})+$)'), (m) => '${m[1]},')} '
        : '';

    // 레짐 표시
    String regimeLabel = '';
    if (signal.regime != null) {
      regimeLabel = switch (signal.regime) {
        'bull' => 'Bull',
        'sideways' => 'Sideways',
        'neutral' => 'Neutral',
        _ => signal.regime!,
      };
    }

    // 타임스탬프 간략 표시
    String timeStr = '';
    if (signal.timestamp.isNotEmpty) {
      try {
        final dt = DateTime.parse(signal.timestamp).toLocal();
        timeStr = '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
      } catch (_) {}
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: Icon(icon, color: color, size: 16),
              ),
              const SizedBox(width: 8),
              Text(
                'BTC ${signal.strategy}',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: color,
                  fontSize: 14,
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  label,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              const Spacer(),
              if (regimeLabel.isNotEmpty)
                Text(
                  regimeLabel,
                  style: TextStyle(
                    fontSize: 11,
                    color: AppColors.mutedTextStrong,
                    fontStyle: FontStyle.italic,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              if (priceStr.isNotEmpty) ...[
                Text(
                  priceStr,
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(width: 8),
              ],
              Expanded(
                child: Text(
                  signal.reason,
                  style: TextStyle(
                    fontSize: 12,
                    color: AppColors.secondaryText,
                  ),
                  overflow: TextOverflow.ellipsis,
                  maxLines: 2,
                ),
              ),
            ],
          ),
          if (timeStr.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              '기준: $timeStr (4h)',
              style: TextStyle(
                fontSize: 10,
                color: AppColors.placeholderText,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
