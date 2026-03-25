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
        const _StrategyOverviewCard(),
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
          backtestResult: 'CAGR +48.1% | MDD -1.3% | 샤프 3.94 | 승률 79.8%',
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
          backtestResult: 'CAGR +56.8% | MDD -1.5% | 샤프 3.96 | 승률 76.7%',
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
          backtestResult: 'CAGR +63.5% | MDD -3.2% | 샤프 3.52 | 승률 71.6%',
        ),
        const SizedBox(height: 12),
        const _StrategyCard(
          title: '적응형 (Adaptive)',
          color: Color(0xFFAB47BC),
          icon: Icons.auto_awesome,
          params: [
            ('ATR 승수', '국면별 동적'),
            ('리밸런싱', '국면별 동적'),
            ('TOP N', '국면별 동적'),
          ],
          entryConditions: _commonEntryConditions,
          stopLoss: '3계층 복합 판별로 국면별 자동 전환',
          positionSizing: '복합점수 비례 배분, 최대 10%/종목',
          backtestResult: 'CAGR +49.0% | MDD -3.2% | 샤프 3.76 | 승률 78.4%',
          extraInfo:
              'Bull / Bear / Neutral 국면을 자동 감지하여\nATR 승수·리밸런싱 주기·TOP N을 동적으로 전환합니다.',
        ),
        const SizedBox(height: 24),
        _SectionHeader(title: '공통 진입 조건', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _EntryConditionsCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '백테스트 결과', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _BacktestResultTable(),
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
  '현재가 > ATR 기반 스톱로스',
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

class _StrategyOverviewCard extends StatelessWidget {
  const _StrategyOverviewCard();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    const accentColor = Color(0xFF7C9BFF);

    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 핵심 아이디어
            Row(
              children: [
                Icon(Icons.lightbulb_outline, color: accentColor, size: 18),
                const SizedBox(width: 8),
                Text(
                  '핵심 아이디어: 추세 추종 + 위험 관리',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: accentColor,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              '강한 추세가 확인된 종목에만 진입하고, ATR 기반 동적 스톱로스로 하방을 제한합니다. '
              '모멘텀이 지속되는 한 보유를 유지하고, 추세가 꺾이면 즉시 청산합니다.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
                height: 1.5,
              ),
            ),
            const Divider(height: 24),

            // 유니버스
            Row(
              children: [
                Icon(Icons.public, color: colorScheme.secondary, size: 16),
                const SizedBox(width: 6),
                Text(
                  '투자 유니버스',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                _TagChip(label: 'S&P 500', color: colorScheme.secondary),
                _TagChip(label: 'Nasdaq 100', color: colorScheme.secondary),
                _TagChip(label: 'KOSPI 200', color: colorScheme.secondary),
                _TagChip(label: 'KOSDAQ 150', color: colorScheme.secondary),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              '동적 수집 ~867 종목 (중복 제거) · 매 실행 시 최신 구성 반영',
              style: theme.textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
              ),
            ),
            const Divider(height: 24),

            // 스크리닝 필터 7단계
            Row(
              children: [
                Icon(Icons.filter_list, color: colorScheme.secondary, size: 16),
                const SizedBox(width: 6),
                Text(
                  '스크리닝 필터 (7단계)',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            ..._filterSteps.asMap().entries.map((e) {
              return _FilterStep(
                step: e.key + 1,
                title: e.value.$1,
                desc: e.value.$2,
                colorScheme: colorScheme,
                theme: theme,
              );
            }),
            const Divider(height: 24),

            // ATR 스톱로스
            Row(
              children: [
                Icon(Icons.shield_outlined, color: colorScheme.secondary, size: 16),
                const SizedBox(width: 6),
                Text(
                  'ATR 기반 동적 스톱로스',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                'Stop Loss = 20일 최고가 − ATR(14) × 승수',
                style: theme.textTheme.bodySmall?.copyWith(
                  fontFamily: 'monospace',
                  color: colorScheme.secondary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              'ATR은 14일 평균 변동폭으로, 종목마다 변동성에 맞는 스톱 거리를 자동 조정합니다. '
              '승수가 클수록 스톱이 넓어져 노이즈에 강하지만 손실도 커집니다.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
                height: 1.5,
              ),
            ),
            const Divider(height: 24),

            // 리밸런싱 & 수수료
            Row(
              children: [
                Icon(Icons.sync, color: colorScheme.secondary, size: 16),
                const SizedBox(width: 6),
                Text(
                  '운영 조건',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            _InfoRow(label: '리밸런싱', value: '격주 (2주마다) 재스크리닝 후 편입/편출'),
            const SizedBox(height: 4),
            _InfoRow(label: '매매 수수료', value: '편도 0.1% (왕복 0.2%) 반영'),
            const SizedBox(height: 4),
            _InfoRow(label: '포지션 수', value: '최대 TOP N (전략별 7~15개)'),
            const SizedBox(height: 4),
            _InfoRow(label: '최대 비중', value: '종목당 10% 상한'),
          ],
        ),
      ),
    );
  }
}

const _filterSteps = [
  ('ADX ≥ 20 (추세 강도)', 'Average Directional Index로 추세가 충분히 강한 종목만 선택'),
  ('MA 정배열 (추세 방향)', '20MA > 50MA > 200MA — 단·중·장기 추세 모두 상향'),
  ('RSI 50 ~ 77 (과매수 배제)', '모멘텀이 살아있되 과열 구간(>77) 진입 금지'),
  ('HH-HL ≥ 2회 (상승 구조)', '60일 내 고점 갱신 + 저점 상승 패턴이 2회 이상 확인'),
  ('52주 고점 대비 ≥ 75%', '고점 대비 25% 이상 하락한 종목 제외'),
  ('거래량 급변/급등락 배제', '20일 평균 대비 3× 거래량 스파이크, 5일 ±10% 급등락 제외'),
  ('현재가 > 스톱로스', 'ATR 기반 동적 스톱 아래로 이미 하락한 종목 진입 불가'),
];

class _FilterStep extends StatelessWidget {
  final int step;
  final String title;
  final String desc;
  final ColorScheme colorScheme;
  final ThemeData theme;

  const _FilterStep({
    required this.step,
    required this.title,
    required this.desc,
    required this.colorScheme,
    required this.theme,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 22,
            height: 22,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: colorScheme.primary.withValues(alpha: 0.15),
              shape: BoxShape.circle,
            ),
            child: Text(
              '$step',
              style: theme.textTheme.labelSmall?.copyWith(
                fontWeight: FontWeight.bold,
                color: colorScheme.primary,
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  desc,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: colorScheme.onSurfaceVariant,
                    height: 1.4,
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

class _TagChip extends StatelessWidget {
  final String label;
  final Color color;

  const _TagChip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
              fontWeight: FontWeight.w600,
              color: color,
            ),
      ),
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
              color: color.withValues(alpha: 0.15),
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
                  children:
                      params.map((p) => _Chip(label: p.$1, value: p.$2, color: color)).toList(),
                ),
                const SizedBox(height: 12),
                _InfoRow(label: '스톱로스', value: stopLoss),
                const SizedBox(height: 4),
                _InfoRow(label: '포지션', value: positionSizing),
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.08),
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

// 백테스트 결과 데이터
const _backtestRows = [
  ('공격적', '1.5', '15', '+48.1%', '-1.3%', '3.94', '79.8%', Color(0xFFEF5350)),
  ('균형형', '2.0', '10', '+56.8%', '-1.5%', '3.96', '76.7%', Color(0xFF42A5F5)),
  ('보수적', '2.5', '7', '+63.5%', '-3.2%', '3.52', '71.6%', Color(0xFF66BB6A)),
  ('적응형', '2.0', '10', '+49.0%', '-3.2%', '3.76', '78.4%', Color(0xFFAB47BC)),
  ('SPY', '-', '-', '+12.6%', '-31.0%', '0.82', '64.3%', Color(0xFF9E9E9E)),
];

class _BacktestResultTable extends StatelessWidget {
  const _BacktestResultTable();

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
            // 기간 설명
            Row(
              children: [
                Icon(Icons.calendar_today, size: 14, color: colorScheme.primary),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    '백테스트 기간: 2015-01-01 ~ 현재 (약 11년)',
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: colorScheme.primary,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              '강세장(2017, 2021) · 하락장(2018, 2020, 2022) · 횡보장을 모두 포함한 기간',
              style: theme.textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              '기준: 격주 리밸런싱 · A진입방식 · 매매 수수료 왕복 0.2% 반영',
              style: theme.textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 16),

            // 테이블 헤더
            _TableRow(
              cells: const ['전략', 'ATR', 'Top N', 'CAGR', 'MDD', '샤프', '승률'],
              isHeader: true,
              rowColor: colorScheme.surfaceContainerHighest,
              textColor: colorScheme.onSurfaceVariant,
              theme: theme,
            ),
            const SizedBox(height: 2),

            // 데이터 행
            ..._backtestRows.map((row) {
              final isSpy = row.$1 == 'SPY';
              return Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: _TableRow(
                  cells: [row.$1, row.$2, row.$3, row.$4, row.$5, row.$6, row.$7],
                  isHeader: false,
                  rowColor: isSpy
                      ? colorScheme.surfaceContainerHighest.withValues(alpha: 0.3)
                      : row.$8.withValues(alpha: 0.08),
                  textColor: isSpy ? colorScheme.onSurfaceVariant : row.$8,
                  theme: theme,
                  accentColor: row.$8,
                  isBenchmark: isSpy,
                ),
              );
            }),

            const SizedBox(height: 12),

            // 범례
            Wrap(
              spacing: 12,
              runSpacing: 4,
              children: [
                _LegendItem(
                  color: colorScheme.primary,
                  label: 'CAGR: 연평균 복합 성장률',
                  theme: theme,
                ),
                _LegendItem(
                  color: colorScheme.primary,
                  label: 'MDD: 최대 낙폭',
                  theme: theme,
                ),
                _LegendItem(
                  color: colorScheme.primary,
                  label: '샤프: 위험 대비 수익',
                  theme: theme,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _TableRow extends StatelessWidget {
  final List<String> cells;
  final bool isHeader;
  final Color rowColor;
  final Color textColor;
  final ThemeData theme;
  final Color? accentColor;
  final bool isBenchmark;

  const _TableRow({
    required this.cells,
    required this.isHeader,
    required this.rowColor,
    required this.textColor,
    required this.theme,
    this.accentColor,
    this.isBenchmark = false,
  });

  @override
  Widget build(BuildContext context) {
    // 컬럼 너비 비율: [전략, ATR, TopN, CAGR, MDD, 샤프, 승률]
    const flexes = [2, 1, 1, 2, 2, 1, 2];

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: rowColor,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        children: cells.asMap().entries.map((e) {
          final idx = e.key;
          final text = e.value;
          final isCAGR = idx == 3;
          final isMDD = idx == 4;

          Color cellColor = textColor;
          if (!isHeader && !isBenchmark) {
            if (isCAGR) cellColor = accentColor ?? textColor;
            if (isMDD) cellColor = const Color(0xFFFF7043);
          }

          return Expanded(
            flex: flexes[idx],
            child: Text(
              text,
              style: isHeader
                  ? theme.textTheme.labelSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: textColor,
                    )
                  : theme.textTheme.bodySmall?.copyWith(
                      fontWeight: isCAGR ? FontWeight.bold : FontWeight.normal,
                      color: cellColor,
                    ),
              textAlign: idx == 0 ? TextAlign.left : TextAlign.center,
            ),
          );
        }).toList(),
      ),
    );
  }
}

class _LegendItem extends StatelessWidget {
  final Color color;
  final String label;
  final ThemeData theme;

  const _LegendItem({
    required this.color,
    required this.label,
    required this.theme,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 4),
        Text(
          label,
          style: theme.textTheme.labelSmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
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
              color: btcColor.withValues(alpha: 0.15),
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
                _BulletRow('레짐별 파라미터 동적 전환 (ATR 승수, 포지션 크기)'),
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: btcColor.withValues(alpha: 0.08),
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
            _InfoRow(label: 'Sector', value: '섹터 ETF 상대강도 (20% 가중)'),
            const SizedBox(height: 4),
            _InfoRow(label: 'Vol Stability', value: '변동성 안정성 (10% 가중)'),
            const SizedBox(height: 12),
            Text(
              '스코어 상위 TOP N 종목을 점수 비례로 배분하며,\n종목당 최대 비중 10%를 상한으로 cap 처리합니다.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
                height: 1.5,
              ),
            ),
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
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.3)),
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
          width: 80,
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
    '추세 강도 지표. 20 이상이면 유효한 추세, 25 이상이면 강한 추세',
  ),
  (
    'RSI',
    'Relative Strength Index',
    '상대강도지수. 과매수(>77) / 과매도(<30) 판단에 사용',
  ),
  (
    '정배열',
    'MA Alignment',
    '20MA > 50MA > 200MA로 단·중·장기 이동평균이 순서대로 정렬된 상태',
  ),
  (
    'HH-HL',
    'Higher High - Higher Low',
    '고점이 높아지고 저점도 높아지는 상승 구조. 추세 지속성의 핵심 패턴',
  ),
  (
    '골든크로스',
    'Golden Cross',
    '단기 이동평균이 장기 이동평균을 상향 돌파하는 것',
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
                        color: colorScheme.primary.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(
                          color: colorScheme.primary.withValues(alpha: 0.3),
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
