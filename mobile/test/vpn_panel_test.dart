import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photonicat/vpn_panel.dart';
import 'package:photonicat/router_controller.dart';

class VpnRouter extends RouterController {
  final sent = <Map<String, dynamic>>[];
  @override
  Future<Map<String, dynamic>> readBackground(String op) => command(op);
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
    if (args?['action'] == 'node') vpn!['mihomo']['selected'] = args!['value'];
    if (args?['action'] == 'awg') {
      vpn!['amneziawg']['selected'] = args!['value'];
    }
    return {'message': 'Сохранено'};
  }
}

class RefreshingVpnRouter extends VpnRouter {
  final reading = Completer<Map<String, dynamic>>();
  @override
  Future<Map<String, dynamic>> command(
    String op, [
    Map<String, dynamic>? args,
  ]) {
    if (op == 'vpn_get') return reading.future;
    return super.command(op, args);
  }
}

class SubscriptionRouter extends VpnRouter {
  final completion = Completer<Map<String, dynamic>>();
  @override
  Future<Map<String, dynamic>> command(
    String op, [
    Map<String, dynamic>? args,
  ]) async {
    if (args?['action'] != 'update-subscription') {
      return super.command(op, args);
    }
    sent.add({'op': op, 'args': args});
    final result = await completion.future;
    vpn!['revision'] = 'v2';
    vpn!['mihomo']['nodes'] = ['RW · Germany', 'RW · New'];
    return result;
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

  testWidgets(
    'subscription button fetches once and shows new nodes and removals',
    (t) async {
      final r = SubscriptionRouter();
      await mount(t, r);
      await t.ensureVisible(find.text('Профили и подписки'));
      await t.tap(find.text('Профили и подписки'));
      await t.pumpAndSettle();
      final button = find.byKey(const ValueKey('refresh-subscription-rw'));
      await t.ensureVisible(button);
      await t.tap(button);
      await t.pump();
      expect(find.text('Загружаю серверы из подписки…'), findsOneWidget);
      expect(t.widget<IconButton>(button).onPressed, isNull);
      expect(
        r.sent
            .where((x) => x['args']?['action'] == 'update-subscription')
            .length,
        1,
      );
      expect(r.sent.last['args'], {
        'action': 'update-subscription',
        'id': 'rw',
        'revision': 'v1',
      });
      r.completion.complete({
        'message': 'Подписка обновлена. Серверов: 2; добавлено: 1, удалено: 1.',
      });
      await t.pumpAndSettle();
      expect(r.vpn!['mihomo']['selected'], 'RW · Germany');
      await t.ensureVisible(find.text('RW · Germany'));
      await t.tap(find.text('RW · Germany'));
      await t.pumpAndSettle();
      expect(find.text('RW · New'), findsOneWidget);
      expect(
        find.text(
          'Mobile · Очень длинное название сервера для всех операторов',
        ),
        findsNothing,
      );
      expect(t.takeException(), isNull);
    },
  );
  testWidgets(
    'failed subscription fetch preserves cached servers and allows retry',
    (t) async {
      final r = SubscriptionRouter();
      await mount(t, r);
      await t.ensureVisible(find.text('Профили и подписки'));
      await t.tap(find.text('Профили и подписки'));
      await t.pumpAndSettle();
      final button = find.byKey(const ValueKey('refresh-subscription-rw'));
      await t.ensureVisible(button);
      await t.tap(button);
      await t.pump();
      r.completion.completeError(StateError('Подписка недоступна'));
      await t.pumpAndSettle();
      expect(
        r.vpn!['mihomo']['nodes'],
        contains('Mobile · Очень длинное название сервера для всех операторов'),
      );
      expect(t.widget<IconButton>(button).onPressed, isNotNull);
      expect(find.textContaining('Подписка недоступна'), findsWidgets);
      expect(find.textContaining('Профили обновлены'), findsNothing);
      expect(t.takeException(), isNull);
    },
  );

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
      await t.tap(
        find.descendant(
          of: find.byKey(const ValueKey('lan-internet-mode')),
          matching: find.text('Direct'),
        ),
      );
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
  testWidgets(
    'WAN Direct is disabled for uplink and available for sharing; GearUP is absent',
    (t) async {
      final r = VpnRouter();
      r.vpn!['ports'] = {
        'installed': true,
        'wan_mode': 'auto',
        'wan_role': 'uplink',
        'lan_mode': 'vpn',
        'lan_state': 'vpn',
        'lan_address': '172.16.0.1',
        'kill_switch': true,
        'gearup': {'running': true},
      };
      await mount(t, r);
      expect(find.text('GearUP'), findsNothing);
      final wan = find.byKey(const ValueKey('wan-internet-mode'));
      final wanChoice = find.descendant(
        of: wan,
        matching: find.widgetWithText(TextButton, 'Direct'),
      );
      await t.ensureVisible(wanChoice);
      expect(t.widget<TextButton>(wanChoice).onPressed, isNull);
      final lan = find.byKey(const ValueKey('lan-internet-mode'));
      final lanChoice = find.descendant(of: lan, matching: find.text('Direct'));
      await t.ensureVisible(lanChoice);
      await t.tap(lanChoice);
      await t.pumpAndSettle();
      expect(r.sent.last['args']['setting'], 'lan_mode');
      expect(r.sent.last['args']['value'], 'direct');
      r.vpn!['ports']['wan_role'] = 'share';
      await mount(t, r);
      await t.ensureVisible(wanChoice);
      await t.tap(wanChoice);
      await t.pumpAndSettle();
      expect(r.sent.last['args']['setting'], 'wan_share_mode');
      expect(r.sent.last['args']['value'], 'direct');
      expect(t.takeException(), isNull);
      await t.pumpWidget(const SizedBox());
    },
  );
  testWidgets('auto is separate, first activation can be cancelled', (t) async {
    final r = VpnRouter();
    r.vpn!['mihomo']['auto'] = {'name': 'PC-Auto', 'ready': false};
    await mount(t, r);
    await t.ensureVisible(find.text('RW · Germany'));
    await t.tap(find.text('RW · Germany'));
    await t.pumpAndSettle();
    expect(find.text('Автовыбор'), findsOneWidget);
    await t.enterText(find.byType(TextField), 'nonexistent');
    await t.pumpAndSettle();
    expect(find.text('Автовыбор'), findsOneWidget);
    await t.tap(find.text('Автовыбор'));
    await t.pumpAndSettle();
    expect(find.text('Включить автовыбор?'), findsOneWidget);
    await t.tap(find.text('Отмена'));
    await t.pumpAndSettle();
    expect(r.sent.where((c) => c['op'] == 'vpn_set'), isEmpty);
    expect(r.vpn!['mihomo']['selected'], 'RW · Germany');
    expect(t.takeException(), isNull);
  });
  testWidgets('auto selection sends stable group ID and shows current leaf', (
    t,
  ) async {
    final r = VpnRouter();
    r.vpn!['mihomo']['auto'] = {
      'name': 'PC-Auto',
      'ready': true,
      'node': 'Mobile · Очень длинное название сервера для всех операторов',
      'delay_ms': 123,
      'alive': true,
    };
    await mount(t, r, width: 320);
    await t.ensureVisible(find.text('RW · Germany'));
    await t.tap(find.text('RW · Germany'));
    await t.pumpAndSettle();
    await t.tap(find.text('Автовыбор'));
    await t.pumpAndSettle();
    expect(r.sent.last['args'], {
      'action': 'node',
      'revision': 'v1',
      'value': 'PC-Auto',
    });
    expect(find.textContaining('Сейчас: Mobile'), findsOneWidget);
    expect(find.textContaining('123 мс'), findsOneWidget);
    expect(r.vpn!['active'], 'amneziawg');
    expect(t.takeException(), isNull);
  });
  testWidgets('background VPN refresh leaves server picker available', (
    t,
  ) async {
    final r = RefreshingVpnRouter();
    await t.binding.setSurfaceSize(const Size(390, 1000));
    addTearDown(() => t.binding.setSurfaceSize(null));
    await t.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(child: VpnPanel(router: r)),
        ),
      ),
    );
    await t.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    await t.ensureVisible(find.text('RW · Germany'));
    await t.tap(find.text('RW · Germany'));
    await t.pump(const Duration(milliseconds: 400));
    expect(find.text('Сервер Mihomo'), findsOneWidget);
    expect(r.sent.where((c) => c['op'] == 'vpn_set'), isEmpty);
    r.reading.complete({});
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
    await t.pumpWidget(const SizedBox());
  });
}
