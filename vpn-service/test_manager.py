import base64
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('vpn_manager', Path(__file__).with_name('manager.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
KEY = base64.b64encode(bytes(range(32))).decode()
CONFIG = f'''[Interface]
PrivateKey = {KEY}
Address = 10.0.0.2/32, fd00::2/128
DNS = 1.1.1.1
MTU = 1280
HeaderProtectionKey = {KEY}
RandomTrailers = on
RekeyAfterTime = 120-180
[Peer]
Endpoint = 127.0.0.1:51820
PersistentKeepalive = 25-35
PresharedKey = {KEY}
PublicKey = {KEY}
AllowedIPs = 0.0.0.0/0, ::/0
'''
class Tests(unittest.TestCase):
    def test_v31_fields_and_peer_order(self):
        text = m.awg_request(CONFIG)
        self.assertIn('random_trailers=true', text)
        self.assertIn('rekey_after_time=120-180', text)
        self.assertIn('persistent_keepalive_interval=25-35', text)
        self.assertIn('header_protection_key=' + bytes(range(32)).hex(), text)
        self.assertLess(text.index('public_key='), text.index('endpoint='))
        self.assertNotIn('Address', text)
        self.assertNotIn('DNS', text)
        self.assertIn('allowed_ip=::/0', text)
    def test_reject_hooks(self):
        with self.assertRaises(ValueError):
            m.awg_request(CONFIG.replace('MTU = 1280', 'PostUp = do-something'))
    def test_reject_ambiguous_peer(self):
        with self.assertRaises(ValueError):
            m.awg_request(CONFIG + '\n[Peer]\nPublicKey = ' + KEY)
    def test_reject_short_key(self):
        with self.assertRaises(ValueError):
            m.awg_request(CONFIG.replace('PrivateKey = ' + KEY, 'PrivateKey = YQ=='))
    def test_same_table_different_rule_is_conflict(self):
        with patch.object(m, 'run', return_value=SimpleNamespace(stdout=json.dumps([{'priority':23501,'table':23501,'src':'all','fwmark':'0x1'}]).encode())):
            with self.assertRaises(RuntimeError):
                m.ensure_rule('-4',23501,['fwmark',23501],23501)
    def test_idempotent_rule(self):
        with patch.object(m, 'run', return_value=SimpleNamespace(stdout=json.dumps([{'priority':23501,'table':23501,'src':'all','fwmark':hex(23501)}]).encode())) as run:
            m.ensure_rule('-4',23501,['fwmark',23501],23501)
            self.assertEqual(run.call_count,1)
    def test_status_does_not_expose_keys(self):
        p={'id':'test','label':'Test'}
        def api(path, **kwargs):
            return {'version':'test','now':'Example','all':['Example']}
        with patch.object(m,'manifest',return_value=[p]), patch.object(m,'state',return_value={'active':'amneziawg','amneziawg':'test','mihomo':'Example'}), patch.object(m.Path,'read_text',return_value='{"profile":"test"}'), patch.object(m,'interface_up',return_value=True), patch.object(m,'ipc',return_value=[('private_key','NEVER_EXPOSE'),('endpoint','NEVER_EXPOSE'),('rx_bytes','12')]), patch.object(m,'api',side_effect=api):
            result=m.status()
            self.assertEqual(result['amneziawg']['rx_bytes'],12)
            self.assertNotIn('NEVER_EXPOSE',json.dumps(result))
    def test_down_engine_routes_fail_closed(self):
        with patch.object(m,'state',return_value={'active':'amneziawg'}), patch.object(m,'interface_up',return_value=False), patch.object(m,'ensure_rule'), patch.object(m,'run') as run:
            m.prepare_routes_locked()
            calls=[c.args for c in run.call_args_list]
            self.assertEqual(sum('unreachable' in c for c in calls),6)
            self.assertFalse(any('dev' in c for c in calls))
            self.assertFalse(any('main' in c for c in calls))
    def test_only_two_engine_routes_exist(self):
        with patch.object(m,'state',return_value={'active':'mihomo'}), patch.object(m,'interface_up',return_value=True), patch.object(m,'ensure_rule'), patch.object(m,'run') as run:
            m.prepare_routes_locked()
            calls=[c.args for c in run.call_args_list]
            interfaces={c[c.index('dev')+1] for c in calls if 'dev' in c}
            self.assertEqual(interfaces,{'pcawg0','pcmh0'})
            tables={c[c.index('table')+1] for c in calls if 'table' in c}
            self.assertEqual(tables,{23500,23501,23502})
    def test_can_select_awg_when_mihomo_is_down(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory, patch.object(m,'ROOT',Path(directory)), patch.object(m,'state',return_value={'active':'mihomo','amneziawg':'test','mihomo':'Example'}), patch.object(m,'interface_up',return_value=True), patch.object(m,'api',side_effect=ConnectionRefusedError), patch.object(m,'prepare_routes_locked') as routes:
            result=m.select_engine('amneziawg')
            self.assertEqual(result['active'],'amneziawg')
            self.assertFalse(result['local_proxy_synced'])
            self.assertEqual(json.loads((Path(directory)/'state.json').read_text())['active'],'amneziawg')
            routes.assert_called_once()
    def test_reject_unavailable_mihomo_before_changing_state(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory, patch.object(m,'ROOT',Path(directory)), patch.object(m,'state',return_value={'active':'amneziawg'}), patch.object(m,'interface_up',return_value=True), patch.object(m,'api',side_effect=ConnectionRefusedError), patch.object(m,'atomic') as write:
            with self.assertRaises(ConnectionRefusedError):m.select_engine('mihomo')
            write.assert_not_called()
if __name__=='__main__':unittest.main()
