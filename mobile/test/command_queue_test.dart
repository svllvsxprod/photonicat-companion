import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:photonicat/command_queue.dart';

void main() {
  test(
    'refresh stays nonblocking, action precedes queued refresh, no overlap',
    () async {
      final queue = CommandQueue(onChanged: () {});
      final readGate = Completer<void>();
      final writeGate = Completer<void>();
      final calls = <String>[];
      var inFlight = 0;
      var maxInFlight = 0;
      Future<void> run(String name, [Future<void>? gate]) async {
        calls.add(name);
        inFlight++;
        if (inFlight > maxInFlight) maxInFlight = inFlight;
        if (gate != null) await gate;
        inFlight--;
      }

      final first = queue.run(
        () => run('read1', readGate.future),
        background: true,
      );
      expect(queue.foregroundBusy, isFalse);
      final second = queue.run(() => run('read2'), background: true);
      final action = queue.run(() => run('write', writeGate.future));
      expect(queue.foregroundBusy, isTrue);
      expect(calls, ['read1']);
      readGate.complete();
      await first;
      await Future<void>.delayed(Duration.zero);
      expect(calls, ['read1', 'write']);
      writeGate.complete();
      await Future.wait([action, second]);
      await Future<void>.delayed(Duration.zero);
      expect(calls, ['read1', 'write', 'read2']);
      expect(maxInFlight, 1);
      expect(queue.busy, isFalse);
      expect(queue.foregroundBusy, isFalse);
    },
  );
  test(
    'failed request is delivered once and does not strand the next action',
    () async {
      final queue = CommandQueue(onChanged: () {});
      final gate = Completer<void>();
      var writes = 0;
      final failed = queue.run(() async {
        await gate.future;
        throw StateError('Disconnected');
      }, background: true);
      final checked = expectLater(failed, throwsStateError);
      final next = queue.run(() async => ++writes);
      gate.complete();
      await checked;
      expect(await next, 1);
      expect(writes, 1);
    },
  );
}
