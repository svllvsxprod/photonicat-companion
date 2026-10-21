import unittest
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'router'))
from control import wifi_target, ControlError


class WifiTargetTests(unittest.TestCase):
    def config(self, disabled='1'):
        return {
            'pcie7': {'type': 'mac80211'},
            'ap': {'device': 'pcie7', 'mode': 'ap'},
            'saved_sta': {'device': 'pcie7', 'mode': 'sta', 'disabled': disabled},
            'other_ap': {'device': 'radio9', 'mode': 'ap'},
        }

    def test_disabled_saved_station_does_not_block_single_ap(self):
        with patch('control.wifi_config', return_value=self.config()):
            self.assertEqual(wifi_target('pcie7'), 'ap')

    def test_enabled_or_unspecified_station_remains_protected(self):
        for disabled in ('0', None):
            with patch('control.wifi_config', return_value=self.config(disabled)):
                with self.assertRaises(ControlError):
                    wifi_target('pcie7')

    def test_multiple_aps_remain_ambiguous_even_if_guest_is_disabled(self):
        config = self.config()
        config['guest'] = {'device': 'pcie7', 'mode': 'ap', 'disabled': '1'}
        with patch('control.wifi_config', return_value=config):
            with self.assertRaises(ControlError):
                wifi_target('pcie7')
