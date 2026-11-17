"""Install unused client networks; keep existing LAN/APs in Direct initially."""
import json
from pathlib import Path
import subprocess


def run(*a):
    subprocess.run(a, capture_output=True, check=True, timeout=30)


def configure(c):
    def set_(key, val): run('uci','set',key+'='+str(val))
    def add(key, val): run('uci','add_list',key+'='+str(val))
    # APs stay on their current network. No Wi-Fi down/up is performed.
    for name, bridge, address, disabled in (
        ('pcdirect', c['direct_bridge'], c['direct_address'], '0'),
        ('pcwifi', c['wifi_bridge'], c['wifi_address'], '0'),
        ('pcwan', c['wan_device'], c['share_address'], '1')):
        if name != 'pcwan':
            set_(f'network.{name}_dev','device')
            for key,value in {'name':bridge,'type':'bridge','bridge_empty':'1'}.items(): set_(f'network.{name}_dev.{key}',value)
        set_(f'network.{name}','interface')
        for key,value in {'proto':'static','device':bridge,'ipaddr':address,'netmask':'255.255.255.0',
                          'ip6assign':'64','ip6class':'local','disabled':disabled}.items():set_(f'network.{name}.{key}',value)
        set_(f'dhcp.{name}','dhcp')
        for key,value in {'interface':name,'start':'100','limit':'100','leasetime':'12h',
                          'dhcpv4':'server','dhcpv6':'server','ra':'server','ra_slaac':'1',
                          'ra_default':'2' if name=='pcwifi' else '1'}.items():set_(f'dhcp.{name}.{key}',value)
    for name, nets in [('pcdirect',['pcdirect','pcwan']),('pcwifi',['pcwifi']),('pcvpn',[])]:
        set_('firewall.'+name,'zone')
        for key,value in {'name':name,'input':'REJECT' if name=='pcvpn' else 'ACCEPT','output':'ACCEPT','forward':'REJECT','mtu_fix':'1'}.items():set_(f'firewall.{name}.{key}',value)
        for n in nets:add(f'firewall.{name}.network',n)
    for dev in ('pcmh0','pcawg0'):add('firewall.pcvpn.device',dev)
    for name,src,dst in [('pc_lan_direct','lan','wan'),('pc_lan_vpn','lan','pcvpn'),
                         ('pc_wifi_vpn','pcwifi','pcvpn'),('pc_direct_wan','pcdirect','wan'),('pc_wan_vpn','pcdirect','pcvpn')]:
        set_('firewall.'+name,'forwarding');set_('firewall.'+name+'.src',src);set_('firewall.'+name+'.dest',dst)
    for zone in ('lan','pcwifi','pcdirect'):
        name='firewall.pcat_companion_'+zone
        set_(name,'rule')
        for k,v in {'name':'Photonicat Companion '+zone,'src':zone,'proto':'tcp','dest_port':'24862','family':'ipv4','target':'ACCEPT'}.items():set_(name+'.'+k,v)
    set_('firewall.@defaults[0].flow_offloading','0');set_('firewall.@defaults[0].flow_offloading_hw','0')
    # Explicit Direct mark allows LAN while a VPN-labelled network stays closed
    # even if the standalone guard is missing at boot.
    lan=c['lan_bridge'];wifi=c['wifi_bridge'];mark=23499
    Path('/etc/nftables.d/30-photonicat-ports.nft').write_text(f'''
chain pcat_lan_fallback {{
 type filter hook forward priority -9; policy accept;
 iifname "{lan}" meta mark {mark} oifname != {{ "pcawg0", "pcmh0" }} accept
 iifname {{ "{lan}", "{wifi}" }} oifname {{ "pcawg0", "pcmh0" }} accept
 iifname {{ "{lan}", "{wifi}" }} counter drop
}}
chain pcat_dns_fallback {{
 type filter hook input priority -9; policy accept;
 iifname {{ "{lan}", "{wifi}" }} meta l4proto {{ tcp, udp }} th dport 53 counter drop
}}
''')
    run('fw4','check')
    for package in ('network','dhcp','firewall'):run('uci','commit',package)
    run('ubus','call','network','reload')
    run('/etc/init.d/firewall','reload')
    run('/etc/init.d/dnsmasq','reload');run('/etc/init.d/odhcpd','reload')
