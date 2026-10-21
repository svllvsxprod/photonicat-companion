import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photonicat/fan_control.dart';
import 'package:photonicat/router_controller.dart';

class FanRouter extends RouterController {
  final sent = <Map<String, dynamic>>[];
  FanRouter() {
    connected = true;
    settings = {
      'fan': {'mode': 'manual', 'level': 7, 'rpm': 3200, 'revision': 'old'},
    };
  }
  @override
  Future<Map<String, dynamic>> command(
    String op, [
    Map<String, dynamic>? args,
  ]) async {
    sent.add({'op': op, 'args': args});
    if (op == 'settings') {
      settings!['fan']['revision'] = 'fresh';
      settings!['fan']['mode'] = 'smart_cool';
    }
    return {};
  }
}

void main() {
  testWidgets('fan slider commits only on release without overwriting mode', (
    t,
  ) async {
    final r = FanRouter();
    await t.pumpWidget(
      MaterialApp(
        home: Scaffold(body: FanControl(router: r)),
      ),
    );
    final g = await t.startGesture(
      t.getCenter(find.byKey(const ValueKey('fan-level'))),
    );
    await g.moveBy(const Offset(-30, 0));
    await t.pump();
    expect(r.sent, isEmpty);
    await g.up();
    await t.pumpAndSettle();
    expect(r.sent.map((x) => x['op']), ['settings', 'fan_set']);
    expect(r.sent.last['args']['revision'], 'fresh');
    expect(r.sent.last['args'].containsKey('mode'), isFalse);
  });
}
