import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photonicat/control_panel.dart';
import 'package:photonicat/router_controller.dart';

class TestRouter extends RouterController {
  final sent = <Map<String, dynamic>>[];
  TestRouter() {
    connected = true;
    settings = {
      'wifi': [
        {
          'id': 'pcie7',
          'ssid': 'My AP',
          'label': 'PCIe',
          'band': '5g',
          'enabled': true,
          'actions': ['wifi_set'],
          'revision': 'old',
        },
      ],
      'screen': {
        'brightness': 75,
        'battery_timeout': 60,
        'power_timeout': 86400,
        'actions': ['screen_set'],
        'revision': 'old',
      },
    };
  }
  @override
  Future<Map<String, dynamic>> command(
    String op, [
    Map<String, dynamic>? args,
  ]) async {
    sent.add({'op': op, 'args': args});
    if (op == 'settings') {
      settings!['screen']['battery_timeout'] = 120;
      settings!['screen']['revision'] = 'fresh';
      settings!['wifi'][0]['ssid'] = 'Changed elsewhere';
      settings!['wifi'][0]['revision'] = 'fresh';
    }
    return {'message': 'Сохранено'};
  }
}

void main() {
  Future<void> mount(WidgetTester tester, TestRouter router) async {
    await tester.binding.setSurfaceSize(const Size(390, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: ControlPanel(router: router),
            ),
          ),
        ),
      ),
    );
  }

  testWidgets('brightness sends once on release and preserves fresh timeout', (
    tester,
  ) async {
    final router = TestRouter();
    await mount(tester, router);
    final gesture = await tester.startGesture(
      tester.getCenter(find.byType(Slider)),
    );
    await gesture.moveBy(const Offset(-40, 0));
    await tester.pump();
    expect(router.sent, isEmpty);
    await gesture.up();
    await tester.pumpAndSettle();
    expect(router.sent.map((r) => r['op']), ['settings', 'screen_set']);
    expect(router.sent.last['args']['battery_timeout'], 120);
    expect(router.sent.last['args']['revision'], 'fresh');
    expect(router.sent.last['args']['brightness'], isNot(75));
    expect(find.byType(AlertDialog), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'inline Wi-Fi targets discovered radio and keeps freshly read SSID',
    (tester) async {
      final router = TestRouter();
      await mount(tester, router);
      await tester.tap(find.byType(Switch));
      await tester.pumpAndSettle();
      expect(router.sent.last['op'], 'wifi_set');
      expect(router.sent.last['args'], {
        'id': 'pcie7',
        'ssid': 'Changed elsewhere',
        'enabled': false,
        'revision': 'fresh',
      });
      expect(find.byType(AlertDialog), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
}
