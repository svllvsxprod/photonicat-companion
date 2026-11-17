import 'dart:async';
import 'dart:collection';

/// Keeps one BLE request in flight. User actions precede queued refreshes.
class CommandQueue {
  CommandQueue({required this.onChanged});
  final void Function() onChanged;
  final _foreground = Queue<_QueuedCommand>();
  final _background = Queue<_QueuedCommand>();
  _QueuedCommand? _active;
  bool get busy =>
      _active != null || _foreground.isNotEmpty || _background.isNotEmpty;
  bool get foregroundBusy =>
      (_active != null && !_active!.background) || _foreground.isNotEmpty;

  Future<T> run<T>(Future<T> Function() task, {bool background = false}) {
    final result = Completer<T>();
    final entry = _QueuedCommand(background, () async {
      try {
        result.complete(await task());
      } catch (error, stack) {
        result.completeError(error, stack);
      }
    });
    (background ? _background : _foreground).add(entry);
    onChanged();
    if (_active == null) unawaited(_drain());
    return result.future;
  }

  Future<void> _drain() async {
    while (_foreground.isNotEmpty || _background.isNotEmpty) {
      final next = (_foreground.isNotEmpty ? _foreground : _background)
          .removeFirst();
      _active = next;
      onChanged();
      await next.run();
      _active = null;
    }
    onChanged();
  }
}

class _QueuedCommand {
  _QueuedCommand(this.background, this.run);
  final bool background;
  final Future<void> Function() run;
}
