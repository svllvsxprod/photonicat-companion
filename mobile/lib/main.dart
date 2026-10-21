import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'router_controller.dart';
import 'control_panel.dart';
import 'vpn_panel.dart';
import 'sms_page.dart';
import 'app_style.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
      systemNavigationBarColor: Colors.black,
      systemNavigationBarIconBrightness: Brightness.light,
    ),
  );
  runApp(const PhotonicatApp());
}

class PhotonicatApp extends StatelessWidget {
  const PhotonicatApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Photonicat',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: Colors.black,
      splashFactory: InkRipple.splashFactory,
      splashColor: const Color(0x22ffea00),
      highlightColor: const Color(0x10ffea00),
      snackBarTheme: const SnackBarThemeData(
        backgroundColor: Color(0xff202218),
        contentTextStyle: TextStyle(color: Colors.white),
        behavior: SnackBarBehavior.floating,
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: const Color(0xff0a0b08),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: const BorderSide(color: rule),
        ),
      ),
      colorScheme: const ColorScheme.dark(
        primary: yellow,
        onPrimary: Colors.black,
        surface: Colors.black,
        onSurface: Colors.white,
        outline: rule,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(48, 52),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(5)),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(48, 52),
          foregroundColor: yellow,
          side: const BorderSide(color: rule),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(5)),
        ),
      ),
      textTheme: const TextTheme(
        bodyMedium: TextStyle(fontSize: 14, height: 1.45),
        bodySmall: TextStyle(color: muted, fontSize: 12, height: 1.5),
      ),
    ),
    home: const RouterScreen(),
  );
}

class RouterScreen extends StatefulWidget {
  const RouterScreen({super.key});
  @override
  State<RouterScreen> createState() => _RouterScreenState();
}

class _RouterScreenState extends State<RouterScreen>
    with WidgetsBindingObserver {
  final router = RouterController();
  final code = TextEditingController();
  int tab = 0;
  bool invalid = false;
  Timer? clock;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    router.addListener(changed);
    router.initialize();
    clock = Timer.periodic(const Duration(seconds: 1), (_) => changed());
  }

  void changed() {
    if (mounted) setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) {
      router.foreground(false);
    } else if (state == AppLifecycleState.resumed) {
      router.foreground(true);
    }
  }

  @override
  void dispose() {
    clock?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    router.removeListener(changed);
    router.dispose();
    code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                key: ValueKey(tab),
                padding: const EdgeInsets.fromLTRB(24, 24, 24, 20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        SvgPicture.asset(
                          'assets/icons/logoLarge.svg',
                          width: 25,
                          height: 31,
                          colorFilter: const ColorFilter.mode(
                            yellow,
                            BlendMode.srcIn,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: FittedBox(
                            fit: BoxFit.scaleDown,
                            alignment: Alignment.centerLeft,
                            child: Text(
                              'PHOTONICAT',
                              style: digits(21, color: Colors.white),
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 3,
                          ),
                          decoration: BoxDecoration(
                            border: Border.all(color: yellow),
                          ),
                          child: Text('02', style: digits(17)),
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        Container(
                          width: 6,
                          height: 6,
                          decoration: BoxDecoration(
                            color: router.connected ? yellow : muted,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Flexible(
                          child: Text(
                            router.phase,
                            style: TextStyle(
                              color: router.connected ? yellow : muted,
                              fontSize: 12,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 27),
                    if (!router.bound)
                      pairing()
                    else ...[
                      if (router.error != null)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 16),
                          child: Text(
                            router.error!,
                            style: const TextStyle(color: yellow),
                          ),
                        ),
                      if (tab != 2 &&
                          tab != 4 &&
                          router.data != null &&
                          !router.fresh)
                        const Padding(
                          padding: EdgeInsets.only(bottom: 16),
                          child: Text(
                            'Последние данные · связь не обновляется',
                            style: TextStyle(color: muted, fontSize: 12),
                          ),
                        ),
                      if (tab == 0)
                        dashboard()
                      else if (tab == 1)
                        devices()
                      else if (tab == 2)
                        VpnPanel(router: router)
                      else if (tab == 3)
                        details()
                      else
                        SmsPage(router: router, embedded: true),
                      const SizedBox(height: 24),
                      if ((tab != 2 && tab != 4) || !router.connected)
                        Row(
                          children: [
                            Expanded(
                              child: FilledButton(
                                onPressed: router.commandBusy
                                    ? null
                                    : router.busy
                                    ? null
                                    : router.connected
                                    ? router.refresh
                                    : router.connect,
                                child: Text(
                                  router.busy
                                      ? 'Подключение…'
                                      : router.connected
                                      ? 'Обновить'
                                      : 'Подключиться',
                                ),
                              ),
                            ),
                            if (router.connected || router.busy) ...[
                              const SizedBox(width: 10),
                              OutlinedButton(
                                onPressed: router.commandBusy
                                    ? null
                                    : router.disconnect,
                                child: const Text('Отключить'),
                              ),
                            ],
                          ],
                        ),
                      if (tab == 3)
                        Padding(
                          padding: const EdgeInsets.only(top: 8),
                          child: TextButton(
                            onPressed: router.commandBusy ? null : forget,
                            child: const Text(
                              'Удалить привязку',
                              style: TextStyle(color: muted),
                            ),
                          ),
                        ),
                      const SizedBox(height: 12),
                      if (tab != 2 && tab != 4)
                        Text(
                          router.age < 0
                              ? 'Данные появятся после подключения'
                              : router.fresh
                              ? 'С роутера · ${router.age} с назад'
                              : 'Последнее обновление · ${router.age} с назад',
                          style: const TextStyle(color: muted, fontSize: 11),
                        ),
                    ],
                  ],
                ),
              ),
            ),
            const Divider(height: 1, color: rule),
            Row(
              children: [
                for (var i = 0; i < 5; i++)
                  Expanded(
                    child: Semantics(
                      selected: tab == i,
                      button: true,
                      label: [
                        'Состояние',
                        'Устройства',
                        'VPN',
                        'Роутер',
                        'СМС',
                      ][i],
                      child: InkWell(
                        onTap: () => setState(() => tab = i),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                [
                                  Icons.speed_outlined,
                                  Icons.devices_outlined,
                                  Icons.shield_outlined,
                                  Icons.router_outlined,
                                  Icons.sms_outlined,
                                ][i],
                                size: 25,
                                color: tab == i ? yellow : muted,
                              ),
                              const SizedBox(height: 8),
                              Text(
                                [
                                  'Состояние',
                                  'Устройства',
                                  'VPN',
                                  'Роутер',
                                  'СМС',
                                ][i],
                                style: TextStyle(
                                  color: tab == i ? yellow : muted,
                                  fontSize: 11,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget pairing() => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Text(
        'ТВОЙ РОУТЕР.\nВСЕГДА РЯДОМ.',
        style: TextStyle(
          color: yellow,
          fontWeight: FontWeight.bold,
          fontSize: 32,
          height: 1.18,
        ),
      ),
      const SizedBox(height: 24),
      const Text(
        'Привяжи Photonicat один раз. Дальше приложение будет находить его по Bluetooth.',
        style: TextStyle(color: muted, fontSize: 16),
      ),
      const SizedBox(height: 24),
      TextField(
        controller: code,
        obscureText: true,
        autocorrect: false,
        enableSuggestions: false,
        keyboardType: TextInputType.visiblePassword,
        decoration: InputDecoration(
          labelText: 'Ключ своего роутера',
          border: const OutlineInputBorder(),
          errorText: invalid ? 'Нужны 64 символа: 0–9 и a–f' : null,
          helperText: 'Выдан при настройке службы на роутере',
          helperMaxLines: 2,
        ),
      ),
      const SizedBox(height: 20),
      SizedBox(
        width: double.infinity,
        child: FilledButton(
          onPressed: () async {
            final ok = await router.bind(code.text);
            if (!mounted) return;
            setState(() => invalid = !ok);
            if (ok) {
              code.clear();
              router.connect();
            }
          },
          child: const Text('Привязать Photonicat'),
        ),
      ),
    ],
  );
  Widget label(String text) => Text(
    text,
    style: const TextStyle(color: muted, fontSize: 11, letterSpacing: 1.6),
  );
  Widget divider() => const Padding(
    padding: EdgeInsets.symmetric(vertical: 20),
    child: Divider(height: 1, color: rule),
  );
  String value(String key, [int decimal = 0]) {
    final v = router.data?[key];
    return v is num ? v.toStringAsFixed(decimal) : '—';
  }

  Widget speed(String icon, String title, double? number) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      label(title),
      const SizedBox(height: 5),
      Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          SvgPicture.asset(
            'assets/icons/$icon.svg',
            width: 15,
            height: 23,
            colorFilter: const ColorFilter.mode(yellow, BlendMode.srcIn),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(
                number == null
                    ? '—'
                    : number.toStringAsFixed(number >= 100 ? 1 : 2),
                style: digits(52),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Padding(
            padding: const EdgeInsets.only(top: 21),
            child: Text('Mbps', style: digits(12, weight: FontWeight.w400)),
          ),
        ],
      ),
      const SizedBox(height: 18),
    ],
  );
  Widget dashboard() {
    final d = router.data;
    final total = (d?['memory_total'] as num?)?.toDouble();
    final available = (d?['memory_available'] as num?)?.toDouble();
    final used = total != null && available != null ? total - available : null;
    final memory = total != null && total > 0 && used != null
        ? 100 * used / total
        : null;
    final remaining = d?['remaining_time'] as String?;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        speed('arrowDown', 'ЗАГРУЗКА · WAN', router.fresh ? router.down : null),
        speed('arrowUp', 'ОТДАЧА · WAN', router.fresh ? router.up : null),
        const Divider(height: 1, color: yellow),
        const SizedBox(height: 24),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                label('БАТАРЕЯ'),
                const SizedBox(height: 5),
                Text('${value('battery')}%', style: digits(32)),
              ],
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                label('ТЕМПЕРАТУРА'),
                const SizedBox(height: 5),
                Text('${value('temperature', 1)}°', style: digits(32)),
              ],
            ),
          ],
        ),
        const SizedBox(height: 14),
        LinearProgressIndicator(
          value: ((d?['battery'] as num?)?.toDouble() ?? 0).clamp(0, 100) / 100,
          minHeight: 5,
          color: yellow,
          backgroundColor: rule,
        ),
        const SizedBox(height: 10),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              d == null
                  ? 'Ожидание'
                  : d['charging'] == true
                  ? 'Заряжается'
                  : 'От батареи',
              style: const TextStyle(color: muted, fontSize: 12),
            ),
            Text(
              '${value('voltage', 2)} V / ${value('power', 1)} W',
              style: digits(11, color: muted, weight: FontWeight.w400),
            ),
          ],
        ),
        const SizedBox(height: 14),
        Row(
          children: [
            const Icon(Icons.schedule, size: 18, color: yellow),
            const SizedBox(width: 9),
            Text(remaining == null ? '—' : '≈ $remaining', style: digits(22)),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                d?['charging'] == true
                    ? 'до завершения зарядки'
                    : 'осталось работы',
                style: const TextStyle(color: muted, fontSize: 12),
              ),
            ),
          ],
        ),
        divider(),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: loadMetric(
                'ПРОЦЕССОР',
                (d?['cpu_percent'] as num?)?.toDouble(),
                'Текущая загрузка',
              ),
            ),
            const SizedBox(width: 24),
            Expanded(
              child: loadMetric(
                'ПАМЯТЬ',
                memory,
                used == null || total == null
                    ? '—'
                    : '${(used / 1048576).toStringAsFixed(1)} / '
                          '${(total / 1048576).toStringAsFixed(1)} ГиБ',
              ),
            ),
          ],
        ),
        divider(),
        label('МОБИЛЬНЫЙ ТРАФИК'),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(child: trafficMetric('Сегодня', d?['mobile_today_bytes'])),
            const SizedBox(width: 24),
            Expanded(
              child: trafficMetric('За месяц', d?['mobile_month_bytes']),
            ),
          ],
        ),
        const SizedBox(height: 8),
        if (d?['modem_present'] == false)
          const Text(
            'Модем пока не установлен.',
            style: TextStyle(color: muted, fontSize: 12),
          ),
        row(
          'WAN · с запуска интерфейса',
          d?['rx_bytes'] is num && d?['tx_bytes'] is num
              ? trafficSize((d!['rx_bytes'] as num) + (d['tx_bytes'] as num))
              : '—',
        ),
        divider(),
        row(
          'Ethernet WAN',
          d == null
              ? '—'
              : d['wan_up'] == true
              ? 'Подключён'
              : 'Нет соединения',
        ),
        row(
          'Wi-Fi',
          d == null
              ? '—'
              : d['wifi_up'] == true
              ? 'Включён'
              : 'Выключен',
        ),
        row(
          'Мобильный модем',
          d == null
              ? '—'
              : d['modem_present'] == null
              ? 'Не определён'
              : d['modem_present'] == true
              ? 'Обнаружен'
              : 'Не установлен',
        ),
      ],
    );
  }

  Widget loadMetric(String title, double? percent, String caption) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      label(title),
      const SizedBox(height: 7),
      Text(
        percent == null ? '—' : '${percent.toStringAsFixed(0)}%',
        style: digits(29),
      ),
      const SizedBox(height: 10),
      LinearProgressIndicator(
        value: percent == null ? 0 : percent.clamp(0, 100) / 100,
        minHeight: 4,
        color: yellow,
        backgroundColor: rule,
      ),
      const SizedBox(height: 7),
      Text(caption, style: const TextStyle(color: muted, fontSize: 11)),
    ],
  );

  String trafficSize(dynamic bytes) {
    if (bytes is! num || bytes < 0) return '—';
    if (bytes >= 1073741824) {
      return '${(bytes / 1073741824).toStringAsFixed(2)} ГиБ';
    }
    return '${(bytes / 1048576).toStringAsFixed(1)} МиБ';
  }

  Widget trafficMetric(String title, dynamic bytes) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(title, style: const TextStyle(color: muted, fontSize: 12)),
      const SizedBox(height: 6),
      Text(
        trafficSize(bytes),
        style: const TextStyle(
          color: yellow,
          fontSize: 23,
          fontWeight: FontWeight.w600,
        ),
      ),
    ],
  );

  Widget row(String title, String text) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 9),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Text(
            title,
            style: const TextStyle(color: muted, fontSize: 14),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            text,
            textAlign: TextAlign.right,
            style: const TextStyle(fontSize: 14),
          ),
        ),
      ],
    ),
  );
  Widget devices() {
    final leases = router.data?['leases'] as List?;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        label('ЛОКАЛЬНАЯ СЕТЬ'),
        const SizedBox(height: 8),
        const Text(
          'Устройства',
          style: TextStyle(
            fontSize: 32,
            fontWeight: FontWeight.bold,
            color: yellow,
          ),
        ),
        const SizedBox(height: 16),
        const Text(
          'Адреса, выданные роутером. Аренда адреса не означает, что устройство сейчас в сети.',
          style: TextStyle(color: muted, fontSize: 13),
        ),
        divider(),
        row('Клиенты Wi-Fi сейчас', value('wifi_clients')),
        if (leases == null)
          const Text(
            'Подключись к роутеру, чтобы увидеть устройства.',
            style: TextStyle(color: muted),
          )
        else if (leases.isEmpty)
          const Text(
            'Выданных адресов пока нет.',
            style: TextStyle(color: muted),
          )
        else
          for (final item in leases) ...[
            divider(),
            Text(
              item['name'] as String,
              style: const TextStyle(color: yellow, fontSize: 21),
            ),
            const SizedBox(height: 6),
            Text(
              item['ip'] as String,
              style: digits(15, color: Colors.white, weight: FontWeight.w400),
            ),
            const SizedBox(height: 6),
            Text(
              item['wifi'] == true ? 'Подключено по Wi-Fi' : 'Аренда DHCP',
              style: const TextStyle(color: muted, fontSize: 12),
            ),
          ],
      ],
    );
  }

  Widget details() {
    final d = router.data;
    final seconds = (d?['uptime'] as num?)?.toInt();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Управление',
          style: TextStyle(
            color: yellow,
            fontSize: 32,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 6),
        const Text(
          'Настройки твоего Photonicat',
          style: TextStyle(color: muted),
        ),
        const SizedBox(height: 24),
        ControlPanel(router: router),
        const SizedBox(height: 24),
        Theme(
          data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
          child: ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: const EdgeInsets.only(bottom: 16),
            iconColor: muted,
            collapsedIconColor: muted,
            title: const Text('Об устройстве', style: TextStyle(fontSize: 16)),
            subtitle: Text(
              'Photonicat 2 · ${router.deviceIdentity ?? '—'}',
              style: const TextStyle(color: muted, fontSize: 12),
            ),
            children: [
              row('Устройство', router.deviceIdentity ?? '—'),
              row(
                'Работает',
                seconds == null
                    ? '—'
                    : '${seconds ~/ 3600} ч ${(seconds ~/ 60) % 60} мин',
              ),
              row('Прошивка', d?['firmware'] as String? ?? '—'),
              row('Ядро', d?['kernel'] as String? ?? '—'),
              row('Служба', d?['service_version'] as String? ?? '—'),
              row(
                'Свободно памяти',
                d == null
                    ? '—'
                    : '${(d['memory_available'] as num) ~/ 1024} МБ',
              ),
              const SizedBox(height: 12),
              const Text(
                'Photonicat Companion · 0.2\nСвязь и команды защищены ключом привязки.',
                style: TextStyle(color: muted, fontSize: 12),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Future<void> forget() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Удалить привязку?'),
        content: const Text(
          'Для повторного подключения понадобится ключ этого роутера.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Отмена'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Удалить'),
          ),
        ],
      ),
    );
    if (ok == true) await router.forget();
  }
}
