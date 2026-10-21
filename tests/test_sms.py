import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'router'))
import sms_control as sms
from control import ControlError

class SmsTests(unittest.TestCase):
 def test_inbox_pagination_excludes_sent_and_detail_preserves_unicode(self):
  rows=[{'id':i,'direction':0,'content':'Привет 🐈 '*200,'sender':'Оператор','timestamp':'2026-10-20'} for i in range(25)]
  rows += [{'id':99,'direction':1,'content':'sent'}]
  with patch.object(sms,'api',return_value={'msg':rows}):
   page=sms.execute('sms_list',{})['sms']
   self.assertEqual([r['id'] for r in page['messages']],list(range(24,14,-1)))
   self.assertEqual(page['next'],15)
   self.assertNotIn('text',page['messages'][0])
   self.assertEqual(len(page['messages'][0]['preview']),140)
   second=sms.execute('sms_list',{'before':15})['sms']
   self.assertEqual(second['messages'][0]['id'],14)
   self.assertEqual(sms.execute('sms_read',{'id':24})['sms_message']['text'],rows[24]['content'])
   with self.assertRaises(ControlError):sms.execute('sms_read',{'id':99})
 def test_invalid_requests_never_call_modem(self):
  with patch.object(sms,'api') as api:
   for op,args in [('sms_delete',{'id':1}),('sms_list',{'before':True}),('sms_list',{'before':-1}),('sms_read',{'id':'1'}),('sms_read',{'id':1,'delete':True}),('sms_list',[])]:
    with self.assertRaises(ControlError):sms.execute(op,args)
   api.assert_not_called()
 def test_invalid_response_and_empty_inbox(self):
  with patch.object(sms,'api',return_value={}):
   with self.assertRaises(ControlError):sms.execute('sms_list',{})
  with patch.object(sms,'api',return_value={'msg':[]}):
   self.assertEqual(sms.execute('sms_list',{})['sms']['messages'],[])
