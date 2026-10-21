"""Fixed LAN privacy policy and conservative DHCP-based WAN role selection."""
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import time
import manager as m

CONFIG = m.ROOT / 'ports.json'
RUNTIME = Path('/var/run/photonicat-ports.json')
GUARD = Path('/etc/photonicat-vpn/ports.nft')
ENGINES = {'amneziawg': 'pcawg0', 'mihomo': 'pcmh0'}
_applied_role = None


class PortsError(ValueError):
    pass


def config():
    return json.loads(CONFIG.read_text())


def secure_mihomo_config():
    import catalog
    c = catalog.configuration()
    c['dns']['nameserver'] = ['https://1.1.1.1/dns-query#PC-Mihomo']
    c['dns']['proxy-server-nameserver'] = ['https://1.1.1.1/dns-query']
    for listener in c['listeners']:
        if listener.get('type') == 'tun':
            listener['dns-hijack'] = []
            # gVisor terminates TCP inside the core; the mixed/system stack
            # needs a kernel TCP listener reachable through the VPN input zone.
            listener['stack'] = 'gvisor'
    # An empty provider must reject, never use Mihomo's implicit DIRECT fallback.
    group = next(g for g in c['proxy-groups'] if g['name'] == 'PC-Mihomo')
    group['proxies'] = ['REJECT']
    catalog.reload_config(c)


def checked_device(value):
    import re
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,15}', value):
        raise PortsError('Некорректное имя порта.')
    return value


def nft(script):
    subprocess.run(['nft', '-f', '-'], input=script, text=True,
                   capture_output=True, check=True, timeout=5)


def guard_text(c, engine):
    lan = checked_device(c['lan_bridge'])
    direct = checked_device(c['direct_bridge'])
    wan = checked_device(c['wan_device'])
    out = f'elements = {{ "{ENGINES[engine]}" }};' if c['lan_enabled'] else ''
    wifi = checked_device(c['wifi_bridge']) if c.get('wifi_bridge') else None
    protected = f'{{ "{lan}", "{wifi}" }}' if wifi else f'"{lan}"'
    wifi_set = f'set wifi_exit {{ type ifname; elements = {{ "{ENGINES[engine]}" }}; }}' if wifi else ''
    lan_direct = c.get('lan_mode', 'vpn') == 'direct' and c['lan_enabled']
    lan_mark = m.SOCKET_MARK if lan_direct else m.ACTIVE_TABLE
    lan_forward = (f'iifname "{lan}" oifname {{ "pcawg0", "pcmh0" }} counter drop\n'
                   f'  iifname "{lan}" counter accept\n'
                   f'  oifname "{lan}" iifname {{ "pcawg0", "pcmh0" }} counter drop') if lan_direct else (
                   f'iifname "{lan}" oifname @vpn_exit counter accept\n'
                   f'  iifname "{lan}" counter drop\n'
                   f'  oifname "{lan}" iifname @vpn_exit counter accept\n'
                   f'  oifname "{lan}" counter drop')
    wifi_mark = f'iifname "{wifi}" meta mark set {m.ACTIVE_TABLE}' if wifi else ''
    direct_nat = f'iifname "{lan}" meta mark {m.SOCKET_MARK} oifname != {{ "pcawg0", "pcmh0" }} counter masquerade' if lan_direct else ''
    wifi_forward = (f'iifname "{wifi}" oifname @wifi_exit counter accept\n'
                    f'  iifname "{wifi}" counter drop') if wifi else ''
    # Independent table survives fw4 reloads and stopping the VPN service.
    # No conntrack-established exception can bypass this forward guard.
    return f'''table inet pcat_ports {{
 set vpn_exit {{ type ifname; {out} }}
 {wifi_set}
 chain mark_lan {{
  type filter hook prerouting priority -140; policy accept;
  iifname "{lan}" meta mark set {lan_mark}
  {wifi_mark}
 }}
 chain dns_lan {{
  type nat hook prerouting priority -105; policy accept;
  iifname {protected} meta nfproto ipv4 meta l4proto {{ tcp, udp }} th dport 53 counter dnat ip to 1.1.1.1
  iifname {protected} meta nfproto ipv6 meta l4proto {{ tcp, udp }} th dport 53 counter dnat ip6 to 2606:4700:4700::1111
 }}
 chain input_guard {{
  type filter hook input priority -10; policy accept;
  iifname {protected} meta l4proto {{ tcp, udp }} th dport 53 counter drop
 }}
 chain forward_guard {{
  type filter hook forward priority -10; policy accept;
  {lan_forward}
  {wifi_forward}
  iifname {{ "{direct}", "{wan}" }} oifname {{ "pcawg0", "pcmh0" }} counter drop
 }}
 chain tunnel_nat {{
  type nat hook postrouting priority 95; policy accept;
  iifname {protected} oifname {{ "pcawg0", "pcmh0" }} counter masquerade
  {direct_nat}
 }}
}}
'''


def sync_guard(engine=None):
    if not CONFIG.exists():
        return
    with (m.ROOT / 'ports-guard.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _sync_guard(engine)


def _sync_guard(engine=None):
    c = config()
    engine = engine or m.state()['active']
    text = guard_text(c, engine)
    if not GUARD.exists() or GUARD.read_text() != text:
        GUARD.write_text(text)
    # Flush/add the set in one nft transaction: never temporarily allow both exits.
    existing = subprocess.run(['nft', 'list', 'table', 'inet', 'pcat_ports'],
                              capture_output=True, timeout=5).returncode == 0
    digest = hashlib.sha256(text.encode()).hexdigest()
    applied = Path('/var/run/photonicat-guard-version')
    if existing and applied.exists() and applied.read_text() == digest:
        value = f'add element inet pcat_ports vpn_exit {{ "{ENGINES[engine]}" }}\n' if c['lan_enabled'] else ''
        if c.get('wifi_bridge'):
            value += f'flush set inet pcat_ports wifi_exit\nadd element inet pcat_ports wifi_exit {{ "{ENGINES[engine]}" }}\n'
        nft('flush set inet pcat_ports vpn_exit\n' + value)
    else:
        # Replacing the table in one transaction upgrades its structure without
        # exposing a gap. A failed transaction retains the previous guard.
        nft(('delete table inet pcat_ports\n' if existing else '') + text)
        applied.write_text(digest)


def carrier(device):
    try:
        return Path('/sys/class/net', device, 'carrier').read_text().strip() == '1'
    except OSError:
        return False


def interface_status(name):
    try:
        return json.loads(subprocess.check_output(
            ['ubus', 'call', 'network.interface.' + name, 'status'],
            timeout=2, stderr=subprocess.DEVNULL))
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def status():
    if not CONFIG.exists():
        return {'installed': False}
    c = config()
    try:
        runtime = json.loads(RUNTIME.read_text())
    except (OSError, ValueError):
        runtime = {}
    role = runtime.get('role', 'detecting')
    wan = interface_status('wan' if role != 'share' else 'pcwan')
    guard = subprocess.run(['nft', 'list', 'table', 'inet', 'pcat_ports'],
                           capture_output=True, timeout=3).returncode == 0
    engine = m.state()['active']
    return {
        'installed': True, 'wan_mode': c['wan_mode'], 'wan_role': role,
        'wan_link': carrier(c['wan_device']), 'lan_link': carrier(c['lan_device']),
        'wan_reason': runtime.get('reason', 'starting'),
        'wan_address': next((a['address'] for a in wan.get('ipv4-address', [])), None),
        'wan_gateway': next((r.get('nexthop') for r in wan.get('route', []) if r.get('target') == '0.0.0.0'), None),
        'lan_enabled': c['lan_enabled'], 'lan_mode': c.get('lan_mode','vpn'), 'kill_switch': guard,
        'lan_state': ('paused' if not c['lan_enabled'] else
                      'direct' if c.get('lan_mode','vpn') == 'direct' else
                      'vpn' if guard and m.interface_up(ENGINES[engine]) else 'blocked'),
        'lan_address': c['lan_address'], 'direct_address': c['direct_address'],
        'share_address': c['share_address'], 'dns_policy': 'direct' if c.get('lan_mode','vpn') == 'direct' else 'vpn_only',
        'ipv6_policy': 'uplink' if c.get('lan_mode','vpn') == 'direct' else 'vpn_or_block', 'engine': engine,
    }


def request(args):
    if set(args) != {'setting', 'value'}:
        raise PortsError('Неизвестные параметры портов.')
    key, value = args['setting'], args['value']
    if key == 'wan_mode':
        if value not in ('auto', 'uplink', 'share'):
            raise PortsError('Неизвестный режим WAN.')
    elif key == 'lan_mode':
        if value not in ('direct', 'vpn'):
            raise PortsError('Неизвестный режим LAN.')
    elif key == 'lan_enabled':
        if type(value) is not bool:
            raise PortsError('Некорректное состояние LAN.')
    else:
        raise PortsError('Неизвестная настройка портов.')
    with (m.ROOT / 'ports.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        c = config()
        m.atomic(CONFIG, {**c, key: value, **({'lan_enabled': True} if key == 'lan_mode' else {})})
        # Pause is immediate and does not depend on the role detector.
        sync_guard()
    return {'message': 'Настройка сохранена. Роль WAN определяется автоматически.' if key == 'wan_mode'
            else 'LAN: Direct.' if key == 'lan_mode' and value == 'direct'
            else 'LAN: VPN с kill switch.' if key == 'lan_mode'
            else 'LAN включён: только VPN.' if value else 'Интернет на LAN заблокирован.'}


def checksum(data):
    if len(data) & 1:
        data += b'\0'
    total = sum(struct.unpack('!' + 'H' * (len(data) // 2), data))
    while total >> 16:
        total = (total & 65535) + (total >> 16)
    return (~total) & 65535


def discover_frame(mac, xid):
    bootp = struct.pack('!BBBBIHH4s4s4s4s16s64s128s', 1, 1, 6, 0, xid, 0, 0x8000,
                        b'\0'*4, b'\0'*4, b'\0'*4, b'\0'*4, mac+b'\0'*10,
                        b'\0'*64, b'\0'*128)
    payload = (bootp + b'\x63\x82\x53\x63\x35\x01\x01\x37\x03\x01\x03\x06\xff').ljust(300, b'\0')
    udp = struct.pack('!HHHH', 68, 67, len(payload)+8, 0) + payload
    ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, len(udp)+20, 0, 0, 64, 17, 0,
                     b'\0'*4, b'\xff'*4)
    ip = ip[:10] + struct.pack('!H', checksum(ip)) + ip[12:]
    return b'\xff'*6 + mac + b'\x08\x00' + ip + udp


def router_solicitation(mac):
    source = b'\0' * 16
    destination = socket.inet_pton(socket.AF_INET6, 'ff02::2')
    body = b'\x85\0\0\0\0\0\0\0'
    pseudo = source + destination + struct.pack('!I3xB', len(body), 58)
    body = body[:2] + struct.pack('!H', checksum(pseudo + body)) + body[4:]
    header = struct.pack('!IHBB16s16s', 6 << 28, len(body), 58, 255, source, destination)
    return bytes.fromhex('333300000002') + mac + b'\x86\xdd' + header + body


def router_advertisement(frame, mac):
    if (len(frame) >= 70 and frame[6:12] != mac and frame[12:14] == b'\x86\xdd'
            and frame[20] == 58 and frame[21] == 255 and frame[54] == 134
            and ipaddress.ip_address(frame[22:38]).is_link_local):
        return 'ra:' + str(ipaddress.ip_address(frame[22:38]))
    return None


def dhcp_offer(frame, mac, xid):
    if len(frame) < 282 or frame[12:14] != b'\x08\x00':
        return None
    ihl = (frame[14] & 15) * 4
    if ihl < 20 or frame[23] != 17:
        return None
    udp = frame[14+ihl:]
    if udp[:4] != b'\x00\x43\x00\x44':
        return None
    data = udp[8:]
    if len(data) < 240 or data[0] != 2 or data[4:8] != struct.pack('!I', xid) or data[28:34] != mac:
        return None
    if data[236:240] != b'\x63\x82\x53\x63':
        return None
    options = {}
    i = 240
    while i < len(data):
        key = data[i]; i += 1
        if key == 255:
            break
        if key == 0:
            continue
        if i >= len(data) or i + 1 + data[i] > len(data):
            return None
        size = data[i]; i += 1
        options[key] = data[i:i+size]; i += size
    if options.get(53) != b'\x02':
        return None
    return str(ipaddress.ip_address(options.get(54, frame[26:30])))


def probe(device, seconds=6):
    """DISCOVER only, never REQUEST a lease or alter the active WAN address."""
    device = checked_device(device)
    mac = bytes.fromhex(Path('/sys/class/net', device, 'address').read_text().strip().replace(':', ''))
    xid = secrets.randbits(32)
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3)) as sock:
        sock.bind((device, 0))
        sock.settimeout(.25)
        end = time.monotonic() + seconds
        send_at = 0
        while time.monotonic() < end:
            if time.monotonic() >= send_at:
                sock.send(discover_frame(mac, xid))
                sock.send(router_solicitation(mac))
                send_at = time.monotonic() + 2
            try:
                frame = sock.recv(65535)
            except socket.timeout:
                continue
            found = dhcp_offer(frame, mac, xid)
            if found:
                # Ignore our own direct-output DHCP server.
                if frame[6:12] != mac:
                    return found
            router = router_advertisement(frame, mac)
            if router:
                return router
    return None


def decide(mode, linked, server, has_lease=False):
    if not linked:
        return 'uplink', 'no_cable'
    if server:
        return 'uplink', 'ipv6_router' if server.startswith('ra:') else 'dhcp_server'
    if has_lease:
        return 'uplink', 'lease'
    if mode == 'uplink':
        return 'uplink', 'manual'
    return 'share', 'manual' if mode == 'share' else 'no_dhcp_server'


def sync_wan_zone(uplink):
    values = json.loads(subprocess.check_output(
        ['ubus', 'call', 'uci', 'get', '{"config":"firewall"}'], text=True))['values']
    zones = [(key, value) for key, value in values.items()
             if value.get('.type') == 'zone' and value.get('name') == 'wan']
    if len(zones) != 1:
        raise PortsError('Не удалось однозначно определить внешнюю зону.')
    key, zone = zones[0]
    networks = zone.get('network', [])
    if isinstance(networks, str):
        networks = networks.split()
    for name in ('wan', 'wan6'):
        if uplink and name not in networks:
            m.run('uci', 'add_list', f'firewall.{key}.network={name}')
        elif not uplink and name in networks:
            m.run('uci', 'del_list', f'firewall.{key}.network={name}')
    m.run('uci', 'commit', 'firewall')


def apply_role(role):
    global _applied_role
    uplink = role == 'uplink'
    current = subprocess.check_output(['uci', '-q', 'get', 'network.pcwan.disabled'], text=True).strip()
    if current == ('1' if uplink else '0') and _applied_role == role:
        return
    _applied_role = None
    if current != ('1' if uplink else '0'):
        # Turn the outgoing role off before bringing the other one up.
        for name in (['pcwan'] if uplink else ['wan', 'wan6']):
            subprocess.run(['ifdown', name], capture_output=True, timeout=5)
        for name in ('wan', 'wan6'):
            m.run('uci', 'set', f'network.{name}.disabled={0 if uplink else 1}')
        m.run('uci', 'set', f'network.pcwan.disabled={1 if uplink else 0}')
        m.run('uci', 'commit', 'network')
        m.run('ubus', 'call', 'network', 'reload')
    if not uplink:
        # network reload returns before the new static interface is ready.
        # Rebuilding dnsmasq/fw4 earlier can omit its DHCP range and leave eth0
        # in the old input/forward zone. The firmware's device-presence checker
        # cannot detect a device which is present but in the wrong zone.
        for _ in range(40):
            ready = interface_status('pcwan')
            if ready.get('up') and ready.get('ipv4-address'):
                break
            time.sleep(.25)
        else:
            raise PortsError('Порт раздачи ещё не получил адрес.')
    # dnsmasq translates the stock wan.ignore flag to a PHYSICAL-device ban.
    # Both logical roles use eth0, so leaving it set also blocks pcwan DHCP.
    m.run('uci', 'set', f'dhcp.wan.ignore={1 if uplink else 0}')
    m.run('uci', 'commit', 'dhcp')
    # fw4 can resolve the physical device of disabled networks. Explicitly
    # detach the two receiving interfaces from the external zone when sharing;
    # otherwise eth0 matches input_wan before input_pcdirect.
    sync_wan_zone(uplink)
    m.run('/etc/init.d/firewall', 'reload')
    m.run('/etc/init.d/dnsmasq', 'reload')
    _applied_role = role
    m.run('logger', '-t', 'photonicat-ports', 'WAN role ready: ' + role, check=False)


def daemon():
    sync_guard()
    # Start conservatively on every boot. Never restore a DHCP server blindly.
    apply_role('uplink')
    role = 'uplink'
    last_link = False
    last_mode = None
    next_probe = 0
    linked_since = time.monotonic()
    while True:
        try:
            c = config()
            linked = carrier(c['wan_device'])
            mode = c['wan_mode']
            if linked != last_link or mode != last_mode:
                apply_role('uplink')
                role = 'uplink'
                linked_since = time.monotonic()
                next_probe = 0
            if not linked:
                m.atomic(RUNTIME, {'role': 'idle', 'reason': 'no_cable'})
            elif time.monotonic() >= next_probe:
                # Let netifd complete ordinary DHCP before the no-server decision.
                if role == 'uplink' and mode == 'auto' and time.monotonic()-linked_since < 12:
                    m.atomic(RUNTIME, {'role': 'detecting', 'reason': 'probing'})
                else:
                    wan = interface_status('wan')
                    lease = wan.get('up') and bool(wan.get('ipv4-address'))
                    server = probe(c['wan_device'])
                    target, reason = decide(mode, linked, server, lease and mode != 'share')
                    # Mode changed while probing: discard this result.
                    if config()['wan_mode'] != mode or not carrier(c['wan_device']):
                        continue
                    apply_role(target)
                    role = target
                    m.atomic(RUNTIME, {'role': role, 'reason': reason})
                    next_probe = time.monotonic() + 20
            last_link, last_mode = linked, mode
        except Exception:
            m.atomic(RUNTIME, {'role': 'error', 'reason': 'retrying'})
        time.sleep(.5)
