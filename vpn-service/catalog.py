"""Private profile imports. Only validated proxy entries are applied, never hooks."""
import base64
import copy
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import urllib.parse
import urllib.request
import zlib
import manager as m

class CatalogError(ValueError):
    pass


def label(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 64 or any(ord(c) < 32 for c in value):
        raise CatalogError('Название должно содержать от 1 до 64 символов.')
    return value.strip()


def decode_awg(text):
    if not isinstance(text, str) or len(text.encode()) > 24576:
        raise CatalogError('Слишком большой профиль. Максимум 24 КБ.')
    text = text.strip().lstrip('\ufeff')
    if text.startswith('vpn://'):
        try:
            value = text[6:]
            raw = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
            if len(raw) > 4 and int.from_bytes(raw[:4], 'big') <= 65536:
                dec = zlib.decompressobj()
                data = dec.decompress(raw[4:], 65537)
                if len(data) > 65536 or not dec.eof or dec.unused_data:
                    raise ValueError()
                raw = data
            text = raw.decode()
        except (ValueError, UnicodeError, zlib.error):
            raise CatalogError('Не удалось прочитать QR Amnezia.') from None
    if text.lstrip().startswith('{'):
        try:
            doc = json.loads(text)
            configs = []
            for container in doc.get('containers', []):
                if not isinstance(container, dict): continue
                awg = container.get('awg')
                if isinstance(awg, dict):
                    last = awg.get('last_config', {})
                    if isinstance(last, str): last = json.loads(last)
                    if isinstance(last, dict) and isinstance(last.get('config'), str): configs.append(last['config'])
            if not configs and isinstance(doc.get('config'), str): configs = [doc['config']]
            if len(configs) != 1: raise ValueError()
            text = configs[0]
        except (ValueError, AttributeError, TypeError):
            raise CatalogError('В QR нет единственного готового профиля AmneziaWG. Экспортируй AmneziaWG native (.conf).') from None
    try:
        interface, peer = m.parse_config(text)
        for key in ['PrivateKey', 'Address']:
            if not interface.get(key): raise ValueError()
        for key in ['PublicKey', 'Endpoint', 'AllowedIPs']:
            if not peer.get(key): raise ValueError()
        addresses = [str(ipaddress.ip_interface(v.strip())) for v in interface['Address'].split(',')]
        if not 1 <= len(addresses) <= 2 or len({ipaddress.ip_interface(a).version for a in addresses}) != len(addresses): raise ValueError()
        allowed = {str(ipaddress.ip_network(p.strip())) for p in peer['AllowedIPs'].split(',')}
        if '0.0.0.0/0' not in allowed: raise ValueError()
        mtu = int(interface.get('MTU', 1280))
        if not 1280 <= mtu <= 1500: raise ValueError()
        m.awg_request(text)
    except (ValueError, KeyError, AssertionError, OSError):
        raise CatalogError('Некорректный профиль AmneziaWG. Нужен один peer, адрес, ключи и полный IPv4-маршрут; команды PostUp/PreDown не поддерживаются.') from None
    return text, addresses, mtu


def public_url(value):
    if not isinstance(value, str) or len(value) > 4096: raise CatalogError('Некорректная ссылка подписки.')
    u = urllib.parse.urlsplit(value)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.fragment:
        raise CatalogError('Нужна HTTPS-ссылка подписки без логина в адресе.')
    try:
        addresses = socket.getaddrinfo(u.hostname, u.port or 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses): raise ValueError()
    except (OSError, ValueError):
        raise CatalogError('Адрес подписки должен быть доступен в интернете.') from None
    return value


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url):
    import yaml
    try:
        request = urllib.request.Request(public_url(url), headers={'User-Agent': 'mihomo'})
        with urllib.request.build_opener(Redirect).open(request, timeout=10) as response:
            raw = response.read(1048577)
        if len(raw) > 1048576: raise ValueError()
        if any(isinstance(token, yaml.tokens.AliasToken) for token in yaml.scan(raw)):
            raise ValueError()
        doc = yaml.safe_load(raw)
        proxies = doc.get('proxies') if isinstance(doc, dict) else None
        if not isinstance(proxies, list) or not 1 <= len(proxies) <= 64: raise ValueError()
        names = set()
        for p in proxies:
            if not isinstance(p, dict) or p.get('type') not in ('ss','ssr','vmess','vless','trojan','hysteria','hysteria2','tuic','wireguard','socks5','http'): raise ValueError()
            name = p.get('name')
            if not isinstance(name, str) or not 1 <= len(name.encode()) <= 160 or name in names: raise ValueError()
            names.add(name)
        return json.dumps({'proxies': proxies}, ensure_ascii=False)
    except CatalogError: raise
    except Exception:
        raise CatalogError('Подписка недоступна или не содержит профили Mihomo/Clash YAML (до 64 серверов).') from None


def private_text(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f: f.write(text)


def configuration():
    return json.loads((m.ROOT / 'mihomo/config.json').read_text())


def subscriptions():
    config = configuration()
    result = []
    try: providers = m.api('/providers/proxies', timeout=2).get('providers', {})
    except OSError: providers = {}
    for key, p in config.get('proxy-providers', {}).items():
        result.append({'id': key, 'label': p.get('override', {}).get('additional-prefix', key).removesuffix(' · '),
                       'count': len(providers.get(key, {}).get('proxies', []))})
    return result


def reload_config(new):
    path = m.ROOT / 'mihomo/config.json'
    old = configuration()
    candidate = m.ROOT / 'mihomo/candidate.json'
    m.atomic(candidate, new)
    test = subprocess.run([str(m.BIN/'mihomo'), '-t', '-d', str(m.ROOT/'mihomo'), '-f', str(candidate)], capture_output=True, timeout=10)
    if test.returncode:
        candidate.unlink(missing_ok=True)
        raise CatalogError('Ядро Mihomo не приняло подписку. Настройки сохранены без изменений.')
    os.replace(candidate, path)
    try:
        m.api('/configs?force=true', 'PUT', {'path': str(path)}, timeout=10)
    except Exception:
        m.atomic(path, old)
        try: m.api('/configs?force=true', 'PUT', {'path': str(path)}, timeout=10)
        except Exception: pass
        raise CatalogError('Не удалось применить подписку. Восстановлена прежняя конфигурация.') from None


def execute(action, args):
    if action == 'import-awg':
        name = label(args['label']); text, addresses, mtu = decode_awg(args['text'])
        profiles = m.manifest()
        if len(profiles) >= 24: raise CatalogError('Можно сохранить не более 24 профилей.')
        if any(p['label'] == name for p in profiles): raise CatalogError('Профиль с таким названием уже существует.')
        identifier = 'awg-' + secrets.token_hex(6)
        path = m.ROOT/'profiles'/(identifier+'.conf')
        private_text(path, text)
        try: m.atomic(m.ROOT/'profiles.json', profiles + [{'id':identifier,'label':name,'addresses':addresses,'mtu':mtu}])
        except Exception: path.unlink(); raise
        return {'message':'Профиль добавлен. Его можно выбрать в списке Amnezia.'}
    if action == 'delete-awg':
        identifier = args['id']; p = m.profile(identifier)
        if identifier == m.state()['amneziawg']: raise CatalogError('Сначала выбери другой профиль Amnezia.')
        m.atomic(m.ROOT/'profiles.json', [p for p in m.manifest() if p['id'] != identifier])
        (m.ROOT/'profiles'/(identifier+'.conf')).unlink(missing_ok=True)
        return {'message':'Профиль удалён.'}
    if action == 'add-subscription':
        name = label(args['label']); config = configuration()
        providers = config['proxy-providers']
        if len(providers) >= 8: raise CatalogError('Можно добавить не более 8 подписок.')
        if any(p.get('override',{}).get('additional-prefix') == name+' · ' for p in providers.values()):
            raise CatalogError('Подписка с таким названием уже существует.')
        data = download(args['url'])
        existing = sum(p['count'] for p in subscriptions())
        if existing + len(json.loads(data)['proxies']) > 64:
            raise CatalogError('Для Bluetooth-списка поддерживается до 64 серверов суммарно.')
        identifier = 'sub-' + secrets.token_hex(6)
        seed = m.ROOT/'mihomo/providers'/(identifier+'.yaml')
        private_text(seed, data)
        providers[identifier] = {'type':'http','url':args['url'],'path':f'./providers/{identifier}.yaml','interval':86400,'header':{'User-Agent':['mihomo']},'override':{'additional-prefix':name+' · '},'health-check':{'enable':False}}
        next(g for g in config['proxy-groups'] if g['name']=='PC-Mihomo')['use'] = list(providers)
        try: reload_config(config)
        except Exception: seed.unlink(missing_ok=True); raise
        return {'message':'Подписка добавлена. Текущий сервер не изменён.'}
    if action in ('delete-subscription','update-subscription'):
        identifier = args['id']; config = configuration(); provider = config['proxy-providers'].get(identifier)
        if provider is None: raise CatalogError('Подписка не найдена. Обнови список.')
        if action == 'update-subscription':
            # Fetch and validate before asking the core to update its own provider.
            download(provider['url'])
            try: m.api('/providers/proxies/'+urllib.parse.quote(identifier,safe=''), 'PUT', timeout=12)
            except OSError: raise CatalogError('Не удалось обновить подписку.') from None
            return {'message':'Подписка обновлена.'}
        if len(config['proxy-providers']) == 1: raise CatalogError('Сначала добавь другую подписку для Mihomo.')
        info = m.api('/providers/proxies/'+urllib.parse.quote(identifier,safe=''))
        names = {p['name'] for p in info.get('proxies',[])}
        if m.state().get('mihomo') in names: raise CatalogError('Сначала выбери сервер из другой подписки.')
        del config['proxy-providers'][identifier]
        next(g for g in config['proxy-groups'] if g['name']=='PC-Mihomo')['use'] = list(config['proxy-providers'])
        reload_config(config)
        # Remove only a known basename under the dedicated provider directory.
        path = m.ROOT/'mihomo'/provider['path']
        if path.resolve().parent == (m.ROOT/'mihomo/providers').resolve(): path.unlink(missing_ok=True)
        return {'message':'Подписка удалена.'}
    raise CatalogError('Неизвестное действие.')
