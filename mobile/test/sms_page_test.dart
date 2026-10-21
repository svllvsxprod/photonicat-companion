import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photonicat/router_controller.dart';
import 'package:photonicat/sms_page.dart';

class SmsRouter extends RouterController {
  final calls = <String>[];
  bool empty = false, fail = false;
  SmsRouter() {
    connected = true;
  }
  @override
  Future<Map<String, dynamic>> command(
    String op, [
    Map<String, dynamic>? args,
  ]) async {
    calls.add(op);
    if (fail) throw Exception('Модем недоступен');
    if (op == 'sms_read') {
      return {
        'sms_message': {
          'id': 7,
          'sender': 'Оператор',
          'time': '20.10.2026',
          'text': 'Полный текст входящего сообщения',
        },
      };
    }
    return {
      'sms': {
        'messages': empty
            ? []
            : [
                {
                  'id': 7,
                  'sender': 'Оператор',
                  'time': '20.10.2026',
                  'preview': 'Входящее сообщение',
                },
              ],
        'next': null,
        'limited': false,
      },
    };
  }
}

void main() {
  testWidgets('loads inbox and opens complete message without mutations', (
    tester,
  ) async {
    final router = SmsRouter();
    await tester.pumpWidget(MaterialApp(home: SmsPage(router: router)));
    await tester.pumpAndSettle();
    expect(find.text('Оператор'), findsOneWidget);
    await tester.tap(find.text('Оператор'));
    await tester.pumpAndSettle();
    expect(find.text('Полный текст входящего сообщения'), findsOneWidget);
    expect(router.calls, ['sms_list', 'sms_read']);
  });
  testWidgets('empty, failed and disconnected states are distinct', (
    tester,
  ) async {
    final router = SmsRouter()..empty = true;
    await tester.pumpWidget(MaterialApp(home: SmsPage(router: router)));
    await tester.pumpAndSettle();
    expect(find.text('Пока нет входящих СМС'), findsOneWidget);
    router.fail = true;
    await tester.tap(find.byTooltip('Обновить СМС'));
    await tester.pumpAndSettle();
    expect(find.text('Модем недоступен'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    final offline = SmsRouter()..connected = false;
    await tester.pumpWidget(MaterialApp(home: SmsPage(router: offline)));
    await tester.pumpAndSettle();
    expect(offline.calls, isEmpty);
    expect(find.textContaining('Подключись к роутеру'), findsOneWidget);
    expect(find.text('Пока нет входящих СМС'), findsNothing);
  });
}
