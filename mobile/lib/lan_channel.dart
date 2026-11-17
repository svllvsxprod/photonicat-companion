import 'dart:async';
import 'dart:io';
import 'lan_connection.dart';
import 'wire_crypto.dart';

abstract interface class LanChannel {
  String get session;
  Stream<List<int>> get messages;
  Future<void> send(List<int> bytes);
  Future<void> close();
}

/// Only yields a channel after the router proves possession of the saved key.
/// A TCP listener alone must never stop discovery of other adapter gateways.
class SocketLanChannel implements LanChannel {
  SocketLanChannel._(this._socket);
  final Socket _socket;
  final _messages = StreamController<List<int>>();
  StreamSubscription<List<int>>? _subscription;
  bool _closed = false;
  @override
  late final String session;
  @override
  Stream<List<int>> get messages => _messages.stream;

  static Future<LanChannel> connect(
    String host,
    WireCrypto crypto,
    int sequence, {
    int port = companionPort,
    Duration timeout = const Duration(seconds: 3),
  }) async {
    final socket = await Socket.connect(
      host,
      port,
      timeout: const Duration(seconds: 2),
    );
    socket.setOption(SocketOption.tcpNoDelay, true);
    final channel = SocketLanChannel._(socket);
    final ready = Completer<void>();
    var authenticated = false;
    var pending = <int>[];
    final challenge = WireCrypto.hex(WireCrypto.random(16));
    void failed(Object error) {
      if (channel._closed) return;
      if (!ready.isCompleted) {
        ready.completeError(error);
      } else if (authenticated && !channel._messages.isClosed) {
        channel._messages.addError(error);
      }
      unawaited(channel.close());
    }

    channel._subscription = socket.listen(
      (bytes) {
        if (channel._closed) return;
        pending.addAll(bytes);
        if (pending.length > 65536) {
          failed(const FormatException('Oversized router response'));
          return;
        }
        int end;
        while ((end = pending.indexOf(10)) >= 0) {
          final line = pending.sublist(0, end);
          pending = pending.sublist(end + 1);
          if (!authenticated) {
            try {
              final reply = crypto.open(line);
              if (reply['seq'] != sequence ||
                  reply['challenge'] != challenge ||
                  reply['sid'] is! String ||
                  (reply['sid'] as String).length != 32) {
                throw const FormatException('Router authentication failed');
              }
              channel.session = reply['sid'] as String;
              authenticated = true;
              ready.complete();
            } catch (error) {
              failed(error);
              return;
            }
          } else {
            channel._messages.add([...line, 10]);
          }
        }
      },
      onError: failed,
      onDone: () {
        if (!ready.isCompleted) {
          ready.completeError(const SocketException('Router disconnected'));
        }
        unawaited(channel.close());
      },
    );
    // Attach an error listener before any socket callback can complete ready.
    final handshake = ready.future.timeout(timeout);
    try {
      await Future.wait([
        channel.send([
          ...crypto.seal({
            'op': 'hello',
            'seq': sequence,
            'challenge': challenge,
          }),
          10,
        ]),
        handshake,
      ], eagerError: true).timeout(timeout);
      if (channel._closed) throw const SocketException('Router disconnected');
      return channel;
    } catch (_) {
      // Observe handshake failure even when the write itself failed first.
      unawaited(handshake.catchError((Object _) {}));
      await channel.close();
      rethrow;
    }
  }

  @override
  Future<void> send(List<int> bytes) async {
    if (_closed) throw const SocketException('Connection closed');
    _socket.add(bytes);
    await _socket.flush();
  }

  @override
  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    _socket.destroy();
    unawaited(_messages.close());
    await _subscription?.cancel();
  }
}
