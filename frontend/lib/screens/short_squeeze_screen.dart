import 'package:flutter/material.dart';

class ShortSqueezeScreen extends StatelessWidget {
  const ShortSqueezeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // 상단 안내 배너
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: colorScheme.primaryContainer,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                Icon(Icons.info_outline,
                    color: colorScheme.onPrimaryContainer, size: 20),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    '숏 스퀴즈 스크리너는 준비 중입니다.\n데이터 소스 연동 후 공매도 비율 상위 종목을 제공합니다.',
                    style: TextStyle(
                      color: colorScheme.onPrimaryContainer,
                      fontSize: 13,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),

          // 주요 지표 카드들
          Text(
            '주요 스크리닝 지표',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
              color: colorScheme.onSurface,
            ),
          ),
          const SizedBox(height: 12),
          _IndicatorCard(
            icon: Icons.trending_down,
            iconColor: Colors.red.shade600,
            title: 'Short Interest (%)',
            description: '발행 주식 대비 공매도 잔량 비율. 높을수록 숏 스퀴즈 가능성 증가.',
            threshold: '기준: ≥ 20%',
          ),
          const SizedBox(height: 8),
          _IndicatorCard(
            icon: Icons.calendar_today,
            iconColor: Colors.orange.shade600,
            title: 'Days to Cover',
            description: '공매도 잔량을 평균 거래량으로 나눈 값. 높을수록 청산 압박 강화.',
            threshold: '기준: ≥ 5일',
          ),
          const SizedBox(height: 8),
          _IndicatorCard(
            icon: Icons.attach_money,
            iconColor: Colors.amber.shade700,
            title: 'Cost to Borrow (%)',
            description: '주식 대여 연간 비용. 높은 비용은 공매도 포지션 유지 부담 증가 의미.',
            threshold: '기준: ≥ 50% (annualized)',
          ),
          const SizedBox(height: 8),
          _IndicatorCard(
            icon: Icons.bar_chart,
            iconColor: Colors.blue.shade600,
            title: '거래량 스파이크',
            description: '최근 거래량이 20일 평균 거래량 대비 급등한 종목. 숏 커버링 신호.',
            threshold: '기준: ≥ 3× 20일 평균',
          ),
          const SizedBox(height: 8),
          _IndicatorCard(
            icon: Icons.show_chart,
            iconColor: Colors.green.shade600,
            title: 'RSI 반등 신호',
            description: '과매도 구간에서 반등하는 RSI 패턴. 숏 스퀴즈 진입 타이밍 확인.',
            threshold: 'RSI 30 이하 → 상향 돌파',
          ),
          const SizedBox(height: 24),

          // 작동 방식 안내
          Text(
            '스크리닝 프로세스',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
              color: colorScheme.onSurface,
            ),
          ),
          const SizedBox(height: 12),
          _ProcessCard(
            steps: [
              (
                '1단계',
                '공매도 잔량 필터',
                'Short Interest ≥ 20% AND Days to Cover ≥ 5'
              ),
              (
                '2단계',
                '촉매 신호 확인',
                '거래량 스파이크 OR Cost to Borrow 급등 OR RSI 반등'
              ),
              (
                '3단계',
                '종합 스퀴즈 점수',
                'SI × DTC × 촉매 강도 종합 산출'
              ),
              (
                '4단계',
                'TOP N 선정',
                '점수 상위 종목 출력 (기본: TOP 10)'
              ),
            ],
            colorScheme: colorScheme,
          ),
          const SizedBox(height: 80),
        ],
      ),
    );
  }
}

class _IndicatorCard extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final String description;
  final String threshold;

  const _IndicatorCard({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.description,
    required this.threshold,
  });

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
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: iconColor.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(icon, color: iconColor, size: 20),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: const TextStyle(
                          fontWeight: FontWeight.bold, fontSize: 14)),
                  const SizedBox(height: 4),
                  Text(description,
                      style: const TextStyle(fontSize: 12, color: Colors.grey)),
                  const SizedBox(height: 6),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: iconColor.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      threshold,
                      style: TextStyle(
                          fontSize: 11,
                          color: iconColor,
                          fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProcessCard extends StatelessWidget {
  final List<(String, String, String)> steps;
  final ColorScheme colorScheme;

  const _ProcessCard({required this.steps, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: steps.map((step) {
            final isLast = step == steps.last;
            return Column(
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 48,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 6, vertical: 3),
                      decoration: BoxDecoration(
                        color: colorScheme.primary,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        step.$1,
                        style: TextStyle(
                            color: colorScheme.onPrimary,
                            fontSize: 10,
                            fontWeight: FontWeight.bold),
                        textAlign: TextAlign.center,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(step.$2,
                              style: const TextStyle(
                                  fontWeight: FontWeight.bold, fontSize: 13)),
                          const SizedBox(height: 2),
                          Text(step.$3,
                              style: const TextStyle(
                                  fontSize: 12, color: Colors.grey)),
                        ],
                      ),
                    ),
                  ],
                ),
                if (!isLast) ...[
                  const SizedBox(height: 8),
                  Padding(
                    padding: const EdgeInsets.only(left: 22),
                    child: Row(
                      children: [
                        Icon(Icons.arrow_downward,
                            size: 14, color: colorScheme.outline),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
              ],
            );
          }).toList(),
        ),
      ),
    );
  }
}
