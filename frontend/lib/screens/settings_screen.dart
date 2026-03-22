import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import '../services/api_client.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _pushEnabled = false;
  bool _isToggling = false;

  // 웹 환경에서는 간이 토큰 사용, 실제 앱에서는 FCM 토큰으로 교체
  String get _deviceToken => 'web_${defaultTargetPlatform.name}';
  String get _platform => kIsWeb ? 'web' : defaultTargetPlatform.name;

  Future<void> _onPushToggle(bool enabled) async {
    if (_isToggling) return;
    setState(() => _isToggling = true);

    try {
      if (enabled) {
        await ApiClient().registerToken(_deviceToken, _platform);
      } else {
        await ApiClient().unregisterToken(_deviceToken);
      }
      setState(() => _pushEnabled = enabled);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('알림 설정 변경 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isToggling = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const SizedBox(height: 16),
        const ListTile(
          title: Text('설정',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
        ),
        const Divider(),
        SwitchListTile(
          title: const Text('푸시 알림'),
          subtitle: const Text('리밸런싱, 스톱로스 알림'),
          value: _pushEnabled,
          onChanged: _isToggling ? null : _onPushToggle,
          secondary: const Icon(Icons.notifications),
        ),
        const Divider(),
        const ListTile(
          leading: Icon(Icons.schedule),
          title: Text('리밸런싱 주기'),
          subtitle: Text('격주 (매 2주 금요일)'),
        ),
        const ListTile(
          leading: Icon(Icons.show_chart),
          title: Text('ATR 승수'),
          subtitle: Text('2.5'),
        ),
        const ListTile(
          leading: Icon(Icons.pie_chart),
          title: Text('최대 단일 비중'),
          subtitle: Text('20%'),
        ),
        const Divider(),
        const ListTile(
          leading: Icon(Icons.info_outline),
          title: Text('버전'),
          subtitle: Text('0.1.0'),
        ),
      ],
    );
  }
}
