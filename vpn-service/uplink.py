"""One outer uplink for both VPN engines; never modifies main routes.

Call sync() while holding manager's control.lock. Table 23510 always contains
a terminal unreachable route in both families, so a missing family cannot
fall through to a different uplink in main.
"""
import hashlib
import json
from pathlib import Path
import re
import time

import manager as m

TABLE = 23510
PRIORITY = 23497
PROTOCOL = 186
BLOCK_METRIC = 42760
RUNTIME = Path('/var/run/photonicat-vpn-uplink.json')
FIELDS = ('dst', 'from', 'gateway', 'dev', 'prefsrc', 'scope', 'metric')


def routes(family, table='main'):
    # This firmware emits truncated JSON for an absent numeric table. Reading
    # all tables distinguishes an empty table from a genuine command failure.
    result = m.run('ip', family, '-j', 'route', 'show', 'table',
                   'all' if table == TABLE else table)
    rows = json.loads(result.stdout)
    if table == TABLE:
        rows = [r for r in rows if str(r.get('table')) == str(TABLE)]
    return rows


def usable(route):
    dev = route.get('dev', '')
    return (bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,15}', dev))
            and dev != 'lo' and not dev.startswith(('pcmh', 'pcawg'))
            and route.get('type', 'unicast') == 'unicast'
            and not set(route.get('flags', [])) & {'linkdown', 'dead'})


def choose(tables, previous=None):
    # Follow the router's IPv4 default priority. IPv6-only access is supported
    # when no usable IPv4 default exists. Equal metrics retain the last choice.
    for family in ('-4', '-6'):
        candidates = [r for r in tables[family] if r.get('dst') == 'default' and usable(r)]
        if candidates:
            return min(candidates, key=lambda r: (
                int(r.get('metric', 0)), r['dev'] != previous, r['dev']))['dev']
    return None


def normalized(route):
    value = {k: route[k] for k in FIELDS if k in route}
    value.setdefault('metric', 0)
    if value.get('scope') == 'global':
        value.pop('scope')
    if value.get('from') == 'all':
        value.pop('from')
    return value


def plan(tables, device):
    return {family: sorted(
        [normalized(r) for r in tables[family] if device and r.get('dev') == device and usable(r)],
        key=lambda r: (r.get('dst') == 'default', json.dumps(r, sort_keys=True)))
        for family in ('-4', '-6')}


def route_args(route):
    args = [route.get('dst', 'default')]
    for key, flag in (('from', 'from'), ('gateway', 'via'), ('dev', 'dev'),
                      ('prefsrc', 'src'), ('scope', 'scope'), ('metric', 'metric')):
        if key in route:
            args += [flag, str(route[key])]
    return args


def ensure_routes(family, wanted):
    current = routes(family, TABLE)
    # iproute2 may print protocol 186 by its standard symbolic name.
    if any(str(r.get('protocol')) not in {str(PROTOCOL), 'bgp'} for r in current):
        raise RuntimeError('VPN uplink table is owned by another service')
    # Keep this route through every update; flushing the table would permit
    # the RPDB to continue to main and use an unintended backup interface.
    m.run('ip', family, 'route', 'replace', 'unreachable', 'default',
          'metric', BLOCK_METRIC, 'proto', PROTOCOL, 'table', TABLE)
    m.ensure_rule(family, PRIORITY, ['fwmark', m.SOCKET_MARK], TABLE)
    actual = [normalized(r) for r in current if r.get('type', 'unicast') == 'unicast']
    # Remove obsolete defaults first, then their connected networks. Install
    # connected networks before new defaults. Failures leave a closed path.
    for route in sorted(actual, key=lambda r: r.get('dst') != 'default'):
        if route not in wanted:
            m.run('ip', family, 'route', 'del', *route_args(route), 'table', TABLE)
    for route in wanted:
        if route not in actual:
            m.run('ip', family, 'route', 'replace', *route_args(route),
                  'proto', PROTOCOL, 'table', TABLE)


def transport_key(device, planned):
    # Metric-only changes on the same path should not interrupt healthy chats.
    material = {f: [{k: v for k, v in r.items() if k != 'metric'} for r in rs]
                for f, rs in planned.items()}
    return hashlib.sha256(json.dumps([device, material], sort_keys=True).encode()).hexdigest()


def source_addresses(device, wanted):
    """Identify usable outer source addresses, excluding the backup uplink.

    Route topology may stay identical after a cellular address replacement.
    Lifetimes and newly added addresses must not disturb existing sockets.
    """
    result = {'-4': [], '-6': []}
    if not device:
        return result
    rows = json.loads(m.run('ip', '-j', 'address', 'show', 'dev', device).stdout)
    for row in rows:
        for address in row.get('addr_info', []):
            family = {'inet': '-4', 'inet6': '-6'}.get(address.get('family'))
            if (family is None or address.get('scope') != 'global'
                    or not address.get('local') or address.get('tentative')
                    or address.get('dadfailed')
                    or not any(r.get('dst') == 'default' for r in wanted[family])):
                continue
            result[family].append(hashlib.sha256(address['local'].encode()).hexdigest())
    return {f: sorted(set(values)) for f, values in result.items()}


def source_address_removed(old, device, addresses):
    if old.get('interface') != device or 'source_addresses' not in old:
        return False
    return any(set(old['source_addresses'].get(f, [])) - set(addresses[f])
               for f in ('-4', '-6'))


def sync(live=True):
    try:
        old = json.loads(RUNTIME.read_text())
    except (OSError, ValueError):
        old = {}
    tables = {f: routes(f) for f in ('-4', '-6')}
    device = choose(tables, old.get('interface'))
    wanted = plan(tables, device)
    addresses = source_addresses(device, wanted)
    for family in ('-4', '-6'):
        ensure_routes(family, wanted[family])
    settings = {'interface-name': device or 'lo', 'routing-mark': m.SOCKET_MARK}
    path = m.ROOT / 'mihomo/config.json'
    config = json.loads(path.read_text())
    if any(config.get(k) != v for k, v in settings.items()):
        m.atomic(path, {**config, **settings})
    key = transport_key(device, wanted)
    changed = (old.get('transport_key') != key
               or source_address_removed(old, device, addresses))
    reconnect = False
    if live:
        actual = m.api('/configs', timeout=2)
        # routing-mark is NOT supported by PATCH in Mihomo. Installation or
        # startup must load the full config. Never repeatedly reload or close
        # user connections when a runtime setting has not been applied.
        if actual.get('routing-mark') != m.SOCKET_MARK:
            raise RuntimeError('VPN routing mark requires a full configuration reload')
        stale = actual.get('interface-name') != settings['interface-name']
        if stale:
            m.api('/configs', 'PATCH', {'interface-name': settings['interface-name']}, timeout=2)
            actual = m.api('/configs', timeout=2)
            if any(actual.get(k) != v for k, v in settings.items()):
                raise RuntimeError('VPN uplink settings were not applied')
        reconnect = changed or stale
        if reconnect:
            # Old TCP sockets cannot migrate their source address. Recreate
            # them once, after installing the new path; never on steady polls.
            m.api('/connections', 'DELETE', timeout=3)
    state = {'interface': device, 'ipv4': any(r.get('dst') == 'default' for r in wanted['-4']),
             'ipv6': any(r.get('dst') == 'default' for r in wanted['-6']),
             'transport_key': key, 'table': TABLE, 'mark': m.SOCKET_MARK,
             'source_addresses': addresses,
             'changed_at': time.time() if changed else old.get('changed_at')}
    if state != old:
        m.atomic(RUNTIME, state)
    return {**state, 'connections_reopened': reconnect}


if __name__ == '__main__':
    import fcntl
    with (m.ROOT / 'control.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        print(json.dumps(sync(live=False)))
