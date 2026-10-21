import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace
import json
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('photonicat_radio', Path(__file__).parents[1] / 'router/photonicat_radio.py')
radio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(radio)


class RadioTests(unittest.TestCase):
    def test_boot_before_client_creation_and_public_api(self):
        class Client:
            def is_fm350(self): return True
            def handle_cesq(self, response): pass
            def handle_gtcainfo(self, response): pass
        class App:
            json = json
            def after_request(self, callback):
                self.callback = callback
                return callback
        class Response:
            status_code = 200
            def __init__(self): self.data = {'modem_network_info': 'UNKNOWN(13)'}
            def get_json(self, silent=True): return self.data
            def set_data(self, value): self.data = json.loads(value)
        app = App()
        pc_app = SimpleNamespace(modem_client=None)
        base = dict(modem_signal_strength=48, sim_state='ready', wwan_powered=True)
        namespace = dict(pc_app=pc_app, flask_app=app, get_dashboard_data=lambda: base)
        fake_modules = {'pc_modem_client': SimpleNamespace(PcModemClient=Client),
                        'flask': SimpleNamespace(request=SimpleNamespace(path='/api/v1/modem/basic.json'))}
        with patch.dict('sys.modules', fake_modules):
            radio.install(namespace)
            self.assertEqual(namespace['get_dashboard_data']()['modem_signal_strength'], 48)
            pc_app.modem_client = Client()
            pc_app.modem_client.handle_cesq('+CESQ: 42,99,255,255,24,64,65,79,93')
            self.assertEqual(namespace['get_dashboard_data']()['modem_signal_strength'], 100)
            self.assertEqual(base['modem_signal_strength'], 48)  # preserve stock cache
            response = app.callback(Response())
            self.assertEqual(response.data['modem_network_info'], '5G NSA')
            self.assertEqual(response.data['modem_serving_quality'], '23 dB, -11 dB, -78 dBm')
            base['sim_state'] = 'absent'
            self.assertEqual(namespace['get_dashboard_data']()['modem_signal_strength'], 0)

    def test_live_nsa_quantization(self):
        result = radio.parse_cesq(b'AT+CESQ\r\n\r\n+CESQ: 42,99,255,255,24,64,65,79,93\n\r\nOK')
        self.assertEqual(result['nr'], dict(rsrp=-78, rsrq=-11, sinr=23))
        self.assertEqual(result['lte'], dict(rsrp=-77, rsrq=-8))
        self.assertEqual(radio.signal_percent(result['nr']['rsrp']), 100)

    def test_lte_fallback_and_invalid(self):
        signal = radio.parse_cesq('+CESQ: 32,99,255,255,14,48,255,255,255\nOK')
        client = SimpleNamespace(_pc_radio_signal=(100, signal))
        self.assertEqual(radio.snapshot(client, 101)['mode'], 'LTE')
        self.assertEqual(radio.snapshot(client, 101)['rsrp'], -93)
        self.assertEqual(radio.snapshot(client, 101)['signal_percent'], 50)
        self.assertIsNone(radio.snapshot(client, 251))
        self.assertIsNone(radio.parse_cesq('ERROR'))
        invalid = radio.parse_cesq('+CESQ: 99,99,255,255,255,255,255,255,255')
        self.assertIsNone(radio.snapshot(SimpleNamespace(_pc_radio_signal=(100, invalid)), 100)['mode'])

    def test_nsa_ca_mixed_newlines_and_band_encoding(self):
        response = ('+GTCAINFO:\nPCC:5001,459,426050,75,75,4,1,4,4,-78\n'
                    'PCC:120,30,6338,50,50,2,1,3,3,-77\r\n'
                    'SCC 1:2,0,107,83,2850,100,255,3,255,4,255,-77\n'
                    'SCC 2:2,0,103,459,1458,50,255,3,255,2,255,-77\n'
                    'SCC 3:2,0,103,459,1602,100,255,3,255,3,255,-77\nOK')
        result = radio.parse_ca(response)
        self.assertEqual([x['band'] for x in result], ['n1', 'B20', 'B7', 'B3', 'B3'])
        self.assertEqual(sum(x['bandwidth_mhz'] for x in result), 75)
        self.assertTrue(all(x['active'] for x in result))
        self.assertEqual(result[0]['dl_layers'], 4)
        self.assertEqual(radio.band_name(501), ('NR', 'n1'))

    def test_idle_zero_nr_uses_lte_without_inventing_weak_nr(self):
        signal = radio.parse_cesq('+CESQ: 42,99,255,255,24,66,0,0,0')
        ca = radio.parse_ca('PCC:5001,459,426050,75,75,4,1,4,4,-75')
        client = SimpleNamespace(_pc_radio_signal=(100, signal), _pc_radio_ca=(99, ca))
        result = radio.snapshot(client, 101)
        self.assertEqual(result['mode'], '5G NSA')
        self.assertEqual(result['signal_source'], 'LTE RSRP')
        self.assertEqual(result['rsrp'], -75)
        self.assertEqual(result['signal_percent'], 100)
        self.assertIsNone(result['nr']['rsrp'])
        self.assertIsNone(result['sinr'])
        client._pc_radio_ca = (-100, ca)
        self.assertEqual(radio.snapshot(client, 101)['mode'], 'LTE')

    def test_old_nr_removed_on_fresh_lte_and_inactive_scc(self):
        ca = radio.parse_ca('PCC:501,4,426050,75,4,1,4,4,-78\nSCC1:1,0,107,3,2850,100,255,2,255,3,255,-93')
        self.assertFalse(ca[1]['active'])
        lte = radio.parse_cesq('+CESQ: 32,99,255,255,14,48')
        client = SimpleNamespace(_pc_radio_signal=(100, lte), _pc_radio_ca=(99, ca))
        self.assertEqual([c['band'] for c in radio.snapshot(client, 100)['carriers']], ['B7'])
        self.assertEqual(radio.parse_ca('PCC:bad\nSCC 1:2,0'), [])


if __name__ == '__main__':
    unittest.main()
