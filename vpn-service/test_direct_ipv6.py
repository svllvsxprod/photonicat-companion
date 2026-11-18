import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import direct_ipv6


class DirectIPv6Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = {'device': 'br-pcdirect', 'up': False, 'data': {}}
        self.uci = {'ra': 'server', 'dhcpv6': 'server'}
        self.pending = ''
        self.writes = []
        self.status_failures = []
        self.addCleanup(patch.stopall)
        patch.object(direct_ipv6, 'open', create=True,
                     side_effect=lambda *a: open(Path(self.temp.name)/'lock', 'w')).start()
        patch.object(direct_ipv6, 'run', side_effect=self.run_command).start()

    def run_command(self, *args):
        if args[:3] == ('ubus', 'call', 'network.interface.pcdirect'):
            if args[3] == 'status':
                if self.status_failures:
                    raise subprocess.CalledProcessError(self.status_failures.pop(0), args)
                return json.dumps(self.state)
            self.state['data'].update(json.loads(args[4])); return ''
        if args[:3] == ('uci', '-q', 'get'):
            key = args[3].split('.')[-1]
            if key not in self.uci: raise subprocess.CalledProcessError(1, args)
            return self.uci[key]
        if args[:2] == ('uci', 'changes'): return self.pending
        self.writes.append(args)
        if args[:2] == ('uci', 'set'):
            key, value = args[2].split('=', 1)
            self.uci[key.split('.')[-1]] = value
        return ''

    def test_modes_survive_idle_active_idle_and_identical_syncs_do_not_write(self):
        direct_ipv6.sync()
        count = len(self.writes)
        for _ in range(5): direct_ipv6.sync()
        self.assertEqual(len(self.writes), count)
        self.assertEqual(self.uci['ra'], 'disabled')
        self.state['up'] = True
        direct_ipv6.sync()
        self.assertEqual(self.uci['ra'], 'server')
        self.assertEqual(self.uci['dhcpv6'], 'server')
        self.state['up'] = False
        direct_ipv6.sync()
        self.assertEqual(self.uci['ra'], 'disabled')
        self.assertEqual(self.uci['pcat_ra'], 'server')

    def test_does_not_commit_another_editors_pending_changes(self):
        self.pending = 'dhcp.lan.leasetime=24h'
        with self.assertRaises(RuntimeError): direct_ipv6.sync()
        self.assertEqual(self.writes, [])

    def test_other_device_is_untouched(self):
        self.state['device'] = 'br-lan'
        direct_ipv6.sync()
        self.assertEqual(self.writes, [])

    def test_missing_interface_does_not_change_dhcp(self):
        self.status_failures = [4]
        self.assertFalse(direct_ipv6.sync())
        self.assertEqual(self.writes, [])
        self.assertEqual(self.uci, {'ra': 'server', 'dhcpv6': 'server'})

    def test_boot_wait_recovers_when_netifd_appears(self):
        self.status_failures = [4, 4]
        with patch.object(direct_ipv6.time, 'sleep') as sleep:
            self.assertTrue(direct_ipv6.wait_until_ready(attempts=3))
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(self.uci['ra'], 'disabled')
        self.assertEqual(self.uci['pcat_ra'], 'server')

    def test_boot_wait_is_bounded_and_keeps_settings(self):
        self.status_failures = [4] * 3
        with patch.object(direct_ipv6.time, 'sleep') as sleep:
            with self.assertLogs(direct_ipv6.LOG, level='ERROR'):
                self.assertFalse(direct_ipv6.wait_until_ready(attempts=3))
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(self.writes, [])

    def test_other_status_errors_are_not_silently_retried(self):
        self.status_failures = [7]
        with patch.object(direct_ipv6.time, 'sleep') as sleep:
            with self.assertRaises(subprocess.CalledProcessError):
                direct_ipv6.wait_until_ready(attempts=3)
        sleep.assert_not_called()
        self.assertEqual(self.writes, [])
