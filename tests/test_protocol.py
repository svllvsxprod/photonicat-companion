import asyncio
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'router'),str(ROOT/'router/vendor')]
from companion import Engine
from crypto import Crypto

class Sink:
    notifying=True
    value=b''
    def __init__(self): self.chunks=[]
    def emit_properties_changed(self, data): self.chunks.append(data['Value'])
    def pop(self, crypto):
        payload=b''.join(chunk[1:] for chunk in self.chunks).strip()
        self.chunks=[]
        return crypto.open(payload)

class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_sequence_and_session(self):
        crypto=Crypto(bytes(range(32)));sink=Sink();engine=Engine(crypto,sink)
        engine.cached={'battery':43}
        # handle() normally invoked through receive, which increments pending.
        async def send(data):
            engine.pending+=1
            await engine.handle('/phone',crypto.seal(data))
        await send({'seq':1,'op':'hello','challenge':'a'*32})
        hello=sink.pop(crypto);self.assertEqual(hello['challenge'],'a'*32)
        query={'seq':2,'op':'status','sid':hello['sid']}
        await send(query);self.assertEqual(sink.pop(crypto)['status']['battery'],43)
        await send(query);self.assertEqual(sink.chunks,[])
        await send({'seq':3,'op':'status','sid':'wrong'});self.assertEqual(sink.chunks,[])
        await send({'seq':3,'op':'reboot','sid':hello['sid']})
        self.assertFalse(sink.pop(crypto)['ok'])
    async def test_unauthenticated_key_is_rejected(self):
        sink=Sink();engine=Engine(Crypto(bytes(range(32))),sink);engine.pending=1
        wrong=Crypto(bytes([42])*32).seal({'seq':1,'op':'hello','challenge':'a'*32})
        await engine.handle('/phone',wrong)
        self.assertEqual(sink.chunks,[]);self.assertEqual(engine.sessions,{})

if __name__=='__main__':unittest.main()
