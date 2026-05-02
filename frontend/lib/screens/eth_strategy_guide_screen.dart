import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

class EthStrategyGuideScreen extends StatelessWidget {
  const EthStrategyGuideScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _SectionHeader(title: 'ETH V10 전략 개요', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _OverviewCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '핵심 로직 (V10 4시간봉)', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _LogicCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: 'BTC ↔ ETH 상관관계 분석', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _CorrelationCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '매매 빈도 / 보유 기간', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _FrequencyCard(),
        const SizedBox(height: 24),
        _SectionHeader(title: '매도 조건', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _ExitConditionsCard(),
        const SizedBox(height: 24),
        _SectionHeader(
          title: '백테스트 결과 (2021~2026)',
          colorScheme: colorScheme,
        ),
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

const _ethColor = Color(0xFF627EEA);

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
              decoration: BoxDecoration(
                color: _ethColor,
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
              color: _ethColor.withValues(alpha: 0.15),
              borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                const Icon(Icons.diamond_outlined, color: _ethColor, size: 22),
                const SizedBox(width: 10),
                Text(
                  'Ethereum V10 — BTC 추세 기반',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: _ethColor,
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
                        color: _ethColor, size: 18),
                    const SizedBox(width: 8),
                    Text(
                      '핵심 아이디어: BTC 신호의 ETH 카피 트레이딩',
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: _ethColor,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  'BTC V10 알고리즘이 같은 봉(t=0)에서 매수 신호를 내면 ETH도 동일하게 진입합니다. '
                  'BTC와 ETH는 4시간봉 기준 lag 0봉 (즉시) 동조하지만, BTC 추세가 ETH보다 '
                  '안정적이고 통계적으로 ETH를 예측합니다 (Granger). ETH 단독 신호는 변동성으로 인해 '
                  'whipsaw 손실이 누적되는 반면, BTC 신호로 게이팅하면 ETH의 변동성 증폭 효과를 '
                  '수익으로 활용할 수 있습니다.',
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
                    _Chip(label: '타임프레임', value: '4시간봉', color: _ethColor),
                    _Chip(label: '방향', value: '롱온리', color: _ethColor),
                    _Chip(label: '신호 소스', value: 'BTC V10', color: _ethColor),
                    _Chip(label: '체결 자산', value: 'ETH/USDT', color: _ethColor),
                  ],
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
              'BTC 4시간봉 데이터에 V10 알고리즘을 실행하고, 같은 봉에서 ETH/USDT에 동일 포지션을 적용합니다.',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colorScheme.onSurfaceVariant, height: 1.5),
            ),
            const SizedBox(height: 12),
            const _BulletRow('Squeeze Momentum 지표 기반 모멘텀 감지'),
            const _BulletRow('Bollinger Band Break 신호 진입 트리거'),
            const _BulletRow('EMA 크로스 필터 (추세 방향 확인)'),
            const _BulletRow('RSI Pullback + 다중 시간프레임 정합성 확인'),
            const _BulletRow('Bull / Bear / Neutral 레짐 자동 판별 (BTC bull regime gating)'),
            const _BulletRow('레짐별 ATR 승수·포지션 크기 동적 전환 (적응형 SL)'),
            const _BulletRow('주간 +1% 목표 기반 복합 최적화 (V10)'),
            const SizedBox(height: 12),
            _HighlightBox(
              color: _ethColor,
              child: const Text(
                'B안 = BTC strategy 신호의 ETH 카피 트레이딩\n'
                '진입 조건은 BTC 가격, 체결과 P&L 계산은 ETH 가격',
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

// ── 3. BTC↔ETH 상관관계 ───────────────────────────────────────

class _CorrelationCard extends StatelessWidget {
  const _CorrelationCard();

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
              '4시간봉 11,656봉(2021-01~2026-04) 분석 결과',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 12),
            const _InfoRow(label: '동시 상관 (전체)', value: '0.837'),
            const _InfoRow(label: 'BTC Bull 구간', value: '0.793'),
            const _InfoRow(label: 'BTC Bear 구간', value: '0.861'),
            const _InfoRow(
              label: 'CCF 최적 lag',
              value: '0봉 (lag 트레이딩 무의미)',
              valueColor: AppColors.warning,
            ),
            const _InfoRow(
              label: 'Granger BTC→ETH',
              value: 'p=0.0003 (유의)',
              valueColor: AppColors.priceUp,
            ),
            const _InfoRow(
              label: 'Rolling 365d corr',
              value: '평균 0.841',
              isLast: true,
            ),
            const SizedBox(height: 12),
            _HighlightBox(
              color: AppColors.infoMid,
              child: const Text(
                'BTC와 ETH는 즉시(lag=0) 동조하지만, BTC의 과거 5~12봉 정보가 ETH 미래를 통계적으로 예측합니다.\n'
                '→ BTC 추세를 ETH 매매의 게이트로 사용',
                style: TextStyle(fontSize: 11, color: Colors.white, height: 1.4),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── 4. 매매 빈도 ──────────────────────────────────────────────

class _FrequencyCard extends StatelessWidget {
  const _FrequencyCard();

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
          children: const [
            _InfoRow(label: '타임프레임', value: '4시간봉'),
            _InfoRow(label: '연 평균 거래 횟수', value: '약 22회'),
            _InfoRow(label: '평균 보유 기간', value: '약 5.9일 (≈ 35봉)'),
            _InfoRow(
              label: '평균 보유 봉 수',
              value: '14~20봉 사이 (V8~V10)',
              isLast: true,
            ),
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
              label: '트레일링 SL',
              desc: 'BTC 가격 / ATR(14) 기반 적응형 스톱 (레짐별 승수 동적 전환)',
              color: AppColors.priceDown,
            ),
            SizedBox(height: 8),
            _ExitRow(
              icon: Icons.flag_outlined,
              label: 'TP (이익 실현)',
              desc: 'BTC 가격이 TP 레벨 도달 시 청산 (V10 = 주간 +1% 목표 기반)',
              color: AppColors.priceUp,
            ),
            SizedBox(height: 8),
            _ExitRow(
              icon: Icons.timer_outlined,
              label: 'max_hold',
              desc: '최대 보유 봉 수 초과 시 강제 청산 (whipsaw 보호)',
              color: AppColors.info,
            ),
            SizedBox(height: 8),
            _ExitRow(
              icon: Icons.layers_outlined,
              label: '레짐 전환',
              desc: 'BTC bull regime 이탈 시 신규 진입 차단, 보유분은 SL/TP 따름',
              color: AppColors.brandAccent,
            ),
            SizedBox(height: 12),
            Text(
              '※ 매도 조건은 모두 BTC 가격/ATR 기준으로 트리거되며, 체결은 ETH 가격에 적용됩니다.',
              style: TextStyle(
                fontSize: 11,
                color: AppColors.mutedText,
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
            style: const TextStyle(fontSize: 12, color: AppColors.mutedText, height: 1.4),
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
                Icon(Icons.info_outline, size: 14, color: AppColors.infoStrong),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'Binance USDT, 수수료 RT 0.1%, 2021-01-01 ~ 2026-04-27',
                    style: TextStyle(
                      fontSize: 11,
                      color: AppColors.infoStrong,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            const Text(
              'B안 (BTC 신호 → ETH 카피) 핵심 결과',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
            ),
            const SizedBox(height: 8),
            Table(
              border: TableBorder.all(
                color: AppColors.divider,
                width: 0.5,
                borderRadius: BorderRadius.circular(4),
              ),
              columnWidths: const {
                0: FlexColumnWidth(1.4),
                1: FlexColumnWidth(1.6),
                2: FlexColumnWidth(1.6),
                3: FlexColumnWidth(1.4),
              },
              children: [
                TableRow(
                  decoration: BoxDecoration(
                    color: colorScheme.primary.withValues(alpha: 0.1),
                  ),
                  children: const [
                    _TableCell('버전', isHeader: true),
                    _TableCell('CAGR', isHeader: true),
                    _TableCell('MDD', isHeader: true),
                    _TableCell('Sharpe', isHeader: true),
                  ],
                ),
                const TableRow(children: [
                  _TableCell('V10 ★'),
                  _TableCell('+45.0%', color: AppColors.priceUp),
                  _TableCell('-33.2%', color: AppColors.priceDown),
                  _TableCell('1.03'),
                ]),
                const TableRow(children: [
                  _TableCell('V9'),
                  _TableCell('+40.6%', color: AppColors.priceUp),
                  _TableCell('-31.0%', color: AppColors.priceDown),
                  _TableCell('0.98'),
                ]),
                const TableRow(children: [
                  _TableCell('V8'),
                  _TableCell('+38.2%', color: AppColors.priceUp),
                  _TableCell('-35.5%', color: AppColors.priceDown),
                  _TableCell('0.95'),
                ]),
              ],
            ),
            const SizedBox(height: 16),
            const Text(
              'Buy & Hold 벤치마크 비교',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
            ),
            const SizedBox(height: 8),
            const _InfoRow(label: 'ETH B&H CAGR / MDD', value: '+23.8% / -81.1%'),
            const _InfoRow(label: 'BTC B&H CAGR / MDD', value: '+20.2% / -77.0%'),
            const _InfoRow(
              label: 'B안 V10 vs ETH B&H',
              value: 'CAGR ≈2배, MDD <1/2',
              valueColor: AppColors.priceUp,
              isLast: true,
            ),
            const SizedBox(height: 12),
            const Text(
              'A안 vs B안 차이 (V10 기준)',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
            ),
            const SizedBox(height: 8),
            Text(
              'A안 (ETH 단독 신호): CAGR +23.4%, MDD -49.6%, 샤프 0.61\n'
              'B안 (BTC 신호 적용): CAGR +45.0%, MDD -33.2%, 샤프 1.03\n'
              '→ 모든 V1~V10에서 B안의 CAGR이 동일하거나 높음. ETH 단독 신호의 whipsaw 손실을 BTC 추세가 흡수.',
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

// ── 7. 주의사항 ───────────────────────────────────────────────

class _CautionsCard extends StatelessWidget {
  const _CautionsCard();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    const cautions = [
      (
        Icons.show_chart,
        '높은 변동성',
        'ETH 4h 수익률 표준편차는 BTC의 약 1.2~1.4배. BTC 신호의 변동성을 증폭하므로 수익뿐 아니라 MDD도 함께 커집니다.',
        AppColors.priceDown,
      ),
      (
        Icons.access_time,
        '청산 지연 가능성',
        'SL/TP 트리거가 BTC 가격/ATR 기준이므로, BTC가 횡보하고 ETH만 급변하는 구간에서는 청산이 늦어질 수 있습니다.',
        AppColors.warning,
      ),
      (
        Icons.history,
        '제한된 백테스트 기간',
        '2021~2026 약 5년, 1~2 사이클만 포함. 다음 사이클에서 동일 성과를 보장하지 않습니다.',
        AppColors.amber,
      ),
      (
        Icons.science_outlined,
        'Hindsight 최적화 위험',
        'V10은 V9에서 파라미터를 완화한 구조. 과적합 가능성을 내재하므로 실전에서는 보수적으로 진입 비중을 결정해야 합니다.',
        AppColors.info,
      ),
      (
        Icons.account_balance,
        '슬리피지 / 수수료 가정',
        'RT 0.1% (Binance VIP 0~3 수준). 시장가 / 대량 주문 시 추가 비용이 발생할 수 있습니다.',
        AppColors.brandAccent,
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
                                  color: AppColors.mutedText,
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

// ── 공통 헬퍼 위젯 ────────────────────────────────────────────

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
