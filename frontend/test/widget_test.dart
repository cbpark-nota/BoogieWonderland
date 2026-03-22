import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:momentum_app/main.dart';
import 'package:momentum_app/providers/screening_provider.dart';
import 'package:momentum_app/providers/market_provider.dart';
import 'package:momentum_app/models/screening_result.dart';

void main() {
  testWidgets('App renders with bottom navigation', (WidgetTester tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          marketStatusProvider.overrideWith((ref) async => null),
          screeningProvider.overrideWith(() => _MockScreeningNotifier()),
        ],
        child: const MomentumApp(),
      ),
    );
    await tester.pump();

    expect(find.text('Dashboard'), findsWidgets);
    expect(find.text('Screening'), findsOneWidget);
    expect(find.text('Portfolio'), findsOneWidget);
  });

  testWidgets('Settings icon is present', (WidgetTester tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          marketStatusProvider.overrideWith((ref) async => null),
          screeningProvider.overrideWith(() => _MockScreeningNotifier()),
        ],
        child: const MomentumApp(),
      ),
    );
    await tester.pump();

    expect(find.byIcon(Icons.settings), findsOneWidget);
  });
}

class _MockScreeningNotifier extends ScreeningNotifier {
  @override
  Future<ScreeningRun?> build() async => null;
}
