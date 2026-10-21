import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:pointycastle/export.dart';

/// AES-256-CTR + HMAC-SHA256, encrypt-then-MAC. Session/sequence checks live above this layer.
class WireCrypto {
  static final _aad = utf8.encode('photonicat-companion-v1');
  late final Uint8List _enc;
  late final Uint8List _mac;
  WireCrypto(List<int> key) {
    if (key.length != 32) throw const FormatException('Expected 256-bit key');
    _enc = _hmac(key, [..._aad, ...utf8.encode('/enc')]);
    _mac = _hmac(key, [..._aad, ...utf8.encode('/mac')]);
  }
  static Uint8List _hmac(List<int> key, List<int> message) =>
      Uint8List.fromList(Hmac(sha256, key).convert(message).bytes);
  static Uint8List random(int size) {
    final r = Random.secure();
    return Uint8List.fromList(List.generate(size, (_) => r.nextInt(256)));
  }

  static String hex(List<int> data) =>
      data.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  static Uint8List fromHex(String text) {
    if (!RegExp(r'^[a-fA-F0-9]{64}$').hasMatch(text)) {
      throw const FormatException('Invalid key');
    }
    return Uint8List.fromList(
      List.generate(
        32,
        (i) => int.parse(text.substring(i * 2, i * 2 + 2), radix: 16),
      ),
    );
  }

  Uint8List _crypt(List<int> input, List<int> iv) {
    final c = SICStreamCipher(
      AESEngine(),
    )..init(true, ParametersWithIV(KeyParameter(_enc), Uint8List.fromList(iv)));
    return c.process(Uint8List.fromList(input));
  }

  List<int> seal(Map<String, dynamic> value) {
    final iv = random(16);
    final body = [1, ...iv, ..._crypt(utf8.encode(jsonEncode(value)), iv)];
    return ascii.encode(
      base64Encode([
        ...body,
        ..._hmac(_mac, [..._aad, ...body]),
      ]),
    );
  }

  Map<String, dynamic> open(List<int> encoded) {
    final packet = base64Decode(ascii.decode(encoded));
    if (packet.length < 50 || packet[0] != 1) {
      throw const FormatException('Invalid envelope');
    }
    final body = packet.sublist(0, packet.length - 32);
    final expected = _hmac(_mac, [..._aad, ...body]);
    var diff = 0;
    for (var i = 0; i < 32; i++) {
      diff |= expected[i] ^ packet[body.length + i];
    }
    if (diff != 0) throw const FormatException('Authentication failed');
    return jsonDecode(
          utf8.decode(_crypt(body.sublist(17), body.sublist(1, 17))),
        )
        as Map<String, dynamic>;
  }
}
