import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/vix_etf_data.dart';
import '../providers/vix_etf_provider.dart';

class VixEtfCalculatorScreen extends ConsumerStatefulWidget {
  const VixEtfCalculatorScreen({super.key});

  @override
  ConsumerState<VixEtfCalculatorScreen> createState() =>
      _VixEtfCalculatorScreenState();
}

class _VixEtfCalculatorScreenState
    extends ConsumerState<VixEtfCalculatorScreen> {
  // 입력 모드: true = R(변동률) 직접 입력, false = 목표 VIX 입력
  bool _useRMode = false;

  // R 직접 입력 (-50% ~ +200%)
  double _rSlider = 0.0; // -50% ~ +200%, 단위: %

  // 목표 VIX 직접 입력
  final _targetVixController = TextEditingController(text: '20');

  static const List<double> _scenarioVixLevels = [
    20, 25, 30, 35, 40, 50, 60, 80
  ];

  @override
  void dispose() {
    _targetVixController.dispose();
    super.dispose();
  }

  double _effectiveR(VixEtfData data) {
    if (_useRMode) {
      return _rSlider / 100.0;
    } else {
      final target = double.tryParse(_targetVixController.text);
      if (target == null) return 0.0;
      return data.rFromTargetVix(target) ?? 0.0;
    }
  }

  @override
  Widget build(BuildContext context) {
    final dataAsync = ref.watch(vixEtfDataProvider);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(vixEtfDataProvider),
        child: dataAsync.when(
          data: (data) => _buildContent(context, data),
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => _buildEmpty(context),
        ),
      ),
    );
  }

  Widget _buildEmpty(BuildContext context) {
    return ListView(
      children: [
        SizedBox(height: MediaQuery.of(context).size.height * 0.4),
        const Center(
          child: Column(
            children: [
              Icon(Icons.show_chart, size: 64, color: Colors.grey),
              SizedBox(height: 16),
              Text('VIX ETF 가격 데이터 없음',
                  style: TextStyle(fontSize: 16, color: Colors.grey)),
              SizedBox(height: 8),
              Text('GitHub Actions 실행 후 데이터가 생성됩니다.',
                  style: TextStyle(fontSize: 13, color: Colors.grey)),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildContent(BuildContext context, VixEtfData data) {
    final r = _effectiveR(data);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _buildPriceInfoCard(context, data),
        const SizedBox(height: 16),
        _buildInputCard(context, data, r),
        const SizedBox(height: 16),
        _buildResultCard(context, data, r),
        const SizedBox(height: 16),
        _buildScenarioTable(context, data),
        const SizedBox(height: 24),
        _buildFormulaNote(context),
        const SizedBox(height: 16),
        if (data.updatedAt.isNotEmpty)
          Center(
            child: Text(
              '업데이트: ${data.updatedAt.substring(0, data.updatedAt.length.clamp(0, 19))}',
              style: const TextStyle(fontSize: 11, color: Colors.grey),
            ),
          ),
      ],
    );
  }

  // ── 현재 ETF 정보 카드 ─────────────────────────────────────

  Widget _buildPriceInfoCard(BuildContext context, VixEtfData data) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('현재 시장 데이터',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
            const SizedBox(height: 12),
            _priceRow('VIX 지수', data.vixCurrent, data.vixPrevClose,
                decimals: 2, prefix: ''),
            const Divider(height: 16),
            _priceRow('SVXY', data.svxyPrice, data.svxyPrevClose),
            const Divider(height: 16),
            _priceRow('SVIX', data.svixPrice, data.svixPrevClose),
          ],
        ),
      ),
    );
  }

  Widget _priceRow(
    String label,
    double? current,
    double? prevClose, {
    int decimals = 2,
    String prefix = '\$',
  }) {
    final currentStr =
        current != null ? '$prefix${current.toStringAsFixed(decimals)}' : 'N/A';
    double? changePct;
    if (current != null && prevClose != null && prevClose != 0) {
      changePct = (current - prevClose) / prevClose * 100;
    }
    final changeColor = changePct == null
        ? Colors.grey
        : changePct >= 0
            ? Colors.red.shade700
            : Colors.blue.shade700;
    final changeStr = changePct != null
        ? '${changePct >= 0 ? '+' : ''}${changePct.toStringAsFixed(2)}%'
        : '';

    return Row(
      children: [
        Text(label,
            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
        const Spacer(),
        Text(currentStr,
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold)),
        if (changePct != null) ...[
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: changeColor.withOpacity(0.1),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(changeStr,
                style: TextStyle(
                    fontSize: 12,
                    color: changeColor,
                    fontWeight: FontWeight.w600)),
          ),
        ],
        if (prevClose != null) ...[
          const SizedBox(width: 8),
          Text('전일: $prefix${prevClose.toStringAsFixed(decimals)}',
              style: const TextStyle(fontSize: 11, color: Colors.grey)),
        ],
      ],
    );
  }

  // ── 입력 카드 ──────────────────────────────────────────────

  Widget _buildInputCard(BuildContext context, VixEtfData data, double r) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('시나리오 입력',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
            const SizedBox(height: 12),
            SegmentedButton<bool>(
              segments: const [
                ButtonSegment(value: false, label: Text('목표 VIX')),
                ButtonSegment(value: true, label: Text('변동률 R 직접')),
              ],
              selected: {_useRMode},
              onSelectionChanged: (s) =>
                  setState(() => _useRMode = s.first),
              style: const ButtonStyle(
                visualDensity: VisualDensity.compact,
              ),
            ),
            const SizedBox(height: 16),
            if (!_useRMode) ...[
              Text(
                '목표 VIX 값 입력  (현재 VIX: ${data.vixCurrent?.toStringAsFixed(2) ?? 'N/A'})',
                style: const TextStyle(fontSize: 13),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _targetVixController,
                      keyboardType: const TextInputType.numberWithOptions(
                          decimal: true),
                      decoration: const InputDecoration(
                        labelText: '목표 VIX',
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                      onChanged: (_) => setState(() {}),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        'R = ${(r * 100).toStringAsFixed(1)}%',
                        style: const TextStyle(
                            fontWeight: FontWeight.bold, fontSize: 15),
                      ),
                      Text(
                        'VIX 선물 지수 변동률',
                        style: TextStyle(fontSize: 11, color: Colors.grey[600]),
                      ),
                    ],
                  ),
                ],
              ),
            ] else ...[
              Text(
                'VIX 선물 지수 변동률 R = ${_rSlider.toStringAsFixed(1)}%',
                style: const TextStyle(
                    fontSize: 14, fontWeight: FontWeight.bold),
              ),
              Slider(
                value: _rSlider,
                min: -50,
                max: 200,
                divisions: 250,
                label: '${_rSlider.toStringAsFixed(1)}%',
                onChanged: (v) => setState(() => _rSlider = v),
              ),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: const [
                  Text('-50%', style: TextStyle(fontSize: 11, color: Colors.grey)),
                  Text('0%', style: TextStyle(fontSize: 11, color: Colors.grey)),
                  Text('+200%', style: TextStyle(fontSize: 11, color: Colors.grey)),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  // ── 결과 카드 ──────────────────────────────────────────────

  Widget _buildResultCard(BuildContext context, VixEtfData data, double r) {
    final svxyTheo = data.svxyTheoretical(r);
    final svixTheo = data.svixTheoretical(r);
    final svxyDev = data.svxyDeviation(r);
    final svixDev = data.svixDeviation(r);

    return Card(
      color: Theme.of(context).colorScheme.primaryContainer.withOpacity(0.3),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'R = ${(r * 100).toStringAsFixed(2)}% 기준 이론가',
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
            ),
            const SizedBox(height: 12),
            _theoreticalRow('SVXY', svxyTheo, svxyDev, data.svxyPrice),
            const Divider(height: 16),
            _theoreticalRow('SVIX', svixTheo, svixDev, data.svixPrice),
          ],
        ),
      ),
    );
  }

  Widget _theoreticalRow(
      String label, double? theoretical, double? deviation, double? current) {
    final theoStr =
        theoretical != null ? '\$${theoretical.toStringAsFixed(2)}' : 'N/A';
    final devStr = deviation != null
        ? '${deviation >= 0 ? '+' : ''}${deviation.toStringAsFixed(2)}%'
        : '';
    final devColor = deviation == null
        ? Colors.grey
        : deviation.abs() < 1
            ? Colors.green.shade700
            : deviation > 0
                ? Colors.orange.shade700
                : Colors.blue.shade700;

    return Row(
      children: [
        Text(label,
            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
        const Spacer(),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(theoStr,
                style: const TextStyle(
                    fontSize: 18, fontWeight: FontWeight.bold)),
            if (deviation != null)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('현재가 ${current != null ? '\$${current.toStringAsFixed(2)}' : ''}',
                      style: const TextStyle(fontSize: 11, color: Colors.grey)),
                  const SizedBox(width: 6),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: devColor.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text('괴리 $devStr',
                        style: TextStyle(
                            fontSize: 11,
                            color: devColor,
                            fontWeight: FontWeight.w600)),
                  ),
                ],
              ),
          ],
        ),
      ],
    );
  }

  // ── 시나리오 테이블 ─────────────────────────────────────────

  Widget _buildScenarioTable(BuildContext context, VixEtfData data) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('VIX 시나리오별 이론가',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
            const SizedBox(height: 4),
            Text(
              'VIX 선물 변동 ≈ ΔVIX 가정 (근사)',
              style: TextStyle(fontSize: 11, color: Colors.grey[600]),
            ),
            const SizedBox(height: 12),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
                columnSpacing: 20,
                headingRowHeight: 36,
                dataRowMinHeight: 32,
                dataRowMaxHeight: 40,
                columns: const [
                  DataColumn(label: Text('VIX', style: TextStyle(fontWeight: FontWeight.bold))),
                  DataColumn(label: Text('R', style: TextStyle(fontWeight: FontWeight.bold))),
                  DataColumn(label: Text('SVXY 이론가', style: TextStyle(fontWeight: FontWeight.bold))),
                  DataColumn(label: Text('SVIX 이론가', style: TextStyle(fontWeight: FontWeight.bold))),
                ],
                rows: _scenarioVixLevels.map((vixLevel) {
                  final r = data.rFromTargetVix(vixLevel) ?? 0.0;
                  final svxy = data.svxyTheoretical(r);
                  final svix = data.svixTheoretical(r);
                  final isCurrentApprox = data.vixCurrent != null &&
                      (vixLevel - data.vixCurrent!).abs() < 2.5;

                  return DataRow(
                    color: isCurrentApprox
                        ? WidgetStateProperty.all(
                            Theme.of(context)
                                .colorScheme
                                .primary
                                .withOpacity(0.08))
                        : null,
                    cells: [
                      DataCell(Text(
                        vixLevel.toStringAsFixed(0),
                        style: TextStyle(
                          fontWeight: isCurrentApprox
                              ? FontWeight.bold
                              : FontWeight.normal,
                        ),
                      )),
                      DataCell(Text(
                        '${(r * 100).toStringAsFixed(1)}%',
                        style: TextStyle(
                          color: r >= 0 ? Colors.red.shade700 : Colors.blue.shade700,
                          fontSize: 12,
                        ),
                      )),
                      DataCell(Text(
                        svxy != null
                            ? '\$${svxy.toStringAsFixed(2)}'
                            : 'N/A',
                        style: TextStyle(
                          color: svxy != null && data.svxyPrevClose != null
                              ? (svxy >= data.svxyPrevClose!
                                  ? Colors.red.shade700
                                  : Colors.blue.shade700)
                              : null,
                          fontWeight: FontWeight.w500,
                        ),
                      )),
                      DataCell(Text(
                        svix != null
                            ? '\$${svix.toStringAsFixed(2)}'
                            : 'N/A',
                        style: TextStyle(
                          color: svix != null && data.svixPrevClose != null
                              ? (svix >= data.svixPrevClose!
                                  ? Colors.red.shade700
                                  : Colors.blue.shade700)
                              : null,
                          fontWeight: FontWeight.w500,
                        ),
                      )),
                    ],
                  );
                }).toList(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ── 수식 설명 ──────────────────────────────────────────────

  Widget _buildFormulaNote(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('계산 수식',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
            const SizedBox(height: 8),
            _formulaLine('SVXY (-0.5x)',
                'prevClose × (1 − 0.5 × R)'),
            _formulaLine('SVIX  (−1x)',
                'prevClose × (1 − R)'),
            const SizedBox(height: 6),
            Text(
              'R = VIX 선물 지수(SPVXSP) 일간 변동률\n'
              '괴리율 = (현재가 − 이론가) / 이론가 × 100%',
              style: TextStyle(fontSize: 11, color: Colors.grey[600]),
            ),
          ],
        ),
      ),
    );
  }

  Widget _formulaLine(String etf, String formula) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          SizedBox(
            width: 90,
            child: Text(etf,
                style: const TextStyle(
                    fontWeight: FontWeight.w600, fontSize: 12)),
          ),
          Expanded(
            child: Text(formula,
                style: const TextStyle(
                    fontFamily: 'monospace', fontSize: 12)),
          ),
        ],
      ),
    );
  }
}
