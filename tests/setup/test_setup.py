import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'installer'))
import probe
import install
from defaults import initial_config


class SetupTests(unittest.TestCase):
    def network(self):
        return {'wan': {'device': 'eth0'}, 'lan': {'device': 'br-lan', 'ipaddr': '172.20.1.1'},
                'dev': {'.type': 'device', 'name': 'br-lan', 'ports': ['eth1']}}

    def test_non_overlapping_networks_preserve_lan_and_start_direct(self):
        net = self.network()
        net['unused'] = {'ipaddr': '172.20.3.1'}
        result = probe.network_plan(net, [{'addr_info': [{'family': 'inet', 'local': '172.20.2.1', 'prefixlen': 24}]}])
        self.assertEqual(result['lan_address'], '172.20.1.1')
        self.assertEqual(result['direct_address'], '172.20.4.1')
        self.assertEqual(result['share_address'], '172.20.5.1')
        self.assertEqual(result['wifi_address'], '172.20.6.1')
        self.assertEqual(result['lan_mode'], 'direct')
        self.assertEqual(result['wan_mode'], 'uplink')

    def test_reject_ambiguous_port_and_injected_name(self):
        for bad in (['eth1', 'eth2'], ['eth0'], ['eth1;reboot']):
            net = self.network(); net['dev']['ports'] = bad
            with self.assertRaises(ValueError): probe.network_plan(net, [])

    def test_each_owner_gets_new_independent_keys_and_no_profiles(self):
        a, b = initial_config(), initial_config()
        self.assertNotEqual(a['key'], b['key'])
        self.assertNotEqual(a['api_secret'], b['api_secret'])
        self.assertNotEqual(a['key'], a['api_secret'])
        self.assertEqual(len(bytes.fromhex(a['key'])), 32)
        self.assertEqual(a['profiles'], [])
        self.assertEqual(a['mihomo']['proxy-providers'], {})
        self.assertEqual(a['mihomo']['proxy-groups'][0]['proxies'], ['REJECT'])

    def test_confirmation_prevents_rollback(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(install, 'rollback') as rollback:
            root = Path(tmp)
            (root/'confirmed').touch()
            install.settle(root)
            rollback.assert_not_called()
            (root/'confirmed').unlink()
            install.settle(root)
            rollback.assert_called_once_with(root)

    def test_existing_installation_and_routing_conflict_refused(self):
        zones = {'lan': {'.type':'zone','name':'lan','network':['lan']}, 'wan': {'.type':'zone','name':'wan'}}
        with patch.object(probe, 'uci', return_value=zones), patch.object(Path, 'exists', return_value=True):
            with self.assertRaisesRegex(ValueError, 'existing_installation'): install.preflight({'supported':True})
        with patch.object(probe, 'uci', side_effect=lambda p: zones if p=='firewall' else {}), patch.object(Path, 'exists', return_value=False), patch.object(probe, 'run', return_value=json.dumps([{'priority':23497}])):
            with self.assertRaisesRegex(ValueError, 'routing_conflict'): install.preflight({'supported':True})

if __name__ == '__main__': unittest.main()
