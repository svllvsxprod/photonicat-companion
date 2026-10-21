import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'router')]
from control import Controls, ControlError, SCREEN_KEYS

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.control = Controls()
        self.radios = [dict(exist=True, device=name, ssid=name, enabled=True,
            encryption='psk2', password='old-test-password', frequency='5g', hidden='1',
            band='5g', capabilities={'bands': {'2g': {}, '5g': {}}}) for name in ['radio3', 'pcie7']]
        self.user = {'templates': {'page0': ['keep']}, 'ping_site0': 'keep.example'}
        self.live = {v: 60 if k != 'brightness' else 100 for k, v in SCREEN_KEYS.items()}
        self.writes = []
        patch('control.wifi_target', return_value='discovered_ap').start()
        patch('control.write_wifi', side_effect=lambda payload: self.fake('/api/v1/wireless.json', payload)).start()
        patch('control.apply_display', return_value=True).start()
        self.api = patch('control.api', side_effect=self.fake).start()
        patch('control.time.sleep').start()
        patch.object(self.control, 'backup').start()
        self.addCleanup(patch.stopall)

    def fake(self, path, payload=None, port=80):
        if payload is not None:
            self.writes.append((path, copy.deepcopy(payload)))
        if path == '/api/v2/wireless.json': return {'interfaces': copy.deepcopy(self.radios)}
        if path == '/api/v1/wireless.json':
            next(r for r in self.radios if r['device'] == payload['device']).update(payload)
            return {'status': 'ok'}
        if path.endswith('go_get_user_config.json'): return copy.deepcopy(self.user)
        if path.endswith('go_get_config.json'): return copy.deepcopy(self.live)
        if path.endswith('go_save_user_config.json'):
            self.user = copy.deepcopy(payload)
            self.live.update(payload)
            return {'status': 'ok'}
        raise AssertionError(path)

    def wifi_args(self):
        radio = self.radios[1]
        return {'id': radio['device'], 'revision': self.control.revision(radio),
                'ssid': 'New AP', 'enabled': False}

    def test_dynamic_radio_selection_preserves_password_and_neighbour(self):
        neighbour = copy.deepcopy(self.radios[0])
        self.control.execute('wifi_set', self.wifi_args())
        self.assertEqual(self.radios[0], neighbour)
        self.assertEqual(self.radios[1]['ssid'], 'New AP')
        self.assertEqual(self.radios[1]['password'], 'old-test-password')
        self.assertTrue(self.writes[0][1]['hide_ssid'])
        self.assertNotIn('password', self.control.wifi_public(self.radios[1]))

    def test_stale_revision_invalid_input_and_unknown_device_cannot_write(self):
        for change in [{'revision': 'old'}, {'ssid': '猫' * 11}, {'password': 'short'},
                       {'enabled': 'yes'}, {'id': '../radio3'}, {'command': 'reboot'}]:
            with self.subTest(change=change), self.assertRaises(ControlError):
                self.control.execute('wifi_set', {**self.wifi_args(), **change})
        self.assertEqual(self.writes, [])

    def test_vpn_mode_revision_prevents_stale_switch_and_preserves_neighbour(self):
        vpn = {'enabled': False, 'network': 'pcdirect', 'engine': 'mihomo'}
        with patch('control.wifi_vpn_info', side_effect=lambda _: dict(vpn)):
            radio = self.radios[1]
            args = dict(id=radio['device'], revision=self.control.wifi_revision(radio, vpn),
                        ssid=radio['ssid'], enabled=radio['enabled'], vpn_enabled=True)
            for value in (1, 'true', None):
                with self.assertRaises(ControlError):
                    self.control.execute('wifi_set', {**args, 'vpn_enabled': value})
            self.assertEqual(self.writes, [])
            neighbour = copy.deepcopy(self.radios[0])
            def write(payload):
                self.fake('/api/v1/wireless.json', payload)
                vpn.update(enabled=payload['vpn_enabled'], network='pcwifi')
            with patch('control.write_wifi', side_effect=write):
                self.control.execute('wifi_set', args)
            self.assertEqual(self.radios[0], neighbour)
            self.assertEqual(self.writes[0][1]['password'], 'old-test-password')
            self.assertTrue(self.writes[0][1]['vpn_enabled'])
            with self.assertRaises(ControlError):
                self.control.execute('wifi_set', args)

    def test_upstream_radio_is_not_an_ap(self):
        self.radios[1]['wifi_wan'] = True
        self.assertEqual(self.control.wifi_public(self.radios[1])['actions'], [])
        with self.assertRaises(ControlError): self.control.execute('wifi_set', self.wifi_args())
        self.assertEqual(self.writes, [])

    def test_screen_saves_only_requested_fields_preserves_layout(self):
        args = dict(brightness=75, battery_timeout=120, power_timeout=3600,
                    revision=self.control.revision(self.user))
        self.control.execute('screen_set', args)
        self.assertEqual(self.user['templates'], {'page0': ['keep']})
        self.assertEqual(self.user['ping_site0'], 'keep.example')
        self.assertEqual(self.live['screen_max_brightness'], 75)
        with self.assertRaises(ControlError): self.control.execute('screen_set', args)
        self.assertEqual(len(self.writes), 1)

    def test_reboot_requires_explicit_confirmation_and_commands_are_allowlisted(self):
        for op, args in [('reboot', {}), ('reboot', {'confirm': 'no'}), ('shell', {'cmd': 'true'})]:
            with self.assertRaises(ControlError): self.control.execute(op, args)
        self.assertEqual(self.writes, [])
