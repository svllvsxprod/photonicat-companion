import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'app_style.dart';
import 'router_controller.dart';
import 'wifi_vpn_panel.dart';
import 'internet_mode_switch.dart';

class VpnPanel extends StatefulWidget {
  const VpnPanel({super.key, required this.router});
  final RouterController router;
  @override
  State<VpnPanel> createState() => _VpnPanelState();
}

class _VpnPanelState extends State<VpnPanel> {
  RouterController get router => widget.router;
  bool loading = false;
  bool initialRequested = false;
  Timer? portRefresh;
  String? problem;
  DateTime? updated;
  final checks = <String, Map<String, dynamic>>{};
  bool get enabled => router.connected && !router.commandBusy && !loading;
  @override
  void initState() {
    super.initState();
    loadWhenConnected();
    portRefresh = Timer.periodic(const Duration(seconds: 15), (_) {
      if (mounted && enabled && router.vpn?['ports']?['installed'] == true) {
        refresh();
      }
    });
  }

  @override
  void dispose() {
    portRefresh?.cancel();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant VpnPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    loadWhenConnected();
  }

  void loadWhenConnected() {
    if (initialRequested || !enabled) return;
    initialRequested = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && enabled) {
        refresh();
      } else {
        initialRequested = false;
      }
    });
  }

  String message(Object error) => error
      .toString()
      .replaceFirst('Bad state: ', '')
      .replaceFirst('StateError: ', '');
  Future<void> refresh() async {
    if (!enabled) return;
    setState(() {
      loading = true;
      problem = null;
    });
    try {
      await router.command('vpn_get');
      await router.command('settings');
      if (mounted) setState(() => updated = DateTime.now());
    } catch (e) {
      if (mounted) setState(() => problem = message(e));
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<bool> change(
    String action,
    Map<String, dynamic> args, {
    String? revision,
  }) async {
    if (!enabled) return false;
    setState(() {
      loading = true;
      problem = null;
    });
    try {
      final reply = await router.command('vpn_set', {
        'action': action,
        'revision': revision ?? router.vpn?['revision'],
        ...args,
      });
      if (!mounted) return true;
      setState(() {
        updated = DateTime.now();
        if (reply['check'] is Map) {
          final check = Map<String, dynamic>.from(reply['check']);
          checks[check['engine'] as String] = check;
        }
      });
      if (reply['message'] is String) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(reply['message'])));
      }
      return true;
    } catch (e) {
      if (mounted) {
        setState(() => problem = message(e));
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(message(e))));
      }
      return false;
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> choose(String engine) async {
    final vpn = router.vpn!;
    final revision = vpn['revision'] as String;
    final data = Map<String, dynamic>.from(vpn[engine]);
    final entries = engine == 'amneziawg'
        ? (data['profiles'] as List)
              .map((p) => MapEntry(p['id'] as String, p['label'] as String))
              .toList()
        : (data['nodes'] as List).map((p) => MapEntry(p as String, p)).toList();
    final picked = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xff0a0b08),
      showDragHandle: true,
      builder: (context) => _ProfilePicker(
        entries: entries,
        selected: data['selected'],
        title: engine == 'amneziawg' ? 'Профиль Amnezia' : 'Сервер Mihomo',
      ),
    );
    if (picked != null && mounted && picked != data['selected']) {
      await change(engine == 'amneziawg' ? 'awg' : 'node', {
        'value': picked,
      }, revision: revision);
    }
  }

  Future<String?> scan(String title) => Navigator.of(
    context,
  ).push<String>(MaterialPageRoute(builder: (_) => _QrScanner(title: title)));

  Future<void> addAwg(bool qr) async {
    String? text;
    var name = '';
    try {
      if (qr) {
        text = await scan('QR профиля Amnezia');
      } else {
        final file = await FilePicker.pickFile(type: FileType.any);
        if (file == null) return;
        final length = await file.length();
        if (length == null || length > 24576) {
          throw StateError('Выбери конфиг размером до 24 КБ.');
        }
        text = utf8.decode(await file.readAsBytes());
        name = file.name.replaceFirst(
          RegExp(r'\.(conf|vpn|json)$', caseSensitive: false),
          '',
        );
      }
      if (text == null || !mounted) return;
      if (utf8.encode(text).length > 24576) {
        throw StateError('Профиль больше 24 КБ.');
      }
      await importDialog(awg: true, initialName: name, content: text);
    } catch (e) {
      if (mounted) setState(() => problem = message(e));
    }
  }

  Future<void> addSubscription(bool qr) async {
    final value = qr ? await scan('QR подписки Mihomo') : '';
    if (value == null || !mounted) return;
    await importDialog(awg: false, content: value);
  }

  Future<void> importDialog({
    required bool awg,
    required String content,
    String initialName = '',
  }) async {
    final name = TextEditingController(text: initialName);
    final link = TextEditingController(text: content);
    final form = GlobalKey<FormState>();
    final values = await showDialog<Map<String, String>>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(awg ? 'Добавить Amnezia' : 'Добавить подписку'),
        content: SingleChildScrollView(
          child: Form(
            key: form,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextFormField(
                  controller: name,
                  autofocus: true,
                  maxLength: 64,
                  decoration: const InputDecoration(labelText: 'Название'),
                  validator: (v) =>
                      (v?.trim().isEmpty ?? true) ? 'Введи название' : null,
                ),
                if (awg)
                  const Text(
                    'Профиль прочитан. Ключи будут переданы на роутер по защищённому Bluetooth-соединению.',
                    style: TextStyle(color: muted, fontSize: 13),
                  )
                else ...[
                  TextFormField(
                    controller: link,
                    obscureText: true,
                    autocorrect: false,
                    enableSuggestions: false,
                    keyboardType: TextInputType.url,
                    decoration: const InputDecoration(
                      labelText: 'HTTPS-ссылка подписки',
                    ),
                    validator: (v) {
                      final uri = Uri.tryParse(v?.trim() ?? '');
                      return uri?.scheme == 'https' &&
                              (uri?.host.isNotEmpty ?? false)
                          ? null
                          : 'Нужна ссылка https://…';
                    },
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    'Формат Mihomo / Clash YAML. Добавление не меняет выбранный сервер.',
                    style: TextStyle(color: muted, fontSize: 13),
                  ),
                ],
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Отмена'),
          ),
          ListenableBuilder(
            listenable: router,
            builder: (context, _) => TextButton(
              onPressed: router.connected && !router.commandBusy
                  ? () {
                      if (form.currentState!.validate()) {
                        Navigator.pop(context, {
                          'label': name.text.trim(),
                          if (!awg) 'url': link.text.trim(),
                        });
                      }
                    }
                  : null,
              child: Text(router.connected ? 'Добавить' : 'Ожидание связи'),
            ),
          ),
        ],
      ),
    );
    // Dialog route can still be animating its editable fields out.
    await Future<void>.delayed(const Duration(milliseconds: 250));
    name.dispose();
    link.dispose();
    if (values != null && mounted) {
      await change(awg ? 'import-awg' : 'add-subscription', {
        ...values,
        if (awg) 'text': content,
      });
    }
  }

  Future<void> remove(String action, String id, String name) async {
    final revision = router.vpn?['revision'] as String?;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Удалить с роутера?'),
        content: Text(
          '«$name» будет удалён. Для возвращения понадобится файл, QR-код или ссылка.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Отмена'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Удалить'),
          ),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      await change(action, {'id': id}, revision: revision);
    }
  }

  @override
  Widget build(BuildContext context) {
    final vpn = router.vpn;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(child: Text('VPN', style: digits(30))),
            IconButton(
              tooltip: 'Обновить VPN',
              onPressed: enabled ? refresh : null,
              icon: const Icon(Icons.refresh, color: yellow),
            ),
          ],
        ),
        const SizedBox(height: 8),
        const Text(
          'Два ядра · один профиль на каждом',
          style: TextStyle(color: muted),
        ),
        const SizedBox(height: 16),
        SizedBox(
          height: 2,
          child: loading ? const LinearProgressIndicator(minHeight: 2) : null,
        ),
        if (problem != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 14),
            child: Text(problem!, style: const TextStyle(color: yellow)),
          ),
        if (!router.connected)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 14),
            child: Text(
              'Нет связи с роутером. Выбор недоступен; показаны последние полученные данные.',
              style: TextStyle(color: muted),
            ),
          ),
        if (vpn == null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 30),
            child: Text(
              loading
                  ? 'Получаем профили с роутера…'
                  : router.connected
                  ? 'Нажми обновление, чтобы получить профили.'
                  : 'Подключись к роутеру, чтобы получить профили.',
              style: const TextStyle(color: muted),
            ),
          )
        else if (vpn['available'] != true)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 30),
            child: Text('VPN-служба на этом роутере ещё не установлена.'),
          )
        else ...[
          const SizedBox(height: 20),
          const Text(
            'АКТИВНЫЙ ВЫХОД',
            style: TextStyle(color: muted, letterSpacing: 1.5, fontSize: 11),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              for (final engine in ['amneziawg', 'mihomo'])
                Expanded(
                  child: Padding(
                    padding: EdgeInsets.only(
                      right: engine == 'amneziawg' ? 6 : 0,
                      left: engine == 'mihomo' ? 6 : 0,
                    ),
                    child: OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        disabledForegroundColor: vpn['active'] == engine
                            ? Colors.black
                            : muted,
                        disabledBackgroundColor: vpn['active'] == engine
                            ? yellow
                            : Colors.transparent,
                        backgroundColor: vpn['active'] == engine
                            ? yellow
                            : Colors.transparent,
                        foregroundColor: vpn['active'] == engine
                            ? Colors.black
                            : muted,
                      ),
                      onPressed:
                          enabled &&
                              vpn['active'] != engine &&
                              vpn[engine]['running'] == true
                          ? () => change('engine', {'value': engine})
                          : null,
                      icon: Icon(
                        vpn['active'] == engine
                            ? Icons.check_circle_outline
                            : Icons.swap_horiz,
                        size: 18,
                      ),
                      label: Text(engine == 'amneziawg' ? 'Amnezia' : 'Mihomo'),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 14),
          Text(
            vpn['routing_scope'] == 'lan'
                ? 'Выбранное ядро используется для подключений в режиме VPN. При его отказе их интернет блокируется.'
                : 'Сети ещё не назначены на VPN. Этот выбор пока не меняет интернет на телефоне и устройствах LAN.',
            style: const TextStyle(color: muted, fontSize: 12, height: 1.5),
          ),
          const SizedBox(height: 24),
          if (vpn['ports']?['installed'] == true) ...[
            portsCard(Map<String, dynamic>.from(vpn['ports'])),
            const SizedBox(height: 20),
            WifiVpnPanel(router: router),
            const SizedBox(height: 24),
          ],
          engineCard('amneziawg', vpn),
          const SizedBox(height: 20),
          engineCard('mihomo', vpn),
          if (vpn['nodes_truncated'] == true)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: Text(
                'Показаны первые 64 сервера. Уменьши список серверов в подписке, чтобы видеть остальные.',
                style: TextStyle(color: muted, fontSize: 12),
              ),
            ),
          const SizedBox(height: 20),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text('Профили и подписки'),
            subtitle: const Text(
              'Обновить или удалить',
              style: TextStyle(color: muted, fontSize: 12),
            ),
            children: [
              for (final profile in vpn['amneziawg']['profiles'] as List)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.vpn_key_outlined, size: 20),
                  title: Text(
                    profile['label'],
                    style: const TextStyle(fontSize: 13),
                  ),
                  subtitle: profile['id'] == vpn['amneziawg']['selected']
                      ? const Text(
                          'Выбран · сначала переключи профиль',
                          style: TextStyle(fontSize: 11),
                        )
                      : null,
                  trailing: IconButton(
                    tooltip: 'Удалить профиль',
                    onPressed:
                        enabled && profile['id'] != vpn['amneziawg']['selected']
                        ? () => remove(
                            'delete-awg',
                            profile['id'],
                            profile['label'],
                          )
                        : null,
                    icon: const Icon(Icons.delete_outline),
                  ),
                ),
              const Divider(color: rule),
              for (final sub in vpn['subscriptions'] as List? ?? [])
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(sub['label']),
                  subtitle: Text(
                    '${sub['count']} серверов',
                    style: const TextStyle(color: muted, fontSize: 12),
                  ),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        tooltip: 'Обновить подписку',
                        onPressed: enabled
                            ? () => change('update-subscription', {
                                'id': sub['id'],
                              })
                            : null,
                        icon: const Icon(Icons.sync),
                      ),
                      IconButton(
                        tooltip: 'Удалить подписку',
                        onPressed: enabled
                            ? () => remove(
                                'delete-subscription',
                                sub['id'],
                                sub['label'],
                              )
                            : null,
                        icon: const Icon(Icons.delete_outline),
                      ),
                    ],
                  ),
                ),
            ],
          ),
          if (updated != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(
                'Профили обновлены в ${updated!.hour.toString().padLeft(2, '0')}:${updated!.minute.toString().padLeft(2, '0')}',
                style: const TextStyle(color: muted, fontSize: 11),
              ),
            ),
        ],
      ],
    );
  }

  Widget engineCard(String engine, Map<String, dynamic> vpn) {
    final data = Map<String, dynamic>.from(vpn[engine]);
    final awg = engine == 'amneziawg';
    String selected = data['selected'] as String? ?? 'Не выбран';
    if (awg) {
      for (final p in data['profiles'] as List) {
        if (p['id'] == selected) {
          selected = p['label'];
          break;
        }
      }
    }
    final check = checks[engine];
    final validCheck = check != null && check['selected'] == data['selected'];
    return Container(
      decoration: BoxDecoration(
        border: Border.all(color: rule),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 10),
            child: Row(
              children: [
                Icon(
                  awg ? Icons.shield_outlined : Icons.hub_outlined,
                  color: yellow,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    awg ? 'AMNEZIA WG' : 'MIHOMO',
                    style: digits(15, color: Colors.white),
                  ),
                ),
                Icon(
                  data['running'] == true
                      ? Icons.check_circle_outline
                      : Icons.error_outline,
                  color: data['running'] == true ? yellow : muted,
                  size: 18,
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              data['running'] == true ? 'Ядро работает' : 'Ядро недоступно',
              style: const TextStyle(color: muted, fontSize: 12),
            ),
          ),
          const SizedBox(height: 10),
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: enabled ? () => choose(engine) : null,
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 16,
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            awg ? 'ПРОФИЛЬ' : 'СЕРВЕР',
                            style: const TextStyle(
                              color: muted,
                              fontSize: 10,
                              letterSpacing: 1,
                            ),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            selected,
                            style: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    const Icon(Icons.unfold_more, color: yellow),
                  ],
                ),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                OutlinedButton.icon(
                  onPressed: enabled && data['running'] == true
                      ? () => change('check', {'value': engine})
                      : null,
                  icon: const Icon(Icons.network_check, size: 18),
                  label: const Text('Проверить выход'),
                ),
                if (validCheck)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      check['ok'] == true
                          ? 'Выход проверен · ${check['ip']}'
                          : 'Нет ответа через этот профиль. Для мобильного сервера проверь в сети оператора.',
                      style: const TextStyle(color: muted, fontSize: 12),
                    ),
                  ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: TextButton.icon(
                        onPressed: enabled
                            ? () => awg ? addAwg(false) : addSubscription(false)
                            : null,
                        icon: Icon(
                          awg ? Icons.file_open_outlined : Icons.add_link,
                          size: 18,
                        ),
                        label: Text(awg ? 'Файл' : 'Подписка'),
                      ),
                    ),
                    Expanded(
                      child: TextButton.icon(
                        onPressed: enabled
                            ? () => awg ? addAwg(true) : addSubscription(true)
                            : null,
                        icon: const Icon(Icons.qr_code_scanner, size: 18),
                        label: const Text('QR-код'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget portsCard(Map<String, dynamic> p) {
    final role = switch (p['wan_role']) {
      'uplink' => 'Приём интернета',
      'share' => 'Раздача без VPN',
      'idle' => 'Кабель не подключён',
      'error' => 'Определяем повторно…',
      _ => 'Определяем подключение…',
    };
    final lan = switch (p['lan_state']) {
      'paused' => 'Интернет заблокирован',
      'direct' => 'Интернет без VPN',
      'vpn' => 'Маршрут через VPN готов',
      _ => 'VPN недоступен · интернет заблокирован',
    };
    final safe = p['kill_switch'] == true;
    Widget card(String title, IconData icon, List<Widget> children) =>
        Container(
          decoration: BoxDecoration(
            border: Border.all(color: rule),
            borderRadius: BorderRadius.circular(6),
          ),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Icon(icon, color: yellow),
                  const SizedBox(width: 10),
                  Text(title, style: digits(17, color: Colors.white)),
                ],
              ),
              const SizedBox(height: 16),
              ...children,
            ],
          ),
        );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        card('WAN', Icons.input, [
          const Text('Direct', style: TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          Text(role, style: const TextStyle(color: muted, fontSize: 13)),
          if (p['wan_link'] == true && p['wan_address'] != null)
            Text(
              p['wan_address'],
              style: const TextStyle(color: muted, fontSize: 12),
            ),
          const SizedBox(height: 12),
          Row(
            children: [
              for (final mode in const {
                'auto': 'Авто',
                'uplink': 'Приём',
                'share': 'Раздача',
              }.entries)
                Expanded(
                  child: Padding(
                    padding: EdgeInsets.only(
                      right: mode.key == 'share' ? 0 : 6,
                    ),
                    child: OutlinedButton(
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 4),
                        backgroundColor: p['wan_mode'] == mode.key
                            ? yellow
                            : Colors.transparent,
                        foregroundColor: p['wan_mode'] == mode.key
                            ? Colors.black
                            : yellow,
                        disabledForegroundColor: p['wan_mode'] == mode.key
                            ? Colors.black
                            : muted,
                      ),
                      onPressed: enabled && p['wan_mode'] != mode.key
                          ? () => change('ports', {
                              'setting': 'wan_mode',
                              'value': mode.key,
                            })
                          : null,
                      child: Text(
                        mode.value,
                        style: const TextStyle(fontSize: 12),
                      ),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            p['wan_mode'] == 'share' &&
                    const [
                      'dhcp_server',
                      'ipv6_router',
                    ].contains(p['wan_reason'])
                ? 'В кабеле найден другой роутер. Раздача не включена, чтобы не мешать его сети.'
                : 'Авто ищет источник по DHCP и IPv6. Для сети со статическим адресом выбери «Приём».',
            style: const TextStyle(color: muted, fontSize: 11, height: 1.4),
          ),
        ]),
        const SizedBox(height: 20),
        card('LAN', Icons.settings_ethernet, [
          Text(
            '${p['lan_link'] == true ? 'Кабель подключён' : 'Нет кабеля'} · ${p['lan_address']}',
            style: const TextStyle(color: muted, fontSize: 12),
          ),
          const SizedBox(height: 8),
          InternetModeSwitch(
            switchKey: const ValueKey('lan-internet-mode'),
            vpn: p['lan_mode'] != 'direct',
            onChanged: enabled
                ? (value) => change('ports', {
                    'setting': 'lan_mode',
                    'value': value ? 'vpn' : 'direct',
                  })
                : null,
          ),
          Text(lan, style: const TextStyle(color: muted, fontSize: 12)),
          const SizedBox(height: 14),
          Row(
            children: [
              Icon(
                safe ? Icons.shield_outlined : Icons.warning_amber,
                color: yellow,
                size: 18,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  p['lan_mode'] == 'direct'
                      ? 'Direct · VPN выключен'
                      : safe
                      ? 'Kill switch включён'
                      : 'Защита требует проверки',
                  style: const TextStyle(color: yellow, fontSize: 13),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            p['lan_mode'] == 'direct'
                ? 'Интернет идёт напрямую через доступный источник.'
                : 'DNS и IPv6 — через VPN. Если VPN недоступен, интернет блокируется.',
            style: TextStyle(color: muted, fontSize: 12, height: 1.5),
          ),
        ]),
      ],
    );
  }
}

class _ProfilePicker extends StatefulWidget {
  const _ProfilePicker({
    required this.entries,
    required this.selected,
    required this.title,
  });
  final List<MapEntry<String, String>> entries;
  final String? selected;
  final String title;
  @override
  State<_ProfilePicker> createState() => _ProfilePickerState();
}

class _ProfilePickerState extends State<_ProfilePicker> {
  String query = '';
  @override
  Widget build(BuildContext context) => SafeArea(
    child: SizedBox(
      height: MediaQuery.sizeOf(context).height * .72,
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          20,
          0,
          20,
          MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.title,
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 16),
            TextField(
              decoration: const InputDecoration(
                hintText: 'Поиск',
                prefixIcon: Icon(Icons.search),
              ),
              onChanged: (v) => setState(() => query = v.toLowerCase()),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: ListView(
                children: [
                  for (final entry in widget.entries.where(
                    (e) => e.value.toLowerCase().contains(query),
                  ))
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(entry.value),
                      trailing: entry.key == widget.selected
                          ? const Icon(Icons.check, color: yellow)
                          : null,
                      onTap: () => Navigator.pop(context, entry.key),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

class _QrScanner extends StatefulWidget {
  const _QrScanner({required this.title});
  final String title;
  @override
  State<_QrScanner> createState() => _QrScannerState();
}

class _QrScannerState extends State<_QrScanner> {
  final controller = MobileScannerController(formats: [BarcodeFormat.qrCode]);
  bool handled = false;
  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  Future<void> imageQr() async {
    File? temporary;
    try {
      final file = await FilePicker.pickFile(type: FileType.image);
      if (file == null || !mounted) return;
      final size = await file.length();
      if (size == null || size > 8 * 1024 * 1024) {
        throw StateError('Изображение должно быть меньше 8 МБ.');
      }
      final directory = await getTemporaryDirectory();
      temporary = File(
        '${directory.path}/vpn-qr-${DateTime.now().microsecondsSinceEpoch}.png',
      );
      await temporary.writeAsBytes(await file.readAsBytes(), flush: true);
      final capture = await controller.analyzeImage(temporary.path);
      final values =
          capture?.barcodes
              .map((b) => b.rawValue)
              .whereType<String>()
              .where((s) => s.isNotEmpty)
              .toList() ??
          [];
      if (values.length != 1) {
        throw StateError('Нужно изображение с одним читаемым QR-кодом.');
      }
      if (mounted && !handled) {
        handled = true;
        Navigator.pop(context, values.single);
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Не удалось прочитать QR. Выбери изображение до 8 МБ с одним QR-кодом.',
            ),
          ),
        );
      }
    } finally {
      if (temporary != null && await temporary.exists()) {
        await temporary.delete();
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(widget.title),
      actions: [
        IconButton(
          tooltip: 'QR из изображения',
          onPressed: imageQr,
          icon: const Icon(Icons.image_outlined),
        ),
        IconButton(
          tooltip: 'Подсветка',
          onPressed: controller.toggleTorch,
          icon: const Icon(Icons.flashlight_on_outlined),
        ),
      ],
    ),
    body: Column(
      children: [
        Expanded(
          child: MobileScanner(
            controller: controller,
            onDetect: (capture) {
              if (handled) return;
              for (final code in capture.barcodes) {
                final text = code.rawValue;
                if (text != null && text.isNotEmpty) {
                  handled = true;
                  Navigator.pop(context, text);
                  break;
                }
              }
            },
            errorBuilder: (context, error) => const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text(
                  'Камера недоступна. Разреши доступ к камере в настройках приложения или используй файл / ссылку.',
                ),
              ),
            ),
          ),
        ),
        const SafeArea(
          top: false,
          child: Padding(
            padding: EdgeInsets.all(24),
            child: Text(
              'Наведи камеру на QR-код. После считывания можно проверить название и подтвердить добавление.',
              style: TextStyle(color: muted),
            ),
          ),
        ),
      ],
    ),
  );
}
