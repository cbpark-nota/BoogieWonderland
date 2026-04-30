import 'package:flutter/material.dart';

class TrendReversalStrategyGuideScreen extends StatelessWidget {
  const TrendReversalStrategyGuideScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _SectionHeader(title: '추세 전환 전략 개요', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _OverviewCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '핵심 로직 (5MA / 120MA 골든크로스)', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _LogicCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '진입 조건', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _EntryConditionsCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '스코어 산식', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _ScoreCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '매도 조건 (v3.3 동일)', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _ExitConditionsCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '백테스트 결과 (2015~2026)', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _BacktestCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '주의사항', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _CautionsCard(),
        const SizedBox(height: 32),
      ],
    );
  }
}

const _trendColor = Color(0xFF42A5F5);

// ── 공통 위젯 ─────────────────────────────────────────────────

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

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;
  final bool isLast;

  const _InfoRow({
    required this.label,
    required this.value,
    this.isLast = false,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label,
                style: TextStyle(fontSize: 13, color: colorScheme.onSurfaceVariant)),
            Flexible(
              child: Text(
                value,
                textAlign: TextAlign.end,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                  color: colorScheme.onSurface,
                ),
              ),
            ),
          ],
        ),
        if (!isLast) const Divider(height: 16),
      ],
    );
  }
}

class _BulletRow extends StatelessWidget {
  final String text;

  const _BulletRow(this.text);

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 6, right: 8),
            child: Container(
              width: 5,
              height: 5,
              decoration: const BoxDecoration(
                color: _trendColor,
                shape: BoxShape.circle,
              ),
            ),
          ),
          Expanded(
            child: Text(
              text,
              style: TextStyle(
                fontSize: 12,
                color: colorScheme.onSurface,
                height: 1.45,
              ),
            ),
          ),
        ],
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

class _HighlightBox extends StatelessWidget {
  final Color color;
  final Widget child;

  const _HighlightBox({required this.color, required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.85),
        borderRadius: BorderRadius.circular(8),
      ),
      child: child,
    );
  }
}

// ── 1. 전략 개요 ──────────────────────────────────────────────

class _OverviewCard extends StatelessWidget {
  const _OverviewCard();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Card(
      elevation: 2,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            decoration: BoxDecoration(
              color: _trendColor.withValues(alpha: 0.15),
              borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                const Icon(Icons.swap_vert, color: _trendColor, size: 22),
                const SizedBox(width: 10),
                Text(
                  '추세 전환 — 5MA / 120MA 골든크로스',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: _trendColor,
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
                Row(
                  children: [
                    const Icon(Icons.lightbulb_outline,
                        color: _trendColor, size: 18),
                    const SizedBox(width: 8),
                    Text(
                      '핵심 아이디어: 장기 추세 전환 포착',
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: _trendColor,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  '단기(5주) 이동평균이 장기(120주) 이동평균을 상향 돌파하는 시점은 '
                  '장기 하락 추세에서 상승 추세로 전환되는 강력한 구조적 신호입니다. '
                  '이 골든크로스 직후 매수해 추세 초입을 잡고, 트레일링 ATR 스톱과 격주 리밸런싱으로 '
                  '약화된 종목은 빠르게 정리합니다.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: colorScheme.onSurfaceVariant,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: const [
                    _Chip(label: '단기 MA', value: '25일 (5주)', color: _trendColor),
                    _Chip(label: '장기 MA', value: '600일 (120주)', color: _trendColor),
                    _Chip(label: '리밸런싱', value: '격주 금요일', color: _trendColor),
                    _Chip(label: '포지션', value: 'Top 25 동일비중', color: _trendColor),
                  ],
                ),
                const SizedBox(height: 12),
                Text(
                  '유니버스: S&P 500 + Nasdaq 100 + KOSPI 200 + KOSDAQ 150 (≈863 종목)',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: colorScheme.onSurfaceVariant,
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

// ── 2. 핵심 로직 ──────────────────────────────────────────────

class _LogicCard extends StatelessWidget {
  const _LogicCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final theme = Theme.of(context);

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
            Text(
              '일봉 기준 25일 / 600일 이동평균을 사용합니다 (5주×5거래일 / 120주×5거래일).',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colorScheme.onSurfaceVariant, height: 1.5),
            ),
            const SizedBox(height: 12),
            const _BulletRow('MA25 (단기): 최근 25 거래일 종가 평균 — 단기 흐름 반영'),
            const _BulletRow('MA600 (장기): 최근 600 거래일 종가 평균 — 약 2.4년 장기 추세'),
            const _BulletRow('골든크로스: 전일까지 MA25 ≤ MA600, 오늘 MA25 > MA600'),
            const _BulletRow('보유 유지: 격주 금요일 리밸런싱 시 MA25 > MA600 유지 여부 확인'),
            const _BulletRow('Top 25: gap ratio 스코어 상위 25 종목만 동일비중 보유'),
            const SizedBox(height: 12),
            _HighlightBox(
              color: _trendColor,
              child: const Text(
                'MA600은 약 2.4년의 장기 추세를 반영합니다.\n'
                '5주 이평이 120주 이평을 돌파한다는 것은 단순 단기 반등이 아닌 구조적 추세 전환의 신호입니다.',
                style: TextStyle(
                    fontSize: 12,
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    height: 1.45),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── 3. 진입 조건 ──────────────────────────────────────────────

class _EntryConditionsCard extends StatelessWidget {
  const _EntryConditionsCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    const conditions = [
      ('필수', '전일까지 MA25 ≤ MA600 (장기 약세 또는 횡보)', Colors.red),
      ('필수', '오늘 MA25 > MA600 (골든크로스 발생)', Colors.red),
      ('스코어', 'gap ratio = (MA25 − MA600) / MA600 — 양수일수록 상위', Colors.blue),
      ('포지션', 'gap ratio Top 25 동일비중 (US/KR 통합 슬롯 공유)', Colors.green),
      ('타이밍', '격주 금요일 리밸런싱 시 신규 진입 / 편출 결정', Colors.orange),
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
            final badgeColor = c.$3.shade600;
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

// ── 4. 스코어 산식 ────────────────────────────────────────────

class _ScoreCard extends StatelessWidget {
  const _ScoreCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final theme = Theme.of(context);

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
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: _trendColor.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: _trendColor.withValues(alpha: 0.3)),
              ),
              child: const Center(
                child: Text(
                  'gap = (MA25 − MA600) / MA600',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    color: _trendColor,
                    fontFamily: 'monospace',
                  ),
                ),
              ),
            ),
            const SizedBox(height: 12),
            Text(
              '5주 이평이 120주 이평을 얼마나 위로 떠 있는지를 비율로 측정합니다. '
              '값이 클수록 골든크로스 이후 추세가 강해진 상태이며, 동일 시점에서 상위 25 종목을 선택합니다.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 12),
            const _BulletRow('gap > 0: MA25가 MA600 위 (보유 유지 가능)'),
            const _BulletRow('gap ≤ 0: MA25가 MA600 아래 (편출 대상)'),
            const _BulletRow('gap 상위 25 외 종목: 격주 리밸런싱 시 자동 정리'),
            const _BulletRow('백테스트 스크립트와 동일한 산식 (정합화 유지)'),
          ],
        ),
      ),
    );
  }
}

// ── 5. 매도 조건 ──────────────────────────────────────────────

class _ExitConditionsCard extends StatelessWidget {
  const _ExitConditionsCard();

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
          children: const [
            _ExitRow(
              icon: Icons.trending_down,
              label: '트레일링 ATR 스톱',
              desc: '매일 체크 — peak = max(누적 peak, 오늘 High), '
                  'stop = max(기존 stop, peak − ATR(14) × 2.5). '
                  'Close ≤ stop 시 즉시 청산.',
              color: Colors.red,
            ),
            SizedBox(height: 8),
            _ExitRow(
              icon: Icons.list_alt,
              label: 'Top 25 이탈',
              desc: '격주 금요일 리밸런싱 시 gap ratio 스코어 Top 25에서 밀려난 종목 청산.',
              color: Colors.blue,
            ),
            SizedBox(height: 12),
            Text(
              '※ v3.3 모멘텀 스크리너와 동일한 매도 로직을 사용합니다 (스톱가는 상향만, 하향 갱신 없음).',
              style: TextStyle(
                fontSize: 11,
                color: Colors.grey,
                fontStyle: FontStyle.italic,
                height: 1.4,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ExitRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String desc;
  final Color color;

  const _ExitRow({
    required this.icon,
    required this.label,
    required this.desc,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 16, color: color),
        const SizedBox(width: 8),
        Text('$label: ',
            style: TextStyle(
                fontSize: 12, fontWeight: FontWeight.bold, color: color)),
        Expanded(
          child: Text(
            desc,
            style: const TextStyle(fontSize: 12, color: Colors.grey, height: 1.4),
          ),
        ),
      ],
    );
  }
}

// ── 6. 백테스트 결과 ──────────────────────────────────────────

class _BacktestCard extends StatelessWidget {
  const _BacktestCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final theme = Theme.of(context);

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
                Icon(Icons.info_outline, size: 14, color: Colors.blue.shade700),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    '2015-01-01 ~ 2026-03-24 · 격주 금요일 리밸런싱 · Top 25 동일비중 · 수수료 편도 0.1%',
                    style: TextStyle(
                      fontSize: 11,
                      color: Colors.blue.shade700,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            const Text(
              '국가별 성과',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
            ),
            const SizedBox(height: 8),
            Table(
              border: TableBorder.all(
                color: Colors.grey.shade300,
                width: 0.5,
                borderRadius: BorderRadius.circular(4),
              ),
              columnWidths: const {
                0: FlexColumnWidth(1.5),
                1: FlexColumnWidth(1.4),
                2: FlexColumnWidth(1.2),
                3: FlexColumnWidth(1.2),
                4: FlexColumnWidth(1.4),
              },
              children: [
                TableRow(
                  decoration: BoxDecoration(
                    color: colorScheme.primary.withValues(alpha: 0.1),
                  ),
                  children: const [
                    _TableCell('시나리오', isHeader: true),
                    _TableCell('CAGR', isHeader: true),
                    _TableCell('MDD', isHeader: true),
                    _TableCell('Sharpe', isHeader: true),
                    _TableCell('승률', isHeader: true),
                  ],
                ),
                const TableRow(children: [
                  _TableCell('통합 ★', highlight: true),
                  _TableCell('+89.8%', color: Colors.green, highlight: true),
                  _TableCell('-2.7%', color: Colors.red, highlight: true),
                  _TableCell('4.15', highlight: true),
                  _TableCell('67.5%', highlight: true),
                ]),
                const TableRow(children: [
                  _TableCell('US'),
                  _TableCell('+79.5%', color: Colors.green),
                  _TableCell('-3.1%', color: Colors.red),
                  _TableCell('3.95'),
                  _TableCell('64.4%'),
                ]),
                const TableRow(children: [
                  _TableCell('KR'),
                  _TableCell('+64.5%', color: Colors.green),
                  _TableCell('-3.3%', color: Colors.red),
                  _TableCell('3.72'),
                  _TableCell('66.8%'),
                ]),
                const TableRow(children: [
                  _TableCell('SPY B&H'),
                  _TableCell('+12.7%'),
                  _TableCell('-31.0%', color: Colors.red),
                  _TableCell('0.82'),
                  _TableCell('64.3%'),
                ]),
              ],
            ),
            const SizedBox(height: 16),
            const Text(
              '거래 통계 (통합 시나리오)',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
            ),
            const SizedBox(height: 8),
            const _InfoRow(label: '총 거래 건수', value: '2,514건'),
            const _InfoRow(label: '거래 승률', value: '44.7%'),
            const _InfoRow(label: '평균 수익', value: '+2.87%'),
            const _InfoRow(
              label: '평균 보유',
              value: '26.1일 (≈ 5.2주)',
              isLast: true,
            ),
            const SizedBox(height: 12),
            Text(
              '※ 기간 승률: 격주 리밸런싱 기간 단위 수익 비율. 거래 승률: 개별 포지션 청산 기준.\n'
              '※ MA600 warm-up이 필요해 실질 첫 거래는 2017년 중반부터 시작 (그 이전은 사실상 현금).',
              style: theme.textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
                height: 1.55,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TableCell extends StatelessWidget {
  final String text;
  final bool isHeader;
  final bool highlight;
  final Color? color;

  const _TableCell(
    this.text, {
    this.isHeader = false,
    this.highlight = false,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      color: highlight ? _trendColor.withValues(alpha: 0.08) : null,
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 6),
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: 11,
          fontWeight: isHeader || highlight ? FontWeight.bold : FontWeight.normal,
          color: color,
        ),
      ),
    );
  }
}

// ── 7. 주의사항 ───────────────────────────────────────────────

class _CautionsCard extends StatelessWidget {
  const _CautionsCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    const cautions = [
      (
        Icons.history,
        '서바이벌 바이어스',
        '현재 S&P 500 / Nasdaq 100 / KOSPI 200 / KOSDAQ 150 구성 종목으로 백테스트했습니다. '
            '2015년 당시 일부 종목은 지수에 속하지 않았거나 상장 전이었을 수 있어, 실제 성과보다 과대 추정 경향이 있습니다.',
        Colors.red,
      ),
      (
        Icons.access_time,
        'MA600 Warm-up',
        'MA600 계산에 600 거래일(약 2.4년)이 필요해 실질 첫 신호는 2017년 중반부터입니다. '
            '백테스트의 초기 약 2년은 사실상 무투자(현금) 기간입니다.',
        Colors.orange,
      ),
      (
        Icons.flash_on,
        '후행성 진입',
        'MA600을 이미 돌파한 종목만 매수하므로 강한 추세에 후행 진입합니다. 추세 초기 진입과 단기 변동성 손실은 ATR 스톱이 흡수합니다.',
        Colors.amber,
      ),
      (
        Icons.balance,
        '거래 승률 < 50%',
        '거래 승률 44.7%로 절반 이하지만 평균 수익(+2.87%)이 평균 손실보다 크기 때문에 누적 수익이 발생합니다. '
            '"손절은 빠르고 수익은 길게" 추세추종 전형의 분포입니다.',
        Colors.blue,
      ),
      (
        Icons.layers_outlined,
        '포지션 집중 가능성',
        'Top 25 동일비중이지만 강세장에서는 Tech 섹터 종목이 상위를 독점할 가능성이 높습니다. 섹터 분산은 별도 리스크 관리가 필요합니다.',
        Colors.purple,
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
          children: cautions.map((c) {
            final color = c.$4.shade600;
            final isLast = c == cautions.last;
            return Column(
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      padding: const EdgeInsets.all(7),
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(c.$1, color: color, size: 16),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(c.$2,
                              style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 13,
                                  color: color)),
                          const SizedBox(height: 4),
                          Text(c.$3,
                              style: const TextStyle(
                                  fontSize: 12,
                                  color: Colors.grey,
                                  height: 1.4)),
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
