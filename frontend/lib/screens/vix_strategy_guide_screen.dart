import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

class VixStrategyGuideScreen extends StatelessWidget {
  const VixStrategyGuideScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _SectionHeader(title: 'VIX 매매 전략 개요', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _OverviewCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: 'ETF 사양', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _EtfSpecCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: 'VIX 선물 지수 구조', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _FuturesIndexCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: 'VIX 현물 → 선물 지수 변환', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _SpotToFuturesCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '경로 의존성', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _PathDependencyCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '매매 전략', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _TradingStrategyCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '백테스트 결과 (2020~2026)', colorScheme: colorScheme),
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
  final Color? valueColor;
  final bool isLast;

  const _InfoRow({
    required this.label,
    required this.value,
    this.valueColor,
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
                  color: valueColor ?? colorScheme.onSurface,
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

// ── 1. 전략 개요 ───────────────────────────────────────────────

class _OverviewCard extends StatelessWidget {
  const _OverviewCard();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    const accentColor = Color(0xFFE53935);

    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.show_chart, color: accentColor, size: 18),
                const SizedBox(width: 8),
                Text(
                  '핵심 아이디어: VIX 급등 → ETF 저가 매수',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: accentColor,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'VIX(공포지수)는 강한 평균 회귀 성질을 지닙니다. VIX가 급등하면 '
              'SVXY/SVIX ETF 가격이 급락하는데, 이때 미리 낮은 가격에 지정가 매수 '
              '주문을 배치해두고, VIX가 정상화되면 선물 콘탱고 구조 덕분에 '
              'ETF가 빠르게 회복하는 원리를 이용합니다.',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _Chip(label: 'VIX 급등 시 진입', color: accentColor),
                _Chip(label: '지정가 계단식 매수', color: AppColors.warningMid),
                _Chip(label: 'VIX 20↓ 시 매도', color: AppColors.priceUpMid),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ── 2. ETF 사양 ────────────────────────────────────────────────

class _EtfSpecCard extends StatelessWidget {
  const _EtfSpecCard();

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
            _EtfBlock(
              ticker: 'SVXY',
              name: 'ProShares Short VIX Short-Term Futures',
              color: AppColors.infoMid,
              items: const [
                ('추종 배율', '-0.5x (일간)'),
                ('추종 지수', 'SPVXSP'),
                ('이론가 수식', 'NAV × (1 - 0.5 × R)'),
                ('비용비율', '0.95%'),
              ],
            ),
            const Divider(height: 24),
            _EtfBlock(
              ticker: 'SVIX',
              name: 'Volatility Shares -1x Short VIX Futures',
              color: AppColors.brandAccentStrong,
              items: const [
                ('추종 배율', '-1x (일간)'),
                ('추종 지수', 'SHORTVOL'),
                ('이론가 수식', 'NAV × (1 - R)'),
                ('비용비율', '1.35%'),
                ('NAV 산정', 'TWAP 15분'),
              ],
            ),
            const Divider(height: 24),
            const _AllocationRow(),
          ],
        ),
      ),
    );
  }
}

class _EtfBlock extends StatelessWidget {
  final String ticker;
  final String name;
  final Color color;
  final List<(String, String)> items;

  const _EtfBlock({
    required this.ticker,
    required this.name,
    required this.color,
    required this.items,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                ticker,
                style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 13),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                name,
                style: TextStyle(fontSize: 11, color: colorScheme.onSurfaceVariant),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        ...items.map((item) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(item.$1,
                      style: TextStyle(
                          fontSize: 12, color: colorScheme.onSurfaceVariant)),
                  Text(item.$2,
                      style: const TextStyle(
                          fontSize: 12, fontWeight: FontWeight.bold)),
                ],
              ),
            )),
      ],
    );
  }
}

class _AllocationRow extends StatelessWidget {
  const _AllocationRow();

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const Icon(Icons.recommend, size: 16, color: AppColors.priceUp),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            '권장 배분: SVXY 60% + SVIX 40%  |  예비자금 30% 별도 보유',
            style: TextStyle(
              fontSize: 12,
              color: AppColors.priceUpStrong,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
      ],
    );
  }
}

// ── 3. VIX 선물 지수 구조 ──────────────────────────────────────

class _FuturesIndexCard extends StatelessWidget {
  const _FuturesIndexCard();

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
            _HighlightBox(
              color: AppColors.rankGold,
              child: Text(
                'SPVXSP / SHORTVOL은 VIX 선물 "지수"이지, 선물 자체가 아닙니다',
                style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: AppColors.amberDeep),
              ),
            ),
            const SizedBox(height: 12),
            const _InfoRow(label: '시작값 (2005-12-20)', value: '100,000'),
            const _InfoRow(label: 'SPVXSP 현재 (2026-04)', value: '≈ 6,162'),
            const _InfoRow(label: 'SHORTVOL 현재 (2026-04)', value: '≈ 1,285'),
            const _InfoRow(
              label: 'VIX 절대값과 비교',
              value: '직접 비교 불가',
              valueColor: AppColors.priceDown,
            ),
            const _InfoRow(
              label: '이론가 계산 입력값',
              value: '일간 변동률(R)',
              isLast: true,
            ),
            const SizedBox(height: 12),
            Text(
              '롤링 구조: 1개월물 + 2개월물 VIX 선물을 매일 롤오버 → '
              '항상 만기까지 약 1개월 유지하는 연속 지수. '
              'contango 환경에서 장기적으로 지수값 하락 → SVXY/SVIX의 구조적 수익 원천.',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 12),
            _ExampleBox(
              text: '예시: SPVXSP 어제 6,000 → 오늘 6,162\n'
                  'R = +2.7%\n'
                  'SVXY 이론가 = 전일 NAV × (1 - 0.5 × 0.027) = 전일 NAV × 0.9865',
            ),
          ],
        ),
      ),
    );
  }
}

// ── 4. VIX 현물 → 선물 지수 변환 ─────────────────────────────

class _SpotToFuturesCard extends StatelessWidget {
  const _SpotToFuturesCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final theme = Theme.of(context);

    const rows = [
      ('VIX 현물 +10%', 'SPVXSP +5%~+7%'),
      ('VIX 현물 +50%', 'SPVXSP +25%~+35%'),
      ('VIX 현물 +100%', 'SPVXSP +50%~+70%'),
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
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'VIX 선물은 만기에 따라 현물보다 둔하게 반응합니다.\n'
              '경험적으로 현물 변동의 약 50~70%만 선물 지수에 반영됩니다.',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 12),
            ...rows.asMap().entries.map((e) => _InfoRow(
                  label: e.value.$1,
                  value: e.value.$2,
                  valueColor: AppColors.warningStrong,
                  isLast: e.key == rows.length - 1,
                )),
            const SizedBox(height: 12),
            _HighlightBox(
              color: AppColors.infoMid,
              child: Text(
                '앱의 VIX 매매 탭은 VIX 현물 변동률을 R로 사용합니다 (근사값).\n'
                '정확한 계산에는 SPVXSP 실제 변동률이 필요합니다.',
                style: const TextStyle(fontSize: 11, color: Colors.white),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── 5. 경로 의존성 ────────────────────────────────────────────

class _PathDependencyCard extends StatelessWidget {
  const _PathDependencyCard();

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
              '일간 리밸런싱으로 인해 같은 누적 변동이라도 경로에 따라 이론가가 달라집니다.',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 12),
            Text('VIX 선물 지수 2일간 총 +44% 상승 (SVXY 기준)',
                style: const TextStyle(
                    fontSize: 12, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            _PathRow(
              path: '경로 A: +20% → +20%',
              result: '\$37.30',
              sub: '분산 급등',
              color: AppColors.warningMid,
            ),
            const SizedBox(height: 6),
            _PathRow(
              path: '경로 B: +40% → +2.86%',
              result: '\$36.31',
              sub: '집중 급등',
              color: AppColors.priceUpMid,
            ),
            const SizedBox(height: 12),
            _HighlightBox(
              color: AppColors.priceUpMid,
              child: const Text(
                '단일일 급등이 매수자에게 가장 유리한 가격(하한) 제공\n'
                '→ 지정가는 단일일 이론가 기준으로 설정',
                style: TextStyle(fontSize: 11, color: Colors.white),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PathRow extends StatelessWidget {
  final String path;
  final String result;
  final String sub;
  final Color color;

  const _PathRow({
    required this.path,
    required this.result,
    required this.sub,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(path, style: const TextStyle(fontSize: 12)),
        ),
        Text(result,
            style: TextStyle(
                fontSize: 13, fontWeight: FontWeight.bold, color: color)),
        const SizedBox(width: 6),
        Text(sub,
            style: TextStyle(
                fontSize: 10, color: color.withValues(alpha: 0.7))),
      ],
    );
  }
}

// ── 6. 매매 전략 ──────────────────────────────────────────────

class _TradingStrategyCard extends StatelessWidget {
  const _TradingStrategyCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    const ladderRows = [
      ('+20%', '~24', '10%'),
      ('+30%', '~26', '10%'),
      ('+40%', '~28', '15%'),
      ('+50%', '~30', '15%'),
      ('+60%', '~32', '15%'),
      ('+70%', '~34', '15%'),
      ('+80%', '~36', '10%'),
      ('+90%', '~38', '5%'),
      ('+100%', '~40', '5%'),
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
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('계단식 지정가 매수',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
            const SizedBox(height: 8),
            Table(
              border: TableBorder.all(
                  color: AppColors.divider, width: 0.5,
                  borderRadius: BorderRadius.circular(4)),
              columnWidths: const {
                0: FlexColumnWidth(2),
                1: FlexColumnWidth(2),
                2: FlexColumnWidth(2),
              },
              children: [
                TableRow(
                  decoration: BoxDecoration(
                      color: colorScheme.primary.withValues(alpha: 0.1)),
                  children: const [
                    _TableCell('선물 지수 변동', isHeader: true),
                    _TableCell('VIX 수준 (근사)', isHeader: true),
                    _TableCell('매수 비중', isHeader: true),
                  ],
                ),
                ...ladderRows.map((r) => TableRow(
                      children: [
                        _TableCell(r.$1),
                        _TableCell(r.$2),
                        _TableCell(r.$3,
                            color: (r.$3 == '15%')
                                ? AppColors.infoStrong
                                : null),
                      ],
                    )),
              ],
            ),
            const SizedBox(height: 16),
            const Text('매도 조건',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
            const SizedBox(height: 8),
            const _ExitRow(
                icon: Icons.looks_one_outlined,
                label: '1단계',
                desc: 'VIX 임계값 하회 시 보유량 1/3 매도',
                color: AppColors.priceUp),
            const SizedBox(height: 6),
            const _ExitRow(
                icon: Icons.looks_two_outlined,
                label: '2단계',
                desc: 'VIX 평균 복귀 시 1/3 추가 매도',
                color: AppColors.info),
            const SizedBox(height: 6),
            const _ExitRow(
                icon: Icons.looks_3_outlined,
                label: '3단계',
                desc: '나머지 1/3은 콘탱고 수익 목적 보유',
                color: AppColors.brandAccent),
            const SizedBox(height: 6),
            const _ExitRow(
                icon: Icons.block,
                label: '손절',
                desc: '투입 원금 대비 -50% 시 전량 매도',
                color: AppColors.priceDown),
            const SizedBox(height: 12),
            _HighlightBox(
              color: AppColors.indigo,
              child: const Text(
                '매도 기준: VIX 20 이하 회복 시 단계적 청산 시작',
                style: TextStyle(fontSize: 12, color: Colors.white, fontWeight: FontWeight.bold),
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
  final Color? color;

  const _TableCell(this.text, {this.isHeader = false, this.color});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 6),
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: 11,
          fontWeight: isHeader ? FontWeight.bold : FontWeight.normal,
          color: color,
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
    final c = color is MaterialColor ? (color as MaterialColor).shade600 : color;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 16, color: c),
        const SizedBox(width: 8),
        Text('$label: ',
            style: TextStyle(
                fontSize: 12, fontWeight: FontWeight.bold, color: c)),
        Expanded(
            child: Text(desc,
                style: const TextStyle(fontSize: 12, color: AppColors.mutedText))),
      ],
    );
  }
}

// ── 7. 백테스트 결과 ──────────────────────────────────────────

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
                Icon(Icons.warning_amber_rounded,
                    size: 15, color: AppColors.rankGold),
                const SizedBox(width: 6),
                Text(
                  '거래 횟수 극도로 적음 — 통계적 유의미성 낮음',
                  style: TextStyle(
                      fontSize: 11,
                      color: AppColors.rankGold,
                      fontStyle: FontStyle.italic),
                ),
              ],
            ),
            const SizedBox(height: 12),
            const _InfoRow(label: '테스트 기간', value: '2020-01 ~ 2026-04'),
            const _InfoRow(label: 'SVXY 공격적 CAGR', value: '5.7%',
                valueColor: AppColors.priceUp),
            const _InfoRow(label: 'SVXY 공격적 Sharpe', value: '0.94',
                valueColor: AppColors.info),
            const _InfoRow(label: 'SVIX 빠른매도 Sharpe', value: '0.73',
                valueColor: AppColors.info),
            const _InfoRow(
              label: 'SVXY 최대 낙폭 (MDD)',
              value: '-49.3% (COVID)',
              valueColor: AppColors.priceDown,
              isLast: true,
            ),
            const SizedBox(height: 12),
            Text(
              'SVIX가 SVXY보다 전반적으로 우수 (단일 레버리지 효과).\n'
              '거래 사례 부족으로 장기적 데이터 축적이 필요합니다.',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 14),
            const Text('역사적 주요 VIX 급등 사례',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
            const SizedBox(height: 8),
            const _HistoricalRow('COVID-19', '2020-03', '82.69', '수일간 급등, 역대 최고'),
            const Divider(height: 12),
            const _HistoricalRow('Volmageddon', '2018-02-05', '37.32', '단일일 급등, XIV 사실상 소멸'),
            const Divider(height: 12),
            const _HistoricalRow('엔캐리 청산', '2024-08-05', '65.73', '급등 후 빠른 회복'),
            const Divider(height: 12),
            const _HistoricalRow('우크라이나', '2022-03', '36.45', '수주간 점진적 상승'),
          ],
        ),
      ),
    );
  }
}

class _HistoricalRow extends StatelessWidget {
  final String event;
  final String date;
  final String vixHigh;
  final String note;

  const _HistoricalRow(this.event, this.date, this.vixHigh, this.note);

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 90,
          child: Text(event,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
        ),
        const SizedBox(width: 6),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('$date  VIX $vixHigh',
                style: const TextStyle(fontSize: 11, color: AppColors.priceDown)),
            Text(note,
                style: const TextStyle(fontSize: 11, color: AppColors.mutedText)),
          ],
        ),
      ],
    );
  }
}

// ── 8. 주의사항 ───────────────────────────────────────────────

class _CautionsCard extends StatelessWidget {
  const _CautionsCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    const cautions = [
      (
        Icons.history,
        'SVXY 이력 변경 (2018-02-27)',
        '-1x → -0.5x 배율 변경 + 액면병합. 2018년 이전 데이터 직접 연결 불가. 백테스트는 2018-03 이후만 권장.',
        AppColors.warning,
      ),
      (
        Icons.data_usage,
        'SPVXSP/SHORTVOL 데이터 미지원',
        'yfinance에서 SPVXSP/SHORTVOL 실시간 데이터를 제공하지 않음. 앱은 VIX 현물 변동률을 근사값으로 사용.',
        AppColors.info,
      ),
      (
        Icons.compare_arrows,
        'VIX 현물 vs 선물 지수 괴리',
        'VIX 현물 변동 ≠ SPVXSP 변동. 선물 지수는 현물의 50~70% 수준으로 반응. 이론가 테이블은 근사값.',
        AppColors.brandAccent,
      ),
      (
        Icons.dangerous,
        'SVIX 전멸 리스크',
        'VIX 선물 지수 단일일 +100% 급등 시 이론상 NAV = 0. 2018년 XIV 단일일 -96% 사례 실존. SVIX 투입 금액은 전액 손실 감수 가능한 수준으로 제한.',
        AppColors.priceDown,
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
            final color = c.$4 is MaterialColor
                ? (c.$4 as MaterialColor).shade600
                : c.$4 as Color;
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

// ── 공통 헬퍼 위젯 ────────────────────────────────────────────

class _Chip extends StatelessWidget {
  final String label;
  final Color color;

  const _Chip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: color),
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

class _ExampleBox extends StatelessWidget {
  final String text;

  const _ExampleBox({required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppColors.subtleBackground,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.divider),
      ),
      child: Text(text,
          style: const TextStyle(
              fontSize: 11, fontFamily: 'monospace', color: Colors.black87)),
    );
  }
}
