#!/usr/bin/env python3
"""Add an unused protected Wi-Fi bridge; existing AP assignments are preserved."""
import ipaddress,json,subprocess,time
from pathlib import Path
import manager as m
import ports

def set_(key,value):m.run('uci','set',f'{key}={value}')
def add(key,value):m.run('uci','add_list',f'{key}={value}')
def install():
 c=ports.config()
 if c.get('wifi_ready'):raise RuntimeError('Wi-Fi VPN already installed')
 if subprocess.check_output(['uci','changes']).strip():raise RuntimeError('Pending UCI changes')
 used=[]
 for interface in json.loads(subprocess.check_output(['ip','-j','-4','addr'])):
  for a in interface.get('addr_info',[]):used.append(ipaddress.ip_network(f"{a['local']}/{a['prefixlen']}",strict=False))
 address=next((f'172.16.{n}.1' for n in range(48,241,16) if not any(ipaddress.ip_network(f'172.16.{n}.0/24').overlaps(x) for x in used)),None)
 if address is None:raise RuntimeError('No free Wi-Fi subnet')
 paths=[Path('/etc/config')/x for x in ('network','dhcp','firewall')]+[ports.CONFIG,Path('/etc/nftables.d/30-photonicat-ports.nft')]
 backups={p:p.read_bytes() for p in paths}
 try:
  # Install privacy rules before any AP can be moved to this bridge.
  m.atomic(ports.CONFIG,{**c,'wifi_bridge':'br-pcwifi','wifi_address':address,'wifi_ready':False})
  ports.sync_guard()
  fallback=Path('/etc/nftables.d/30-photonicat-ports.nft')
  fallback.write_text(backups[fallback].decode().replace('iifname "'+c['lan_bridge']+'"', 'iifname { "'+c['lan_bridge']+'", "br-pcwifi" }'))
  set_('network.pcwifi_dev','device');set_('network.pcwifi_dev.name','br-pcwifi')
  set_('network.pcwifi_dev.type','bridge');set_('network.pcwifi_dev.bridge_empty','1')
  set_('network.pcwifi','interface')
  for k,v in dict(proto='static',device='br-pcwifi',ipaddr=address,netmask='255.255.255.0',ip6assign='64',ip6hint='30',disabled='0').items():set_('network.pcwifi.'+k,v)
  add('network.pcwifi.ip6class','local')
  set_('dhcp.pcwifi','dhcp')
  for k,v in dict(interface='pcwifi',start='100',limit='100',leasetime='12h',dhcpv4='server',dhcpv6='server',ra='server',ra_slaac='1',ra_default='2').items():set_('dhcp.pcwifi.'+k,v)
  add('dhcp.pcwifi.dhcp_option','6,1.1.1.1');add('dhcp.pcwifi.dns','2606:4700:4700::1111')
  set_('firewall.pcwifi','zone')
  for k,v in dict(name='pcwifi',input='ACCEPT',output='ACCEPT',forward='REJECT').items():set_('firewall.pcwifi.'+k,v)
  add('firewall.pcwifi.network','pcwifi')
  set_('firewall.pc_wifi_vpn','forwarding');set_('firewall.pc_wifi_vpn.src','pcwifi');set_('firewall.pc_wifi_vpn.dest','pcvpn')
  m.run('fw4','check')
  for package in ('network','dhcp','firewall'):m.run('uci','commit',package)
  m.run('ubus','call','network','reload')
  for _ in range(40):
   status=ports.interface_status('pcwifi')
   if status.get('up') and any(a.get('address')==address for a in status.get('ipv4-address',[])):break
   time.sleep(.5)
  else:raise RuntimeError('Protected Wi-Fi bridge did not start')
  m.run('/etc/init.d/firewall','reload');m.run('/etc/init.d/dnsmasq','reload');m.run('/etc/init.d/odhcpd','reload')
  m.atomic(ports.CONFIG,{**ports.config(),'wifi_ready':True})
 except Exception:
  for p,b in backups.items():p.write_bytes(b)
  for package in ('network','dhcp','firewall'):m.run('uci','revert',package,check=False)
  ports.sync_guard();m.run('ubus','call','network','reload');m.run('/etc/init.d/firewall','reload');m.run('/etc/init.d/dnsmasq','reload')
  raise
 print(json.dumps({'wifi_address':address,'ready':True}))
if __name__=='__main__':install()
