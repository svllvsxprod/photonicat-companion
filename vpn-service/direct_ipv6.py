#!/usr/bin/env python3
"""Gate legacy odhcpd on Direct carrier; retain the intended active modes."""
import fcntl
import json
import subprocess


def run(*args):
    return subprocess.check_output(args, text=True, timeout=8).strip()


def sync():
    # set_data emits ifupdate; serialize events and avoid a feedback loop.
    with open('/var/run/photonicat-direct-ipv6.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads(run('ubus', 'call', 'network.interface.pcdirect', 'status'))
        if state.get('device') != 'br-pcdirect':
            return
        desired = {}
        changes = {}
        for key in ('ra', 'dhcpv6'):
            current = run('uci', '-q', 'get', 'dhcp.pcdirect.' + key)
            try:
                active = run('uci', '-q', 'get', 'dhcp.pcdirect.pcat_' + key)
            except subprocess.CalledProcessError:
                active = current
                changes['pcat_' + key] = active
            if active not in ('server', 'relay', 'hybrid', 'disabled'):
                raise ValueError('Invalid Direct IPv6 mode')
            desired[key] = active if state.get('up') else 'disabled'
            if current != desired[key]:
                changes[key] = desired[key]
        # This old odhcpd can re-arm stale RA timers despite netifd overlays.
        # Make UCI authoritative too, only on transitions, and never commit
        # another editor's pending DHCP changes.
        if changes:
            if run('uci', 'changes', 'dhcp'):
                raise RuntimeError('Pending DHCP changes; Direct IPv6 sync deferred')
            for key, value in changes.items():
                run('uci', 'set', 'dhcp.pcdirect.' + key + '=' + value)
            run('uci', 'commit', 'dhcp')
        if any(state.get('data', {}).get(k) != v for k, v in desired.items()):
            run('ubus', 'call', 'network.interface.pcdirect', 'set_data', json.dumps(desired))
        if changes:
            run('/etc/init.d/odhcpd', 'reload')


if __name__ == '__main__':
    sync()
