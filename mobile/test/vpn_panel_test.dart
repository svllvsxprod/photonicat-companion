import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photonicat/vpn_panel.dart';
import 'package:photonicat/router_controller.dart';

class VpnRouter extends RouterController {
  final sent = <Map<String, dynamic>>[];
  VpnRouter() {
    connected = true;
    vpn = {
      'available': true,
      'active': 'amneziawg',
      'revision': 'v1',
      'amneziawg': {
        'selected': 'a',
        'applied': 'a',
        'running': true,
        'profiles': [
          {'id': 'a', 'label': 'Germany'},
          {'id': 'b', 'label': 'Another'},
        ],
      },
      'mihomo': {
        'selected': 'RW · Germany',
        'applied': 'RW · Germany',
        'running': true,
        'nodes': [
          'RW · Germany',
          'Mobile · Очень длинное название сервера для всех операторов',
        ],
      },
      'subscriptions': [
        {'id': 'rw', 'label': 'RW', 'count': 2},
      ],
    };
  }
  @override
  Future<Map<String, dynamic>> command(
    String op, [
    Map<String, dynamic>? args,
  ]) async {
    sent.add({'op': op, 'args': args});
    if (args?['action'] == 'engine') vpn!['active'] = args!['value'];
    if (args?['action'] == 'awg') {
      vpn!['amneziawg']['selected'] = args!['value'];
    }
    return {'message': 'Сохранено'};
  }
}

void main() {
  Future<void> mount(WidgetTester t, VpnRouter r, {double width = 360}) async {
    await t.binding.setSurfaceSize(Size(width, 900));
    addTearDown(() => t.binding.setSurfaceSize(null));
    await t.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: Scaffold(
          body: SingleChildScrollView(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: VpnPanel(router: r),
            ),
          ),
        ),
      ),
    );
    await t.pumpAndSettle();
  }

  testWidgets('switch changes only selected engine and carries revision', (
    t,
  ) async {
    final r = VpnRouter();
    await mount(t, r);
    await t.tap(find.text('Mihomo'));
    await t.pumpAndSettle();
    expect(r.sent.last['args'], {
      'action': 'engine',
      'revision': 'v1',
      'value': 'mihomo',
    });
    expect(r.vpn!['amneziawg']['selected'], 'a');
    expect(t.takeException(), isNull);
  });
  testWidgets(
    'profile selection is explicit and does not switch other engine',
    (t) async {
      final r = VpnRouter();
      await mount(t, r);
      await t.tap(find.text('Germany'));
      await t.pumpAndSettle();
      await t.tap(find.text('Another'));
      await t.pumpAndSettle();
      expect(r.sent.last['args'], {
        'action': 'awg',
        'revision': 'v1',
        'value': 'b',
      });
      expect(r.vpn!['mihomo']['selected'], 'RW · Germany');
      expect(t.takeException(), isNull);
    },
  );
  testWidgets('offline controls disabled, both QR entrances visible', (
    t,
  ) async {
    final r = VpnRouter();
    r.connected = false;
    await mount(t, r);
    expect(find.text('QR-код'), findsNWidgets(2));
    final buttons = t.widgetList<OutlinedButton>(find.byType(OutlinedButton));
    expect(buttons.every((b) => b.onPressed == null), isTrue);
    expect(r.sent, isEmpty);
    expect(t.takeException(), isNull);
  });
  testWidgets(
    'LAN mode is independent of WAN role and uses Direct VPN control',
    (t) async {
      final r = VpnRouter();
      r.vpn!['routing_scope'] = 'lan';
      r.vpn!['ports'] = {
        'installed': true,
        'wan_mode': 'auto',
        'wan_role': 'uplink',
        'wan_link': true,
        'lan_link': true,
        'wan_address': '192.0.2.2',
        'lan_enabled': true,
        'lan_state': 'vpn',
        'lan_address': '172.16.0.1',
        'kill_switch': true,
      };
      await mount(t, r);
      await t.ensureVisible(find.text('Раздача'));
      await t.tap(find.text('Раздача'));
      await t.pumpAndSettle();
      expect(r.sent.last['args'], {
        'action': 'ports',
        'revision': 'v1',
        'setting': 'wan_mode',
        'value': 'share',
      });
      await t.ensureVisible(find.byKey(const ValueKey('lan-internet-mode')));
      await t.tap(find.byKey(const ValueKey('lan-internet-mode')));
      await t.pumpAndSettle();
      expect(r.sent.last['args'], {
        'action': 'ports',
        'revision': 'v1',
        'setting': 'lan_mode',
        'value': 'direct',
      });
      expect(find.text('Kill switch включён'), findsOneWidget);
      expect(t.takeException(), isNull);
      await t.pumpWidget(const SizedBox());
    },
  );
}
