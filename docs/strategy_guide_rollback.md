# Strategy Guide Rollback — 제거된 콘텐츠 보존

이 파일은 `frontend/lib/screens/strategy_guide_screen.dart`에서 제거된 내용을 복원용으로 보존합니다.
(2026-03-30 변경)

---

## 4번: 스크리닝 필터 — 각 항목의 상세 설명

`_filterSteps` 데이터를 아래로 교체하면 복원됩니다.

```dart
const _filterSteps = [
  ('ADX ≥ 20 (추세 강도)', 'Average Directional Index로 추세가 충분히 강한 종목만 선택'),
  ('MA 정배열 (추세 방향)', '20MA > 50MA > 200MA — 단·중·장기 추세 모두 상향'),
  ('RSI 50 ~ 77 (과매수 배제)', '모멘텀이 살아있되 과열 구간(>77) 진입 금지'),
  ('HH-HL ≥ 2회 (상승 구조)', '60일 내 고점 갱신 + 저점 상승 패턴이 2회 이상 확인'),
  ('52주 고점 대비 ≥ 75%', '고점 대비 25% 이상 하락한 종목 제외'),
  ('거래량 급변/급등락 배제', '20일 평균 대비 3× 거래량 스파이크, 5일 ±10% 급등락 제외'),
  ('현재가 > 스톱로스', 'ATR 기반 동적 스톱 아래로 이미 하락한 종목 진입 불가'),
];
```

그리고 `_FilterStep` 위젯을 아래로 교체하면 됩니다.

```dart
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
```

그리고 매핑 코드를 아래로 교체:

```dart
..._filterSteps.asMap().entries.map((e) {
  return _FilterStep(
    step: e.key + 1,
    title: e.value.$1,
    desc: e.value.$2,
    colorScheme: colorScheme,
    theme: theme,
  );
}),
```

---

## 5번: ATR 기반 동적 스톱로스 섹션

`_StrategyOverviewCard`의 `_FilterStep` 목록 다음 `Divider` 이후에 복원합니다.

```dart
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
```

---

## 6번: 스코어 산식 섹션

`build()` 메서드의 `_BtcStrategyCard()` 다음에 복원합니다.

```dart
        const SizedBox(height: 24),
        _SectionHeader(title: '스코어 산식', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _ScoreFormulaCard(),
```

그리고 `_ScoreFormulaCard` 클래스:

```dart
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
```

---

## 7번: 용어 설명 섹션

`build()` 메서드의 `_ScoreFormulaCard()` (또는 `_BtcStrategyCard()`) 다음에 복원합니다.

```dart
        const SizedBox(height: 24),
        _SectionHeader(title: '용어 설명', colorScheme: colorScheme),
        const SizedBox(height: 12),
        const _GlossaryCard(),
```

그리고 `_glossaryTerms` 데이터 및 `_GlossaryCard` 클래스:

```dart
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
                        // ... (term.$2 영어명, term.$3 설명)
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
```
