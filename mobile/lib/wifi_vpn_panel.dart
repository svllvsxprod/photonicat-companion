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
              vpn: radio['vpn']['enabled'] == true,
              onChanged: enabled
                  ? (value) =>
                        apply({'vpn_enabled': value}, radioId: radio['id'])
                  : null,
            ),
            if (radio['vpn']['enabled'] == true)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text(
                  '${(router.vpn?['active'] ?? radio['vpn']['engine']) == 'mihomo' ? 'Mihomo' : 'AmneziaWG'} · kill switch',
                  style: const TextStyle(color: yellow, fontSize: 12),
                ),
              ),
            Text(
              radio['vpn']['enabled'] == true
                  ? 'Kill switch включён. При потере VPN интернет блокируется, включая DNS и IPv6.'
                  : 'Direct — без VPN. В режиме VPN используется основное ядро с kill switch.',
              style: const TextStyle(color: muted, fontSize: 11, height: 1.4),
            ),
            const SizedBox(height: 6),
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
