"""Optional performance profile for PhotonicatWrt 26.04.1. Run as root via SSH."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path('/etc/photonicat-vpn')
CONFIG = ROOT / 'mihomo/config.json'
STATE = Path('/etc/photonicat-companion/performance-rollback.json')
BIN = Path('/opt/photonicat-vpn/mihomo')
PLATFORM = Path('/usr/libexec/platform/packet-steering.sh')
HELPER = Path('/etc/photonicat-rps.sh')
HOOK = Path('/etc/hotplug.d/net/98-photonicat-rps')
WAN = Path('/sys/class/net/eth0/queues/rx-0/rps_cpus')
TUN = Path('/sys/class/net/pcmh0/queues/rx-0/rps_cpus')

HELPER_TEXT = r'''#!/bin/sh
# Run the firmware's packet steering, then apply this device's measured RPS layout.
stock=/usr/libexec/network/packet-steering.uc
if [ "$1" = net-add ]; then
    mode=$(uci -q get 'network.@globals[0].packet_steering')
else
    mode=$1
    flows=$(uci -q get 'network.@globals[0].steering_flows')
    if [ "${flows:-0}" -gt 0 ] 2>/dev/null; then
        "$stock" -l "$flows" "$mode" || exit $?
    else
        "$stock" "$mode" || exit $?
    fi
fi
[ "$(cat /tmp/sysinfo/board_name)" = ariaboard,photonicat2 ] || exit 0
apply_mask() {
    local queue="/sys/class/net/$1/queues/rx-0/rps_cpus"
    [ -w "$queue" ] || return 0
    [ "$(cat "$queue")" = "$2" ] || printf '%s\n' "$2" > "$queue"
}
if [ "$mode" = 1 ]; then
    apply_mask eth0 00 || exit 1
    apply_mask pcmh0 fc
else
    # The factory steering script manages physical network devices only.
    apply_mask pcmh0 00
fi
'''

HOOK_TEXT = r'''#!/bin/sh
# A Mihomo restart can recreate its TUN without a netifd interface event.
case "$ACTION:${DEVICENAME:-$INTERFACE}" in
    add:pcmh0|add:eth0)
        [ "$(readlink /usr/libexec/platform/packet-steering.sh)" != /etc/photonicat-rps.sh ] ||
            /etc/photonicat-rps.sh net-add
        ;;
esac
'''


class Unsupported(Exception):
    pass


def atomic(path, data, mode=0o600):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out:
        temp = Path(out.name)
        try:
            out.write(data)
            out.flush()
            os.fchmod(out.fileno(), mode)
            os.fsync(out.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)


def command(*args):
    return subprocess.check_output(args, stderr=subprocess.DEVNULL, timeout=15).decode().strip()


def listener(config):
    matches = [v for v in config.get('listeners', []) if v.get('type') == 'tun' and v.get('device') == 'pcmh0']
    if len(matches) != 1:
        raise Unsupported()
    return matches[0]


def target_values(tun):
    if tun.get('stack') not in ('gvisor', 'mips'):
        raise Unsupported()
    values = {'stack': 'mips', 'gso': True}
    if tun.get('mtu') == 1280:
        values['mtu'] = 1500
    return values


def check_files():
    missing = []
    for path, content in ((HELPER, HELPER_TEXT), (HOOK, HOOK_TEXT)):
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.read_text() != content)):
            raise Unsupported()
        if not path.exists():
            missing.append(str(path))
    if PLATFORM.is_symlink() and os.readlink(PLATFORM) == str(HELPER):
        pass
    elif PLATFORM.is_symlink() or PLATFORM.exists():
        raise Unsupported()
    else:
        missing.append(str(PLATFORM))
    return missing


def set_config(config):
    content = (json.dumps(config, ensure_ascii=False, indent=2) + '\n').encode()
    with tempfile.NamedTemporaryFile(dir=CONFIG.parent, suffix='.json') as candidate:
        candidate.write(content)
        candidate.flush()
        command(str(BIN), '-t', '-d', str(CONFIG.parent), '-f', candidate.name)
    atomic(CONFIG, content)


def restore(state):
    check_files()
    config = json.loads(CONFIG.read_text())
    tun = listener(config)
    changed = False
    for key, new in state['new'].items():
        if tun.get(key) == new:
            if key in state['old']:
                tun[key] = state['old'][key]
            else:
                tun.pop(key, None)
            changed = True
    if changed:
        set_config(config)
    for path in (PLATFORM, HOOK, HELPER):
        if str(path) in state['created']:
            path.unlink(missing_ok=True)
    for path, key in ((WAN, 'wan'), (TUN, 'tun')):
        if path.exists() and state[key] is not None:
            path.write_text(state[key])
    STATE.unlink(missing_ok=True)


def update(action):
    board = json.loads(command('ubus', 'call', 'system', 'board'))
    release = board.get('release', {})
    if (board.get('board_name') != 'ariaboard,photonicat2' or release.get('version') != '26.04.1'
            or release.get('distribution', '').lower() != 'photonicatwrt'):
        raise Unsupported()
    if not CONFIG.is_file() or not STATE.parent.is_dir():
        raise Unsupported()
    with (ROOT / 'control.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if action == 'restore':
            if not STATE.is_file():
                return 'no_backup'
            restore(json.loads(STATE.read_text()))
            return 'restored'
        if (command('uci', '-q', 'get', 'network.@globals[0].packet_steering') != '1'
                or command('uci', '-q', 'get', 'network.wan.device') != 'eth0'
                or not Path('/usr/libexec/network/packet-steering.uc').is_file()
                or not WAN.exists() or not TUN.exists()
                or 'v1.19.32' not in command(str(BIN), '-v').split()):
            raise Unsupported()
        missing = check_files()
        config = json.loads(CONFIG.read_text())
        tun = listener(config)
        new = {k: v for k, v in target_values(tun).items() if tun.get(k) != v}
        live = WAN.read_text().strip() == '00' and TUN.read_text().strip() == 'fc'
        if action == 'check':
            return 'ready' if not (missing or new) and live else 'available'
        if STATE.exists():
            state = json.loads(STATE.read_text())
            if state.get('pending'):
                restore(state)
                return 'retry'
            if new or missing:
                return 'modified'
        if not (missing or new):
            if not live:
                command(str(HELPER), 'net-add')
            return 'ready'
        state = {'old': {k: tun[k] for k in new if k in tun}, 'new': new,
                 'created': missing, 'wan': WAN.read_text(), 'tun': TUN.read_text(), 'pending': True}
        atomic(STATE, json.dumps(state).encode())
        try:
            for path, content in ((HELPER, HELPER_TEXT), (HOOK, HOOK_TEXT)):
                if str(path) in missing:
                    atomic(path, content.encode(), 0o755)
            if str(PLATFORM) in missing:
                PLATFORM.parent.mkdir(mode=0o755, exist_ok=True)
                PLATFORM.symlink_to(HELPER)
            if new:
                tun.update(new)
                set_config(config)
            command(str(HELPER), 'net-add')
            if WAN.read_text().strip() != '00' or TUN.read_text().strip() != 'fc':
                raise RuntimeError()
            state['pending'] = False
            atomic(STATE, json.dumps(state).encode())
        except Exception:
            restore(state)
            raise
        return 'saved' if new else 'ready'


if __name__ == '__main__':
    try:
        action = sys.argv[1]
        if action not in ('check', 'apply', 'restore'):
            raise Unsupported()
        status = update(action)
    except Unsupported:
        status = 'unsupported'
    except BlockingIOError:
        status = 'busy'
    except Exception:
        status = 'failed'
    print(json.dumps({'status': status}))
