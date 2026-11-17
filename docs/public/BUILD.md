# Build and tests

[Back to the project](../../README.md)

## Requirements and commands

| Path | Contents |
| --- | --- |
| `mobile/` | Shared Flutter UI, Android/iOS/macOS/Windows hosts and tests. |
| `router/ · vpn-service/` | Authenticated BLE/LAN service, telemetry, controls and VPN routing. |
| `installer/` | Compatibility probes and transactional setup. |
| `docs/public/` | Illustrated setup, usage and release notes. |
| `tools/` | Desktop build scripts and allowlisted source exporter. |

Use Flutter 3.44.2 / Dart 3.12.2. Mac builds require Xcode; Windows builds require Visual Studio C++ and Inno Setup 6.3+; Android builds require an Android SDK and JDK 17. Android release builds currently use the local test signing configuration; provide your own private signing configuration for your distribution, never commit a keystore.

```sh
cd mobile
flutter pub get
flutter analyze
flutter test
flutter build apk --release
# From the repository root on the respective platform:
# bash tools/build-macos.sh
# pwsh -File tools/build-windows.ps1
```

Python checks use an isolated environment: install `requirements-dev.txt`, then run `python -m unittest discover -s tests`, `python -m unittest discover -s tests/setup`, and `python -m unittest discover -s vpn-service -p 'test_*.py'`. The audited setup payload is included; `tools/build-public-payload.py` recreates it from pinned upstream components and requires Go. Device provisioning is an explicit separate action; `tools/provision_phone.py` uses `PHOTONICAT_SSH_TARGET` and optional `ADB`.

