import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'app_style.dart';
import 'router_controller.dart';

class FanControl extends StatefulWidget {
  const FanControl({super.key, required this.router});
  final RouterController router;
  @override
  State<FanControl> createState() => _FanControlState();
}

class _FanControlState extends State<FanControl> {
  bool applying = false;
  double? draft;
  RouterController get router => widget.router;
  bool get enabled => router.connected && !router.commandBusy && !applying;
  Future<void> save(Map<String, dynamic> change) async {
    setState(() => applying = true);
    try {
      await router.command('settings');
      final fan = router.settings?['fan'];
      if (fan is! Map) throw StateError('Вентилятор недоступен.');
      await router.command('fan_set', {'revision': fan['revision'], ...change});
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString().replaceFirst('Bad state: ', ''))),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          applying = false;
          draft = null;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final fan = router.settings?['fan'];
    if (fan is! Map) return const SizedBox.shrink();
    final level = draft ?? (fan['level'] as num).toDouble();
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: const Color(0xff0a0b08),
          border: Border.all(color: rule),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                SvgPicture.asset(
                  'assets/icons/fan.svg',
                  width: 24,
                  height: 24,
                  colorFilter: const ColorFilter.mode(yellow, BlendMode.srcIn),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Text(
                    'Вентилятор',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
                  ),
                ),
                Text('${level.round()}/9', style: digits(24)),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                for (final mode in {
                  'manual': 'Вручную',
                  'smart_quiet': 'Тише',
                  'smart_cool': 'Холоднее',
                }.entries)
                  Expanded(
                    child: TextButton(
                      onPressed: enabled && fan['mode'] != mode.key
                          ? () => save({'mode': mode.key})
                          : null,
                      style: TextButton.styleFrom(
                        backgroundColor: fan['mode'] == mode.key
                            ? yellow
                            : Colors.transparent,
                        disabledForegroundColor: fan['mode'] == mode.key
                            ? Colors.black
                            : muted,
                        foregroundColor: yellow,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 3,
                          vertical: 12,
                        ),
                      ),
                      child: Text(
                        mode.value,
                        style: const TextStyle(fontSize: 12),
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 16),
            Text(
              fan['mode'] == 'manual' ? 'Скорость' : 'Максимальная скорость',
              style: const TextStyle(color: muted),
            ),
            Slider(
              key: const ValueKey('fan-level'),
              min: 0,
              max: 9,
              divisions: 9,
              value: level.clamp(0, 9),
              activeColor: yellow,
              inactiveColor: rule,
              label: '${level.round()}/9',
              onChanged: enabled ? (v) => setState(() => draft = v) : null,
              onChangeEnd: enabled ? (v) => save({'level': v.round()}) : null,
            ),
            Text(
              fan['rpm'] == null
                  ? 'Обороты недоступны'
                  : '${fan['rpm']} об/мин',
              style: const TextStyle(color: muted, fontSize: 12),
            ),
            if (fan['mode'] != 'manual')
              const Padding(
                padding: EdgeInsets.only(top: 6),
                child: Text(
                  'Скорость регулируется автоматически по температуре.',
                  style: TextStyle(color: muted, fontSize: 12),
                ),
              ),
            if (applying)
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: LinearProgressIndicator(
                  color: yellow,
                  backgroundColor: rule,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
