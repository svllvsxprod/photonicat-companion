import 'package:flutter/material.dart';
import 'app_style.dart';

/// The same Direct and VPN choices for every client network.
class InternetModeSwitch extends StatelessWidget {
  const InternetModeSwitch({
    super.key,
    required this.mode,
    required this.onChanged,
    this.switchKey,
  });
  final String mode;
  final ValueChanged<String>? onChanged;
  final Key? switchKey;

  @override
  Widget build(BuildContext context) => Container(
    key: switchKey,
    decoration: BoxDecoration(
      color: Colors.black.withValues(alpha: .18),
      border: Border.all(color: rule),
      borderRadius: BorderRadius.circular(8),
    ),
    padding: const EdgeInsets.all(3),
    child: Row(
      children: [
        for (final entry in const {'direct': 'Direct', 'vpn': 'VPN'}.entries)
          Expanded(
            child: Semantics(
              selected: mode == entry.key,
              child: TextButton(
                key: ValueKey('${switchKey ?? 'internet'}-${entry.key}'),
                style: TextButton.styleFrom(
                  minimumSize: const Size(0, 44),
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  backgroundColor: mode == entry.key
                      ? yellow
                      : Colors.transparent,
                  foregroundColor: mode == entry.key ? Colors.black : muted,
                  disabledForegroundColor: mode == entry.key
                      ? Colors.black54
                      : muted.withValues(alpha: .5),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(5),
                  ),
                ),
                onPressed: onChanged == null
                    ? null
                    : () => onChanged!(entry.key),
                child: Text(
                  entry.value,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          ),
      ],
    ),
  );
}
