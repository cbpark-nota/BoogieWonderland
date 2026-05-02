import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

class StopLossIndicator extends StatelessWidget {
  final double marginPct;

  const StopLossIndicator({super.key, required this.marginPct});

  @override
  Widget build(BuildContext context) {
    Color color;
    String label;

    if (marginPct <= 0) {
      color = AppColors.priceDown;
      label = 'BREACH';
    } else if (marginPct < 5) {
      color = AppColors.warning;
      label = '${marginPct.toStringAsFixed(1)}%';
    } else {
      color = AppColors.priceUp;
      label = '${marginPct.toStringAsFixed(1)}%';
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(label,
          style: TextStyle(
              color: color, fontWeight: FontWeight.bold, fontSize: 12)),
    );
  }
}
