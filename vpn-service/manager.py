#!/usr/bin/env python3
"""Photonicat VPN control. Root-only files, fixed commands, no network-facing API.
Only owned routing tables/rules are changed; the main table is never modified.
"""
import base64
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import ssl
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.parse

ROOT = Path('/etc/photonicat-vpn')
BIN = Path('/opt/photonicat-vpn')
ACTIVE_TABLE = 23500
ENGINES = {
    'amneziawg': {'interface': 'pcawg0', 'table': 23501, 'port': 17881, 'group': 'PC-Amnezia'},
    'mihomo': {'interface': 'pcmh0', 'table': 23502, 'port': 17882, 'group': 'PC-Mihomo'},
}
RUNTIME = Path('/var/run/photonicat-vpn-awg.json')
SOCKET_MARK = 23499


def manifest():
    return json.loads((ROOT / 'profiles.json').read_text())


def profile(identifier):
    return next(p for p in manifest() if p['id'] == identifier)


def run(*args, check=True):
    return subprocess.run(list(map(str, args)), capture_output=True, check=check, timeout=10)


def atomic(path, data):
    temp = path.with_suffix('.new')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    os.replace(temp, path)


def ipc(interface, message):
    if not re.fullmatch(r'pcawg[0-9]+', interface):
        raise ValueError('Unknown interface')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(5)
        conn.connect('/var/run/amneziawg/' + interface + '.sock')
        conn.sendall(message.encode() + b'\n\n')
        data = b''
        while not data.endswith(b'\n\n') and len(data) < 65536:
            part = conn.recv(4096)
            if not part:
                break
            data += part
    fields = [tuple(line.split('=', 1)) for line in data.decode().splitlines() if '=' in line]
    if ('errno', '0') not in fields:
        raise RuntimeError('AmneziaWG rejected configuration')
    return fields


KEYS = {'PrivateKey': 'private_key', 'ListenPort': 'listen_port',
        'HeaderProtectionKey': 'header_protection_key',
        'ContentPaddingAddition': 'content_padding_addition', 'RekeyAfterTime': 'rekey_after_time',
        'RekeyTimeout': 'rekey_timeout', 'RejectAfterTime': 'reject_after_time',
        'KeepaliveTimeout': 'keepalive_timeout', 'MaxHandshakeAttempts': 'max_handshake_attempts',
        'RandomTrailers': 'random_trailers', 'DisableCookies': 'disable_cookies',
        **{k: k.lower() for k in ['Jc', 'Jmin', 'Jmax', 'S1', 'S2', 'S3', 'S4',
                                  'H1', 'H2', 'H3', 'H4', 'I1', 'I2', 'I3', 'I4', 'I5']}}
PEER_KEYS = {'PublicKey': 'public_key', 'PresharedKey': 'preshared_key',
             'Endpoint': 'endpoint', 'PersistentKeepalive': 'persistent_keepalive_interval'}


def parse_config(text):
    sections = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line in ('[Interface]', '[Peer]'):
            sections.append((line, {}))
        elif '=' in line and sections:
            key, value = map(str.strip, line.split('=', 1))
            if key in sections[-1][1]:
                raise ValueError('Duplicate config field')
            sections[-1][1][key] = value
        else:
            raise ValueError('Invalid config')
    if [s for s, _ in sections] != ['[Interface]', '[Peer]']:
        raise ValueError('Exactly one peer per profile is required')
    interface, peer = sections[0][1], sections[1][1]
    if set(interface) - (set(KEYS) | {'Address', 'DNS', 'MTU'}):
        raise ValueError('Unsupported config field or hook')
    if set(peer) - (set(PEER_KEYS) | {'AllowedIPs'}):
        raise ValueError('Unsupported peer field')
    return interface, peer


def awg_request(text):
    interface, peer = parse_config(text)
    lines = ['set=1', 'replace_peers=true', f'fwmark={SOCKET_MARK}']
    for fields, mapping in [(interface, KEYS), (peer, PEER_KEYS)]:
        # public_key must start the peer section regardless of source file order.
        order = sorted(fields, key=lambda key: key != 'PublicKey')
        for key in order:
            if key not in mapping:
                continue
            value = fields[key]
            if key in ('PrivateKey', 'PublicKey', 'PresharedKey', 'HeaderProtectionKey'):
                raw = base64.b64decode(value, validate=True)
                if len(raw) != 32:
                    raise ValueError('Invalid key length')
                value = raw.hex()
            if key in ('RandomTrailers', 'DisableCookies'):
                if value.lower() not in ('true', 'false', '1', '0', 'on', 'off', 'yes', 'no'):
                    raise ValueError('Invalid boolean')
                value = 'true' if value.lower() in ('1', 'true', 'on', 'yes') else 'false'
            if key == 'Endpoint':
                host, port = value.rsplit(':', 1)
                host = host.strip('[]')
                address = socket.getaddrinfo(host, int(port), type=socket.SOCK_DGRAM)[0][4][0]
                value = f'[{address}]:{port}' if ':' in address else f'{address}:{port}'
            lines.append(mapping[key] + '=' + value)
    lines.append('replace_allowed_ips=true')
    for prefix in peer['AllowedIPs'].split(','):
        lines.append('allowed_ip=' + str(ipaddress.ip_network(prefix.strip())))
    return '\n'.join(lines)


def ensure_rule(family, priority, selector, table):
    rules = json.loads(run('ip', family, '-j', 'rule').stdout)
    existing = [r for r in rules if r.get('priority') == priority]
    if existing:
        # Never replace an unrelated owner's rule at this priority.
        rule = existing[0]
        matches = str(rule.get('table')) == str(table)
        if selector[0] == 'fwmark':
            mark = rule.get('fwmark', '0')
            matches &= int(str(mark), 0) == int(selector[1])
            matches &= rule.get('src', 'all') == 'all'
            matches &= int(str(rule.get('fwmask', '0xffffffff')), 0) == 0xffffffff
        elif selector[0] == 'from':
            matches &= rule.get('src') in (selector[1], selector[1] + ('/32' if family == '-4' else '/128'))
            matches &= 'fwmark' not in rule
        matches &= not any(k in rule for k in ('iif', 'oif', 'dst', 'ipproto', 'not'))
        if len(existing) != 1 or not matches:
            raise RuntimeError('Routing rule priority conflict')
        return
    run('ip', family, 'rule', 'add', 'pref', priority, *selector, 'table', table)


def state():
    return json.loads((ROOT / 'state.json').read_text())


def interface_up(name):
    try:
        return bool(int(Path('/sys/class/net/' + name + '/flags').read_text().strip(), 16) & 1)
    except OSError:
        return False


def prepare_routes_locked():
    selected = state()['active']
    if (ROOT / 'ports.json').exists():
        import ports
        ports.sync_guard(selected)
    for fam in ('-4', '-6'):
        ensure_rule(fam, SOCKET_MARK, ['fwmark', SOCKET_MARK], 'main')
        for name, e in {**ENGINES, 'active': {**ENGINES[selected], 'table': ACTIVE_TABLE}}.items():
            table = e['table']
            run('ip', fam, 'route', 'replace', 'unreachable', 'default', 'metric', 32760, 'table', table)
            ensure_rule(fam, table, ['fwmark', table], table)
            if interface_up(e['interface']):
                run('ip', fam, 'route', 'replace', 'default', 'dev', e['interface'], 'metric', 10, 'table', table)
            else:
                run('ip', fam, 'route', 'del', 'default', 'metric', 10, 'table', table, check=False)


def prepare_routes():
    with (ROOT / 'control.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        prepare_routes_locked()


def awg_run():
    stopped = False
    child = None
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
        if child is not None and child.poll() is None:
            child.terminate()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopped:
        identifier = state()['amneziawg']
        p = profile(identifier)
        interface = ENGINES['amneziawg']['interface']
        RUNTIME.unlink(missing_ok=True)
        child = subprocess.Popen([str(BIN / 'amneziawg-go'), '-f', interface],
                                 env={**os.environ, 'LOG_LEVEL': 'error'})
        try:
            for _ in range(100):
                if stopped:
                    return
                if child.poll() is not None:
                    raise RuntimeError('AmneziaWG exited')
                if Path('/var/run/amneziawg/' + interface + '.sock').exists():
                    break
                time.sleep(.1)
            ipc(interface, awg_request((ROOT / 'profiles' / (identifier + '.conf')).read_text()))
            for address in p['addresses']:
                run('ip', 'address', 'replace', address, 'dev', interface, 'noprefixroute')
            run('ip', 'link', 'set', interface, 'mtu', p['mtu'], 'up')
            atomic(RUNTIME, {'profile': identifier, 'pid': child.pid})
            while not stopped and state()['amneziawg'] == identifier:
                if child.poll() is not None:
                    raise RuntimeError('AmneziaWG exited')
                time.sleep(.25)
        finally:
            RUNTIME.unlink(missing_ok=True)
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


def api(path, method='GET', payload=None, timeout=10):
    token = (ROOT / 'api-secret').read_text().strip()
    request = urllib.request.Request('http://127.0.0.1:19090' + path,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        data=None if payload is None else json.dumps(payload).encode(), method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
        return json.loads(data) if data else {}


def select_engine(engine):
    e = ENGINES[engine]
    if not interface_up(e['interface']):
        raise RuntimeError('Engine interface is not running')
    with (ROOT / 'control.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = state()
        proxy_synced = True
        try:
            api('/proxies/PC-Active', 'PUT', {'name': e['group']}, timeout=.5 if engine == 'amneziawg' else 3)
        except (OSError, ValueError):
            # Native AWG routing must remain selectable if the other core is down.
            if engine != 'amneziawg':
                raise
            proxy_synced = False
        try:
            atomic(ROOT / 'state.json', {**old, 'active': engine})
            prepare_routes_locked()
        except Exception:
            atomic(ROOT / 'state.json', old)
            try:
                api('/proxies/PC-Active', 'PUT', {'name': ENGINES[old['active']]['group']})
            except (OSError, ValueError):
                pass
            prepare_routes_locked()
            raise
    return {'active': engine, 'local_proxy_synced': proxy_synced,
            'scope': 'LAN VPN' if (ROOT / 'ports.json').exists() else 'VPN selector only'}


def select_awg(identifier):
    profile(identifier)
    with (ROOT / 'control.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = state()
        atomic(ROOT / 'state.json', {**old, 'amneziawg': identifier})
        try:
            for _ in range(100):
                try:
                    ready = json.loads(RUNTIME.read_text())['profile'] == identifier
                except (OSError, ValueError):
                    ready = False
                if ready and interface_up(ENGINES['amneziawg']['interface']):
                    prepare_routes_locked()
                    return {'amneziawg': identifier}
                time.sleep(.1)
            raise RuntimeError('AmneziaWG profile activation timed out')
        except Exception:
            atomic(ROOT / 'state.json', old)
            raise


def select_node(name):
    group = api('/proxies/PC-Mihomo')
    if name in ('DIRECT', 'COMPATIBLE', 'REJECT') or name not in group['all']:
        raise ValueError('Unknown subscription node')
    with (ROOT / 'control.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = state()
        previous = group.get('now')
        api('/proxies/PC-Mihomo', 'PUT', {'name': name})
        try:
            atomic(ROOT / 'state.json', {**old, 'mihomo': name})
        except Exception:
            if previous:
                api('/proxies/PC-Mihomo', 'PUT', {'name': previous})
            raise
    return {'mihomo': name}


def reconcile():
    # Restore persisted choices after a Mihomo restart; providers must be ready first.
    with (ROOT / 'control.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        prepare_routes_locked()
        s = state()
        for group, selected in [('PC-Active', ENGINES[s['active']]['group']), ('PC-Mihomo', s.get('mihomo'))]:
            current = api('/proxies/' + group, timeout=.5)
            if selected and selected in current.get('all', []) and current.get('now') != selected:
                api('/proxies/' + group, 'PUT', {'name': selected}, timeout=.5)


def status():
    s = state()
    result = {'active': s['active'], 'amneziawg': {'selected': s['amneziawg'], 'profiles': [{'id': p['id'], 'label': p['label']} for p in manifest()]}, 'mihomo': {'selected': s.get('mihomo'), 'nodes': []}}
    for engine, e in ENGINES.items():
        result[engine].update(e)
        result[engine]['running'] = interface_up(e['interface'])
    if result['amneziawg']['running']:
        try:
            runtime = json.loads(RUNTIME.read_text())
            result['amneziawg']['applied'] = runtime['profile']
            raw = dict(ipc(ENGINES['amneziawg']['interface'], 'get=1'))
            for key in ('last_handshake_time_sec', 'rx_bytes', 'tx_bytes'):
                result['amneziawg'][key] = int(raw.get(key, 0))
        except (OSError, RuntimeError, ValueError):
            result['amneziawg']['running'] = False
    try:
        result['mihomo']['version'] = api('/version', timeout=1)['version']
        group = api('/proxies/PC-Mihomo', timeout=1)
        result['mihomo']['applied'] = group.get('now')
        result['mihomo']['nodes'] = [n for n in group.get('all', []) if n not in ('DIRECT','COMPATIBLE','REJECT')]
        result['active_proxy'] = api('/proxies/PC-Active', timeout=1).get('now')
    except Exception:
        result['mihomo']['running'] = False
    return result


def check_exit(engine):
    e = ENGINES[engine]
    selected = state()['amneziawg' if engine == 'amneziawg' else 'mihomo']
    started = time.monotonic()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(8)
            sock.setsockopt(socket.SOL_SOCKET, 36, e['table'])
            sock.connect(('1.1.1.1', 443))
            with ssl.create_default_context().wrap_socket(sock, server_hostname='one.one.one.one') as conn:
                conn.sendall(b'GET /cdn-cgi/trace HTTP/1.1\r\nHost: one.one.one.one\r\nConnection: close\r\n\r\n')
                data = b''
                while len(data) < 16384:
                    part = conn.recv(4096)
                    if not part: break
                    data += part
        fields = dict(line.split('=', 1) for line in data.decode().splitlines() if '=' in line)
        address = str(ipaddress.ip_address(fields['ip']))
        return {'engine': engine, 'selected': selected, 'ok': True, 'ip': address,
                'elapsed_ms': round((time.monotonic()-started)*1000)}
    except (OSError, ValueError, KeyError):
        return {'engine': engine, 'selected': selected, 'ok': False}


def cleanup():
    for fam in ('-4', '-6'):
        for table in (ACTIVE_TABLE, 23501, 23502):
            run('ip', fam, 'rule', 'del', 'pref', table, 'fwmark', table, 'table', table, check=False)
            run('ip', fam, 'route', 'flush', 'table', table, check=False)
        run('ip', fam, 'rule', 'del', 'pref', SOCKET_MARK, 'fwmark', SOCKET_MARK, 'table', 'main', check=False)


if __name__ == '__main__':
    try:
        action = sys.argv[1]
        if action == 'awg-run':
            awg_run()
        elif action == 'routes':
            prepare_routes()
        elif action == 'monitor':
            while True:
                try:
                    reconcile()
                except Exception as exc:
                    print('VPN reconciliation pending: ' + type(exc).__name__, flush=True)
                time.sleep(5)
        elif action == 'status':
            print(json.dumps(status(), ensure_ascii=False))
        elif action == 'select-engine':
            print(json.dumps(select_engine(sys.argv[2]), ensure_ascii=False))
        elif action == 'select-awg':
            print(json.dumps(select_awg(sys.argv[2]), ensure_ascii=False))
        elif action == 'select-node':
            print(json.dumps(select_node(sys.argv[2]), ensure_ascii=False))
        elif action == 'check':
            print(json.dumps(check_exit(sys.argv[2])))
        elif action == 'manage':
            import catalog
            request = json.loads(sys.stdin.read(32769))
            with (ROOT / 'control.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                print(json.dumps(catalog.execute(request['action'], request['args']), ensure_ascii=False))
        elif action == 'catalog':
            import catalog
            print(json.dumps(catalog.subscriptions(), ensure_ascii=False))
        elif action == 'ports-status':
            import ports
            print(json.dumps(ports.status(), ensure_ascii=False))
        elif action == 'ports-set':
            import ports
            print(json.dumps(ports.request(json.loads(sys.stdin.read(1024))), ensure_ascii=False))
        elif action == 'ports-guard':
            import ports
            ports.sync_guard()
        elif action == 'ports-monitor':
            import ports
            ports.daemon()
        elif action == 'cleanup':
            cleanup()
        else:
            raise ValueError('Unknown action')
    except Exception as exc:
        print(json.dumps({'error': str(exc) if type(exc).__name__ in ('CatalogError', 'PortsError') else 'Операция VPN не выполнена.'}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
