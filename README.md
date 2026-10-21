<p align="center"><a href="README.md">English</a> · <a href="README.ru.md">Русский</a></p>
<h1 align="center">Photonicat Companion</h1>
<p align="center">A Bluetooth companion for router telemetry, device controls and VPN routing.</p>
<p align="center"><img alt="Flutter" src="https://img.shields.io/badge/Flutter-f4e600?style=flat-square"> <img alt="Python" src="https://img.shields.io/badge/Python-f4e600?style=flat-square"> <img alt="Bluetooth LE" src="https://img.shields.io/badge/Bluetooth%20LE-f4e600?style=flat-square"></p>

<p align="center">
<img src="docs/readme/current-status.png" width="30%" alt="Status demo">
<img src="docs/readme/current-vpn.png" width="30%" alt="Current Direct / VPN controls">
<img src="docs/readme/current-controls.png" width="30%" alt="Current screen and fan controls">
</p>
> Current app widgets rendered on 2026-10-21 in an isolated demo environment. Readings, names and addresses are fictional; branding is replaced. This is not a live-device measurement.

## Highlights

| Feature | What is included |
| --- | --- |
| Live telemetry | Transfer rates, battery, temperature, CPU, memory and traffic counters. |
| Five workspaces | Status, connected devices, VPN, router controls and read-only SMS. |
| Router controls | Wi-Fi settings, screen brightness and timeout, manual fan level and presets. |
| Direct ↔ VPN | AmneziaWG/Mihomo selection and per-interface routing controls. |
| Local BLE link | Flutter client with a Python BlueZ GATT service and pairing-key protection. |

## Source layout

| Path | Contents |
| --- | --- |
| `mobile/` | Flutter app, Android/iOS hosts and widget tests. |
| `router/` | BLE service, telemetry and controls. |
| `vpn-service/` | VPN integration scripts and service documentation. |
| `tests/ · tools/` | Python tests and setup utilities. |

## Local development

```sh
python3 -m unittest discover -s tests
cd mobile
flutter pub get
flutter analyze
flutter test
flutter run
```

`tools/provision_phone.py` uses `PHOTONICAT_SSH_TARGET` and optional `ADB`. It is an explicit device-provisioning utility, not part of routine preview startup.

## Project status & scope

Android is the primary target (minimum Android 12). The iOS host is included; physical iOS operation is not claimed. Router installation requires a compatible Linux/BlueZ environment and separately provisioned pairing/VPN keys. The custom encrypted protocol has not received an independent security audit. No keys, phone provisioning state or live device captures are included.

## Rights & dependencies

Sources are published for inspection. No general reuse license has been selected for original project code. Included third-party components retain their own licenses: [RIGHTS.md](RIGHTS.md).

---

<p align="center">
<a href="https://t.me/tribute/app?startapp=dK9j"><img src="docs/readme/support-tribute.svg" height="36" alt="Support via Tribute"></a>
<a href="https://nowpayments.io/donation/svllvsx"><img src="docs/readme/support-nowpayments.svg" height="36" alt="Support via NOWPayments"></a>
<a href="https://t.me/svllvsxprod"><img src="docs/readme/telegram.svg" height="36" alt="Telegram"></a>
</p>
