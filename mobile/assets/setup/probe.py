"""Read-only setup inventory. Never returns Wi-Fi keys, SIM IDs or VPN profiles."""
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def run(*args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=10)
    if p.returncode:
        raise ValueError('probe_command_failed')
    return p.stdout


def uci(package):
    return json.loads(run('ubus', 'call', 'uci', 'get', json.dumps({'config': package})))['values']


def words(value):
    return value.split() if isinstance(value, str) else value if isinstance(value, list) else []


def network_plan(network, addresses):
    """Discover ports, allocate disjoint subnets; never assume radio/port order."""
    wan = network.get('wan', {}).get('device')
    lan = network.get('lan', {}).get('device')
    if not all(isinstance(v, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,15}', v) for v in (wan, lan)):
        raise ValueError('port_mapping_unsupported')
    bridges = [s for s in network.values() if s.get('.type') == 'device' and s.get('name') == lan]
    if len(bridges) != 1 or len(words(bridges[0].get('ports'))) != 1:
        raise ValueError('lan_bridge_unsupported')
    port = words(bridges[0]['ports'])[0]
    if port == wan or not re.fullmatch(r'[a-zA-Z0-9_-]{1,15}', port):
        raise ValueError('port_mapping_unsupported')
    lan_address = str(ipaddress.IPv4Address(network['lan']['ipaddr']))
    used = [ipaddress.ip_network(f"{a['local']}/{a['prefixlen']}", strict=False)
            for row in addresses for a in row.get('addr_info', []) if a.get('family') == 'inet']
    # Also reserve configured but currently down networks.
    for row in network.values():
        try: used.append(ipaddress.ip_network(str(row['ipaddr'])+'/'+str(row.get('netmask', 24)), strict=False))
        except (ValueError, KeyError): pass
    candidates = [ipaddress.ip_network(f'172.20.{n}.0/24') for n in range(1, 254)]
    available = [n for n in candidates if not any(n.overlaps(x) for x in used)]
    if len(available) < 3: raise ValueError('no_free_subnets')
    return {'wan_device': wan, 'lan_device': port, 'lan_bridge': lan, 'lan_address': lan_address,
            'direct_bridge': 'br-pcdirect', 'wifi_bridge': 'br-pcwifi',
            **{key: str(net.network_address+1) for key, net in zip(
                ('direct_address', 'share_address', 'wifi_address'), available)},
            'wan_mode': 'uplink', 'lan_mode': 'direct', 'wan_share_mode': 'direct',
            'lan_enabled': True, 'wifi_ready': True, 'lan_mode_ready': True}


def inventory():
    board = json.loads(run('ubus', 'call', 'system', 'board'))
    errors = []
    if os.geteuid() != 0: errors.append('root_required')
    if board.get('board_name') != 'ariaboard,photonicat2': errors.append('unsupported_board')
    release = board.get('release', {})
    if release.get('distribution', '').lower() != 'photonicatwrt' or release.get('version') != '26.04.1':
        errors.append('unsupported_firmware')
    for command in ('ip', 'nft', 'fw4', 'uci', 'ubus'):
        if not shutil.which(command): errors.append('missing_'+command)
    for module in ('yaml', 'uci', 'ssl', 'asyncio'):
        if importlib.util.find_spec(module) is None: errors.append('missing_python_'+module)
    if not Path('/dev/net/tun').exists(): errors.append('tun_unavailable')
    if run('uci', 'changes').strip(): errors.append('pending_changes')
    free = shutil.disk_usage('/overlay' if Path('/overlay').exists() else '/').free
    if free < 180*1024*1024: errors.append('storage_low')
    installed = Path('/etc/photonicat-companion/key').is_file()
    plan = None
    if not installed:
        try: plan = network_plan(uci('network'), json.loads(run('ip', '-j', '-4', 'addr')))
        except (ValueError, KeyError) as exc: errors.append(str(exc) if str(exc) in ('port_mapping_unsupported','lan_bridge_unsupported','no_free_subnets') else 'network_unsupported')
    wifi = []
    for p in sorted(Path('/sys/class/ieee80211').glob('phy*')):
        dev = (p/'device').resolve()
        driver = (dev/'driver').resolve().name if (dev/'driver').exists() else 'unknown'
        wifi.append({'phy': p.name, 'driver': driver, 'bus': 'PCIe' if '/pci' in str(dev) else 'Встроенный/USB'})
    modems = []
    for p in Path('/sys/bus/usb/devices').glob('*'):
        try:
            product = (p/'product').read_text().strip()[:80]
            maker = (p/'manufacturer').read_text().strip()[:80] if (p/'manufacturer').exists() else ''
            if any(x in (product+' '+maker).lower() for x in ('fibocom','fm350','quectel','modem','simcom')):
                modems.append({'name': product, 'vendor': maker, 'bus': 'USB'})
        except OSError: pass
    # PCIe modems expose WWAN control nodes without opening AT ports.
    for p in Path('/sys/class/wwan').glob('*'):
        if 'at' in p.name or 'mbim' in p.name: modems.append({'name': p.name, 'vendor': '', 'bus': 'WWAN'})
    return {'model': board.get('model'), 'firmware': release.get('version'),
            'supported': not errors, 'errors': errors, 'installed': installed,
            'wifi': wifi, 'modems': modems, 'free_mb': free//1048576, 'plan': plan}

if __name__ == '__main__':
    try: print(json.dumps(inventory(), ensure_ascii=False))
    except Exception: print(json.dumps({'supported': False, 'errors': ['probe_failed']}))
