import 'dart:async';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:photonicat/lan_channel.dart';
import 'package:photonicat/lan_connection.dart';
import 'package:photonicat/router_controller.dart';
import 'package:photonicat/wire_crypto.dart';

const key = '000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f';
final crypto = WireCrypto(WireCrypto.fromHex(key));

class FakeChannel implements LanChannel {
  FakeChannel(this.localAddress);
  final String localAddress;
  @override
  final String session = 'a' * 32;
  final input = StreamController<List<int>>();
  bool failWrite = false, silent = false, closed = false;
  final operations = <String>[];
  @override
  Stream<List<int>> get messages => input.stream;
  @override
  Future<void> send(List<int> bytes) async {
    if (failWrite) throw const SocketException('adapter lost');
    final request = crypto.open(bytes.sublist(0, bytes.length - 1));
    operations.add(request['op'] as String);
    if (silent) return;
    input.add([
      ...crypto.seal({
        'seq': request['seq'],
        'sid': session,
        'ok': true,
        'status': {
          'sample_time': DateTime.now().millisecondsSinceEpoch / 1000,
          'sample_age': 0,
        },
      }),
      10,
    ]);
  }

  @override
  Future<void> close() async {
    if (closed) return;
    closed = true;
    unawaited(input.close());
  }
}

Future<void> until(bool Function() condition) async {
  final deadline = DateTime.now().add(const Duration(seconds: 3));
  while (!condition()) {
    if (DateTime.now().isAfter(deadline)) fail('Condition did not become true');
    await Future<void>.delayed(const Duration(milliseconds: 10));
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  test(
    'discovers gateways from both adapters, including scoped Mac routes',
    () {
      expect(
        parseMacGateways(
          'default 192.168.1.1 UGScg en0\ndefault 172.16.0.1 UGScIg en5\n',
        ),
        ['192.168.1.1', '172.16.0.1'],
      );
      expect(
        parseWindowsGateways('192.168.1.1\r\n172.16.0.1\r\n192.168.1.1\r\n'),
        ['192.168.1.1', '172.16.0.1'],
      );
    },
  );

  for (final from in ['wifi', 'ethernet']) {
    test(
      '$from loss switches to the other adapter and keeps polling',
      () async {
        final to = from == 'wifi' ? 'ethernet' : 'wifi';
        final interfaces = <String, String>{'10.0.0.2': from, '10.0.1.2': to};
        final channels = <FakeChannel>[];
        final controller = RouterController(
          useLan: true,
          discoverLan: (_) async => ['router'],
          readLanInterfaces: () async => Map.of(interfaces),
          openLan: (_, _, _) async {
            final c = FakeChannel(channels.isEmpty ? '10.0.0.2' : '10.0.1.2');
            channels.add(c);
            return c;
          },
          lanMonitorInterval: const Duration(milliseconds: 20),
          lanRetryDelay: const Duration(milliseconds: 10),
          statusPollInterval: const Duration(milliseconds: 20),
        );
        addTearDown(controller.dispose);
        await controller.bind(key);
        await controller.connect();
        await until(() => controller.fresh);
        interfaces.remove('10.0.0.2');
        await until(() => channels.length == 2 && controller.fresh);
        expect(channels.first.closed, true);
        await until(() => channels.last.operations.length >= 2);
        await controller.disconnect();
        await Future<void>.delayed(const Duration(milliseconds: 80));
        expect(
          channels.length,
          2,
        ); // Explicit disconnect must not resurrect itself.
      },
    );
  }

  for (final failure in ['write', 'silent']) {
    test(
      '$failure socket failure reconnects even without an adapter notification',
      () async {
        final channels = <FakeChannel>[];
        final controller = RouterController(
          useLan: true,
          discoverLan: (_) async => ['router'],
          readLanInterfaces: () async => {'10.0.0.2': 'ethernet'},
          openLan: (_, _, _) async {
            final c = FakeChannel('10.0.0.2');
            channels.add(c);
            return c;
          },
          lanRetryDelay: const Duration(milliseconds: 10),
          lanReadTimeout: const Duration(milliseconds: 50),
          statusPollInterval: const Duration(milliseconds: 20),
        );
        addTearDown(controller.dispose);
        await controller.bind(key);
        await controller.connect();
        await until(() => controller.fresh);
        channels.first.failWrite = failure == 'write';
        channels.first.silent = failure == 'silent';
        await until(() => channels.length == 2 && controller.fresh);
        expect(channels.first.closed, true);
      },
    );
  }

  test('does not replay a mutating command after a lost response', () async {
    final channels = <FakeChannel>[];
    final controller = RouterController(
      useLan: true,
      discoverLan: (_) async => ['router'],
      readLanInterfaces: () async => {'10.0.0.2': 'ethernet'},
      openLan: (_, _, _) async {
        final c = FakeChannel('10.0.0.2');
        channels.add(c);
        return c;
      },
      lanRetryDelay: const Duration(milliseconds: 10),
    );
    addTearDown(controller.dispose);
    await controller.bind(key);
    await controller.connect();
    await until(() => controller.fresh);
    channels.first.silent = true;
    final command = controller.command('reboot');
    final expected = expectLater(command, throwsStateError);
    await until(() => channels.first.operations.contains('reboot'));
    await channels.first.close();
    await expected;
    await until(() => channels.length == 2 && controller.fresh);
    expect(channels.last.operations, isNot(contains('reboot')));
  });

  test('late discovery result is closed after a manual disconnect', () async {
    final pending = Completer<LanChannel>();
    final controller = RouterController(
      useLan: true,
      discoverLan: (_) async => ['router'],
      readLanInterfaces: () async => {},
      openLan: (_, _, _) => pending.future,
    );
    addTearDown(controller.dispose);
    await controller.bind(key);
    final connecting = controller.connect();
    await Future<void>.delayed(const Duration(milliseconds: 10));
    await controller.disconnect();
    final link = FakeChannel('10.0.0.2');
    pending.complete(link);
    await connecting;
    expect(controller.connected, false);
    expect(link.closed, true);
  });

  test('simultaneous reconnect requests open only one channel', () async {
    var opens = 0;
    final controller = RouterController(
      useLan: true,
      discoverLan: (_) async => ['router'],
      readLanInterfaces: () async => {'10.0.0.2': 'ethernet'},
      openLan: (_, _, _) async {
        opens++;
        return FakeChannel('10.0.0.2');
      },
    );
    addTearDown(controller.dispose);
    await controller.bind(key);
    await Future.wait([controller.connect(), controller.connect()]);
    expect(opens, 1);
  });

  for (final problem in ['key', 'challenge', 'sequence']) {
    test('rejects router handshake with wrong $problem', () async {
      final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
      final sockets = <Socket>[];
      addTearDown(() async {
        for (final s in sockets) {
          s.destroy();
        }
        await server.close();
      });
      server.listen((socket) {
        sockets.add(socket);
        final bytes = <int>[];
        socket.listen((chunk) {
          bytes.addAll(chunk);
          final end = bytes.indexOf(10);
          if (end < 0) return;
          final request = crypto.open(bytes.sublist(0, end));
          bytes.removeRange(0, end + 1);
          final signing = problem == 'key'
              ? WireCrypto(List.filled(32, 255))
              : crypto;
          socket.add([
            ...signing.seal({
              'seq': problem == 'sequence' ? 999 : request['seq'],
              'challenge': problem == 'challenge'
                  ? 'wrong'
                  : request['challenge'],
              'sid': 'b' * 32,
            }),
            10,
          ]);
        });
      });
      await expectLater(
        SocketLanChannel.connect('127.0.0.1', crypto, 1, port: server.port),
        throwsFormatException,
      );
    });
  }

  test(
    'TCP listener without valid router proof is rejected; next candidate works',
    () async {
      final sockets = <Socket>[];
      final silent = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
      final router = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(() async {
        for (final s in sockets) {
          s.destroy();
        }
        await silent.close();
        await router.close();
      });
      silent.listen((s) {
        sockets.add(s);
        s.listen((_) {});
      });
      router.listen((s) {
        sockets.add(s);
        final pending = <int>[];
        s.listen((bytes) {
          pending.addAll(bytes);
          final end = pending.indexOf(10);
          if (end < 0) return;
          final request = crypto.open(pending.sublist(0, end));
          pending.removeRange(0, end + 1);
          s.add([
            ...crypto.seal({
              'seq': request['seq'],
              'sid': 'b' * 32,
              'challenge': request['challenge'],
            }),
            10,
          ]);
        });
      });
      final attempts = <String>[];
      final controller = RouterController(
        useLan: true,
        discoverLan: (_) async => ['silent', 'router'],
        readLanInterfaces: () async => {},
        openLan: (host, crypto, seq) {
          attempts.add(host);
          return SocketLanChannel.connect(
            '127.0.0.1',
            crypto,
            seq,
            port: host == 'silent' ? silent.port : router.port,
            timeout: const Duration(milliseconds: 80),
          );
        },
        lanMonitorInterval: const Duration(hours: 1),
      );
      addTearDown(controller.dispose);
      await controller.bind(key);
      await controller.connect();
      expect(controller.connected, true);
      expect(attempts, ['silent', 'router']);
    },
  );
}
