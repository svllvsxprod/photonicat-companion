# Local build compatibility patch

Source: reactive_ble_mobile 5.4.0, BSD-3-Clause (see LICENSE).
Only upstream source modification: android/build.gradle compileSdkVersion 33 -> 36.
This permits AndroidX dependencies used by the current Flutter engine.
Paired with flutter_reactive_ble and reactive_ble_platform_interface 5.4.0.
The latest 5.6.0 requires a newer Android/Kotlin toolchain; upgrade the three
packages together when adopting that toolchain. No Bluetooth runtime behavior
was patched. Dependency override is committed in the app pubspec.
