import asyncio
import struct
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
from takctl.simulation.transports import proto, decode, mv, Mumble


class WireTest(unittest.TestCase):
    def test_wire_fields_unknown_fields_and_bounds(self):
        self.assertEqual(decode(proto(f1=300,f2='SIM-ONE',f21=7)),{1:[300],2:[b'SIM-ONE'],21:[7]})
        for data in (b'\x80',b'\x12\x03ab',b'\0'):
            with self.assertRaises(ValueError):decode(data)
        self.assertEqual(mv(127),b'\x7f');self.assertEqual(mv(128),b'\x80\x80')
        self.assertEqual(mv(0x2003),b'\xa0\x03')


class MumbleSocketTest(unittest.IsolatedAsyncioTestCase):
    async def test_auth_sync_channel_and_audio_tunnel_on_one_loop(self):
        authenticated=asyncio.Event();audio=asyncio.Event();received=[];handlers=[]
        async def server(reader,writer):
            handlers.append(asyncio.current_task())
            try:
                async def read():
                    kind,size=struct.unpack('!HI',await reader.readexactly(6));return kind,await reader.readexactly(size)
                kind,version=await read();self.assertEqual(kind,0)
                kind,auth=await read();self.assertEqual(kind,2)
                self.assertEqual(decode(auth)[1],[b'SIM-ONE---sim:one']);authenticated.set()
                for kind,body in ((7,proto(f1=1,f3='Exercise')),(5,proto(f1=99))):writer.write(struct.pack('!HI',kind,len(body))+body)
                await writer.drain()
                while True:
                    kind,body=await read();received.append((kind,body))
                    if kind==9:writer.write(struct.pack('!HI',9,len(body))+body);await writer.drain()
                    if kind==1:audio.set()
            except asyncio.IncompleteReadError:pass
            finally:writer.close();await writer.wait_closed()
        listener=await asyncio.start_server(server,'127.0.0.1',0)
        port=listener.sockets[0].getsockname()[1]
        identity={'voice_cert_file':'unused','voice_key_file':'unused','voice_channels':['Exercise']}
        daemon=SimpleNamespace(config={'identities':[identity],'mumble':{'port':port,'server_name':'localhost'}},handshakes=asyncio.Semaphore(4),sessions={0:SimpleNamespace(info={'connected':True})})
        original=asyncio.open_connection
        async def connect(host,port,**kwargs):return await original(host,port)
        link=None
        try:
            with patch('takctl.simulation.transports.ssl.create_default_context',return_value=Mock()),patch('takctl.simulation.transports.asyncio.open_connection',connect):
                link=Mumble(daemon,{'id':'one','uid':'sim:one','callsign':'SIM-ONE','identity_slot':0})
                await asyncio.wait_for(authenticated.wait(),5)
                for _ in range(100):
                    if link.info.get('channel')=='Exercise':break
                    await asyncio.sleep(.01)
                self.assertTrue(link.info['connected']);self.assertEqual(link.info['channel'],'Exercise')
                await link.ptt([b'fake-opus'])
                await asyncio.wait_for(audio.wait(),1)
                self.assertEqual(received[-1],(1,b'\x80\0'+mv(0x2000|9)+b'fake-opus'))
        finally:
            if link:link.cancel();await asyncio.gather(link.task,return_exceptions=True)
            listener.close();await listener.wait_closed()
            await asyncio.gather(*handlers,return_exceptions=True)
