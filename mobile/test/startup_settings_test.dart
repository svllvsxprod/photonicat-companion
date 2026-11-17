import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photonicat/startup_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('toggle confirms native state and can disable pending approval', (
    tester,
  ) async {
    var status = 'disabled';
    final requested = <bool>[];
    var settings = false;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      StartupSettings.channel,
      (call) async {
        if (call.method == 'set') {
          requested.add(call.arguments as bool);
          status = call.arguments == true ? 'approval' : 'disabled';
        }
        if (call.method == 'settings') settings = true;
        return {'status': status};
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        StartupSettings.channel,
        null,
      ),
    );
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: StartupSettings())),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byType(SwitchListTile));
    await tester.pumpAndSettle();
    expect(requested, [true]);
    expect(
      find.text('Нужно разрешить автозапуск в настройках системы.'),
      findsOneWidget,
    );
    await tester.tap(find.text('Открыть настройки системы'));
    await tester.pumpAndSettle();
    expect(settings, isTrue);
    await tester.tap(find.byType(SwitchListTile));
    await tester.pumpAndSettle();
    expect(requested, [true, false]);
    expect(
      find.text('Нужно разрешить автозапуск в настройках системы.'),
      findsNothing,
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('failed registration does not claim enabled', (tester) async {
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      StartupSettings.channel,
      (call) async {
        if (call.method == 'set') {
          throw PlatformException(code: 'install_first');
        }
        return {'status': 'disabled'};
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        StartupSettings.channel,
        null,
      ),
    );
    await tester.pumpWidget(
      const MaterialApp(home: Scaffold(body: StartupSettings())),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byType(SwitchListTile));
    await tester.pumpAndSettle();
    expect(
      tester.widget<SwitchListTile>(find.byType(SwitchListTile)).value,
      isFalse,
    );
    expect(find.textContaining('Сначала перенеси Photonicat'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
}
