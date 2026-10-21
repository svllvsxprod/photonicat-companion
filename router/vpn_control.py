"""Allowlisted bridge to the root-only VPN manager; no secrets returned to BLE."""
import json
from pathlib import Path
import subprocess
MANAGER = Path('/opt/photonicat-vpn/manager.py')

class VpnError(Exception): pass

def call(action, value=None, payload=None):
    if not MANAGER.is_file(): raise VpnError('VPN-служба на этом роутере не установлена.')
    command = ['/usr/bin/python3', str(MANAGER), action]
    if value is not None: command.append(value)
    try:
        result = subprocess.run(command, input=None if payload is None else json.dumps(payload),
                                capture_output=True, text=True, timeout=35)
        if result.returncode:
            try: message = json.loads(result.stderr).get('error')
            except ValueError: message = None
            raise VpnError(message or 'Не удалось применить VPN. Обнови состояние.')
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise VpnError('VPN-служба не ответила. Обнови состояние перед повтором.') from None


def snapshot(revision):
    if not MANAGER.is_file(): return {'available':False}
    raw = call('status')
    output = {'available':True, 'active':raw['active'], 'routing_scope':'unassigned'}
    for engine in ('amneziawg','mihomo'):
        fields = ('selected','applied','running','last_handshake_time_sec','rx_bytes','tx_bytes','version')
        output[engine] = {k:raw[engine][k] for k in fields if k in raw[engine]}
    output['amneziawg']['profiles'] = raw['amneziawg']['profiles']
    output['mihomo']['nodes'] = raw['mihomo']['nodes'][:64]
    output['nodes_truncated'] = len(raw['mihomo']['nodes']) > 64
    output['subscriptions'] = call('catalog')
    output['ports'] = call('ports-status')
    if output['ports'].get('installed'):
        output['routing_scope'] = 'lan'
    output['revision'] = revision({k:output[k] for k in ('active','subscriptions')} | {
        'awg':output['amneziawg']['selected'],'mihomo':output['mihomo']['selected'],
        'profiles':output['amneziawg']['profiles'],'nodes':output['mihomo']['nodes'],
        'ports': {k:output['ports'].get(k) for k in ('installed','wan_mode','lan_enabled','lan_mode')}})
    return output


def execute(args, revision):
    if not isinstance(args, dict): raise VpnError('Некорректные параметры VPN.')
    action = args.get('action')
    schemas = {'engine':{'value'},'awg':{'value'},'node':{'value'},'check':{'value'},
               'import-awg':{'label','text'},'delete-awg':{'id'},'add-subscription':{'label','url'},
               'delete-subscription':{'id'},'update-subscription':{'id'},'ports':{'setting','value'}}
    if action not in schemas or set(args) != schemas[action] | {'action','revision'}:
        raise VpnError('Неизвестные параметры VPN.')
    if action != 'ports' and any(not isinstance(args[k],str) for k in schemas[action]): raise VpnError('Некорректные значения VPN.')
    current = snapshot(revision)
    if not current.get('available'): raise VpnError('VPN-служба не установлена.')
    if args['revision'] != current['revision']: raise VpnError('Список VPN изменился. Обнови его и повтори действие.')
    value = args.get('value')
    if action == 'ports':
        if args['setting'] == 'wan_mode' and value in ('auto','uplink','share'):
            return call('ports-set',payload={'setting':args['setting'],'value':value})
        if args['setting'] == 'lan_mode' and value in ('direct','vpn'):
            return call('ports-set',payload={'setting':args['setting'],'value':value})
        if args['setting'] == 'lan_enabled' and type(value) is bool:
            return call('ports-set',payload={'setting':args['setting'],'value':value})
        raise VpnError('Некорректная настройка порта.')
    if action in ('engine','check') and value not in ('amneziawg','mihomo'): raise VpnError('Неизвестное ядро.')
    if action in ('awg','delete-awg') and (value or args.get('id')) not in {p['id'] for p in current['amneziawg']['profiles']}:
        raise VpnError('Профиль не найден.')
    if action == 'node' and value not in current['mihomo']['nodes']: raise VpnError('Сервер не найден.')
    if action == 'check': return {'check':call('check',value)}
    if action in ('engine','awg','node'):
        call({'engine':'select-engine','awg':'select-awg','node':'select-node'}[action],value)
        return {'message':'Выбор сохранён.'}
    return call('manage',payload={'action':action,'args':{k:args[k] for k in schemas[action]}})
