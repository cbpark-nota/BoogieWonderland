import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

class ShortSqueezeStrategyGuideScreen extends StatelessWidget {
  const ShortSqueezeStrategyGuideScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _SectionHeader(title: '숏 스퀴즈 전략 개요', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _OverviewCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '주요 지표', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _IndicatorsCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '진입 조건', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _EntryConditionsCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '청산 조건', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _ExitConditionsCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '백테스트 결과 (예시)', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _BacktestCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '용어 설명', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _GlossaryCard(),
        const SizedBox(height: 32),
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  final ColorScheme colorScheme;

  const _SectionHeader({required this.title, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 4,
          height: 22,
          decoration: BoxDecoration(
            color: colorScheme.primary,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const SizedBox(width: 10),
        Text(
          title,
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
                color: colorScheme.primary,
              ),
        ),
      ],
    );
  }
}

class _OverviewCard extends StatelessWidget {
  const _OverviewCard();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    const accentColor = Color(0xFFEF5350);

    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.compress, color: accentColor, size: 18),
                const SizedBox(width: 8),
                Text(
                  '핵심 아이디어: 공매도 과부하 → 강제 청산',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: accentColor,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              '공매도 잔량이 많고 커버일수가 긴 종목에서 촉매(거래량 스파이크, 호재)가 발생하면 '
              '공매도 세력이 강제 청산(Buy to Cover)에 나서며 급등이 발생합니다. '
              '이 "숏 스퀴즈" 현상을 선행 지표로 포착하여 진입하는 전략입니다.',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                _StatChip(label: 'Short Interest', value: '≥ 20%',
                    color: AppColors.priceDownMid),
                const SizedBox(width: 8),
                _StatChip(label: 'Days to Cover', value: '≥ 5일',
                    color: AppColors.warningMid),
                const SizedBox(width: 8),
                _StatChip(label: '촉매 신호', value: '필수',
                    color: AppColors.infoMid),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _StatChip extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _StatChip(
      {required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Column(
        children: [
          Text(label,
              style: TextStyle(fontSize: 10, color: color)),
          Text(value,
              style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                  color: color)),
        ],
      ),
    );
  }
}

class _IndicatorsCard extends StatelessWidget {
  const _IndicatorsCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    const indicators = [
      (
        Icons.trending_down,
        'Short Interest (%)',
        '발행 주식 대비 공매도 잔량 비율. 공매도 세력의 규모를 나타내는 핵심 지표.',
        AppColors.priceDown,
      ),
      (
        Icons.calendar_today,
        'Days to Cover (DTC)',
        '공매도 잔량 / 일평균 거래량. 높을수록 공매도 세력이 청산하기 어려움.',
        AppColors.warning,
      ),
      (
        Icons.attach_money,
        'Cost to Borrow (CTB)',
        '주식 대여 연간 비용(%). 높으면 공매도 유지 비용이 커져 청산 압박 강화.',
        AppColors.amber,
      ),
      (
        Icons.bar_chart,
        '거래량 스파이크',
        '20일 평균 대비 거래량 급증. 공매도 청산 또는 신규 매수세 유입 신호.',
        AppColors.info,
      ),
      (
        Icons.show_chart,
        'RSI 반등',
        '과매도(RSI ≤ 30) 이후 상향 돌파. 바닥 확인 후 반등 타이밍 포착.',
        AppColors.priceUp,
      ),
    ];

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: indicators.map((ind) {
            final color = ind.$4 is MaterialColor
                ? (ind.$4 as MaterialColor).shade600
                : ind.$4 as Color;
            final isLast = ind == indicators.last;
            return Column(
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(ind.$1, color: color, size: 18),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(ind.$2,
                              style: const TextStyle(
                                  fontWeight: FontWeight.bold, fontSize: 13)),
                          const SizedBox(height: 4),
                          Text(ind.$3,
                              style: const TextStyle(
                                  fontSize: 12, color: AppColors.mutedText)),
                        ],
                      ),
                    ),
                  ],
                ),
                if (!isLast) const Divider(height: 20),
              ],
            );
          }).toList(),
        ),
      ),
    );
  }
}

class _EntryConditionsCard extends StatelessWidget {
  const _EntryConditionsCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    const conditions = [
      ('필수', 'Short Interest ≥ 20%', AppColors.priceDown),
      ('필수', 'Days to Cover ≥ 5일', AppColors.priceDown),
      ('촉매', '거래량 ≥ 3× 20일 평균 OR Cost to Borrow 급등', AppColors.warning),
      ('촉매', 'RSI 30 이하 → 상향 돌파 (선택적)', AppColors.warning),
      ('추세', '주가 5일 이상 연속 하락 후 반등 시작', AppColors.info),
      ('리스크', '시가총액 ≥ 1억 달러 (소형주 유동성 리스크 필터)', AppColors.priceUp),
    ];

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: conditions.map((c) {
            final badgeColor = c.$3 is MaterialColor
                ? (c.$3 as MaterialColor).shade600
                : c.$3 as Color;
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: badgeColor,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(c.$1,
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10,
                            fontWeight: FontWeight.bold)),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(c.$2,
                        style: const TextStyle(fontSize: 13)),
                  ),
                ],
              ),
            );
          }).toList(),
        ),
      ),
    );
  }
}

class _ExitConditionsCard extends StatelessWidget {
  const _ExitConditionsCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    const conditions = [
      (Icons.stop_circle_outlined, '스톱로스', '진입가 대비 -8% 또는 ATR × 1.5 하회 시 손절'),
      (Icons.trending_up, '목표가 도달', '진입가 대비 +20~30% 또는 Short Interest 10% 미만으로 하락'),
      (Icons.timer_off_outlined, '시간 청산', '진입 후 10거래일 경과 시 목표 미달성이면 청산'),
      (Icons.warning_amber_outlined, '모멘텀 소멸', 'Short Interest 빠른 감소 + 거래량 급감 → 스퀴즈 종료 신호'),
    ];

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: conditions.map((c) {
            final isLast = c == conditions.last;
            return Column(
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(c.$1, size: 18, color: AppColors.priceDownSoft),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(c.$2,
                              style: const TextStyle(
                                  fontWeight: FontWeight.bold, fontSize: 13)),
                          const SizedBox(height: 3),
                          Text(c.$3,
                              style: const TextStyle(
                                  fontSize: 12, color: AppColors.mutedText)),
                        ],
                      ),
                    ),
                  ],
                ),
                if (!isLast) const Divider(height: 20),
              ],
            );
          }).toList(),
        ),
      ),
    );
  }
}

class _BacktestCard extends StatelessWidget {
  const _BacktestCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.info_outline,
                    size: 16, color: colorScheme.primary),
                const SizedBox(width: 8),
                Text('데이터 소스 연동 후 실제 백테스트 예정',
                    style: TextStyle(
                        fontSize: 12,
                        color: colorScheme.primary,
                        fontStyle: FontStyle.italic)),
              ],
            ),
            const SizedBox(height: 12),
            const _BacktestRow(
              label: '테스트 기간',
              value: '2015 ~ 2026',
              color: AppColors.mutedText,
            ),
            const Divider(height: 16),
            const _BacktestRow(
              label: '예상 CAGR',
              value: '준비 중',
              color: AppColors.mutedText,
            ),
            const Divider(height: 16),
            const _BacktestRow(
              label: '예상 MDD',
              value: '준비 중',
              color: AppColors.mutedText,
            ),
            const Divider(height: 16),
            const _BacktestRow(
              label: '예상 샤프비율',
              value: '준비 중',
              color: AppColors.mutedText,
            ),
            const Divider(height: 16),
            const _BacktestRow(
              label: '평균 보유기간',
              value: '5~10 거래일 (단기)',
              color: AppColors.info,
            ),
          ],
        ),
      ),
    );
  }
}

class _BacktestRow extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _BacktestRow(
      {required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label,
            style: const TextStyle(fontSize: 13, color: AppColors.mutedText)),
        Text(value,
            style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.bold,
                color: color)),
      ],
    );
  }
}

class _GlossaryCard extends StatelessWidget {
  const _GlossaryCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    const terms = [
      ('Short Interest', '발행 주식 중 공매도된 주식의 비율'),
      ('Days to Cover', '공매도 잔량을 평균 일간 거래량으로 나눈 값. 청산에 걸리는 예상 일수'),
      ('Cost to Borrow', '공매도를 위해 주식을 빌리는 연간 비용 (%)'),
      ('숏 스퀴즈', '공매도 세력이 상승세에 강제 청산하며 추가 상승을 유발하는 현상'),
      ('Buy to Cover', '공매도 포지션 청산을 위한 매수. 스퀴즈의 핵심 메커니즘'),
      ('Float', '실제 유통 가능한 주식 수. Short Interest는 Float 대비로도 측정'),
    ];

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: terms.map((t) {
            final isLast = t == terms.last;
            return Column(
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 110,
                      child: Text(t.$1,
                          style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 12,
                              color: colorScheme.primary)),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(t.$2,
                          style: const TextStyle(
                              fontSize: 12, color: AppColors.mutedText)),
                    ),
                  ],
                ),
                if (!isLast) const Divider(height: 16),
              ],
            );
          }).toList(),
        ),
      ),
    );
  }
}
