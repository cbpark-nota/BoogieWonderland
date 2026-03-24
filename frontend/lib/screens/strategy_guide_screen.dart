import 'package:flutter/material.dart';

class StrategyGuideScreen extends StatelessWidget {
  const StrategyGuideScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _SectionHeader(title: '주식 스크리닝 전략', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _StrategyCard(
          title: '공격적 (Aggressive)',
          color: Color(0xFFEF5350),
          icon: Icons.trending_up,
          params: [
            ('ATR 승수', '1.5'),
            ('리밸런싱', '격주'),
            ('TOP N', '15'),
          ],
          entryConditions: _commonEntryConditions,
          stopLoss: 'ATR 기반 동적 (20d High − ATR × 1.5)',
          positionSizing: '복합점수 비례 배분, 최대 10%/종목',
          backtestResult: 'CAGR +48.1% | MDD -1.3% | 샤프 3.94',
        ),
        const SizedBox(height: 12),
        const _StrategyCard(
          title: '균형형 (Balanced)',
          color: Color(0xFF42A5F5),
          icon: Icons.balance,
          params: [
            ('ATR 승수', '2.0'),
            ('리밸런싱', '격주'),
            ('TOP N', '10'),
          ],
          entryConditions: _commonEntryConditions,
          stopLoss: 'ATR 기반 동적 (20d High − ATR × 2.0)',
          positionSizing: '복합점수 비례 배분, 최대 10%/종목',
          backtestResult: 'CAGR +56.8% | MDD -1.5% | 샤프 3.96',
        ),
        const SizedBox(height: 12),
        const _StrategyCard(
          title: '보수적 (Conservative)',
          color: Color(0xFF66BB6A),
          icon: Icons.security,
          params: [
            ('ATR 승수', '2.5'),
            ('리밸런싱', '격주'),
            ('TOP N', '7'),
          ],
          entryConditions: _commonEntryConditions,
          stopLoss: 'ATR 기반 동적 (20d High − ATR × 2.5)',
          positionSizing: '복합점수 비례 배분, 최대 10%/종목',
          backtestResult: 'CAGR +63.5% | MDD -3.2% | 샤프 3.52',
        ),
        const SizedBox(height: 12),
        const _StrategyCard(
          title: '적응형 (Adaptive)',
          color: Color(0xFFAB47BC),
          icon: Icons.auto_awesome,
          params: [
            ('ATR 승수', '국면별 동적'),
            ('리밸런싱', '격주'),
            ('TOP N', '국면별 동적'),
          ],
          entryConditions: _commonEntryConditions,
          stopLoss: '3계층 복합 판별로 국면별 자동 전환',
          positionSizing: '복합점수 비례 배분, 최대 10%/종목',
          backtestResult: 'CAGR +49.0% | MDD -3.2% | 샤프 3.76',
          extraInfo: 'Bull / Bear / Neutral 국면을 자동 감지하여\nATR 승수·리밸런싱 주기·TOP N을 동적으로 전환합니다.',
        ),
        const SizedBox(height: 24),
        _SectionHeader(title: '공통 진입 조건', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _EntryConditionsCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '비트코인 V10 전략', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _BtcStrategyCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '스코어 산식', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _ScoreFormulaCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '용어 설명', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _GlossaryCard(),
        const SizedBox(height: 32),
      ],
    );
  }
}

const _commonEntryConditions = [
  'ADX ≥ 20',
  'RSI 50 ~ 77',
  '20MA > 50MA > 200MA (정배열)',
  'HH-HL ≥ 2 (60일 내)',
  '현재가 ≥ 52주 고점 × 75%',
  '거래량 스파이크 < 3× (20일 평균)',
  '5일 급등락 < ±10%',
];

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

class _StrategyCard extends StatelessWidget {
  final String title;
  final Color color;
  final IconData icon;
  final List<(String, String)> params;
  final List<String> entryConditions;
  final String stopLoss;
  final String positionSizing;
  final String backtestResult;
  final String? extraInfo;

  const _StrategyCard({
    required this.title,
    required this.color,
    required this.icon,
    required this.params,
    required this.entryConditions,
    required this.stopLoss,
    required this.positionSizing,
    required this.backtestResult,
    this.extraInfo,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      elevation: 2,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            decoration: BoxDecoration(
              color: color.withOpacity(0.15),
              borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                Icon(icon, color: color, size: 22),
                const SizedBox(width: 10),
                Text(
                  title,
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: color,
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: params.map((p) => _Chip(label: p.$1, value: p.$2, color: color)).toList(),
                ),
                const SizedBox(height: 12),
                _InfoRow(label: '스톱로스', value: stopLoss),
                const SizedBox(height: 4),
                _InfoRow(label: '포지션', value: positionSizing),
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: color.withOpacity(0.08),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.bar_chart, size: 16, color: color),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          backtestResult,
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: color,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                if (extraInfo != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    extraInfo!,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _EntryConditionsCard extends StatelessWidget {
  const _EntryConditionsCard();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: _commonEntryConditions.map((cond) {
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.check_circle_outline, size: 16, color: colorScheme.primary),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(cond, style: theme.textTheme.bodyMedium),
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

class _BtcStrategyCard extends StatelessWidget {
  const _BtcStrategyCard();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    const btcColor = Color(0xFFF7931A);
    return Card(
      elevation: 2,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            decoration: BoxDecoration(
              color: btcColor.withOpacity(0.15),
              borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                const Icon(Icons.currency_bitcoin, color: btcColor, size: 22),
                const SizedBox(width: 10),
                Text(
                  'Bitcoin V10 — 4시간봉',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: btcColor,
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: const [
                    _Chip(label: '타임프레임', value: '4시간봉', color: btcColor),
                    _Chip(label: '방향', value: '롱온리', color: btcColor),
                    _Chip(label: '스톱로스', value: '적응형 SL', color: btcColor),
                  ],
                ),
                const SizedBox(height: 12),
                _BulletRow('Squeeze Momentum 지표 기반 모멘텀 감지'),
                _BulletRow('Bollinger Band Break 신호 진입 트리거'),
                _BulletRow('EMA 크로스 필터 (추세 방향 확인)'),
                _BulletRow('Bull / Bear / Neutral 레짐 자동 판별'),
                _BulletRow('레짐별 파라미터 동적 전환'),
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: btcColor.withOpacity(0.08),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.bar_chart, size: 16, color: btcColor),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          'CAGR 31.5% | MDD -28.4% | 샤프 0.89',
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: btcColor,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ScoreFormulaCard extends StatelessWidget {
  const _ScoreFormulaCard();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Score = ADX × 0.4 + 3M_Return × 0.3\n'
              '      + Sector_Strength × 0.2 + Vol_Stability × 0.1',
              style: theme.textTheme.bodyMedium?.copyWith(
                fontFamily: 'monospace',
                color: colorScheme.secondary,
                fontWeight: FontWeight.w600,
              ),
            ),
            const Divider(height: 20),
            _InfoRow(label: 'ADX', value: '추세 강도 (40% 가중)'),
            const SizedBox(height: 4),
            _InfoRow(label: '3M Return', value: '3개월 수익률 (30% 가중)'),
            const SizedBox(height: 4),
            _InfoRow(label: 'Sector Strength', value: '섹터 ETF 상대강도 (20% 가중)'),
            const SizedBox(height: 4),
            _InfoRow(label: 'Vol Stability', value: '변동성 안정성 (10% 가중)'),
          ],
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _Chip({required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: RichText(
        text: TextSpan(
          style: theme.textTheme.bodySmall,
          children: [
            TextSpan(
              text: '$label: ',
              style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
            ),
            TextSpan(
              text: value,
              style: TextStyle(fontWeight: FontWeight.bold, color: color),
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;

  const _InfoRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 72,
          child: Text(
            label,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ),
        const SizedBox(width: 4),
        Expanded(
          child: Text(value, style: theme.textTheme.bodySmall),
        ),
      ],
    );
  }
}

class _BulletRow extends StatelessWidget {
  final String text;
  const _BulletRow(this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('• ', style: TextStyle(fontSize: 14)),
          Expanded(
            child: Text(text, style: Theme.of(context).textTheme.bodySmall),
          ),
        ],
      ),
    );
  }
}

const _glossaryTerms = [
  (
    'ATR',
    'Average True Range',
    '일정 기간의 평균 변동폭. 스톱로스 거리를 동적으로 설정하는 데 사용',
  ),
  (
    'CAGR',
    'Compound Annual Growth Rate',
    '연평균 복합 성장률. 투자 수익률을 연간 기준으로 환산한 지표',
  ),
  (
    'MDD',
    'Maximum Drawdown',
    '최대 낙폭. 고점 대비 최대 하락 비율로 위험도를 나타냄',
  ),
  (
    '샤프지수',
    'Sharpe Ratio',
    '위험 대비 수익률. 높을수록 위험 대비 수익이 좋음',
  ),
  (
    'ADX',
    'Average Directional Index',
    '추세 강도 지표. 25 이상이면 강한 추세',
  ),
  (
    'RSI',
    'Relative Strength Index',
    '상대강도지수. 과매수(>70) / 과매도(<30) 판단에 사용',
  ),
  (
    '골든크로스',
    'Golden Cross',
    '단기 이동평균이 장기 이동평균을 상향 돌파하는 것',
  ),
  (
    '데드크로스',
    'Dead Cross',
    '단기 이동평균이 장기 이동평균을 하향 돌파하는 것',
  ),
  (
    '볼린저 밴드',
    'Bollinger Bands',
    '이동평균 ± 표준편차로 구성된 밴드. 가격 변동성을 시각화',
  ),
  (
    '스퀴즈',
    'Squeeze',
    '볼린저 밴드가 켈트너 채널 안으로 수축한 상태. 변동성 확장 직전 신호',
  ),
  (
    'EMA',
    'Exponential Moving Average',
    '지수이동평균. 최근 데이터에 더 높은 가중치 부여',
  ),
  (
    '레짐',
    'Regime',
    '시장 국면. Bull(상승) / Bear(하락) / Neutral(중립)으로 분류',
  ),
];

class _GlossaryCard extends StatelessWidget {
  const _GlossaryCard();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: _glossaryTerms.asMap().entries.map((entry) {
            final i = entry.key;
            final term = entry.value;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (i != 0) const Divider(height: 16, thickness: 0.5),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 2,
                      ),
                      decoration: BoxDecoration(
                        color: colorScheme.primary.withOpacity(0.12),
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(
                          color: colorScheme.primary.withOpacity(0.3),
                        ),
                      ),
                      child: Text(
                        term.$1,
                        style: theme.textTheme.bodySmall?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: colorScheme.primary,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            term.$2,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: colorScheme.onSurfaceVariant,
                              fontStyle: FontStyle.italic,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            term.$3,
                            style: theme.textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            );
          }).toList(),
        ),
      ),
    );
  }
}
