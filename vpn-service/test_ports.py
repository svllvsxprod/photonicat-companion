import struct
import unittest
from unittest.mock import patch
import socket
import json
import ports


class PortsTests(unittest.TestCase):
    def test_sharing_removes_only_ethernet_receivers_from_external_zone(self):
        values = {'values': {'cfgwan': {'.type': 'zone', 'name': 'wan',
                             'network': ['wan', 'wan6', 'wwan_fm350', 'wan_wifi']}}}
        with patch.object(ports.subprocess, 'check_output', return_value=json.dumps(values)), \
             patch.object(ports.m, 'run') as command:
            ports.sync_wan_zone(False)
        self.assertEqual(command.call_args_list[0].args,
                         ('uci', 'del_list', 'firewall.cfgwan.network=wan'))
        self.assertEqual(command.call_args_list[1].args,
                         ('uci', 'del_list', 'firewall.cfgwan.network=wan6'))
        self.assertEqual(command.call_count, 3)

    def test_share_waits_for_address_before_firewall_and_dhcp_reload(self):
        events = []
        def status(_):
            events.append('status')
            return {'up': True, 'ipv4-address': [{'address': '172.16.32.1'}]} if events.count('status') > 1 else {}
        with patch.object(ports, '_applied_role', None), \
             patch.object(ports.subprocess, 'check_output', return_value='1'), \
             patch.object(ports.subprocess, 'run'), \
             patch.object(ports, 'sync_wan_zone'), \
             patch.object(ports, 'interface_status', side_effect=status), \
             patch.object(ports.time, 'sleep'), \
             patch.object(ports.m, 'run', side_effect=lambda *a, **kw: events.append(a)):
            ports.apply_role('share')
        fw = events.index(('/etc/init.d/firewall', 'reload'))
        dns = events.index(('/etc/init.d/dnsmasq', 'reload'))
        self.assertEqual(events[:fw].count('status'), 2)
        self.assertLess(fw, dns)
        self.assertIn(('uci', 'set', 'dhcp.wan.ignore=0'), events[:dns])

    def test_failed_reload_is_retried_even_when_uci_already_changed(self):
        with patch.object(ports, '_applied_role', None), \
             patch.object(ports.subprocess, 'check_output', return_value='0'), \
             patch.object(ports, 'interface_status', return_value={'up': True, 'ipv4-address': [{}]}), \
             patch.object(ports.m, 'run', side_effect=RuntimeError('reload failed')):
            with self.assertRaises(RuntimeError):
                ports.apply_role('share')
            self.assertIsNone(ports._applied_role)

    def test_ipv6_router_prevents_sharing_and_own_ra_is_ignored(self):
        mac = bytes.fromhex('020000000001')
        frame = bytearray(ports.router_solicitation(mac) + b'\0' * 8)
        frame[6:12] = bytes.fromhex('020000000002')
        frame[22:38] = socket.inet_pton(socket.AF_INET6, 'fe80::1')
        frame[54] = 134
        self.assertEqual(ports.router_advertisement(bytes(frame), mac), 'ra:fe80::1')
        self.assertEqual(ports.decide('share', True, 'ra:fe80::1'), ('uplink', 'ipv6_router'))
        frame[6:12] = mac
        self.assertIsNone(ports.router_advertisement(bytes(frame), mac))

    def test_dhcp_server_always_wins_even_without_internet_or_manual_share(self):
        for mode in ('auto', 'uplink', 'share'):
            self.assertEqual(ports.decide(mode, True, '192.0.2.1')[0], 'uplink')

    def test_auto_is_conservative_about_existing_lease(self):
        self.assertEqual(ports.decide('auto', True, None, True)[0], 'uplink')
        self.assertEqual(ports.decide('auto', True, None, False)[0], 'share')
        self.assertEqual(ports.decide('share', False, None)[0], 'uplink')
        self.assertEqual(ports.decide('uplink', True, None)[0], 'uplink')

    def test_guard_enforces_v4_v6_dns_and_only_selected_exit(self):
        c = dict(lan_bridge='br-lan', direct_bridge='br-pcdirect',
                 wan_device='eth0', lan_enabled=True)
        text = ports.guard_text(c, 'mihomo')
        self.assertIn('elements = { "pcmh0" }', text)
        self.assertIn('dnat ip to 1.1.1.1', text)
        self.assertIn('dnat ip6 to 2606:4700:4700::1111', text)
        self.assertIn('iifname "br-lan" counter drop', text)
        self.assertNotIn('established', text)
        c['lan_enabled'] = False
        self.assertIn('set vpn_exit { type ifname;  }', ports.guard_text(c, 'mihomo'))

    def test_wifi_remains_protected_when_lan_paused_and_engine_changes(self):
        c = dict(lan_bridge='br-lan', direct_bridge='br-pcdirect',
                 wan_device='eth0', lan_enabled=False, wifi_bridge='br-pcwifi')
        for engine, interface in ports.ENGINES.items():
            text = ports.guard_text(c, engine)
            self.assertIn('set vpn_exit { type ifname;  }', text)
            self.assertIn('set wifi_exit { type ifname; elements = { "' + interface + '" }; }', text)
            self.assertIn('iifname "br-pcwifi" oifname @wifi_exit counter accept', text)
            self.assertIn('iifname "br-pcwifi" counter drop', text)
            self.assertIn('iifname "br-pcwifi" meta mark set', text)
            self.assertNotIn('established', text)

    def test_direct_lan_never_routes_to_vpn_and_keeps_wifi_protected(self):
        c = dict(lan_bridge='br-lan', direct_bridge='br-pcdirect', wan_device='eth0', lan_enabled=True, lan_mode='direct', wifi_bridge='br-pcwifi')
        text = ports.guard_text(c, 'mihomo')
        self.assertIn('iifname "br-lan" meta mark set ' + str(ports.m.SOCKET_MARK), text)
        self.assertIn('iifname "br-lan" oifname { "pcawg0", "pcmh0" } counter drop', text)
        self.assertIn('iifname "br-pcwifi" counter drop', text)
        c['lan_enabled'] = False
        self.assertNotIn('iifname "br-lan" counter accept', ports.guard_text(c, 'mihomo'))

    def test_dhcp_parser_ignores_unrelated_and_malformed_packets(self):
        mac = bytes.fromhex('020000000001')
        xid = 1234
        request = ports.discover_frame(mac, xid)
        self.assertEqual(ports.checksum(request[14:34]), 0)
        self.assertIsNone(ports.dhcp_offer(request, mac, xid))
        frame = bytearray(request)
        frame[34:38] = b'\x00\x43\x00\x44'
        frame[42] = 2
        frame[282:285] = b'\x35\x01\x02'
        frame[26:30] = b'\xc0\x00\x02\x01'
        self.assertEqual(ports.dhcp_offer(bytes(frame), mac, xid), '192.0.2.1')
        self.assertIsNone(ports.dhcp_offer(bytes(frame), mac, 1235))
        self.assertIsNone(ports.dhcp_offer(bytes(frame[:280]), mac, xid))


if __name__ == '__main__':
    unittest.main()
