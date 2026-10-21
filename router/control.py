"""Capability discovery and allowlisted controls for stock PhotonicatWrt APIs.
No client-supplied paths, shell commands, or modem-specific AT commands.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import time
import tempfile
import urllib.request


class ControlError(Exception):
    pass


def api(path, payload=None, port=80):
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f'http://127.0.0.1:{port}{path}', data=body,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            value = json.load(response)
        if not isinstance(value, dict) or value.get('status') in ('error', 'failed'):
            raise ControlError('Штатная служба отклонила запрос.')
        return value
    except (OSError, ValueError) as exc:
        raise ControlError('Штатная служба недоступна. Обнови состояние.') from exc


def stock_write(path, payload):
    # Stock state-changing APIs require a session-bound CSRF token, including
    # privileged loopback callers. Obtain it normally; never disable the guard.
    import http.cookiejar
    from html.parser import HTMLParser
    class TokenParser(HTMLParser):
        token = None
        def handle_starttag(self, tag, attrs):
            fields = dict(attrs)
            if tag == 'input' and fields.get('name') == 'csrf_token':
                self.token = fields.get('value')
            elif tag == 'meta' and fields.get('name') == 'csrf-token':
                self.token = fields.get('content')
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    try:
        with client.open('http://127.0.0.1/login', timeout=8) as response:
            parser = TokenParser();parser.feed(response.read(262144).decode())
        if not parser.token:raise ControlError('Штатная служба не предоставила токен управления.')
        request = urllib.request.Request('http://127.0.0.1' + path,
                    data=json.dumps(payload).encode(),
                    headers={'Content-Type': 'application/json', 'X-CSRF-Token': parser.token})
        with client.open(request, timeout=8) as response:value = json.load(response)
        if not isinstance(value, dict) or value.get('status') != 'ok':
            raise ControlError('Штатная служба отклонила настройку.')
        return value
    except (OSError, ValueError) as exc:
        raise ControlError('Не удалось изменить настройку через штатную службу.') from exc


def optional_api(path, port=80):
    try:
        return api(path, port=port)
    except ControlError:
        return None


def modem_status():
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect('/tmp/pcat-manager.sock')
            sock.sendall(b'{"command":"modem-status-get"}\0')
            data = b''
            while b'\0' not in data and len(data) < 65536:
                part = sock.recv(4096)
                if not part:
                    break
                data += part
        result = json.loads(data.split(b'\0')[0])
        if result.get('code') != 0:
            return None
        return {key: result.get(key) for key in
                ('mode', 'sim-state', 'interface-enabled', 'signal-strength', 'isp-name')}
    except (OSError, ValueError, AttributeError):
        return None


SCREEN_KEYS = {
    'brightness': 'screen_max_brightness',
    'battery_timeout': 'screen_dimmer_time_on_battery_seconds',
    'power_timeout': 'screen_dimmer_time_on_dc_seconds',
}


def wifi_config():
    try:
        import uci
        return uci.Uci().get_all('wireless')
    except Exception as exc:
        raise ControlError('Локальное управление Wi-Fi недоступно.') from exc


def wifi_target(device):
    config = wifi_config()
    interfaces = [(name, section) for name, section in config.items()
                  if section.get('device') == device]
    aps = [(name, section) for name, section in interfaces if section.get('mode') == 'ap']
    # Firmware retains an explicitly disabled STA profile after Wi-Fi WAN use.
    # It is safe to retain that profile while editing the one AP. An enabled
    # STA (even when not associated) or multiple APs still needs separate UI.
    other_enabled = any(section.get('mode') != 'ap' and str(section.get('disabled')) != '1'
                        for _, section in interfaces)
    if device not in config or len(aps) != 1 or other_enabled:
        raise ControlError('Эта конфигурация доступна только для просмотра.')
    return aps[0][0]


def wifi_vpn_info(device):
    try:
        root = Path('/etc/photonicat-vpn')
        ports = json.loads((root / 'ports.json').read_text())
        if not ports.get('wifi_ready'):
            return None
        section = wifi_target(device)
        network = wifi_config()[section].get('network')
        if isinstance(network, list):
            network = network[0] if len(network) == 1 else None
        if network not in ('pcdirect', 'pcwifi'):
            return None
        state = json.loads((root / 'state.json').read_text())
        return {'enabled': network == 'pcwifi', 'engine': state['active'],
                'profile': state.get(state['active'], ''), 'network': network}
    except (OSError, ValueError, KeyError, ControlError):
        return None


def write_wifi(payload):
    import uci
    section = wifi_target(payload['device'])
    pending = subprocess.run(['/sbin/uci', '-q', 'changes', 'wireless'],
                             capture_output=True, timeout=5)
    if pending.returncode != 0 or pending.stdout.strip():
        raise ControlError('В системе есть несохранённые настройки Wi-Fi. Сначала заверши их изменение.')
    # Private staging avoids committing another tool's pending UCI changes.
    with tempfile.TemporaryDirectory(prefix='pcat-uci-') as staging:
        context = uci.Uci(savedir=staging)
        for name, option, value in [
            (payload['device'], 'disabled', '0' if payload['enabled'] else '1'),
            (section, 'disabled', '0' if payload['enabled'] else '1'),
            (section, 'ssid', payload['ssid']), (section, 'key', payload['password']),
        ]:
            context.set('wireless', name, option, value)
        if 'vpn_enabled' in payload:
            context.set('wireless', section, 'network',
                        'pcwifi' if payload['vpn_enabled'] else 'pcdirect')
        context.commit('wireless')
    if 'vpn_enabled' in payload:
        # Recreate the AP so hostapd joins the new bridge and clients renew DHCP.
        for action in ('down', 'up'):
            result = subprocess.run(['/sbin/wifi', action, payload['device']],
                                    capture_output=True, timeout=20)
            if result.returncode:
                raise ControlError('Режим сохранён, но перезапуск Wi-Fi не подтверждён.')
        return
    # Stock netifd reload reads changed configuration; reconf targets this radio.
    result = subprocess.run(['/sbin/wifi', 'reconf', payload['device']],
                            capture_output=True, timeout=20)
    if result.returncode:
        raise ControlError('Настройки сохранены, но запуск Wi-Fi не подтверждён. Обнови состояние.')


def apply_display():
    service = Path('/etc/init.d/pcat2-display-mini')
    if not service.is_file():
        # Saved settings still apply on the next native screen wake.
        return False
    try:
        result = subprocess.run([str(service), 'restart'], capture_output=True, timeout=12)
        if result.returncode:
            return False
        for _ in range(8):
            time.sleep(0.5)
            if optional_api('/api/v1/go_get_config.json', port=8081) is not None:
                return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    return False


class Controls:
    def __init__(self):
        self.revision_key = secrets.token_bytes(32)

    def revision(self, value):
        # Passwords may be in source configs. A keyed digest is not an offline
        # password verifier, and no password is sent back to the mobile UI.
        return hmac.new(self.revision_key, json.dumps(value, sort_keys=True).encode(),
                        hashlib.sha256).hexdigest()[:32]

    def wifi_raw(self):
        result = api('/api/v2/wireless.json')
        if not isinstance(result.get('interfaces'), list):
            raise ControlError('Прошивка не предоставляет список Wi-Fi.')
        return [r for r in result['interfaces'] if isinstance(r, dict) and r.get('exist') is True]

    def wifi_public(self, radio):
        supported = (all(k in radio for k in
                         ('device', 'ssid', 'enabled', 'encryption', 'frequency', 'hidden'))
                     and isinstance(radio.get('device'), str)
                     and re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', radio['device']) is not None
                     and radio.get('wifi_wan') is not True
                     and radio.get('encryption') in ('psk2', 'sae', 'sae-mixed', 'psk-mixed')
                     and isinstance(radio.get('password'), str))
        if supported:
            try:
                wifi_target(radio['device'])
            except ControlError:
                supported = False
        vpn = wifi_vpn_info(radio.get('device', '')) if supported else None
        return {
            'id': radio.get('device', ''), 'label': radio.get('device_type', 'Wi-Fi'),
            'ssid': radio.get('ssid', ''), 'enabled': radio.get('enabled') is True,
            'band': radio.get('band', ''), 'role': 'uplink' if radio.get('wifi_wan') else 'ap',
            'bands': list(radio.get('capabilities', {}).get('bands', {})),
            'actions': ['wifi_set'] if supported else [],
            'vpn': vpn,
            'revision': self.wifi_revision(radio, vpn),
        }

    def wifi_revision(self, radio, vpn):
        return self.revision(radio if vpn is None else
                             {'radio': radio, 'network': vpn['network']})

    def fan_raw(self):
        mode = api('/api/v1/fan_mode.json').get('fan_mode')
        level = api('/api/v1/fan_speed.json').get('fan_speed')
        if mode not in ('manual', 'smart_quiet', 'smart_cool') or type(level) is not int or not 0 <= level <= 9:
            raise ControlError('Управление вентилятором недоступно.')
        return {'mode': mode, 'level': level}

    def fan_public(self):
        raw = self.fan_raw()
        actual = optional_api('/api/v1/fan_speed_actual.json') or {}
        rpm = actual.get('fan_speed_rpm')
        return {**raw, 'rpm': rpm if type(rpm) is int and rpm >= 0 else None,
                'revision': self.revision(raw), 'actions': ['fan_set']}

    def set_fan(self, args):
        if set(args) not in ({'revision', 'mode'}, {'revision', 'level'}):
            raise ControlError('Некорректные параметры вентилятора.')
        raw = self.fan_raw()
        if args['revision'] != self.revision(raw):
            raise ControlError('Настройки вентилятора изменились. Обнови данные.')
        if 'mode' in args:
            if args['mode'] not in ('manual', 'smart_quiet', 'smart_cool'):
                raise ControlError('Неизвестный режим вентилятора.')
            field, endpoint = 'mode', 'fan_mode'
        else:
            if type(args['level']) is not int or not 0 <= args['level'] <= 9:
                raise ControlError('Скорость вентилятора: от 0 до 9.')
            field, endpoint = 'level', 'fan_speed'
        if args[field] == raw[field]:return {'message': 'Настройки уже совпадают.'}
        directory = Path('/etc/photonicat-companion/backups')
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            fd = os.open(directory / 'fan.before.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:pass
        else:
            with os.fdopen(fd, 'w') as out:json.dump(raw, out)
        stock_write('/api/v1/' + endpoint + '.json', {endpoint: args[field]})
        if self.fan_raw()[field] != args[field]:
            raise ControlError('Результат не подтверждён. Обнови состояние вентилятора.')
        return {'message': 'Настройка вентилятора сохранена.'}

    def screen_raw(self):
        current = api('/api/v1/go_get_config.json', port=8081)
        if not all(type(current.get(v)) is int for v in SCREEN_KEYS.values()):
            raise ControlError('Настройки экрана не поддерживаются этой прошивкой.')
        return current

    def snapshot(self):
        result = {'schema': 1, 'backend': 'photonicat-stock-api', 'wifi': [],
                  'screen': None, 'fan': None, 'modem': modem_status(), 'actions': [], 'unavailable': []}
        try:
            result['wifi'] = [self.wifi_public(r) for r in self.wifi_raw()]
        except ControlError:
            result['unavailable'].append('Wi-Fi')
        try:
            screen = self.screen_raw()
            user = api('/api/v1/go_get_user_config.json', port=8081)
            result['screen'] = {k: screen[v] for k, v in SCREEN_KEYS.items()}
            result['screen']['revision'] = self.revision(user)
            result['screen']['actions'] = ['screen_set']
        except ControlError:
            result['unavailable'].append('Экран')
        try:
            result['fan'] = self.fan_public()
        except ControlError:
            pass
        # Reboot is available only on the OpenWrt backend, not inferred from model.
        if Path('/etc/openwrt_release').is_file() and Path('/sbin/reboot').is_file():
            result['actions'].append('reboot')
        return result

    def backup(self, name, source):
        directory = Path('/etc/photonicat-companion/backups')
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = directory / name
        # Retain the first pre-companion configuration, on the router only.
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return
        with os.fdopen(fd, 'wb') as out:
            out.write(Path(source).read_bytes())

    def execute(self, operation, args):
        if not isinstance(args, dict):
            raise ControlError('Некорректные параметры.')
        if operation == 'wifi_set':
            return self.set_wifi(args)
        if operation == 'fan_set':
            return self.set_fan(args)
        if operation == 'screen_set':
            return self.set_screen(args)
        if operation == 'reboot':
            if args != {'confirm': 'reboot'} or 'reboot' not in self.snapshot()['actions']:
                raise ControlError('Перезагрузка не подтверждена или недоступна.')
            # Engine schedules it only after transmitting the authenticated reply.
            return {'message': 'Перезагрузка запрошена. Связь временно прервётся.'}
        raise ControlError('Эта функция не поддерживается службой.')

    def set_wifi(self, args):
        if set(args) - {'id', 'revision', 'ssid', 'enabled', 'password', 'vpn_enabled'}:
            raise ControlError('Неизвестный параметр Wi-Fi.')
        radio = next((r for r in self.wifi_raw() if r.get('device') == args.get('id')), None)
        if radio is None or 'wifi_set' not in self.wifi_public(radio)['actions']:
            raise ControlError('Точка доступа недоступна или не поддерживает редактирование.')
        vpn = wifi_vpn_info(radio['device'])
        if args.get('revision') != self.wifi_revision(radio, vpn):
            raise ControlError('Настройки уже изменились. Закрой форму и открой её снова.')
        if 'vpn_enabled' in args and (type(args['vpn_enabled']) is not bool or vpn is None):
            raise ControlError('Режим VPN недоступен для этой точки доступа.')
        ssid, enabled, password = args.get('ssid'), args.get('enabled'), args.get('password')
        if (not isinstance(ssid, str) or not 1 <= len(ssid.encode('utf-8')) <= 32
                or any(ord(c) < 32 or ord(c) == 127 for c in ssid) or type(enabled) is not bool):
            raise ControlError('Имя сети должно занимать 1–32 байта UTF-8.')
        if password is not None and (not isinstance(password, str) or not 8 <= len(password) <= 63
                                    or any(not 32 <= ord(c) <= 126 for c in password)):
            raise ControlError('Пароль: 8–63 печатных символа латиницы, цифр и знаков.')
        payload = {k: radio[k] for k in ('device', 'ssid', 'encryption', 'password', 'frequency', 'enabled')}
        payload['hide_ssid'] = str(radio.get('hidden', '0')) == '1'
        payload.update(ssid=ssid, enabled=enabled)
        if password is not None:
            payload['password'] = password
        if 'vpn_enabled' in args and args['vpn_enabled'] != vpn['enabled']:
            payload['vpn_enabled'] = args['vpn_enabled']
        if (ssid == radio['ssid'] and enabled == radio['enabled']
                and payload['password'] == radio['password'] and 'vpn_enabled' not in payload):
            return {'message': 'Настройки уже совпадают.'}
        self.backup('wireless.before', '/etc/config/wireless')
        write_wifi(payload)
        for _ in range(12):
            time.sleep(1)
            updated = next((r for r in self.wifi_raw() if r.get('device') == radio['device']), {})
            updated_vpn = wifi_vpn_info(radio['device'])
            vpn_applied = ('vpn_enabled' not in payload or
                           (updated_vpn is not None and updated_vpn['enabled'] == payload['vpn_enabled']))
            if vpn_applied and all(updated.get(k) == payload[k] for k in ('ssid', 'enabled', 'password')):
                return {'message': 'Wi-Fi сохранён. Подключение клиентов может занять несколько секунд.'}
        raise ControlError('Запрос отправлен, но результат не подтверждён. Обнови состояние перед повтором.')

    def set_screen(self, args):
        if set(args) != {*SCREEN_KEYS, 'revision'}:
            raise ControlError('Некорректные параметры экрана.')
        for key, low, high in [('brightness', 5, 100), ('battery_timeout', 10, 86400), ('power_timeout', 10, 86400)]:
            if type(args[key]) is not int or not low <= args[key] <= high:
                raise ControlError('Яркость: 5–100%; таймер: 10–86400 секунд.')
        user = api('/api/v1/go_get_user_config.json', port=8081)
        if args['revision'] != self.revision(user):
            raise ControlError('Настройки уже изменились. Закрой форму и открой её снова.')
        previous = self.screen_raw()
        self.backup('display.before.json', '/etc/pcat2_mini_display-user_config.json')
        updates = {v: args[k] for k, v in SCREEN_KEYS.items()}
        merged = {**user, **updates}
        api('/api/v1/go_save_user_config.json', merged, port=8081)
        saved = api('/api/v1/go_get_user_config.json', port=8081)
        live = self.screen_raw()
        if saved != merged or any(live.get(k) != v for k, v in updates.items()):
            raise ControlError('Сохранение экрана не подтверждено. Обнови состояние.')
        if previous['screen_max_brightness'] != args['brightness'] and not apply_display():
            return {'message': 'Сохранено. Яркость применится при следующем пробуждении экрана.'}
        return {'message': 'Настройки экрана сохранены.'}
