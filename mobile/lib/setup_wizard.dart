import 'dart:async';
import 'dart:convert';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'app_style.dart';
import 'setup_connection.dart';

/// Preview uses synthetic data and never constructs an SSH client or reads keys.
class SetupWizard extends StatefulWidget {
  const SetupWizard({super.key, this.demo = false, this.onConnected});
  final bool demo;
  final Future<void> Function(SetupResult)? onConnected;
  @override
  State<SetupWizard> createState() => _SetupWizardState();
}

class _SetupWizardState extends State<SetupWizard> {
  final host = TextEditingController(text: '172.16.0.1');
  final password = TextEditingController();
  final subscription = TextEditingController();
  final subscriptionName = TextEditingController(text: 'Моя подписка');
  SetupConnection? connection;
  SetupResult? result;
  Map<String, dynamic>? hardware;
  final profiles = <({String name, String text})>[];
  final imported = <String>{};
  int step = 0;
  bool busy = false, reveal = false;
  String? error;
  String progress = '';
  Timer? clipboardClear;

  @override
  void initState() {
    super.initState();
    if (widget.demo) host.text = '192.168.8.1';
  }

  @override
  void dispose() {
    connection?.close();
    for (final c in [host, password, subscription, subscriptionName]) {
      c.clear();
      c.dispose();
    }
    profiles.clear();
    // The timer intentionally survives disposal to clear only our own key.
    super.dispose();
  }

  Future<void> work(Future<void> Function() action) async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await action();
    } catch (e) {
      if (mounted) {
        setState(
          () => error = e is SetupFailure
              ? e.message
              : 'Не удалось завершить шаг. Проверь подключение и повтори. Данные доступа не записаны в журнал.',
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<bool> trust(String fingerprint, bool changed) async =>
      await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (context) => AlertDialog(
          title: Text(changed ? 'Ключ роутера изменился' : 'Это твой роутер?'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                changed
                    ? 'Ранее по этому адресу был другой SSH-ключ. Подтверждай только если ты заменил или перепрошил роутер.'
                    : 'Убедись, что компьютер подключён к твоему Photonicat. Это отпечаток SSH-ключа устройства; он будет запомнен.',
              ),
              const SizedBox(height: 16),
              SelectableText(fingerprint, style: const TextStyle(fontSize: 12)),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Отмена'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Это мой роутер'),
            ),
          ],
        ),
      ) ??
      false;

  Future<void> inspect() => work(() async {
    if (widget.demo) {
      hardware = {
        'model': 'Photonicat 2',
        'firmware': '26.04.1',
        'supported': true,
        'installed': false,
        'wifi': [
          {'phy': 'phy0', 'driver': 'Встроенный Wi-Fi', 'bus': 'Встроенный'},
          {
            'phy': 'phy1',
            'driver': 'Qualcomm · драйвер доступен',
            'bus': 'PCIe',
          },
        ],
        'modems': [
          {'name': 'Fibocom FM350-GL', 'vendor': 'Fibocom', 'bus': 'USB'},
        ],
        'errors': [],
      };
    } else {
      connection?.close();
      connection = SetupConnection();
      await connection!.connect(host.text.trim(), password.text, trust);
      password.clear();
      hardware = await connection!.inspect();
    }
    if (mounted) setState(() => step = 1);
  });

  Future<void> install() => work(() async {
    if (widget.demo) {
      result = SetupResult(
        host.text,
        '0000000000000000000000000000000000000000000000000000000000000000',
      );
    } else {
      result ??= await connection!.install(hardware?['installed'] == true, (
        message,
      ) {
        if (mounted) setState(() => progress = message);
      });
    }
    if (!widget.demo && result != null) {
      await widget.onConnected?.call(result!);
    }
    if (mounted) setState(() => step = 2);
  });

  Future<void> pickProfiles() => work(() async {
    if (widget.demo) {
      profiles.addAll([
        (name: 'Германия.conf', text: 'demo'),
        (name: 'Нидерланды.conf', text: 'demo'),
      ]);
      return;
    }
    final files = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['conf'],
    );
    if (files.isEmpty) return;
    if (profiles.length + files.length > 24) {
      throw const SetupFailure('Можно добавить до 24 профилей.');
    }
    for (final file in files) {
      final size = await file.length();
      if (size == null || size > 24576) {
        throw const SetupFailure('Файл профиля должен быть не больше 24 КБ.');
      }
      final text = utf8.decode(await file.readAsBytes());
      if (!text.contains('[Interface]') || !text.contains('[Peer]')) {
        throw const SetupFailure(
          'Выбери экспортированный конфиг AmneziaWG .conf.',
        );
      }
      if (profiles.any((p) => p.name == file.name)) continue;
      profiles.add((name: file.name, text: text));
    }
  });

  Future<void> importVpn() => work(() async {
    final url = subscription.text.trim();
    if (url.isNotEmpty) {
      final u = Uri.tryParse(url);
      if (u == null ||
          u.scheme != 'https' ||
          u.host.isEmpty ||
          u.userInfo.isNotEmpty) {
        throw const SetupFailure(
          'Вставь HTTPS-ссылку подписки от своего VPN-провайдера.',
        );
      }
      if (!imported.contains('subscription')) {
        if (!widget.demo) {
          await connection!.addSubscription(subscriptionName.text.trim(), url);
        }
        imported.add('subscription');
      }
    }
    for (final p in profiles) {
      if (imported.contains(p.name)) continue;
      if (!widget.demo) {
        await connection!.addProfile(
          p.name.replaceFirst(RegExp(r'\.conf$', caseSensitive: false), ''),
          p.text,
        );
      }
      imported.add(p.name);
    }
    subscription.clear();
    profiles.clear();
    if (mounted) setState(() => step = 3);
  });

  Future<void> copyKey() async {
    if (result == null) return;
    final key = result!.key;
    await Clipboard.setData(ClipboardData(text: key));
    clipboardClear?.cancel();
    clipboardClear = Timer(const Duration(seconds: 60), () async {
      // Do not erase an unrelated item copied after this key.
      if ((await Clipboard.getData(Clipboard.kTextPlain))?.text == key) {
        await Clipboard.setData(const ClipboardData(text: ''));
      }
    });
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Ключ скопирован. Буфер очистится через минуту, если в нём останется этот ключ.',
          ),
        ),
      );
    }
  }

  Widget paragraph(String text) => Padding(
    padding: const EdgeInsets.only(bottom: 16),
    child: Text(text, style: const TextStyle(color: muted, height: 1.5)),
  );
  Widget field(
    TextEditingController controller,
    String label, {
    bool secret = false,
    String? hint,
  }) => Padding(
    padding: const EdgeInsets.only(bottom: 16),
    child: TextField(
      controller: controller,
      obscureText: secret,
      enabled: !busy,
      autocorrect: false,
      enableSuggestions: false,
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        border: const OutlineInputBorder(),
      ),
    ),
  );
  Widget button(String label, VoidCallback? action) => SizedBox(
    width: double.infinity,
    child: FilledButton(onPressed: busy ? null : action, child: Text(label)),
  );
  Widget device(IconData icon, String title, String subtitle) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Row(
      children: [
        Icon(icon, color: yellow),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title),
              Text(
                subtitle,
                style: const TextStyle(color: muted, fontSize: 12),
              ),
            ],
          ),
        ),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !busy,
    child: Scaffold(
      appBar: AppBar(
        title: const Text('Настроить Photonicat'),
        backgroundColor: Colors.black,
        leading: busy ? const SizedBox() : null,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (widget.demo)
              const Padding(
                padding: EdgeInsets.only(bottom: 12),
                child: Text(
                  'ДЕМОНСТРАЦИЯ · данные вымышлены',
                  style: TextStyle(color: yellow, fontSize: 11),
                ),
              ),
            Text(
              'ШАГ ${step + 1} ИЗ 4',
              style: const TextStyle(
                color: muted,
                fontSize: 11,
                letterSpacing: 2,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              [
                'Подключение',
                'Оборудование и установка',
                'Твои VPN-профили',
                'Всё готово',
              ][step],
              style: const TextStyle(
                color: yellow,
                fontSize: 28,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 20),
            if (step == 0) ...[
              paragraph(
                'Подключи компьютер к LAN-порту или Wi-Fi Photonicat, а сам роутер — к питанию. Для загрузки подписок роутеру нужен интернет через WAN или мобильную сеть.',
              ),
              field(
                host,
                'Адрес роутера',
                hint: 'Адрес из панели роутера или свойств подключения',
              ),
              field(password, 'Пароль администратора', secret: true),
              paragraph(
                'Это пароль root / SSH твоего роутера, а не пароль Wi-Fi. Мастер его не сохраняет. При первом входе нужно подтвердить отпечаток устройства.',
              ),
              paragraph(
                'Поддерживается Photonicat 2 со штатной PhotonicatWrt 26.04.1. Прошивка и драйверы автоматически не заменяются.',
              ),
              button('Проверить роутер', inspect),
            ],
            if (step == 1) ...[
              device(
                Icons.router_outlined,
                hardware?['model']?.toString() ?? 'Photonicat',
                'PhotonicatWrt ${hardware?['firmware'] ?? '—'}',
              ),
              for (final w in (hardware?['wifi'] as List? ?? []))
                device(Icons.wifi, w['driver'].toString(), w['bus'].toString()),
              for (final m in (hardware?['modems'] as List? ?? []))
                device(
                  Icons.cell_tower,
                  m['name'].toString(),
                  '${m['bus']} · обнаружен',
                ),
              if ((hardware?['modems'] as List? ?? []).isEmpty)
                paragraph(
                  'Мобильный модем не обнаружен. Его можно установить позже; управление роутером доступно без модема.',
                ),
              const Divider(color: rule),
              const SizedBox(height: 12),
              paragraph(
                'Распознавание устройства не доказывает доступность мобильного интернета. SIM, APN и поддержку драйверов проверяет штатная система роутера.',
              ),
              if (hardware?['installed'] == true)
                paragraph(
                  'Служба уже установлена. Получим её существующий ключ и привяжем приложение. Переустановка не требуется.',
                )
              else
                paragraph(
                  'Установим службу управления, Mihomo и AmneziaWG. LAN и Wi-Fi начнут с Direct. VPN включается отдельно после выбора профиля. Если связь не подтвердится, установка автоматически откатится.',
                ),
              if (hardware?['supported'] != true) ...[
                paragraph(
                  'Эта конфигурация пока не поддерживается. Ничего не установлено. Причины: ${(hardware?['errors'] as List? ?? []).join(', ')}.',
                ),
                button('Проверить ещё раз', inspect),
              ] else
                button(
                  hardware?['installed'] == true
                      ? 'Привязать приложение'
                      : 'Установить и подключиться',
                  install,
                ),
            ],
            if (step == 2) ...[
              paragraph(
                'Добавь свою подписку Mihomo или несколько файлов AmneziaWG. Можно использовать оба ядра. Профили не включаются автоматически.',
              ),
              field(subscriptionName, 'Название подписки'),
              field(
                subscription,
                'HTTPS-ссылка подписки',
                secret: true,
                hint: 'От своего VPN-провайдера',
              ),
              paragraph(
                'Нужна подписка формата Clash / Mihomo. Для Amnezia экспортируй готовый профиль AmneziaWG (.conf), а не параметры доступа к серверу.',
              ),
              OutlinedButton.icon(
                onPressed: busy ? null : pickProfiles,
                icon: const Icon(Icons.file_open_outlined),
                label: const Text('Выбрать файлы .conf'),
              ),
              for (final p in profiles)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.description_outlined),
                  title: Text(p.name),
                  subtitle: imported.contains(p.name)
                      ? const Text('Добавлен')
                      : null,
                  trailing: IconButton(
                    onPressed: busy
                        ? null
                        : () => setState(() => profiles.remove(p)),
                    icon: const Icon(Icons.close),
                  ),
                ),
              const SizedBox(height: 16),
              button('Добавить и продолжить', importVpn),
              TextButton(
                onPressed: busy ? null : () => setState(() => step = 3),
                child: const Text('Добавить позже'),
              ),
            ],
            if (step == 3) ...[
              device(
                Icons.verified_user_outlined,
                'Защищённое соединение готово',
                'Ключ получен автоматически',
              ),
              paragraph(
                'Ключ уже получен, авторизация проверена. Приложение сохранило ключ в защищённом хранилище этого компьютера. Вводить его вручную не нужно.',
              ),
              paragraph(
                'Для включения VPN открой вкладку VPN, выбери сервер / профиль и режим VPN для нужного подключения. Новая установка начинает с Direct; при повторной привязке режимы сохраняются.',
              ),
              const Divider(color: rule),
              const SizedBox(height: 12),
              const Text(
                'Ключ для других устройств',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              paragraph(
                'Это полный доступ к управлению твоим роутером. Сохрани его в менеджере паролей. Не публикуй его и не отправляй вместе с инструкцией.',
              ),
              if (reveal)
                SelectableText(
                  result?.key ?? '',
                  style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
                )
              else
                const Text(
                  '••••••••  ••••••••  ••••••••  ••••••••',
                  style: TextStyle(color: muted),
                ),
              Wrap(
                spacing: 8,
                children: [
                  TextButton.icon(
                    onPressed: () => setState(() => reveal = !reveal),
                    icon: Icon(
                      reveal ? Icons.visibility_off : Icons.visibility,
                    ),
                    label: Text(reveal ? 'Скрыть' : 'Показать ключ'),
                  ),
                  TextButton.icon(
                    onPressed: copyKey,
                    icon: const Icon(Icons.copy),
                    label: const Text('Скопировать'),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              button(
                'Открыть управление',
                () => Navigator.of(context).pop(widget.demo ? null : result),
              ),
            ],
            if (busy) ...[
              const SizedBox(height: 20),
              const LinearProgressIndicator(),
              const SizedBox(height: 12),
              Text(
                progress.isEmpty ? 'Проверяем…' : progress,
                style: const TextStyle(color: muted),
              ),
            ],
            if (error != null) ...[
              const SizedBox(height: 16),
              Text(error!, style: const TextStyle(color: yellow)),
            ],
          ],
        ),
      ),
    ),
  );
}
