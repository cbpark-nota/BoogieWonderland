import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../config/app_config.dart';
import '../models/portfolio_data.dart';
import '../providers/serverless_providers.dart';
// RebalanceMode, RebalanceSignal, selectedRebalanceModeProvider,
// rebalanceSignalProvider 는 serverless_providers.dart 에서 export

class PortfolioScreen extends ConsumerWidget {
  const PortfolioScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!AppConfig.isServerless) {
      return const _LegacyPortfolioPlaceholder();
    }

    final portfolioAsync = ref.watch(portfolioDataProvider);
    final signalAsync = ref.watch(rebalanceSignalProvider);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(portfolioDataProvider);
          ref.invalidate(rebalanceSignalProvider);
        },
        child: portfolioAsync.when(
          data: (portfolio) => portfolio.isEmpty
              ? _buildEmpty(context)
              : _buildPortfolio(context, portfolio, signalAsync.asData?.value),
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => _buildEmpty(context),
        ),
      ),
    );
  }

  Widget _buildEmpty(BuildContext context) {
    return ListView(
      children: [
        SizedBox(
          height: MediaQuery.of(context).size.height * 0.6,
          child: const Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.account_balance_wallet_outlined,
                    size: 64, color: Colors.grey),
                SizedBox(height: 16),
                Text('포트폴리오 데이터가 없습니다',
                    style: TextStyle(fontSize: 16, color: Colors.grey)),
                SizedBox(height: 8),
                Padding(
                  padding: EdgeInsets.symmetric(horizontal: 32),
                  child: Text(
                    'scripts/portfolio.xlsx를 작성 후\nGitHub Actions를 실행하세요.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 13, color: Colors.grey),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildPortfolio(
      BuildContext context, PortfolioData portfolio, RebalanceSignal? signal) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _SummaryCard(portfolio: portfolio),
        const SizedBox(height: 16),
        const _RebalanceModeSelector(),
        if (signal?.rebalanceDate != null) ...[
          const SizedBox(height: 4),
          Center(
            child: Text(
              '리밸런싱 기준일: ${signal!.rebalanceDate}',
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ),
        ],
        const SizedBox(height: 16),
        _WeightChart(holdings: portfolio.holdings),
        const SizedBox(height: 16),
        _HoldingsList(holdings: portfolio.holdings, signal: signal),
        const SizedBox(height: 8),
        if (portfolio.updatedAt.isNotEmpty)
          Center(
            child: Text(
              '업데이트: ${portfolio.updatedAt.substring(0, 10)}',
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ),
        const SizedBox(height: 80),
      ],
    );
  }
}

// ── 요약 카드 ─────────────────────────────────────────────────

class _SummaryCard extends StatefulWidget {
  const _SummaryCard({required this.portfolio});
  final PortfolioData portfolio;

  @override
  State<_SummaryCard> createState() => _SummaryCardState();
}

class _SummaryCardState extends State<_SummaryCard> {
  bool _showKrw = true; // true: 원화(₩), false: 달러($)

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final p = widget.portfolio;
    final isPositive = p.totalReturnPct >= 0;
    final returnColor = isPositive ? Colors.green : Colors.red;

    final invested = _showKrw ? p.totalInvestedKrw : p.totalInvestedUsd;
    final current = _showKrw ? p.totalCurrentKrw : p.totalCurrentUsd;

    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 헤더 + 통화 토글
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('포트폴리오 요약',
                    style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: cs.primary)),
                _CurrencyToggle(
                  showKrw: _showKrw,
                  onChanged: (v) => setState(() => _showKrw = v),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                    child: _MetricTile(
                        label: '총 투자금액',
                        value: _formatAmount(invested))),
                Expanded(
                    child: _MetricTile(
                        label: '현재 평가금액',
                        value: _formatAmount(current))),
                Expanded(
                    child: _MetricTile(
                        label: '전체 수익률',
                        value:
                            '${isPositive ? '+' : ''}${p.totalReturnPct.toStringAsFixed(2)}%',
                        valueColor: returnColor)),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              p.usdkrw != null
                  ? '환율 USD/KRW: ${p.usdkrw!.toStringAsFixed(0)}원'
                  : '환율 조회 실패',
              style: TextStyle(
                fontSize: 11,
                color: p.usdkrw != null ? Colors.grey : Colors.orange,
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatAmount(double v) {
    if (_showKrw) {
      if (v >= 100000000) return '₩${(v / 100000000).toStringAsFixed(1)}억';
      if (v >= 10000) return '₩${(v / 10000).toStringAsFixed(0)}만';
      return '₩${v.toStringAsFixed(0)}';
    } else {
      if (v >= 1000000) return '\$${(v / 1000000).toStringAsFixed(1)}M';
      if (v >= 1000) return '\$${(v / 1000).toStringAsFixed(1)}K';
      return '\$${v.toStringAsFixed(0)}';
    }
  }
}

class _CurrencyToggle extends StatelessWidget {
  const _CurrencyToggle({required this.showKrw, required this.onChanged});
  final bool showKrw;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _ToggleBtn(label: '₩', selected: showKrw, onTap: () => onChanged(true)),
        const SizedBox(width: 4),
        _ToggleBtn(label: '\$', selected: !showKrw, onTap: () => onChanged(false)),
      ],
    );
  }
}

class _ToggleBtn extends StatelessWidget {
  const _ToggleBtn({required this.label, required this.selected, required this.onTap});
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
        decoration: BoxDecoration(
          color: selected ? cs.primary : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: selected ? cs.primary : Colors.grey),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.bold,
            color: selected ? cs.onPrimary : Colors.grey,
          ),
        ),
      ),
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({required this.label, required this.value, this.valueColor});
  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Text(label,
            style: const TextStyle(fontSize: 11, color: Colors.grey),
            textAlign: TextAlign.center),
        const SizedBox(height: 4),
        Text(value,
            style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.bold,
                color: valueColor),
            textAlign: TextAlign.center),
      ],
    );
  }
}

// ── 비중 바 차트 ──────────────────────────────────────────────

class _WeightChart extends StatelessWidget {
  const _WeightChart({required this.holdings});
  final List<PortfolioHolding> holdings;

  static const _colors = [
    Color(0xFF2196F3), Color(0xFF4CAF50), Color(0xFFFF9800),
    Color(0xFF9C27B0), Color(0xFFF44336), Color(0xFF00BCD4),
    Color(0xFF795548), Color(0xFF607D8B), Color(0xFFE91E63),
    Color(0xFF3F51B5),
  ];

  @override
  Widget build(BuildContext context) {
    if (holdings.isEmpty) return const SizedBox.shrink();

    // weight 기준 내림차순 정렬
    final sorted = [...holdings]
      ..sort((a, b) => (b.weightPct ?? 0).compareTo(a.weightPct ?? 0));

    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('종목별 비중',
                style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.bold,
                    color: Theme.of(context).colorScheme.primary)),
            const SizedBox(height: 12),
            ...sorted.asMap().entries.map((entry) {
              final i = entry.key;
              final h = entry.value;
              final color = _colors[i % _colors.length];
              final pct = h.weightPct ?? 0;
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: [
                    SizedBox(
                      width: 80,
                      child: Text(
                        h.ticker.replaceAll('.KS', '').replaceAll('.KQ', ''),
                        style: const TextStyle(fontSize: 12),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: LayoutBuilder(
                        builder: (ctx, constraints) => Stack(
                          children: [
                            Container(
                              height: 18,
                              decoration: BoxDecoration(
                                color: Colors.grey.withAlpha(30),
                                borderRadius: BorderRadius.circular(4),
                              ),
                            ),
                            Container(
                              height: 18,
                              width: constraints.maxWidth * (pct / 100),
                              decoration: BoxDecoration(
                                color: color.withAlpha(200),
                                borderRadius: BorderRadius.circular(4),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    SizedBox(
                      width: 42,
                      child: Text(
                        '${pct.toStringAsFixed(1)}%',
                        style: const TextStyle(fontSize: 12),
                        textAlign: TextAlign.right,
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}

// ── 종목 리스트 ───────────────────────────────────────────────

class _HoldingsList extends StatelessWidget {
  const _HoldingsList({required this.holdings, this.signal});
  final List<PortfolioHolding> holdings;
  final RebalanceSignal? signal;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('보유 종목 (${holdings.length})',
            style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        ...holdings.map((h) => _HoldingCard(holding: h, signal: signal)),
      ],
    );
  }
}

class _HoldingCard extends StatelessWidget {
  const _HoldingCard({required this.holding, this.signal});
  final PortfolioHolding holding;
  final RebalanceSignal? signal;

  bool get _shouldSell => signal?.shouldSell(holding.ticker) ?? false;

  @override
  Widget build(BuildContext context) {
    final returnPct = holding.returnPct;
    final isPositive = (returnPct ?? 0) >= 0;
    final returnColor = returnPct == null
        ? Colors.grey
        : isPositive
            ? Colors.green
            : Colors.red;

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        child: Column(
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 스톱로스 경고 아이콘
                if (holding.stopTriggered)
                  const Padding(
                    padding: EdgeInsets.only(right: 6, top: 2),
                    child: Icon(Icons.warning_amber_rounded,
                        size: 18, color: Colors.red),
                  ),
                // 종목명 + 티커
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Text(holding.name,
                              style: const TextStyle(
                                  fontWeight: FontWeight.bold, fontSize: 14)),
                          const SizedBox(width: 6),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 5, vertical: 1),
                            decoration: BoxDecoration(
                              color: holding.isKr
                                  ? Colors.orange.withAlpha(40)
                                  : Colors.blue.withAlpha(40),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              holding.market,
                              style: TextStyle(
                                  fontSize: 10,
                                  color: holding.isKr
                                      ? Colors.orange
                                      : Colors.blue),
                            ),
                          ),
                        ],
                      ),
                      Text(
                        holding.ticker,
                        style:
                            const TextStyle(fontSize: 11, color: Colors.grey),
                      ),
                    ],
                  ),
                ),
                // 수익률
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      returnPct == null
                          ? '-'
                          : '${isPositive ? '+' : ''}${returnPct.toStringAsFixed(2)}%',
                      style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: returnColor),
                    ),
                    Text(
                      '비중 ${holding.weightPct?.toStringAsFixed(1) ?? '-'}%',
                      style:
                          const TextStyle(fontSize: 11, color: Colors.grey),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 6),
            // 가격 정보
            Row(
              children: [
                _PriceChip(
                  label: '진입가',
                  value: holding.formatPrice(holding.entryPrice),
                ),
                const SizedBox(width: 8),
                _PriceChip(
                  label: '현재가',
                  value: holding.formatPrice(holding.currentPrice),
                  highlight: true,
                  color: returnColor,
                ),
                const SizedBox(width: 8),
                _PriceChip(
                  label: '${holding.shares.toStringAsFixed(holding.shares == holding.shares.truncateToDouble() ? 0 : 2)}주',
                  value: holding.formatPrice(holding.currentValue),
                ),
                const Spacer(),
                if (holding.stopLoss != null)
                  _PriceChip(
                    label: 'SL',
                    value: holding.formatPrice(holding.stopLoss),
                    color: Colors.red,
                  ),
              ],
            ),
            if (_shouldSell)
              Container(
                margin: const EdgeInsets.only(top: 6),
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.orange.withAlpha(20),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: Colors.orange.withAlpha(80)),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.swap_horiz_rounded,
                        size: 14, color: Colors.orange),
                    SizedBox(width: 4),
                    Text('매도 검토',
                        style: TextStyle(fontSize: 12, color: Colors.orange)),
                  ],
                ),
              ),
            if (holding.stopTriggered)
              Container(
                margin: const EdgeInsets.only(top: 6),
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.red.withAlpha(20),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: Colors.red.withAlpha(60)),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.warning_amber_rounded,
                        size: 14, color: Colors.red),
                    SizedBox(width: 4),
                    Text('스톱로스 이탈',
                        style: TextStyle(fontSize: 12, color: Colors.red)),
                  ],
                ),
              ),
            if (holding.atrStop != null) ...[
              const SizedBox(height: 6),
              _AtrStopRow(holding: holding),
            ],
            if (holding.memo.isNotEmpty)
              Align(
                alignment: Alignment.centerLeft,
                child: Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    holding.memo,
                    style:
                        const TextStyle(fontSize: 11, color: Colors.grey),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _PriceChip extends StatelessWidget {
  const _PriceChip(
      {required this.label, required this.value, this.highlight = false, this.color});
  final String label;
  final String value;
  final bool highlight;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: const TextStyle(fontSize: 10, color: Colors.grey)),
        Text(value,
            style: TextStyle(
                fontSize: 12,
                fontWeight:
                    highlight ? FontWeight.bold : FontWeight.normal,
                color: color)),
      ],
    );
  }
}

// ── ATR 스톱 행 ───────────────────────────────────────────────

class _AtrStopRow extends StatelessWidget {
  const _AtrStopRow({required this.holding});
  final PortfolioHolding holding;

  @override
  Widget build(BuildContext context) {
    final atrStop = holding.atrStop!;
    final distPct = holding.atrStopDistPct;
    final triggered = holding.atrStopTriggered;

    Color statusColor;
    String statusLabel;
    IconData statusIcon;
    if (triggered || (distPct != null && distPct <= 0)) {
      statusColor = Colors.red;
      statusLabel = '추세 이탈';
      statusIcon = Icons.trending_down;
    } else if (distPct != null && distPct <= 3) {
      statusColor = Colors.red;
      statusLabel = '위험 ${distPct.toStringAsFixed(1)}%';
      statusIcon = Icons.warning_amber_rounded;
    } else if (distPct != null && distPct <= 7) {
      statusColor = Colors.orange;
      statusLabel = '주의 ${distPct.toStringAsFixed(1)}%';
      statusIcon = Icons.info_outline;
    } else {
      statusColor = Colors.green;
      statusLabel = distPct != null ? '안전 ${distPct.toStringAsFixed(1)}%' : '안전';
      statusIcon = Icons.check_circle_outline;
    }

    // 0~20% 범위로 진행바 정규화
    final barFill = distPct == null
        ? 0.0
        : (distPct.clamp(0.0, 20.0) / 20.0);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: statusColor.withAlpha(12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: statusColor.withAlpha(50)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(statusIcon, size: 13, color: statusColor),
              const SizedBox(width: 4),
              Text(
                'ATR 스톱 (균형형×2.0)',
                style: TextStyle(
                    fontSize: 11,
                    color: statusColor,
                    fontWeight: FontWeight.w600),
              ),
              const Spacer(),
              Text(
                holding.formatPrice(atrStop),
                style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: statusColor),
              ),
              const SizedBox(width: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: statusColor.withAlpha(30),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  statusLabel,
                  style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      color: statusColor),
                ),
              ),
            ],
          ),
          const SizedBox(height: 5),
          LayoutBuilder(
            builder: (ctx, constraints) => Stack(
              children: [
                Container(
                  height: 4,
                  width: constraints.maxWidth,
                  decoration: BoxDecoration(
                    color: Colors.grey.withAlpha(40),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                Container(
                  height: 4,
                  width: constraints.maxWidth * barFill,
                  decoration: BoxDecoration(
                    color: statusColor.withAlpha(180),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 3),
          Text(
            '현재가 ${holding.formatPrice(holding.currentPrice)}  →  스톱 ${holding.formatPrice(atrStop)}  │  20일 고점 기준',
            style: const TextStyle(fontSize: 10, color: Colors.grey),
          ),
        ],
      ),
    );
  }
}

// ── 리밸런싱 주기 선택기 ───────────────────────────────────────

class _RebalanceModeSelector extends ConsumerWidget {
  const _RebalanceModeSelector();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = ref.watch(selectedRebalanceModeProvider);
    final cs = Theme.of(context).colorScheme;

    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('리밸런싱 주기',
                style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.bold,
                    color: cs.primary)),
            const SizedBox(height: 8),
            Row(
              children: RebalanceMode.values.map((mode) {
                final isSelected = mode == selected;
                final color = switch (mode) {
                  RebalanceMode.aggressive => Colors.red.shade600,
                  RebalanceMode.balanced => Colors.blue.shade600,
                  RebalanceMode.conservative => Colors.amber.shade700,
                };
                return Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 2),
                    child: GestureDetector(
                      onTap: () => ref
                          .read(selectedRebalanceModeProvider.notifier)
                          .state = mode,
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 150),
                        padding: const EdgeInsets.symmetric(vertical: 7),
                        decoration: BoxDecoration(
                          color: isSelected
                              ? color.withAlpha(220)
                              : Colors.transparent,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                            color: isSelected ? color : Colors.grey.withAlpha(80),
                          ),
                        ),
                        child: Column(
                          children: [
                            Text(
                              mode.label,
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.bold,
                                color: isSelected ? Colors.white : null,
                              ),
                            ),
                            Text(
                              mode.description,
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontSize: 10,
                                color: isSelected
                                    ? Colors.white.withAlpha(200)
                                    : Colors.grey,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
          ],
        ),
      ),
    );
  }
}

// ── 비서버리스 모드 플레이스홀더 ──────────────────────────────

class _LegacyPortfolioPlaceholder extends StatelessWidget {
  const _LegacyPortfolioPlaceholder();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.account_balance_wallet_outlined,
              size: 64, color: Colors.grey),
          SizedBox(height: 16),
          Text('포트폴리오',
              style: TextStyle(fontSize: 16, color: Colors.grey)),
        ],
      ),
    );
  }
}
