import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:photonicat/wire_crypto.dart';

void main() {
  final cipher = WireCrypto(List.generate(32, (i) => i));
  test('decrypts Python router envelope including Cyrillic', () {
    final fixture = jsonDecode(
      File('test/fixtures/python_envelope.json').readAsStringSync(),
    );
    expect(cipher.open(ascii.encode(fixture['packet'])), fixture['expected']);
  });
  test('roundtrip and fresh nonces', () {
    final input = {'seq': 17, 'text': 'Состояние роутера'};
    final a = cipher.seal(input), b = cipher.seal(input);
    expect(a, isNot(equals(b)));
    expect(cipher.open(a), input);
  });
  test('rejects ciphertext modification and wrong key', () {
    final encoded = cipher.seal({'seq': 1});
    final packet = base64Decode(ascii.decode(encoded));
    packet[20] ^= 1;
    expect(
      () => cipher.open(ascii.encode(base64Encode(packet))),
      throwsFormatException,
    );
    expect(
      () => WireCrypto(List.filled(32, 42)).open(encoded),
      throwsFormatException,
    );
  });
  test('rejects malformed and truncated packets', () {
    expect(() => cipher.open(ascii.encode('bad')), throwsFormatException);
    expect(
      () => cipher.open(ascii.encode(base64Encode([1, 2, 3]))),
      throwsFormatException,
    );
    expect(() => WireCrypto.fromHex('1234'), throwsFormatException);
  });
}
