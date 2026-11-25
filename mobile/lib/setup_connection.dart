import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:dartssh2/dartssh2.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'wire_crypto.dart';

class SetupFailure implements Exception {
  const SetupFailure(this.message);
  final String message;
  @override
  String toString() => message;
}

bool validSetupAddress(String text) {
  final a = InternetAddress.tryParse(text);
  if (a == null || a.type != InternetAddressType.IPv4) return false;
  final b = a.rawAddress;
  return b[0] == 10 ||
      (b[0] == 172 && b[1] >= 16 && b[1] <= 31) ||
      (b[0] == 192 && b[1] == 168);
}

class SetupResult {
  const SetupResult(this.address, this.key);
  final String address;
  final String key;
}

class SetupConnection {
  SSHClient? _client;
  String address = '';
  final _vault = const FlutterSecureStorage(
    mOptions: MacOsOptions(
      accountName: 'dev.svllvsx.photonicat.desktop',
      usesDataProtectionKeychain: false,
    ),
  );

  Future<void> connect(
    String host,
    String password,
    Future<bool> Function(String fingerprint, bool changed) trust,
  ) async {
    if (!validSetupAddress(host)) {
      throw const SetupFailure('Укажи локальный IPv4-адрес своего роутера.');
    }
    address = host;
    final pinKey = 'ssh_host_${sha256.convert(utf8.encode(host))}';
    final oldPin = await _vault.read(key: pinKey);
    var rejected = false;
    String? acceptedPin;
    try {
      final socket = await SSHSocket.connect(
        host,
        22,
        timeout: const Duration(seconds: 8),
      );
      _client = SSHClient(
        socket,
        username: 'root',
        authTimeout: const Duration(seconds: 60),
        onPasswordRequest: () => password,
        onVerifyHostKey: (type, bytes) async {
          final fingerprint = utf8.decode(bytes);
          if (oldPin == fingerprint) return true;
          final accept = await trust(fingerprint, oldPin != null);
          rejected = !accept;
          if (accept) acceptedPin = fingerprint;
          return accept;
        },
      );
      await _client!.authenticated;
      if (acceptedPin != null) {
        await _vault.write(key: pinKey, value: acceptedPin);
      }
    } catch (_) {
      close();
      throw SetupFailure(
        rejected
            ? 'Подключение отменено: ключ SSH не подтверждён.'
            : 'Не удалось войти по SSH. Проверь адрес, пароль администратора и подключение к роутеру.',
      );
    }
  }

  Future<Uint8List> _run(
    String command, {
    List<int>? input,
    Duration timeout = const Duration(seconds: 45),
  }) async {
    final client = _client;
    if (client == null) {
      throw const SetupFailure('Подключись к роутеру заново.');
    }
    final session = await client.execute(command);
    final output = BytesBuilder(copy: false);
    var tooLarge = false;
    final out = session.stdout.listen((chunk) {
      if (output.length + chunk.length > 256 * 1024) {
        tooLarge = true;
        session.close();
      } else {
        output.add(chunk);
      }
    });
    // Remote stderr can contain account URLs: consume but never display or log it.
    final outDone = out.asFuture<void>();
    final err = session.stderr.listen((_) {});
    try {
      await (() async {
        if (input != null) {
          for (var offset = 0; offset < input.length; offset += 32768) {
            final end = (offset + 32768).clamp(0, input.length);
            session.stdin.add(Uint8List.fromList(input.sublist(offset, end)));
            await session.flush();
          }
        }
        await session.stdin.close();
        await session.done;
        await outDone;
      })().timeout(timeout);
      if (tooLarge || session.exitCode != 0) {
        throw const SetupFailure(
          'Операция на роутере не завершена. Повтори проверку подключения.',
        );
      }
      return output.takeBytes();
    } on TimeoutException {
      session.close();
      throw const SetupFailure(
        'Время ожидания истекло. Если новая установка не подтверждена, роутер автоматически откатит её.',
      );
    } finally {
      await out.cancel();
      await err.cancel();
    }
  }

  Future<Map<String, dynamic>> inspect() async {
    final script = await rootBundle.loadString('assets/setup/probe.py');
    final result = await _run('python3 -', input: utf8.encode(script));
    try {
      return jsonDecode(utf8.decode(result)) as Map<String, dynamic>;
    } catch (_) {
      throw const SetupFailure(
        'Не удалось проверить прошивку. Требуется штатная PhotonicatWrt с Python 3.',
      );
    }
  }

  Future<SetupResult> install(
    bool existing,
    void Function(String) progress,
  ) async {
    if (existing) {
      progress('Получаем ключ установленной службы');
      final key = utf8
          .decode(await _run('cat /etc/photonicat-companion/key'))
          .trim();
      WireCrypto.fromHex(key);
      await verifyService(key);
      return SetupResult(address, key);
    }
    final payload = (await rootBundle.load(
      'assets/setup/payload.tar.gz',
    )).buffer.asUint8List();
    final expected = (await rootBundle.loadString(
      'assets/setup/payload.sha256',
    )).trim();
    if (sha256.convert(payload).toString() != expected) {
      throw const SetupFailure(
        'Установочный пакет повреждён. Скачай приложение заново.',
      );
    }
    final nonce = WireCrypto.hex(WireCrypto.random(12));
    final folder = '/tmp/photonicat-setup-$nonce';
    progress('Передаём проверенный установочный пакет');
    await _run(
      'umask 077; mkdir -m 700 $folder && cat > $folder/payload.tar.gz',
      input: payload,
      timeout: const Duration(minutes: 3),
    );
    progress('Устанавливаем службы и безопасные начальные настройки');
    final output = await _run(
      'cd $folder && test "\$(sha256sum payload.tar.gz | cut -d " " -f 1)" = "$expected" && tar -xzf payload.tar.gz && rm payload.tar.gz && python3 install.py',
      timeout: const Duration(minutes: 3),
    );
    final result = jsonDecode(utf8.decode(output)) as Map<String, dynamic>;
    if (result['ok'] != true) {
      throw const SetupFailure(
        'Установка не завершена. Если связь не подтверждена, изменения автоматически откатятся.',
      );
    }
    final key = result['key'] as String;
    WireCrypto.fromHex(key);
    final transaction = result['transaction'] as String;
    if (!RegExp(r'^[a-f0-9]{24}$').hasMatch(transaction)) {
      throw const SetupFailure('Некорректный ответ установщика.');
    }
    progress('Проверяем защищённое соединение');
    await verifyService(key);
    // Only a successful authenticated exchange can cancel the rollback timer.
    final confirmation =
        '''import fcntl,pathlib
p=pathlib.Path('/root/photonicat-install-backups/$transaction')
with (p/'transaction.lock').open('w') as f:
 fcntl.flock(f,fcntl.LOCK_EX)
 if (p/'result.json').exists():raise RuntimeError('rolled_back')
 (p/'confirmed').touch(mode=0o600)
''';
    await _run('python3 -', input: utf8.encode(confirmation));
    // Keep the watchdog code until it observes confirmation; no secrets are in it.
    return SetupResult(address, key);
  }

  Future<void> verifyService(String key) async {
    final crypto = WireCrypto(WireCrypto.fromHex(key));
    for (var attempt = 0; attempt < 12; attempt++) {
      Socket? socket;
      try {
        socket = await Socket.connect(
          address,
          24862,
          timeout: const Duration(seconds: 2),
        );
        final challenge = WireCrypto.hex(WireCrypto.random(16));
        var received = 0;
        final reply = socket
            .map((chunk) {
              received += chunk.length;
              if (received > 65536) throw const FormatException();
              return chunk;
            })
            .cast<List<int>>()
            .transform(utf8.decoder)
            .transform(const LineSplitter())
            .first
            .timeout(const Duration(seconds: 4));
        socket.add([
          ...crypto.seal({'op': 'hello', 'seq': 1, 'challenge': challenge}),
          10,
        ]);
        final message = await reply;
        if (message.length > 65536) throw const FormatException();
        final value = crypto.open(ascii.encode(message));
        if (value['seq'] != 1 ||
            value['challenge'] != challenge ||
            value['sid'] is! String ||
            (value['sid'] as String).length != 32) {
          throw const FormatException();
        }
        return;
      } catch (_) {
        if (attempt == 11) {
          throw const SetupFailure(
            'Служба не подтвердила соединение. Новая установка автоматически откатится; пароль администратора не менялся.',
          );
        }
        await Future<void>.delayed(const Duration(seconds: 1));
      } finally {
        socket?.destroy();
      }
    }
  }

  Future<String> setPerformance({required bool restore}) async {
    final script = await rootBundle.loadString('assets/setup/performance.py');
    final operation = restore ? 'restore' : 'apply';
    final reply = await _run(
      'python3 - $operation',
      input: utf8.encode(script),
    );
    final status = jsonDecode(utf8.decode(reply))['status'];
    return switch (status) {
      'ready' => 'Распределение нагрузки включено. Настройки Mihomo сохранены.',
      'saved' =>
        'Настройки сохранены. Новый режим Mihomo вступит в силу при следующем запуске роутера.',
      'restored' =>
        'Прежние настройки восстановлены. Перезапусти роутер в удобное время.',
      'no_backup' => 'На этом роутере нет изменений, внесённых этим мастером.',
      'unsupported' => throw const SetupFailure(
        'Настройка доступна для штатного Photonicat 2 с проводным WAN eth0, Mihomo 1.19.32 и обычным распределением пакетов. Индивидуальные настройки сохранены.',
      ),
      'modified' => throw const SetupFailure(
        'Сохранённые настройки были изменены вручную. Проверь их перед повторным применением.',
      ),
      'busy' || 'retry' => throw const SetupFailure(
        'Повтори действие после завершения текущей операции роутера.',
      ),
      _ => throw const SetupFailure(
        'Роутер не смог завершить настройку производительности.',
      ),
    };
  }

  Future<void> addSubscription(String label, String url) =>
      _manage('add-subscription', {'label': label, 'url': url});
  Future<void> addProfile(String label, String text) =>
      _manage('import-awg', {'label': label, 'text': text});
  Future<void> _manage(String action, Map<String, String> args) async {
    await _run(
      'python3 /opt/photonicat-vpn/manager.py manage',
      input: utf8.encode(jsonEncode({'action': action, 'args': args})),
      timeout: const Duration(seconds: 60),
    );
  }

  void close() {
    _client?.close();
    _client = null;
  }
}
