import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photonicat/wifi_vpn_panel.dart';
import 'control_panel_test.dart' show TestRouter;

void main() {
  testWidgets('Wi-Fi VPN switch uses fresh settings and preserves AP state', (
    tester,
  ) async {
    final router = TestRouter();
    router.settings!['wifi'][0]['vpn'] = {'enabled': false, 'engine': 'mihomo'};
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(child: WifiVpnPanel(router: router)),
        ),
      ),
    );
    final toggle = find.byKey(const ValueKey('wifi-vpn-pcie7'));
    await tester.ensureVisible(toggle);
    await tester.tap(toggle);
    await tester.pumpAndSettle();
    expect(router.sent.map((r) => r['op']), ['settings', 'wifi_set']);
    expect(router.sent.last['args'], {
      'revision': 'fresh',
      'id': 'pcie7',
      'ssid': 'Changed elsewhere',
      'enabled': true,
      'vpn_enabled': true,
    });
  });
}
