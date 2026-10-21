import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'router'))
import vpn_control as v
class VpnControlTests(unittest.TestCase):
 def setUp(self):
  self.snapshot={'available':True,'revision':'current','amneziawg':{'profiles':[{'id':'awg1'}]},'mihomo':{'nodes':['Node']}}
 def test_stale_request_never_executes(self):
  with patch.object(v,'snapshot',return_value=self.snapshot),patch.object(v,'call') as call:
   with self.assertRaises(v.VpnError):v.execute({'action':'engine','value':'mihomo','revision':'old'},lambda v:'current')
   call.assert_not_called()
 def test_arbitrary_command_and_unknown_fields_rejected(self):
  for args in [{'action':'shell','value':'reboot','revision':'current'},{'action':'engine','value':'mihomo','revision':'current','path':'/etc/passwd'}]:
   with self.assertRaises(v.VpnError):v.execute(args,lambda v:'current')
 def test_unknown_node_rejected(self):
  with patch.object(v,'snapshot',return_value=self.snapshot),patch.object(v,'call') as call:
   with self.assertRaises(v.VpnError):v.execute({'action':'node','value':'unknown','revision':'current'},lambda v:'current')
   call.assert_not_called()
 def test_known_node_uses_fixed_action(self):
  with patch.object(v,'snapshot',return_value=self.snapshot),patch.object(v,'call') as call:
   v.execute({'action':'node','value':'Node','revision':'current'},lambda v:'current')
   call.assert_called_once_with('select-node','Node')
 def test_ports_accept_explicit_lan_mode_and_boolean_pause(self):
  with patch.object(v,'snapshot',return_value=self.snapshot),patch.object(v,'call') as call:
   v.execute({'action':'ports','setting':'lan_enabled','value':False,'revision':'current'},lambda v:'current')
   call.assert_called_once_with('ports-set',payload={'setting':'lan_enabled','value':False})
   call.reset_mock()
   v.execute({'action':'ports','setting':'lan_mode','value':'direct','revision':'current'},lambda v:'current')
   call.assert_called_once_with('ports-set',payload={'setting':'lan_mode','value':'direct'})
   for key,value in [('lan_enabled','direct'),('wan_mode','shell'),('lan_mode','shell')]:
    with self.assertRaises(v.VpnError):
     v.execute({'action':'ports','setting':key,'value':value,'revision':'current'},lambda v:'current')
if __name__=='__main__':unittest.main()
