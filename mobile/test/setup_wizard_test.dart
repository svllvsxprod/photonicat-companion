import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photonicat/setup_wizard.dart';
import 'package:photonicat/setup_connection.dart';

void main() {
  test('setup accepts only local IPv4 addresses', () {
    for (final address in ['172.16.0.1', '192.168.8.1', '10.0.0.1']) {
      expect(validSetupAddress(address), isTrue);
    }
    for (final address in ['example.org', '8.8.8.8', '127.0.0.1', '::1', '172.32.0.1', '192.168.8.1;reboot']) {
      expect(validSetupAddress(address), isFalse);
    }
  });
  testWidgets('all four demo screens use no device and keep export key hidden', (tester) async {
    tester.view.physicalSize = const Size(430, 1800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const MaterialApp(home: SetupWizard(demo: true)));
    expect(find.text('Подключение'), findsOneWidget);
    await tester.tap(find.text('Проверить роутер'));
    await tester.pumpAndSettle();
    expect(find.text('Fibocom FM350-GL'), findsOneWidget);
    await tester.tap(find.text('Установить и подключиться'));
    await tester.pumpAndSettle();
    expect(find.text('Твои VPN-профили'), findsOneWidget);
    await tester.tap(find.text('Производительность VPN'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Применить оптимизацию'));
    await tester.pumpAndSettle();
    expect(find.text('Предпросмотр настройки производительности.'), findsOneWidget);
    await tester.tap(find.text('Производительность VPN'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Выбрать файлы .conf'));
    await tester.pumpAndSettle();
    expect(find.text('Германия.conf'), findsOneWidget);
    await tester.tap(find.text('Добавить и продолжить'));
    await tester.pumpAndSettle();
    expect(find.text('Всё готово'), findsOneWidget);
    final demoKey = '0' * 64;
    expect(find.text(demoKey), findsNothing);
    await tester.tap(find.text('Показать ключ'));
    await tester.pumpAndSettle();
    expect(find.text(demoKey), findsOneWidget);
    await tester.tap(find.text('Скрыть'));
    await tester.pumpAndSettle();
    expect(find.text(demoKey), findsNothing);
  });
}
