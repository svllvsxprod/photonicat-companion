<p align="center"><a href="README.md">English</a> · <a href="README.ru.md">Русский</a></p>
<h1 align="center">Photonicat Companion</h1>
<p align="center">Router telemetry, VPN and device controls on Android, macOS and Windows.</p>
<p align="center"><img alt="Flutter" src="https://img.shields.io/badge/Flutter-f4e600?style=flat-square"> <img alt="Python" src="https://img.shields.io/badge/Python-f4e600?style=flat-square"> <img alt="Bluetooth LE" src="https://img.shields.io/badge/Bluetooth%20LE-f4e600?style=flat-square"></p>

<p align="center">
<img src="docs/readme/current-status.png" width="30%" alt="Status demo">
<img src="docs/readme/current-vpn.png" width="30%" alt="Current Direct / VPN controls">
<img src="docs/readme/current-controls.png" width="30%" alt="Current screen and fan controls">
</p>
> Sample Android screens with fictional data. The desktop version looks slightly different.

## Your router, close at hand

Photonicat Companion shows how your Photonicat 2 is doing and lets you control Wi-Fi, VPN, the screen and the fan. Android connects over Bluetooth. On a computer, it uses Wi-Fi or Ethernet and opens from a small cat icon in the menu bar or system tray.

### Download 0.7.5 beta

| Device | Download |
| --- | --- |
| Android 12 or later | [APK](https://github.com/svllvsxprod/photonicat-companion/releases/download/v0.7.5-beta.1/Photonicat-0.7.5-Android.apk) |
| Apple Silicon Mac, macOS 12 or later | [DMG](https://github.com/svllvsxprod/photonicat-companion/releases/download/v0.7.5-beta.1/Photonicat-0.7.5-beta.1-macOS-AppleSilicon.dmg) |
| Windows x64 | [EXE installer](https://github.com/svllvsxprod/photonicat-companion/releases/download/v0.7.5-beta.1/Photonicat-0.7.5-Windows-x64-Setup.exe) |

[All downloads and release notes →](https://github.com/svllvsxprod/photonicat-companion/releases/tag/v0.7.5-beta.1)

This is a test release. Your system may display a signing warning; see the release notes for details. iPhone is not supported yet.

### What you can do

- Check battery, temperature, connection speed, CPU and memory usage.
- Change Wi-Fi settings, screen brightness and fan speed.
- Add Mihomo subscriptions and AmneziaWG profiles, then choose direct internet or VPN.
- View connected devices and incoming text messages.
- Set up the router's companion service with a desktop wizard.

**New in 0.7.5:** Mac and Windows reconnect automatically when you switch from Wi-Fi to Ethernet or back. You do not need to enter your pairing key again.

### Get started

1. Install the desktop app and connect to the router's Wi-Fi or LAN port.
2. Click the cat icon → **«Настроить роутер»**. The wizard asks for the router address and administrator password.
3. Finish setup and save the pairing key. To use Android, install the APK and enter that same key in the app.

[First setup, step by step with screenshots (RU) →](docs/public/SETUP_RU.md)

[Phone installation, VPN and troubleshooting (RU) →](docs/public/USAGE_RU.md)

The wizard targets Photonicat 2 with PhotonicatWrt 26.04.1. A complete setup on a factory-fresh router still needs testing. No owner's keys or VPN subscriptions are bundled: you use your own.

### About

An independent project, not an official Photonicat product. [Source and build instructions](docs/public/BUILD.md) · [Rights and licenses](RIGHTS.md). Source is published for inspection; no general reuse license has been selected yet.

---

<p align="center">
<a href="https://t.me/tribute/app?startapp=dK9j"><img src="docs/readme/support-tribute.svg" height="36" alt="Support via Tribute"></a>
<a href="https://nowpayments.io/donation/svllvsx"><img src="docs/readme/support-nowpayments.svg" height="36" alt="Support via NOWPayments"></a>
<a href="https://t.me/svllvsxprod"><img src="docs/readme/telegram.svg" height="36" alt="Telegram"></a>
</p>
