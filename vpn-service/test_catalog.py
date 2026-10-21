import base64,json,sys,unittest,zlib,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import catalog,manager
KEY=base64.b64encode(bytes(range(32))).decode()
CONF=f'[Interface]\nPrivateKey = {KEY}\nAddress = 10.1.0.2/32\nJc = 4\n[Peer]\nPublicKey = {KEY}\nEndpoint = 127.0.0.1:51234\nAllowedIPs = 0.0.0.0/0\n'
class CatalogTests(unittest.TestCase):
 def test_native_qr(self):self.assertEqual(catalog.decode_awg(CONF)[1],['10.1.0.2/32'])
 def test_amnezia_vpn_compressed_qr(self):
  text=json.dumps({'containers':[{'awg':{'last_config':json.dumps({'config':CONF})}}]}).encode()
  qr='vpn://'+base64.urlsafe_b64encode(len(text).to_bytes(4,'big')+zlib.compress(text)).decode().rstrip('=')
  self.assertEqual(catalog.decode_awg(qr)[0],CONF)
 def test_reject_qr_zip_bomb(self):
  value=b'a'*70000;qr='vpn://'+base64.urlsafe_b64encode((1).to_bytes(4,'big')+zlib.compress(value)).decode()
  with self.assertRaises(catalog.CatalogError):catalog.decode_awg(qr)
 def test_reject_remote_install_credentials(self):
  with self.assertRaises(catalog.CatalogError):catalog.decode_awg(json.dumps({'hostName':'example.org','password':'x'}))
 def test_reject_commands(self):
  with self.assertRaises(catalog.CatalogError):catalog.decode_awg(CONF.replace('Jc = 4','PostUp = bad'))
 def test_reject_local_subscription(self):
  with self.assertRaises(catalog.CatalogError):catalog.public_url('https://127.0.0.1/secret')
 def test_import_does_not_select_and_delete_active_is_blocked(self):
  with tempfile.TemporaryDirectory() as d, patch.object(manager,'ROOT',Path(d)):
   (Path(d)/'profiles').mkdir();manager.atomic(Path(d)/'profiles.json',[])
   manager.atomic(Path(d)/'state.json',{'amneziawg':'existing'})
   catalog.execute('import-awg',{'label':'Test','text':CONF})
   p=manager.manifest()[0];self.assertEqual(manager.state()['amneziawg'],'existing')
   self.assertEqual((Path(d)/'profiles'/(p['id']+'.conf')).stat().st_mode&0o777,0o600)
   manager.atomic(Path(d)/'state.json',{'amneziawg':p['id']})
   with self.assertRaises(catalog.CatalogError):catalog.execute('delete-awg',{'id':p['id']})
   self.assertEqual(len(manager.manifest()),1)
if __name__=='__main__':unittest.main()
