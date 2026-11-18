#!/usr/bin/env python3
"""Gate legacy odhcpd on Direct carrier; retain the intended active modes."""
import fcntl
import json
import logging
import subprocess
import sys
import time

LOG = logging.getLogger('photonicat-direct-ipv6')


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE, timeout=8).strip()


def sync():
    # set_data emits ifupdate; serialize events and avoid a feedback loop.
    with open('/var/run/photonicat-direct-ipv6.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.loads(run('ubus', 'call', 'network.interface.pcdirect', 'status'))
        except subprocess.CalledProcessError as exc:
            # netifd publishes this object after early boot and removes it
            # during teardown. Do not mutate DHCP based on a missing object.
            if exc.returncode == 4:
                return False
            raise
        if state.get('device') != 'br-pcdirect':
            return True
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
        return True


def wait_until_ready(attempts=61, interval=2):
    """Bounded boot worker; hotplug handles subsequent interface changes."""
    for attempt in range(attempts):
        if sync():
            LOG.info('Direct IPv6 startup synchronization complete')
            return True
        if attempt == 0:
            LOG.info('Waiting for Direct interface; current network remains unchanged')
        if attempt + 1 < attempts:
            time.sleep(interval)
    LOG.error('Direct interface unavailable after startup wait; hotplug will retry')
    return False


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    if sys.argv[1:] == ['--wait']:
        sys.exit(0 if wait_until_ready() else 1)
    if sys.argv[1:]:
        sys.exit('Usage: direct_ipv6.py [--wait]')
    sync()
