import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/vix_etf_data.dart';
import '../providers/vix_etf_provider.dart';

// VIX 시나리오 테이블 목표 레벨
const _kVixScenarios = [20.0, 25.0, 30.0, 35.0, 40.0, 50.0, 60.0, 80.0];

class VixEtfCalculatorScreen extends ConsumerWidget {
  const VixEtfCalculatorScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(vixEtfProvider),
        child: ref.watch(vixEtfProvider).when(
          data: (data) {
            if (data == null) return _buildError('데이터를 불러올 수 없습니다.');
            return _VixContent(data: data);
          },
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => _buildError('$e'),
        ),
      ),
    );
  }

  Widget _buildError(String msg) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, size: 48, color: Colors.grey),
          const SizedBox(height: 8),
          Text(
            '데이터 로드 실패\n$msg',
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.grey),
          ),
        ],
      ),
    );
  }
}

// ── 메인 콘텐츠 ─────────────────────────────────────────────

class _VixContent extends ConsumerStatefulWidget {
  final VixEtfData data;

  const _VixContent({required this.data});

  @override
  ConsumerState<_VixContent> createState() => _VixContentState();
}

class _VixContentState extends ConsumerState<_VixContent> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final targetVix = ref.watch(targetVixProvider);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _CurrentPriceCard(data: widget.data),
        const SizedBox(height: 16),
        _TargetInputCard(
          controller: _controller,
          onChanged: (val) {
            final parsed = double.tryParse(val);
            ref.read(targetVixProvider.notifier).set(parsed);
          },
          data: widget.data,
          targetVix: targetVix,
        ),
        const SizedBox(height: 16),
        _ScenarioTable(data: widget.data),
      ],
    );
  }
}

// ── 현재가 카드 ─────────────────────────────────────────────

class _CurrentPriceCard extends StatelessWidget {
  final VixEtfData data;

  const _CurrentPriceCard({required this.data});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Card(
      color: colorScheme.primaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.show_chart,
                    color: colorScheme.onPrimaryContainer, size: 18),
                const SizedBox(width: 6),
                Text(
                  'VIX ETF 현재가',
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    color: colorScheme.onPrimaryContainer,
                  ),
                ),
                const Spacer(),
                Text(
                  _formatDate(data.runDate),
                  style: TextStyle(
                    fontSize: 11,
                    color: colorScheme.onPrimaryContainer.withAlpha(180),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _priceItem('VIX', data.vix.toStringAsFixed(2),
                    colorScheme.onPrimaryContainer),
                _divider(colorScheme.onPrimaryContainer),
                _priceItem('SVXY', '\$${data.svxy.toStringAsFixed(2)}',
                    colorScheme.onPrimaryContainer),
                _divider(colorScheme.onPrimaryContainer),
                _priceItem('SVIX', '\$${data.svix.toStringAsFixed(2)}',
                    colorScheme.onPrimaryContainer),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _priceItem(String label, String value, Color color) {
    return Column(
      children: [
        Text(label, style: TextStyle(fontSize: 11, color: color.withAlpha(180))),
        const SizedBox(height: 2),
        Text(
          value,
          style: TextStyle(
              fontWeight: FontWeight.bold, fontSize: 20, color: color),
        ),
      ],
    );
  }

  Widget _divider(Color color) {
    return Container(width: 1, height: 36, color: color.withAlpha(50));
  }

  String _formatDate(String iso) {
    try {
      final dt = DateTime.parse(iso);
      return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-'
          '${dt.day.toString().padLeft(2, '0')}';
    } catch (_) {
      return iso;
    }
  }
}

// ── 목표 VIX 입력 카드 ──────────────────────────────────────

class _TargetInputCard extends StatelessWidget {
  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  final VixEtfData data;
  final double? targetVix;

  const _TargetInputCard({
    required this.controller,
    required this.onChanged,
    required this.data,
    required this.targetVix,
  });

  @override
  Widget build(BuildContext context) {
    final svxyFair =
        targetVix != null ? data.svxyFair(targetVix!) : null;
    final svixFair =
        targetVix != null ? data.svixFair(targetVix!) : null;
    final r = targetVix != null
        ? (targetVix! - data.vix) / data.vix * 100
        : null;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('VIX 목표값 입력',
                style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            TextField(
              controller: controller,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(
                hintText: '예: 30',
                labelText: 'VIX 목표값',
                border: const OutlineInputBorder(),
                suffixText: r != null
                    ? '${r >= 0 ? '+' : ''}${r.toStringAsFixed(1)}%'
                    : null,
                suffixStyle: TextStyle(
                  color: r == null
                      ? null
                      : r >= 0
                          ? Colors.red.shade700
                          : Colors.green.shade700,
                  fontWeight: FontWeight.bold,
                ),
              ),
              onChanged: onChanged,
            ),
            if (targetVix != null && svxyFair != null && svixFair != null) ...[
              const SizedBox(height: 14),
              _ResultRow(label: 'SVXY 이론가', value: '\$${svxyFair.toStringAsFixed(2)}', current: data.svxy),
              const SizedBox(height: 6),
              _ResultRow(label: 'SVIX 이론가', value: '\$${svixFair.toStringAsFixed(2)}', current: data.svix),
              const SizedBox(height: 8),
              Text(
                '수식: R = (목표 - 현재) / 현재,  SVXY = 현재가 × (1 - 0.5R),  SVIX = 현재가 × (1 - R)',
                style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ResultRow extends StatelessWidget {
  final String label;
  final String value;
  final double current;

  const _ResultRow({
    required this.label,
    required this.value,
    required this.current,
  });

  @override
  Widget build(BuildContext context) {
    final parsed = double.tryParse(value.replaceAll('\$', ''));
    final diff = parsed != null ? parsed - current : null;
    final diffStr = diff != null
        ? ' (${diff >= 0 ? '+' : ''}\$${diff.toStringAsFixed(2)})'
        : '';
    final diffColor = diff == null
        ? Colors.grey
        : diff >= 0
            ? Colors.green.shade700
            : Colors.red.shade700;

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: const TextStyle(fontSize: 14)),
        RichText(
          text: TextSpan(
            children: [
              TextSpan(
                text: value,
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                  color: Colors.black,
                ),
              ),
              TextSpan(
                text: diffStr,
                style: TextStyle(fontSize: 12, color: diffColor),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

// ── 시나리오 테이블 ──────────────────────────────────────────

class _ScenarioTable extends StatelessWidget {
  final VixEtfData data;

  const _ScenarioTable({required this.data});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('VIX 시나리오 이론가',
                style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 2),
            Text(
              '현재 VIX ${data.vix.toStringAsFixed(2)} 기준',
              style: const TextStyle(fontSize: 11, color: Colors.grey),
            ),
            const SizedBox(height: 10),
            Table(
              border: TableBorder.all(
                color: colorScheme.outlineVariant,
                width: 0.5,
              ),
              columnWidths: const {
                0: FlexColumnWidth(1.1),
                1: FlexColumnWidth(1.0),
                2: FlexColumnWidth(1.3),
                3: FlexColumnWidth(1.3),
              },
              children: [
                _headerRow(),
                ..._kVixScenarios.map((vixTarget) => _dataRow(context, vixTarget)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  TableRow _headerRow() {
    return TableRow(
      decoration: BoxDecoration(color: Colors.grey.shade200),
      children: const [
        _Cell(text: 'VIX', isHeader: true),
        _Cell(text: 'R', isHeader: true),
        _Cell(text: 'SVXY', isHeader: true),
        _Cell(text: 'SVIX', isHeader: true),
      ],
    );
  }

  TableRow _dataRow(BuildContext context, double vixTarget) {
    final r = (vixTarget - data.vix) / data.vix;
    final svxyFair = data.svxyFair(vixTarget);
    final svixFair = data.svixFair(vixTarget);
    final isHighStress = vixTarget >= 40;

    return TableRow(
      decoration: isHighStress
          ? BoxDecoration(color: Colors.red.shade50)
          : null,
      children: [
        _Cell(text: vixTarget.toStringAsFixed(0), bold: isHighStress),
        _Cell(
          text: '${r >= 0 ? '+' : ''}${(r * 100).toStringAsFixed(0)}%',
          color: r >= 0 ? Colors.red.shade700 : Colors.green.shade700,
        ),
        _Cell(
          text: '\$${svxyFair.toStringAsFixed(2)}',
          color: r >= 0 ? Colors.red.shade700 : Colors.green.shade700,
        ),
        _Cell(
          text: '\$${svixFair.toStringAsFixed(2)}',
          color: r >= 0 ? Colors.red.shade700 : Colors.green.shade700,
        ),
      ],
    );
  }
}

class _Cell extends StatelessWidget {
  final String text;
  final bool isHeader;
  final bool bold;
  final Color? color;

  const _Cell({
    required this.text,
    this.isHeader = false,
    this.bold = false,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 8),
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: isHeader ? 11 : 12,
          fontWeight: (isHeader || bold) ? FontWeight.bold : FontWeight.normal,
          color: color,
        ),
      ),
    );
  }
}
