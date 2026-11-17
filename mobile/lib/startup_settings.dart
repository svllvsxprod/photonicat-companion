import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'app_style.dart';

class StartupSettings extends StatefulWidget {
  const StartupSettings({super.key});
  static const channel = MethodChannel('photonicat/startup');
  @override
  State<StartupSettings> createState() => _StartupSettingsState();
}

class _StartupSettingsState extends State<StartupSettings>
    with WidgetsBindingObserver {
  String status = 'loading';
  String? error, explanation;
  bool busy = false, reading = false;
  Timer? refresh;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    read();
    refresh = Timer.periodic(const Duration(seconds: 3), (_) => read());
  }

  @override
  void dispose() {
    refresh?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) read();
  }

  void apply(Map<dynamic, dynamic>? value) {
    if (!mounted) return;
    setState(() {
      status = value?['status'] as String? ?? 'error';
      explanation = value?['message'] as String?;
    });
  }

  Future<void> read() async {
    if (busy || reading) return;
    reading = true;
    try {
      apply(await StartupSettings.channel.invokeMapMethod('get'));
    } catch (_) {
      if (mounted) setState(() => status = 'error');
    } finally {
      reading = false;
    }
  }

  Future<void> change(bool enabled) async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      apply(await StartupSettings.channel.invokeMapMethod('set', enabled));
    } on PlatformException catch (e) {
      if (mounted) {
        setState(
          () => error = e.code == 'install_first'
              ? 'Сначала перенеси Photonicat в папку «Программы» и запусти оттуда.'
              : 'Не удалось изменить автозапуск. Проверь настройки системы.',
        );
      }
    } catch (_) {
      if (mounted) setState(() => error = 'Автозапуск сейчас недоступен.');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> settings() async {
    try {
      await StartupSettings.channel.invokeMethod<void>('settings');
    } catch (_) {
      if (mounted) {
        setState(
          () => error = 'Открой раздел автозапуска в настройках системы.',
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 24),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'Приложение на компьютере',
          style: TextStyle(color: muted, fontSize: 12),
        ),
        SwitchListTile.adaptive(
          contentPadding: EdgeInsets.zero,
          title: const Text('Запускать при входе в систему'),
          subtitle: const Text(
            'Только значок в строке меню или трее, без открытия окна.',
          ),
          value: status == 'enabled' || status == 'approval',
          onChanged:
              busy ||
                  status == 'loading' ||
                  status == 'unsupported' ||
                  status == 'error'
              ? null
              : change,
        ),
        if (busy) const LinearProgressIndicator(),
        if (status == 'approval') ...[
          const Text(
            'Нужно разрешить автозапуск в настройках системы.',
            style: TextStyle(color: yellow),
          ),
          TextButton(
            onPressed: settings,
            child: const Text('Открыть настройки системы'),
          ),
        ],
        if (status == 'unsupported')
          Text(
            explanation ?? 'Автозапуск недоступен в этой версии системы.',
            style: const TextStyle(color: muted),
          ),
        if (status == 'error')
          TextButton(
            onPressed: read,
            child: const Text('Проверить автозапуск ещё раз'),
          ),
        if (error != null) Text(error!, style: const TextStyle(color: yellow)),
        const Divider(color: rule),
      ],
    ),
  );
}
