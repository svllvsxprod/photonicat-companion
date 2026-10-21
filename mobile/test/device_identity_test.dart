import 'package:flutter_test/flutter_test.dart';
import 'package:photonicat/router_controller.dart';

void main() {
  test(
    'router discovery identity matches Python HMAC and separates owners',
    () {
      const key =
          '000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f';
      expect(RouterController.identityFor(key), 'd07b1e60');
      expect(RouterController.identityFor('ff' * 32), isNot('d07b1e60'));
    },
  );
}
