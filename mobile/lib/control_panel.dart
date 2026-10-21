import 'dart:convert';
import 'package:flutter/material.dart';
import 'router_controller.dart';
import 'app_style.dart';
import 'fan_control.dart';

class ControlPanel extends StatefulWidget {
  const ControlPanel({super.key, required this.router});
  final RouterController router;
  @override
  State<ControlPanel> createState() => _ControlPanelState();
}

class _ControlPanelState extends State<ControlPanel> {
  RouterController get router => widget.router;
  double? draftBrightness;
  bool applying = false;
  final Map<String, bool> draftWifi = {};
  bool get enabled => router.connected && !router.commandBusy && !applying;

  Future<void> apply(Map<String, dynamic> changes, {String? radioId}) async {
    setState(() => applying = true);
    try {
      await router.command('settings');
      final config = radioId == null
          ? (router.settings?['screen'])
          : (router.settings?['wifi'] as List? ?? [])
                .where((r) => r['id'] == radioId)
                .firstOrNull;
      if (config is! Map) {
        throw StateError('Устройство недоступно. Обнови состояние.');
      }
      final args = <String, dynamic>{'revision': config['revision']};
      if (radioId == null) {
        for (final field in [
          'brightness',
          'battery_timeout',
          'power_timeout',
        ]) {
          args[field] = config[field];
        }
      } else {
        args.addAll({
          'id': radioId,
          'ssid': config['ssid'],
          'enabled': config['enabled'],
        });
      }
      args.addAll(changes);
      final result = await router.command(
        radioId == null ? 'screen_set' : 'wifi_set',
        args,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(result['message'] as String? ?? 'Сохранено'),
            duration: const Duration(seconds: 3),
          ),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(_message(error))));
      }
    } finally {
      if (mounted) {
        setState(() {
          applying = false;
          draftBrightness = null;
          draftWifi.clear();
        });
      }
    }
  }

  Widget inlineTimer(String label, String field, dynamic value) => Row(
    children: [
      Expanded(
        child: Text(label, style: const TextStyle(color: muted, fontSize: 13)),
      ),
      const SizedBox(width: 8),
      PopupMenuButton<int>(
        tooltip: label,
        enabled: enabled,
        initialValue: value is int ? value : null,
        onSelected: (v) => apply({field: v}),
        itemBuilder: (_) => [
          for (final seconds in [10, 30, 60, 120, 300, 600, 3600, 86400])
            PopupMenuItem(value: seconds, child: Text(durationLabel(seconds))),
        ],
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 14),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                durationLabel(value),
                style: TextStyle(color: enabled ? yellow : muted),
              ),
              const SizedBox(width: 8),
              const Icon(Icons.expand_more, size: 18, color: muted),
            ],
          ),
        ),
      ),
    ],
  );

  Future<void> edit(BuildContext context, {String? radioId}) async {
    try {
      await router.command('settings');
      if (!context.mounted) return;
      Map<String, dynamic>? config;
      if (radioId == null) {
        final value = router.settings?['screen'];
        if (value is Map) config = Map<String, dynamic>.from(value);
      } else {
        for (final radio in router.settings?['wifi'] as List? ?? []) {
          if (radio['id'] == radioId) config = Map<String, dynamic>.from(radio);
        }
      }
      if (config == null) throw StateError('Устройство больше не доступно.');
      final message = await showDialog<String>(
        context: context,
        barrierDismissible: false,
        builder: (_) => ControlEditor(
          router: router,
          config: config!,
          wifi: radioId != null,
        ),
      );
      if (context.mounted && message != null) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(message)));
      }
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(_message(error))));
      }
    }
  }

  Future<void> refresh(BuildContext context) async {
    try {
      await router.command('settings');
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(_message(error))));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final settings = router.settings;
    final radios = settings?['wifi'] as List? ?? [];
    final screen = settings?['screen'];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            const Expanded(
              child: Text(
                'СЕТЬ И УСТРОЙСТВО',
                style: TextStyle(
                  color: muted,
                  letterSpacing: 1.5,
                  fontSize: 11,
                ),
              ),
            ),
            IconButton(
              tooltip: 'Обновить устройства',
              onPressed: enabled ? () => refresh(context) : null,
              icon: const Icon(Icons.refresh, size: 21, color: muted),
            ),
          ],
        ),
        SizedBox(
          height: 2,
          child: router.commandBusy || applying
              ? const LinearProgressIndicator(minHeight: 2)
              : null,
        ),
        if (settings == null || settings.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 24),
            child: Text(
              'Подключись, чтобы увидеть доступные настройки.',
              style: TextStyle(color: muted),
            ),
          ),
        for (final radio in radios) ...[
          ControlTile(
            icon: Icons.wifi,
            title: 'Wi-Fi',
            trailing: Switch(
              value: draftWifi[radio['id']] ?? radio['enabled'] == true,
              onChanged:
                  enabled &&
                      (radio['actions'] as List? ?? []).contains('wifi_set')
                  ? (v) {
                      setState(() => draftWifi[radio['id']] = v);
                      apply({'enabled': v}, radioId: radio['id']);
                    }
                  : null,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  radio['ssid'] as String? ?? 'Без имени',
                  style: const TextStyle(
                    fontSize: 19,
                    color: yellow,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  '${radio['label'] == 'Onboard' ? 'Встроенная плата' : radio['label']} · ${bandName(radio['band'])}',
                  style: const TextStyle(color: muted, fontSize: 12),
                ),
                const SizedBox(height: 3),
                Text(
                  radio['role'] == 'uplink'
                      ? 'Подключение к другой сети'
                      : 'Точка доступа',
                  style: const TextStyle(color: muted, fontSize: 12),
                ),
                if ((radio['actions'] as List? ?? []).contains('wifi_set')) ...[
                  const SizedBox(height: 12),
                  const Divider(color: rule, height: 1),
                  Material(
                    color: Colors.transparent,
                    child: InkWell(
                      borderRadius: BorderRadius.circular(3),
                      onTap: enabled
                          ? () => edit(context, radioId: radio['id'])
                          : null,
                      child: Padding(
                        padding: const EdgeInsets.symmetric(
                          vertical: 16,
                          horizontal: 4,
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                'Имя сети и пароль',
                                style: TextStyle(
                                  color: enabled ? yellow : muted,
                                ),
                              ),
                            ),
                            Icon(
                              Icons.chevron_right,
                              size: 19,
                              color: enabled ? yellow : muted,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
                if (!(radio['actions'] as List? ?? []).contains(
                  'wifi_set',
                )) ...[
                  const SizedBox(height: 8),
                  const Text(
                    'Доступен только просмотр',
                    style: TextStyle(color: muted, fontSize: 12),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 12),
        ],
        if (screen is Map) ...[
          ControlTile(
            icon: Icons.brightness_6_outlined,
            title: 'Экран',
            value: '${draftBrightness?.round() ?? screen['brightness']}%',
            numeric: true,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Яркость',
                  style: TextStyle(color: muted, fontSize: 12),
                ),
                Slider(
                  value:
                      (draftBrightness ??
                              (screen['brightness'] as num).toDouble())
                          .clamp(5, 100),
                  min: 5,
                  max: 100,
                  divisions: 19,
                  label: '${draftBrightness?.round() ?? screen['brightness']}%',
                  onChanged:
                      enabled &&
                          (screen['actions'] as List? ?? []).contains(
                            'screen_set',
                          )
                      ? (v) => setState(() => draftBrightness = v)
                      : null,
                  onChangeEnd: (v) => apply({'brightness': v.round()}),
                ),
                const Divider(color: rule, height: 1),
                inlineTimer(
                  'Гасить от батареи',
                  'battery_timeout',
                  screen['battery_timeout'],
                ),
                inlineTimer(
                  'От внешнего питания',
                  'power_timeout',
                  screen['power_timeout'],
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
        ],
        if ((settings?['unavailable'] as List? ?? []).isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: Text(
              'Службы недоступны: ${(settings!['unavailable'] as List).join(', ')}',
              style: const TextStyle(color: muted, fontSize: 12),
            ),
          ),
        FanControl(router: router),
        if ((settings?['actions'] as List? ?? []).contains('reboot'))
          ControlTile(
            icon: Icons.restart_alt,
            title: 'Перезагрузка',
            onTap: enabled ? () => reboot(context) : null,
            child: const Text(
              'С подтверждением перед запуском',
              style: TextStyle(color: muted, fontSize: 12),
            ),
          ),
      ],
    );
  }

  Future<void> reboot(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Перезагрузить Photonicat?'),
        content: const Text(
          'Интернет и Bluetooth временно отключатся. После запуска снова подключись в приложении.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Перезагрузить'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      final result = await router.command('reboot', {'confirm': 'reboot'});
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(result['message'])));
      }
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(_message(error))));
      }
    }
  }
}

String bandName(dynamic value) => switch (value) {
  '2g' => '2,4 ГГц',
  '5g' => '5 ГГц',
  '6g' => '6 ГГц',
  _ => '$value',
};
String durationLabel(dynamic value) {
  if (value is! num) return '—';
  final seconds = value.toInt();
  if (seconds >= 3600 && seconds % 3600 == 0) return '${seconds ~/ 3600} ч';
  if (seconds >= 60 && seconds % 60 == 0) return '${seconds ~/ 60} мин';
  return '$seconds с';
}

class ControlTile extends StatelessWidget {
  const ControlTile({
    super.key,
    required this.icon,
    required this.title,
    required this.child,
    this.value,
    this.trailing,
    this.onTap,
    this.active = true,
    this.numeric = false,
  });
  final IconData icon;
  final String title;
  final Widget child;
  final String? value;
  final Widget? trailing;
  final VoidCallback? onTap;
  final bool active, numeric;
  @override
  Widget build(BuildContext context) => Material(
    color: const Color(0xff0a0b08),
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(6),
      side: const BorderSide(color: rule),
    ),
    clipBehavior: Clip.antiAlias,
    child: InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(icon, color: yellow, size: 23),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                if (value != null) ...[
                  const SizedBox(width: 8),
                  Text(
                    value!,
                    style: numeric
                        ? digits(22)
                        : TextStyle(
                            color: active ? yellow : muted,
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 1,
                          ),
                  ),
                ],
                ?trailing,
                if (onTap != null) ...[
                  const SizedBox(width: 10),
                  const Icon(Icons.chevron_right, color: muted, size: 19),
                ],
              ],
            ),
            const SizedBox(height: 14),
            child,
          ],
        ),
      ),
    ),
  );
}

String _message(Object error) => error is StateError
    ? error.message.toString()
    : 'Не удалось выполнить команду. Обнови состояние.';

class ControlEditor extends StatefulWidget {
  const ControlEditor({
    super.key,
    required this.router,
    required this.config,
    required this.wifi,
  });
  final RouterController router;
  final Map<String, dynamic> config;
  final bool wifi;
  @override
  State<ControlEditor> createState() => _ControlEditorState();
}

class _ControlEditorState extends State<ControlEditor> {
  final form = GlobalKey<FormState>();
  late final TextEditingController ssid;
  final password = TextEditingController();
  late bool enabled;
  late int brightness, batteryTimeout, powerTimeout;
  bool saving = false;
  String? error;
  @override
  void initState() {
    super.initState();
    ssid = TextEditingController(text: widget.config['ssid'] as String? ?? '');
    enabled = widget.config['enabled'] == true;
    brightness = (widget.config['brightness'] as num?)?.toInt() ?? 100;
    batteryTimeout = (widget.config['battery_timeout'] as num?)?.toInt() ?? 60;
    powerTimeout = (widget.config['power_timeout'] as num?)?.toInt() ?? 86400;
  }

  @override
  void dispose() {
    ssid.dispose();
    password.dispose();
    super.dispose();
  }

  Widget timer(String label, int value, ValueChanged<int> change) {
    final choices = {10, 30, 60, 120, 300, 600, 3600, 86400, value}.toList()
      ..sort();
    return DropdownButtonFormField<int>(
      initialValue: value,
      decoration: InputDecoration(labelText: label),
      items: choices
          .map(
            (v) => DropdownMenuItem(
              value: v,
              child: Text(
                v >= 3600 && v % 3600 == 0
                    ? '${v ~/ 3600} ч'
                    : v >= 60 && v % 60 == 0
                    ? '${v ~/ 60} мин'
                    : '$v сек',
              ),
            ),
          )
          .toList(),
      onChanged: saving
          ? null
          : (v) {
              if (v != null) setState(() => change(v));
            },
    );
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !saving,
    child: AlertDialog(
      title: Text(widget.wifi ? 'Имя сети и пароль' : 'Встроенный экран'),
      content: SizedBox(
        width: 360,
        child: SingleChildScrollView(
          child: Form(
            key: form,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (widget.wifi) ...[
                  TextFormField(
                    controller: ssid,
                    enabled: !saving,
                    decoration: const InputDecoration(labelText: 'Имя сети'),
                    validator: (s) =>
                        s == null ||
                            utf8.encode(s).isEmpty ||
                            utf8.encode(s).length > 32 ||
                            s.runes.any((c) => c < 32 || c == 127)
                        ? 'От 1 до 32 байт UTF-8'
                        : null,
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: password,
                    enabled: !saving,
                    obscureText: true,
                    autocorrect: false,
                    enableSuggestions: false,
                    decoration: const InputDecoration(
                      labelText: 'Новый пароль',
                      helperText: 'Пусто — сохранить текущий пароль',
                      helperMaxLines: 2,
                    ),
                    validator: (s) => s == null || s.isEmpty
                        ? null
                        : s.length < 8 ||
                              s.length > 63 ||
                              s.runes.any((c) => c < 32 || c > 126)
                        ? '8–63 символа: латиница, цифры, знаки'
                        : null,
                  ),
                  const SizedBox(height: 18),
                  const Text(
                    'После сохранения устройства Wi-Fi могут отключиться. Связь приложения с роутером идёт по Bluetooth.',
                    style: TextStyle(color: muted, fontSize: 12),
                  ),
                ] else ...[
                  Text(
                    'Яркость · $brightness%',
                    style: const TextStyle(color: yellow, fontSize: 20),
                  ),
                  Slider(
                    value: brightness.clamp(5, 100).toDouble(),
                    min: 5,
                    max: 100,
                    divisions: 19,
                    onChanged: saving
                        ? null
                        : (v) => setState(() => brightness = v.round()),
                  ),
                  timer(
                    'Гасить экран от батареи через',
                    batteryTimeout,
                    (v) => batteryTimeout = v,
                  ),
                  const SizedBox(height: 14),
                  timer(
                    'От внешнего питания через',
                    powerTimeout,
                    (v) => powerTimeout = v,
                  ),
                  const SizedBox(height: 14),
                  const Text(
                    'Настройки сохраняются после перезагрузки.',
                    style: TextStyle(color: muted, fontSize: 12),
                  ),
                ],
                if (error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 16),
                    child: Text(error!, style: const TextStyle(color: yellow)),
                  ),
                if (saving)
                  const Padding(
                    padding: EdgeInsets.only(top: 16),
                    child: LinearProgressIndicator(),
                  ),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.pop(context),
          child: const Text('Отмена'),
        ),
        FilledButton(
          onPressed: saving ? null : save,
          child: Text(saving ? 'Сохраняю…' : 'Сохранить'),
        ),
      ],
    ),
  );

  Future<void> save() async {
    if (!form.currentState!.validate()) return;
    setState(() {
      saving = true;
      error = null;
    });
    try {
      final args = <String, dynamic>{'revision': widget.config['revision']};
      if (widget.wifi) {
        args.addAll({
          'id': widget.config['id'],
          'ssid': ssid.text,
          'enabled': enabled,
        });
        if (password.text.isNotEmpty) args['password'] = password.text;
      } else {
        args.addAll({
          'brightness': brightness,
          'battery_timeout': batteryTimeout,
          'power_timeout': powerTimeout,
        });
      }
      final result = await widget.router.command(
        widget.wifi ? 'wifi_set' : 'screen_set',
        args,
      );
      if (mounted) {
        Navigator.pop(context, result['message'] as String? ?? 'Сохранено.');
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          saving = false;
          error = _message(e);
        });
      }
    }
  }
}
