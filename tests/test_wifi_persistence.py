import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('wifi_persistence', Path(__file__).parents[1] / 'router/wifi_persistence.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WifiPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.config = {'wireless.radio7': 'wifi-device'}
        self.intents = {}
        self.original = Mock(return_value=True)
        self.ns = dict(enable_radio=self.original, get_intents=lambda: self.intents,
                       uci_show_dict=lambda *a, **kw: self.config)
        module.install(self.ns)

    def enable(self):
        return self.ns['enable_radio']('radio7', ['guest', 'main'])

    def test_off_intent_survives_regenerated_config(self):
        self.intents['radio7'] = False
        self.assertFalse(self.enable())
        self.original.assert_not_called()

    def test_uci_off_wins_over_stale_on_intent(self):
        self.intents['radio7'] = True
        self.config['wireless.radio7.disabled'] = '1'
        self.assertFalse(self.enable())
        self.original.assert_not_called()

    def test_disabled_vif_not_resurrected_alongside_enabled_ap(self):
        self.config['wireless.guest.disabled'] = '1'
        self.assertFalse(self.enable())
        self.original.assert_not_called()

    def test_manual_enable_can_recover_normally(self):
        self.intents['radio7'] = True
        self.config['wireless.radio7.disabled'] = '0'
        self.assertTrue(self.enable())
        self.original.assert_called_once_with('radio7', ['guest', 'main'])

    def test_missing_configuration_never_enables(self):
        self.config.clear()
        self.assertFalse(self.enable())
        self.original.assert_not_called()

    def test_smart_wan_without_backup_does_not_unpark_ap(self):
        unpark = Mock(return_value=True)
        restore = Mock()
        ns = {'_unpark_ap_without_backup': unpark, '_restore_radio_state': restore}
        module.install_wan(ns)
        self.assertFalse(ns['_unpark_ap_without_backup']('radio7'))
        unpark.assert_not_called()
        self.assertIs(ns['_restore_radio_state'], restore)
