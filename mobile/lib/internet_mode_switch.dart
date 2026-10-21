import 'package:flutter/material.dart';
import 'app_style.dart';

class InternetModeSwitch extends StatelessWidget {
  const InternetModeSwitch({
    super.key,
    required this.vpn,
    required this.onChanged,
    this.switchKey,
  });
  final bool vpn;
  final ValueChanged<bool>? onChanged;
  final Key? switchKey;
  @override
  Widget build(BuildContext context) => Row(
    children: [
      for (final value in [false, true]) ...[
        if (value)
          Semantics(
            label: 'Режим интернета: Direct или VPN',
            child: Switch.adaptive(
              key: switchKey,
              value: vpn,
              activeThumbColor: yellow,
              onChanged: onChanged,
            ),
          ),
        Expanded(
          child: TextButton(
            onPressed: onChanged == null ? null : () => onChanged!(value),
            child: Text(
              value ? 'VPN' : 'Direct',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: vpn == value ? yellow : muted,
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
      ],
    ],
  );
}
