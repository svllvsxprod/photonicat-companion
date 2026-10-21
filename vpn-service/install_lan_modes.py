"""Enable explicit LAN Direct mode; existing VPN policy remains the default."""
from pathlib import Path
import manager as m, ports

def install():
 c=ports.config()
 if c.get('lan_mode_ready'):return
 if m.run('uci','changes').stdout.strip():raise RuntimeError('Pending UCI changes')
 fallback=Path('/etc/nftables.d/30-photonicat-ports.nft')
 old=fallback.read_text();firewall=Path('/etc/config/firewall');old_firewall=firewall.read_bytes()
 try:
  # Only the independent guard can set this mark for an explicitly Direct LAN.
  rule=f' iifname "{ports.checked_device(c["lan_bridge"])}" meta mark {m.SOCKET_MARK} oifname != {{ "pcawg0", "pcmh0" }} accept\n'
  fallback.write_text(old.replace(' type filter hook forward priority -9; policy accept;\n',' type filter hook forward priority -9; policy accept;\n'+rule))
  m.run('uci','set','firewall.pc_lan_direct=forwarding');m.run('uci','set','firewall.pc_lan_direct.src=lan');m.run('uci','set','firewall.pc_lan_direct.dest=wan')
  m.run('fw4','check');m.run('uci','commit','firewall');m.run('/etc/init.d/firewall','reload')
  m.atomic(ports.CONFIG,{**c,'lan_mode':c.get('lan_mode','vpn'),'lan_mode_ready':True})
  ports.sync_guard()
 except Exception:
  fallback.write_text(old);firewall.write_bytes(old_firewall)
  m.run('uci','revert','firewall',check=False);m.run('/etc/init.d/firewall','reload',check=False)
  m.atomic(ports.CONFIG,c);ports.sync_guard();raise
if __name__=='__main__':install()
