#!/usr/bin/env python3
"""One-time scoped migration; run only after taking a private UCI backup."""
import ipaddress
import json
from pathlib import Path
import subprocess
import ports
import manager as m


def uci(*args):
    return subprocess.check_output(['uci', *args], text=True).strip()


def set_(key, value):
    m.run('uci', 'set', f'{key}={value}')


def add(key, value):
    m.run('uci', 'add_list', f'{key}={value}')


def install():
    if ports.CONFIG.exists():
        raise RuntimeError('Already installed')
    if uci('changes'):
        raise RuntimeError('Uncommitted UCI changes')
    wan = ports.checked_device(uci('get', 'network.wan.device'))
    lan_bridge = ports.checked_device(uci('get', 'network.lan.device'))
    devices = json.loads(subprocess.check_output(['ubus','call','uci','get','{"config":"network"}']))['values']
    bridges = [v for v in devices.values() if v.get('.type') == 'device' and v.get('name') == lan_bridge]
    if len(bridges) != 1 or len(bridges[0].get('ports', [])) != 1:
        raise RuntimeError('Expected a single physical LAN port')
    lan = ports.checked_device(bridges[0]['ports'][0])
    if wan == lan:
        raise RuntimeError('Port mapping ambiguous')
    lan_address = uci('get', 'network.lan.ipaddr')
    direct, share = '172.16.16.1', '172.16.32.1'
    for addr in json.loads(subprocess.check_output(['ip', '-j', '-4', 'addr'])):
        for a in addr.get('addr_info', []):
            network = ipaddress.ip_network(f"{a['local']}/{a['prefixlen']}", strict=False)
            if any(ipaddress.ip_address(x) in network for x in (direct, share)):
                raise RuntimeError('New subnet overlaps an existing interface')
    c = dict(wan_device=wan, lan_device=lan, lan_bridge=lan_bridge,
             direct_bridge='br-pcdirect', lan_address=lan_address,
             direct_address=direct, share_address=share, wan_mode='auto', lan_enabled=True)
    m.atomic(ports.CONFIG, c)
    # Install the fail-closed guard before changing any bridge or forwarding.
    ports.sync_guard()
    set_('network.pcdirect_dev', 'device')
    set_('network.pcdirect_dev.name', 'br-pcdirect')
    set_('network.pcdirect_dev.type', 'bridge')
    set_('network.pcdirect_dev.bridge_empty', '1')
    for name, device, address, hint in [
        ('pcdirect', 'br-pcdirect', direct, '10'), ('pcwan', wan, share, '20')
    ]:
        set_(f'network.{name}', 'interface')
        for k,v in dict(proto='static', device=device, ipaddr=address,
                        netmask='255.255.255.0', ip6assign='64', ip6hint=hint,
                        ip6class='local', disabled='1' if name=='pcwan' else '0').items():
            set_(f'network.{name}.{k}', v)
        set_(f'dhcp.{name}', 'dhcp')
        for k,v in dict(interface=name, start='100', limit='100', leasetime='12h',
                        dhcpv4='server', dhcpv6='server', ra='server', ra_slaac='1').items():
            set_(f'dhcp.{name}.{k}', v)
    m.run('uci', '-q', 'delete', 'network.lan.ip6class', check=False)
    add('network.lan.ip6class', 'local')
    set_('dhcp.lan.ra_default', '2')
    # Explicit VPN DNS advertisements; NAT also captures hard-coded port-53 DNS.
    m.run('uci', '-q', 'delete', 'dhcp.lan.dhcp_option', check=False)
    add('dhcp.lan.dhcp_option', '6,1.1.1.1')
    m.run('uci', '-q', 'delete', 'dhcp.lan.dns', check=False)
    add('dhcp.lan.dns', '2606:4700:4700::1111')
    wireless = json.loads(subprocess.check_output(['ubus','call','uci','get','{"config":"wireless"}']))['values']
    moved = []
    for section, v in wireless.items():
        networks = v.get('network', [])
        if isinstance(networks, str):
            networks = networks.split()
        if v.get('.type') == 'wifi-iface' and v.get('mode') == 'ap' and networks == ['lan']:
            set_(f'wireless.{section}.network', 'pcdirect')
            moved.append(section)
    if not moved:
        raise RuntimeError('No Wi-Fi AP found to separate from LAN')
    # Delete only the existing direct LAN forwarding, retaining all other zones.
    firewall = json.loads(subprocess.check_output(['ubus','call','uci','get','{"config":"firewall"}']))['values']
    for section,v in firewall.items():
        if v.get('.type') == 'forwarding' and v.get('src') == 'lan' and v.get('dest') == 'wan':
            m.run('uci', 'delete', 'firewall.'+section)
    for name, networks in [('pcdirect', ['pcdirect','pcwan']), ('pcvpn', [])]:
        set_(f'firewall.{name}', 'zone')
        for k,v in dict(name=name, input='ACCEPT' if name=='pcdirect' else 'REJECT',
                        output='ACCEPT', forward='REJECT').items():
            set_(f'firewall.{name}.{k}', v)
        for n in networks:
            add(f'firewall.{name}.network', n)
    for device in ports.ENGINES.values():
        add('firewall.pcvpn.device', device)
    set_('firewall.pcvpn.mtu_fix', '1')
    for name, src, dst in [('pc_lan_vpn','lan','pcvpn'),('pc_direct_wan','pcdirect','wan')]:
        set_(f'firewall.{name}', 'forwarding')
        set_(f'firewall.{name}.src', src)
        set_(f'firewall.{name}.dest', dst)
    set_('firewall.@defaults[0].flow_offloading', '0')
    set_('firewall.@defaults[0].flow_offloading_hw', '0')
    # fw4 fallback is present even if the independent guard service fails at boot.
    Path('/etc/nftables.d/30-photonicat-ports.nft').write_text(f'''
chain pcat_lan_fallback {{
 type filter hook forward priority -9; policy accept;
 iifname "{lan_bridge}" oifname {{ "pcawg0", "pcmh0" }} accept
 iifname "{lan_bridge}" counter drop
}}
chain pcat_dns_fallback {{
 type filter hook input priority -9; policy accept;
 iifname "{lan_bridge}" meta l4proto {{ tcp, udp }} th dport 53 counter drop
}}
''')
    m.run('fw4', 'check')
    for package in ('network','wireless','dhcp','firewall'):
        m.run('uci','commit',package)
    m.run('/etc/init.d/firewall','reload')
    m.run('ubus','call','network','reload')
    # netifd's reconf may retain the old hostapd bridge; recreate affected APs.
    radios = {wireless[name]['device'] for name in moved}
    for radio in radios:
        m.run('/sbin/wifi', 'down', radio)
        m.run('/sbin/wifi', 'up', radio)
    m.run('/etc/init.d/dnsmasq','restart')
    m.run('/etc/init.d/odhcpd','restart')
    m.prepare_routes()
    ports.secure_mihomo_config()
    print(json.dumps({'installed':True, 'mapping':c, 'wifi_moved':moved}))


if __name__ == '__main__':
    install()
