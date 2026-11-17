import 'package:flutter/material.dart';
import 'app_style.dart';
import 'router_controller.dart';
import 'internet_mode_switch.dart';

class WifiVpnPanel extends StatefulWidget {
  const WifiVpnPanel({super.key, required this.router});
  final RouterController router;
  @override
  State<WifiVpnPanel> createState() => _WifiVpnPanelState();
}

class _WifiVpnPanelState extends State<WifiVpnPanel> {
  RouterController get router => widget.router;
  bool applying = false;
  bool get enabled => router.connected && !router.commandBusy && !applying;
  Future<void> apply(
    Map<String, dynamic> changes, {
    required String radioId,
  }) async {
    if (!enabled) return;
    setState(() => applying = true);
    try {
      await router.command('settings');
      final radio = (router.settings?['wifi'] as List? ?? [])
          .where((r) => r['id'] == radioId)
          .firstOrNull;
      if (radio is! Map || radio['vpn'] is! Map) {
        throw StateError('Сеть больше не доступна. Обнови данные.');
      }
      final result = await router.command('wifi_set', {
        'id': radioId,
        'revision': radio['revision'],
        'ssid': radio['ssid'],
        'enabled': radio['enabled'],
        ...changes,
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(result['message'] as String? ?? 'Режим сохранён'),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString().replaceFirst('Bad state: ', ''))),
        );
      }
    } finally {
      if (mounted) setState(() => applying = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final radios = (router.settings?['wifi'] as List? ?? [])
        .where((r) => r['vpn'] is Map)
        .toList();
    return Container(
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
              const Icon(Icons.wifi, color: yellow),
              const SizedBox(width: 10),
              Text('Wi-Fi', style: digits(17, color: Colors.white)),
            ],
          ),
          if (applying)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: LinearProgressIndicator(
                color: yellow,
                backgroundColor: rule,
              ),
            ),
          if (radios.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: Text(
                'Нет доступных сетей для переключения. Обнови данные роутера.',
                style: TextStyle(color: muted, fontSize: 12),
              ),
            ),
          for (final radio in radios) ...[
            const SizedBox(height: 20),
            Text(
              radio['ssid'] as String,
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
            ),
            Text(
              '${radio['label'] == 'Onboard' ? 'Встроенная плата' : radio['label']} · ${radio['enabled'] == true ? 'Включена' : 'Выключена'}',
              style: const TextStyle(color: muted, fontSize: 12),
            ),

            const SizedBox(height: 12),
            const Divider(color: rule, height: 1),
            const SizedBox(height: 8),
            InternetModeSwitch(
              switchKey: ValueKey('wifi-vpn-${radio['id']}'),
              mode:
                  radio['vpn']['mode'] as String? ??
                  (radio['vpn']['enabled'] == true ? 'vpn' : 'direct'),
              onChanged: enabled
                  ? (value) =>
                        apply({'internet_mode': value}, radioId: radio['id'])
                  : null,
            ),
            if (radio['vpn']['enabled'] == true)
              Padding(
                padding: const EdgeInsets.only(top: 16, bottom: 12),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Padding(
                      padding: EdgeInsets.only(top: 1),
                      child: Icon(
                        Icons.shield_outlined,
                        color: yellow,
                        size: 22,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Защита VPN включена',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            (router.vpn?['active'] ?? radio['vpn']['engine']) ==
                                    'mihomo'
                                ? 'Mihomo'
                                : 'AmneziaWG',
                            style: const TextStyle(color: muted, fontSize: 11),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              )
            else
              const SizedBox(height: 12),
            Text(
              radio['vpn']['enabled'] == true
                  ? 'При потере VPN интернет блокируется, включая DNS и IPv6.'
                  : 'Direct — без VPN. В режиме VPN используется основное ядро с kill switch.',
              style: const TextStyle(color: muted, fontSize: 11, height: 1.4),
            ),
            const SizedBox(height: 12),
            const Text(
              'Смена режима перезапускает эту точку доступа.',
              style: TextStyle(color: muted, fontSize: 11),
            ),
          ],
        ],
      ),
    );
  }
}
