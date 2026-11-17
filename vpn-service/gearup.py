"""Admission into the isolated GearUP LAN; vendor code never edits host settings."""
import json
from pathlib import Path
import subprocess

SERVICE = Path('/opt/photonicat-gearup/service.py')
NETWORK = Path('/etc/photonicat-gearup/network.json')
BRIDGE = 'br-pcgearup'


def status():
    if not SERVICE.exists() or not NETWORK.exists():
        return {'installed': False, 'running': False}
    try:
        return json.loads(subprocess.check_output(['python3', str(SERVICE), 'status'], timeout=5))
    except (OSError, ValueError, subprocess.SubprocessError):
        return {'installed': True, 'running': False}


def require_ready():
    if not status().get('running'):
        raise ValueError('Контейнер GearUP не запущен. Режим не изменён.')


def port_plan(values, c, role):
    """Only owned port memberships/proto are changed. Other bridge ports survive."""
    devices = [(name, s) for name, s in values.items() if s.get('.type') == 'device']
    lan = next((name for name, s in devices if s.get('name') == c['lan_bridge']), None)
    gu = next((name for name, s in devices if s.get('name') == BRIDGE), None)
    if not lan or not gu:
        raise ValueError('Сеть GearUP ещё не установлена.')
    def members(section):
        v = values[section].get('ports', [])
        return list(v) if isinstance(v, list) else v.split()
    before = {lan: members(lan), gu: members(gu)}
    after = {k: list(v) for k, v in before.items()}
    for section in after:
        after[section] = [d for d in after[section] if d not in (c['lan_device'], c['wan_device'])]
    after[gu if c.get('lan_mode') == 'gearup' and c.get('lan_enabled', True) else lan].append(c['lan_device'])
    wan_gearup = role == 'share' and c.get('wan_share_mode', 'direct') == 'gearup'
    if wan_gearup:
        after[gu].append(c['wan_device'])
    changes = {}
    for section in after:
        if after[section] != before[section]:
            changes[section+'.ports'] = after[section]
    desired = {'pcwan.device': BRIDGE if wan_gearup else c['wan_device'],
               'pcwan.proto': 'none' if wan_gearup else 'static'}
    for key, value in desired.items():
        section, option = key.split('.')
        if values.get(section, {}).get(option) != value:
            changes[key] = value
    return changes


def configure_ports(c, role, reload=True):
    if not NETWORK.exists():
        return False
    values = json.loads(subprocess.check_output(['ubus','call','uci','get','{"config":"network"}'], timeout=5))['values']
    plan = port_plan(values, c, role)
    if not plan:
        return False
    if subprocess.check_output(['uci','changes','network'], timeout=5).strip():
        raise ValueError('Есть несохранённые настройки сети. Заверши их изменение.')
    def run(*a):
        subprocess.run(a, check=True, capture_output=True, timeout=10)
    for key, value in plan.items():
        if isinstance(value, list):
            subprocess.run(['uci','-q','delete','network.'+key], capture_output=True, timeout=5)
            for item in value:
                run('uci','add_list','network.'+key+'='+item)
        else:
            run('uci','set','network.'+key+'='+value)
    run('uci','commit','network')
    if reload:
        run('ubus','call','network','reload')
        import time
        expected = BRIDGE if c.get('lan_mode') == 'gearup' and c.get('lan_enabled', True) else c['lan_bridge']
        for _ in range(40):
            master = Path('/sys/class/net', c['lan_device'], 'master')
            if master.exists() and master.resolve().name == expected:
                break
            time.sleep(.25)
        else:
            raise ValueError('Не подтверждено подключение LAN к выбранной сети.')
        run('/etc/init.d/firewall','reload')
        run('/etc/init.d/dnsmasq','reload')
        run('/etc/init.d/odhcpd','reload')
    return True


def own_macs(c):
    """Ignore our GearUP DHCP server when probing a sharing WAN port."""
    result = set()
    for device in (BRIDGE,):
        try:
            result.add(bytes.fromhex(Path('/sys/class/net', device, 'address').read_text().strip().replace(':','')))
        except (OSError, ValueError):
            pass
    try:
        result.add(bytes.fromhex(json.loads(NETWORK.read_text())['mac'].replace(':','')))
    except (OSError, ValueError, KeyError):
        pass
    return result
