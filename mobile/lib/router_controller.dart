import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:convert';
import 'package:crypto/crypto.dart' as digest;
import 'package:flutter/foundation.dart';
import 'package:flutter_reactive_ble/flutter_reactive_ble.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'wire_crypto.dart';

class RouterController extends ChangeNotifier {
  static final service = Uuid.parse('b8b3c190-78b7-4f23-9c44-743d94c0a001');
  static final rx = Uuid.parse('b8b3c190-78b7-4f23-9c44-743d94c0a002');
  static final tx = Uuid.parse('b8b3c190-78b7-4f23-9c44-743d94c0a003');
  final _ble = FlutterReactiveBle();
  final _vault = const FlutterSecureStorage();
  final _clock = Stopwatch()..start();
  StreamSubscription<DiscoveredDevice>? _scan;
  StreamSubscription<ConnectionStateUpdate>? _connection;
  StreamSubscription<List<int>>? _notifications;
  Timer? _deadline, _poll, _retry;
  WireCrypto? _crypto;
  QualifiedCharacteristic? _writer;
  int _generation = 0, _sequence = 0, _expected = -1, _payload = 19;
  String _session = '', _challenge = '';
  List<int> _input = [];
  bool _foreground = true, _wanted = true, initialized = false;
  bool bound = false, busy = false, connected = false;
  String phase = 'Готов к подключению';
  String? error;
  Map<String, dynamic>? data;
  Map<String, dynamic>? _previousSample;
  double? down, up;
  int? _updated;
  String? deviceIdentity;
  String _operation = '';
  Completer<Map<String, dynamic>>? _command;
  bool commandBusy = false;
  Map<String, dynamic>? settings;
  Map<String, dynamic>? vpn;
  int _initialRetryBudget = 1;
  bool _linkOpened = false;
  int get age =>
      _updated == null ? -1 : (_clock.elapsedMilliseconds - _updated!) ~/ 1000;
  bool get fresh =>
      connected &&
      age >= 0 &&
      age < 12 &&
      ((data?['sample_age'] as num?) ?? double.infinity) + age < 15;

  Future<void> initialize() async {
    try {
      if (kDebugMode && Platform.isAndroid) {
        final folder = await getApplicationSupportDirectory();
        final bootstrap = File('${folder.path}/bootstrap.key');
        if (await bootstrap.exists()) {
          try {
            await _save((await bootstrap.readAsString()).trim());
          } finally {
            await bootstrap.delete();
          }
        }
      }
      final key = await _vault.read(key: 'router_key');
      if (key != null) {
        _crypto = WireCrypto(WireCrypto.fromHex(key));
        deviceIdentity = identityFor(key);
        bound = true;
      }
    } catch (_) {
      error = 'Не удалось прочитать привязку. Введи ключ ещё раз.';
    }
    initialized = true;
    notifyListeners();
    if (bound && _foreground) await connect();
  }

  Future<void> _save(String key) async {
    WireCrypto.fromHex(key);
    await _vault.write(key: 'router_key', value: key);
    _crypto = WireCrypto(WireCrypto.fromHex(key));
    deviceIdentity = identityFor(key);
    bound = true;
  }

  Future<bool> bind(String key) async {
    try {
      await _save(key.trim());
      error = null;
      notifyListeners();
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> forget() async {
    await disconnect();
    await _vault.delete(key: 'router_key');
    _crypto = null;
    bound = false;
    data = null;
    _updated = null;
    settings = null;
    vpn = null;
    deviceIdentity = null;
    notifyListeners();
  }

  Future<void> foreground(bool value) async {
    _foreground = value;
    if (!value) {
      // A system pairing/permission sheet temporarily pauses Flutter. Do not
      // abort the in-flight GATT connection while the user is responding.
      if (busy) return;
      await _close();
      phase = 'Связь приостановлена';
      notifyListeners();
    } else if (initialized && bound && _wanted && !busy && !connected) {
      await connect();
    }
  }

  Future<void> _close() async {
    _generation++;
    _deadline?.cancel();
    _poll?.cancel();
    _retry?.cancel();
    final scan = _scan, notices = _notifications, connection = _connection;
    _scan = null;
    _notifications = null;
    _connection = null;
    _writer = null;
    _session = '';
    _expected = -1;
    _input = [];
    busy = false;
    connected = false;
    down = null;
    up = null;
    _payload = 19;
    _previousSample = null;
    if (_command != null && !_command!.isCompleted) {
      _command!.completeError(
        StateError(
          'Связь прервалась. Результат команды неизвестен — обнови настройки перед повтором.',
        ),
      );
    }
    _command = null;
    await scan?.cancel();
    await notices?.cancel();
    await connection?.cancel();
  }

  Future<void> disconnect() async {
    _wanted = false;
    await _close();
    phase = 'Отключено';
    error = null;
    notifyListeners();
  }

  Future<void> _fail(String text, {bool retry = false}) async {
    if (!retry) _wanted = false;
    await _close();
    phase = 'Нет связи';
    error = text;
    notifyListeners();
    if (retry && _wanted && _foreground) {
      _retry = Timer(
        const Duration(seconds: 3),
        () => connect(autoRetry: true),
      );
    }
  }

  Future<void> connect({bool autoRetry = false}) async {
    if (!bound || !_foreground || busy) return;
    if (!autoRetry) _initialRetryBudget = 1;
    _linkOpened = false;
    _wanted = true;
    await _close();
    busy = true;
    phase = 'Ищу Photonicat…';
    error = null;
    notifyListeners();
    final generation = _generation;
    try {
      if (Platform.isAndroid) {
        final permission = await [
          Permission.bluetoothScan,
          Permission.bluetoothConnect,
        ].request();
        if (permission.values.any((s) => !s.isGranted)) {
          await _fail(
            'Разреши доступ к устройствам поблизости в настройках приложения.',
            retry: false,
          );
          return;
        }
      }
      if (generation != _generation) return;
      if (_ble.status != BleStatus.ready) {
        await _ble.statusStream
            .firstWhere((s) => s == BleStatus.ready)
            .timeout(const Duration(seconds: 6));
      }
      if (generation != _generation) return;
      _deadline = Timer(
        const Duration(seconds: 45),
        () => _fail('Роутер не найден. Поднеси телефон ближе.'),
      );
      _scan = _ble
          .scanForDevices(
            withServices: [service],
            scanMode: ScanMode.lowLatency,
          )
          .listen(
            (device) async {
              if (generation != _generation || _scan == null) return;
              if (device.name != 'PCat-$deviceIdentity') return;
              final scan = _scan;
              _scan = null;
              await scan?.cancel();
              _deadline?.cancel();
              if (generation != _generation) return;
              phase = 'Соединяюсь…';
              notifyListeners();
              _deadline = Timer(
                const Duration(seconds: 45),
                () => _fail('Роутер не ответил. Нажми «Подключить» ещё раз.'),
              );
              _connection = _ble
                  .connectToDevice(
                    id: device.id,
                    servicesWithCharacteristicsToDiscover: {
                      service: [rx, tx],
                    },
                    connectionTimeout: const Duration(seconds: 45),
                  )
                  .listen(
                    (update) {
                      if (generation != _generation) return;
                      if (update.connectionState ==
                          DeviceConnectionState.connected) {
                        _linkOpened = true;
                        unawaited(_prepare(device.id, generation));
                      } else if (update.connectionState ==
                          DeviceConnectionState.disconnected) {
                        final retry = !_linkOpened && _initialRetryBudget > 0;
                        if (retry) _initialRetryBudget--;
                        unawaited(
                          _fail(
                            retry
                                ? 'Повторяю установку Bluetooth-соединения…'
                                : 'Связь с роутером прервалась.',
                            retry: retry,
                          ),
                        );
                      }
                    },
                    onError: (Object e) {
                      if (kDebugMode) debugPrint("BLE stream failed: $e");
                      if (generation == _generation) {
                        unawaited(_fail('Не удалось соединиться с роутером.'));
                      }
                    },
                  );
            },
            onError: (Object e) {
              if (kDebugMode) debugPrint("BLE stream failed: $e");
              if (generation == _generation) {
                unawaited(_fail('Поиск Bluetooth недоступен.'));
              }
            },
          );
    } catch (_) {
      if (generation == _generation) {
        await _fail('Включи Bluetooth и повтори подключение.', retry: false);
      }
    }
  }

  Future<void> _prepare(String device, int generation) async {
    try {
      final mtu = await _ble.requestMtu(deviceId: device, mtu: 247);
      if (generation != _generation) return;
      _payload = (mtu - 4).clamp(19, 180);
      // Android can start bonding as soon as the link opens. Service discovery
      // must wait for the same pairing operation, without disconnect/reconnect.
      for (var attempt = 0; ; attempt++) {
        if (generation != _generation) return;
        try {
          await _ble.discoverAllServices(device);
          break;
        } catch (e) {
          if (!e.toString().contains('Bonding is in progress') ||
              attempt >= 60) {
            rethrow;
          }
          phase = 'Ожидаю подтверждения сопряжения…';
          notifyListeners();
          await Future<void>.delayed(const Duration(milliseconds: 500));
        }
      }
      if (generation != _generation) return;
      _writer = QualifiedCharacteristic(
        serviceId: service,
        characteristicId: rx,
        deviceId: device,
      );
      final reader = QualifiedCharacteristic(
        serviceId: service,
        characteristicId: tx,
        deviceId: device,
      );
      _notifications = _ble
          .subscribeToCharacteristic(reader)
          .listen(
            (bytes) {
              if (generation == _generation) _receive(bytes);
            },
            onError: (Object e) {
              if (kDebugMode) debugPrint("BLE stream failed: $e");
              if (generation == _generation) {
                unawaited(_fail('Получение данных прервалось.'));
              }
            },
          );
      // Allow CCC subscription to finish before the first request (no completion exposed by plugin).
      await Future<void>.delayed(const Duration(milliseconds: 600));
      if (generation != _generation) return;
      phase = 'Проверяю привязку…';
      notifyListeners();
      _challenge = WireCrypto.hex(WireCrypto.random(16));
      await _send('hello');
    } catch (e) {
      if (kDebugMode) debugPrint('BLE prepare failed: $e');
      if (generation == _generation) {
        await _fail('Сервис Bluetooth недоступен.');
      }
    }
  }

  Future<void> refresh() async {
    if (connected && !commandBusy && _expected < 0) {
      _poll?.cancel();
      await _send('status');
    }
  }

  static String identityFor(String key) => digest.Hmac(
    digest.sha256,
    WireCrypto.fromHex(key),
  ).convert(utf8.encode('photonicat/device-id/v1')).toString().substring(0, 8);

  Future<Map<String, dynamic>> command(
    String op, [
    Map<String, dynamic>? args,
  ]) async {
    if (!connected || commandBusy) {
      throw StateError('Сначала дождись подключения к роутеру.');
    }
    commandBusy = true;
    notifyListeners();
    try {
      _poll?.cancel();
      for (var attempt = 0; _expected >= 0 && attempt < 100; attempt++) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
      }
      _poll?.cancel();
      if (!connected || _expected >= 0) {
        throw StateError('Роутер занят. Повтори после обновления данных.');
      }
      final result = Completer<Map<String, dynamic>>();
      _command = result;
      // Attach the listener before sending: _close may complete with an error.
      final response = result.future;
      unawaited(_send(op, args));
      return await response;
    } finally {
      _command = null;
      commandBusy = false;
      notifyListeners();
      if (connected && _expected < 0) {
        _poll = Timer(const Duration(seconds: 1), () => _send('status'));
      }
    }
  }

  Future<void> _send(String op, [Map<String, dynamic>? args]) async {
    if (_expected >= 0 || _writer == null || _crypto == null) return;
    final generation = _generation;
    final request = <String, dynamic>{'seq': ++_sequence, 'op': op};
    if (args != null) request['args'] = args;
    _operation = op;
    if (op == 'hello') {
      request['challenge'] = _challenge;
    } else {
      request['sid'] = _session;
    }
    final bytes = [..._crypto!.seal(request), 10];
    _expected = _sequence;
    _deadline?.cancel();
    _deadline = Timer(
      Duration(seconds: op.startsWith('vpn_') || op == 'wifi_set' ? 90 : 45),
      () => _fail('Нет ответа от роутера. Обнови состояние после подключения.'),
    );
    try {
      for (var start = 0; start < bytes.length; start += _payload) {
        if (generation != _generation || _writer == null) return;
        await _ble.writeCharacteristicWithResponse(
          _writer!,
          value: [
            start == 0 ? 1 : 0,
            ...bytes.sublist(start, min(start + _payload, bytes.length)),
          ],
        );
      }
    } catch (_) {
      if (generation == _generation) await _fail('Не удалось передать запрос.');
    }
  }

  void _receive(List<int> bytes) {
    if (bytes.isEmpty) return;
    if (bytes.first == 1) _input = [];
    _input.addAll(bytes.skip(1));
    if (_input.length > 65536) {
      unawaited(_fail('Некорректный ответ.'));
      return;
    }
    if (_input.isEmpty || _input.last != 10) return;
    final encoded = _input.sublist(0, _input.length - 1);
    _input = [];
    try {
      final reply = _crypto!.open(encoded);
      if (reply['seq'] != _expected) return;
      if (_session.isEmpty) {
        if (reply['challenge'] != _challenge ||
            reply['sid'] is! String ||
            (reply['sid'] as String).length != 32) {
          throw const FormatException();
        }
        _session = reply['sid'];
        _expected = -1;
        _deadline?.cancel();
        connected = true;
        busy = false;
        phase = 'Bluetooth · защищено';
        error = null;
        notifyListeners();
        unawaited(_send('status'));
      } else {
        if (reply['sid'] != _session) {
          throw const FormatException();
        }
        if (_operation != 'status') {
          _expected = -1;
          _deadline?.cancel();
          if (reply['vpn'] is Map) {
            vpn = Map<String, dynamic>.from(reply['vpn']);
          }
          if (reply['settings'] is Map) {
            settings = Map<String, dynamic>.from(reply['settings']);
          }
          if (reply['ok'] != true) {
            _command?.completeError(
              StateError(reply['error'] as String? ?? 'Команда отклонена.'),
            );
          } else {
            _command?.complete(reply);
          }
          notifyListeners();
          return;
        }
        if (reply['ok'] != true) throw const FormatException();
        final next = Map<String, dynamic>.from(reply['status']);
        if (next['settings'] is Map) {
          settings = Map<String, dynamic>.from(next['settings']);
        }
        final dt = _previousSample == null
            ? 0.0
            : ((next['sample_time'] as num) -
                      (_previousSample!['sample_time'] as num))
                  .toDouble();
        double? speed(String name) {
          if (dt <= 0 || _previousSample?[name] is! num || next[name] is! num) {
            return null;
          }
          final delta = (next[name] as num) - (_previousSample![name] as num);
          return delta < 0 ? null : delta * 8 / dt / 1000000;
        }

        down = speed('rx_bytes');
        up = speed('tx_bytes');
        data = next;
        _previousSample = next;
        _updated = _clock.elapsedMilliseconds;
        _expected = -1;
        _deadline?.cancel();
        error = null;
        notifyListeners();
        if (!commandBusy) {
          _poll = Timer(const Duration(seconds: 3), () => _send('status'));
        }
      }
    } catch (_) {
      _wanted = false;
      unawaited(
        _fail(
          'Проверка привязки не пройдена. Проверь ключ роутера.',
          retry: false,
        ),
      );
    }
  }

  @override
  void dispose() {
    _wanted = false;
    unawaited(_close());
    super.dispose();
  }
}
