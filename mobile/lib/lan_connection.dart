import 'dart:async';
import 'dart:convert';
import 'dart:io';

const companionPort = 24862;
bool get isDesktop => Platform.isMacOS || Platform.isWindows;

List<String> parseMacGateways(String output) => output
    .split('\n')
    .map(
      (line) =>
          RegExp(r'^default\s+(\d+\.\d+\.\d+\.\d+)\s').firstMatch(line.trim()),
    )
    .whereType<RegExpMatch>()
    .map((match) => match.group(1)!)
    .toSet()
    .toList();

List<String> parseWindowsGateways(String output) => output
    .split(RegExp(r'\s+'))
    .where(
      (value) =>
          InternetAddress.tryParse(value)?.type == InternetAddressType.IPv4,
    )
    .where((value) => value != '0.0.0.0')
    .toSet()
    .toList();

Future<String> _routeOutput() async {
  // Read all adapter gateways, not just the default Internet connection.
  final process = await Process.start(
    Platform.isMacOS ? '/usr/sbin/netstat' : 'powershell.exe',
    Platform.isMacOS
        ? ['-rn', '-f', 'inet']
        : [
            '-NoProfile',
            '-NonInteractive',
            '-Command',
            'Get-NetIPConfiguration | Where-Object { \$_.NetAdapter.Status -eq "Up" } | ForEach-Object { \$_.IPv4DefaultGateway.NextHop }',
          ],
  );
  final output = process.stdout.transform(utf8.decoder).join();
  final errors = process.stderr.drain<void>();
  try {
    await process.exitCode.timeout(const Duration(seconds: 3));
    await errors;
    return await output;
  } finally {
    process.kill();
  }
}

Future<List<String>> routerCandidates(String? saved) async {
  final hosts = <String>{};
  try {
    final output = await _routeOutput();
    hosts.addAll(
      Platform.isMacOS
          ? parseMacGateways(output)
          : parseWindowsGateways(output),
    );
  } catch (_) {
    // A failed OS query must not prevent trying the saved address and defaults.
  }
  if (saved != null && saved.isNotEmpty) hosts.add(saved);
  hosts.addAll([
    '172.16.48.1',
    '172.16.0.1',
    '172.16.32.1',
    '172.16.16.1',
    '172.31.254.1',
  ]);
  return hosts.toList();
}

/// Local IPv4 address -> adapter identity. No Internet connectivity test is used.
Future<Map<String, String>> lanInterfaces() async {
  final addresses = <String, List<String>>{};
  for (final adapter in await NetworkInterface.list(
    type: InternetAddressType.IPv4,
  )) {
    for (final address in adapter.addresses) {
      addresses
          .putIfAbsent(address.address, () => [])
          .add('${adapter.index}:${adapter.name}');
    }
  }
  return addresses.map((address, adapters) {
    adapters.sort();
    return MapEntry(address, adapters.join('|'));
  });
}
