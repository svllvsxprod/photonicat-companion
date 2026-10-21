import sys,unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'router'))
from control import Controls,ControlError
class FanTests(unittest.TestCase):
 def setUp(self):
  self.c=Controls();self.data={'mode':'smart_quiet','level':7};self.writes=[]
 def api(self,path,payload=None,port=80):
  key='mode' if 'fan_mode' in path else 'level'
  if payload is not None:
   self.writes.append(payload);self.data[key]=next(iter(payload.values()))
  return {'fan_mode':self.data['mode']} if key=='mode' else {'fan_speed':self.data['level']}
 def test_level_preserves_mode_and_accepts_zero(self):
  with tempfile.TemporaryDirectory() as d, patch('control.Path',return_value=Path(d)),patch('control.api',side_effect=self.api),patch('control.stock_write',side_effect=self.api):
   self.c.execute('fan_set',{'revision':self.c.revision(self.data),'level':0})
   self.assertEqual(self.data,{'mode':'smart_quiet','level':0})
   self.assertEqual(self.writes,[{'fan_speed':0}])
   self.assertEqual(json.loads((Path(d)/'fan.before.json').read_text())['level'],7)
 def test_stale_or_out_of_range_cannot_write(self):
  with patch('control.api',side_effect=self.api),patch('control.stock_write',side_effect=self.api):
   for change in ({'level':True},{'level':10},{'mode':'off'},{'level':3,'mode':'manual'}):
    with self.assertRaises(ControlError):self.c.execute('fan_set',{'revision':self.c.revision(self.data),**change})
   with self.assertRaises(ControlError):self.c.execute('fan_set',{'revision':'old','level':2})
   self.assertEqual(self.writes,[])
