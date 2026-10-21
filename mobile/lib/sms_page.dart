import 'package:flutter/material.dart';
import 'app_style.dart';
import 'router_controller.dart';

class SmsPage extends StatefulWidget {
  const SmsPage({super.key, required this.router, this.embedded = false});
  final RouterController router;
  final bool embedded;
  @override
  State<SmsPage> createState() => _SmsPageState();
}

class _SmsPageState extends State<SmsPage> {
  final List<Map<String, dynamic>> messages = [];
  bool loading = false, loaded = false, limited = false;
  int? next;
  String? error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) refresh();
    });
  }

  Future<void> refresh({bool more = false}) async {
    if (loading || !widget.router.connected || widget.router.commandBusy) {
      return;
    }
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final result = await widget.router.command(
        'sms_list',
        more ? {'before': next} : {},
      );
      final inbox = Map<String, dynamic>.from(result['sms'] as Map);
      final rows = (inbox['messages'] as List).map(
        (m) => Map<String, dynamic>.from(m as Map),
      );
      if (!mounted) return;
      setState(() {
        if (!more) messages.clear();
        final ids = messages.map((m) => m['id']).toSet();
        messages.addAll(rows.where((m) => !ids.contains(m['id'])));
        next = inbox['next'] as int?;
        limited = inbox['limited'] == true;
        loaded = true;
      });
    } catch (e) {
      if (mounted) {
        setState(
          () => error = e.toString().replaceFirst(
            RegExp(r'^(Exception|StateError|Bad state): '),
            '',
          ),
        );
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> open(Map<String, dynamic> message) async {
    if (loading || !widget.router.connected || widget.router.commandBusy) {
      return;
    }
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final result = await widget.router.command('sms_read', {
        'id': message['id'],
      });
      if (!mounted) return;
      final sms = result['sms_message'] as Map;
      await Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => Scaffold(
            appBar: AppBar(title: const Text('СМС')),
            body: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    sms['sender'] as String,
                    style: const TextStyle(fontSize: 24, color: yellow),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    sms['time'] as String,
                    style: const TextStyle(color: muted, fontSize: 12),
                  ),
                  const SizedBox(height: 24),
                  const Divider(color: rule),
                  const SizedBox(height: 16),
                  SelectableText(
                    sms['text'] as String,
                    style: const TextStyle(fontSize: 17, height: 1.6),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    } catch (e) {
      if (mounted) {
        setState(() => error = e.toString().replaceFirst('Exception: ', ''));
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: widget.router,
    builder: (context, _) {
      final available =
          widget.router.connected && !widget.router.commandBusy && !loading;
      final content = ListView(
        shrinkWrap: widget.embedded,
        padding: widget.embedded ? EdgeInsets.zero : const EdgeInsets.all(24),
        physics: widget.embedded
            ? const NeverScrollableScrollPhysics()
            : const AlwaysScrollableScrollPhysics(),
        children: [
          if (widget.embedded)
            Row(
              children: [
                Expanded(
                  child: Text('СМС', style: digits(30, color: Colors.white)),
                ),
                IconButton(
                  tooltip: 'Обновить СМС',
                  onPressed: available ? refresh : null,
                  icon: const Icon(Icons.refresh, color: yellow),
                ),
              ],
            ),
          if (widget.embedded) const SizedBox(height: 24),
          const Text(
            'ВХОДЯЩИЕ',
            style: TextStyle(color: yellow, fontSize: 12, letterSpacing: 2),
          ),
          const SizedBox(height: 8),
          const Text(
            'Сообщения на SIM-карту роутера',
            style: TextStyle(color: muted, fontSize: 13),
          ),
          const SizedBox(height: 24),
          if (loading)
            const Padding(
              padding: EdgeInsets.only(bottom: 20),
              child: LinearProgressIndicator(
                color: yellow,
                backgroundColor: rule,
              ),
            ),
          if (!widget.router.connected)
            const Padding(
              padding: EdgeInsets.only(bottom: 20),
              child: Text(
                'Подключись к роутеру по Bluetooth, чтобы загрузить СМС.',
                style: TextStyle(color: muted),
              ),
            ),
          if (error != null) ...[
            Text(error!, style: const TextStyle(color: Colors.orangeAccent)),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton(
                onPressed: available ? refresh : null,
                child: const Text('Повторить'),
              ),
            ),
          ],
          if (loaded && messages.isEmpty && !loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 48),
              child: Column(
                children: [
                  Icon(Icons.mark_email_read_outlined, size: 42, color: muted),
                  SizedBox(height: 16),
                  Text('Пока нет входящих СМС', style: TextStyle(color: muted)),
                ],
              ),
            ),
          for (final sms in messages) ...[
            ListTile(
              contentPadding: const EdgeInsets.symmetric(vertical: 12),
              leading: const Icon(Icons.sms_outlined, color: yellow),
              title: Text(
                sms['sender'] as String,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              subtitle: Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      sms['preview'] as String,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: muted, height: 1.4),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      sms['time'] as String,
                      style: const TextStyle(color: muted, fontSize: 11),
                    ),
                  ],
                ),
              ),
              trailing: const Icon(Icons.chevron_right, color: muted, size: 18),
              onTap: available ? () => open(sms) : null,
            ),
            const Divider(color: rule, height: 1),
          ],
          if (next != null)
            Padding(
              padding: const EdgeInsets.only(top: 16),
              child: OutlinedButton(
                onPressed: available ? () => refresh(more: true) : null,
                child: const Text('Загрузить ещё'),
              ),
            ),
          if (limited)
            const Padding(
              padding: EdgeInsets.only(top: 24),
              child: Text(
                'Доступны последние 200 сообщений в памяти роутера.',
                style: TextStyle(color: muted, fontSize: 12),
              ),
            ),
        ],
      );
      if (widget.embedded) return content;
      return Scaffold(
        appBar: AppBar(
          title: Text('СМС', style: digits(22)),
          actions: [
            IconButton(
              tooltip: 'Обновить СМС',
              onPressed: available ? refresh : null,
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        body: RefreshIndicator(
          color: yellow,
          onRefresh: refresh,
          child: content,
        ),
      );
    },
  );
}
