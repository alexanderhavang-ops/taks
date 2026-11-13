"""Async XMPP and Mumble clients, sharing SimKeeper's single event loop.

Mumble control wire fields follow mumble-voip/mumble src/Mumble.proto.
Voice uses the legacy Opus TCP-tunnel format advertised as version 1.4.
"""
import asyncio
import ctypes
import ctypes.util
import hashlib
from pathlib import Path
import random
import ssl
import struct
import time
import uuid
import wave


def varint(n):
    out=bytearray()
    while n>127: out.append((n&127)|128);n>>=7
    return bytes(out)+bytes([n])


def proto(**fields):
    out=b''
    for key,value in fields.items():
        num=int(key[1:])
        if isinstance(value,int):out+=varint(num<<3)+varint(value)
        else:
            value=value.encode() if isinstance(value,str) else value
            out+=varint((num<<3)|2)+varint(len(value))+value
    return out


def decode(data):
    def read(pos):
        n=0
        for shift in range(0,70,7):
            if pos>=len(data):raise ValueError('Truncated protobuf')
            b=data[pos];pos+=1;n|=(b&127)<<shift
            if b<128:return n,pos
        raise ValueError('Oversized protobuf varint')
    pos=0;out={}
    while pos<len(data):
        tag,pos=read(pos);num,kind=tag>>3,tag&7
        if not num:raise ValueError('Invalid protobuf field')
        if kind==0:value,pos=read(pos)
        elif kind in (1,2,5):
            if kind==2:size,pos=read(pos)
            else:size=8 if kind==1 else 4
            if size>len(data)-pos:raise ValueError('Truncated protobuf field')
            value=data[pos:pos+size];pos+=size
        else:raise ValueError('Unsupported protobuf wire type')
        out.setdefault(num,[]).append(value)
    return out


def mv(n):
    # Mumble voice varint differs from protobuf (network byte order).
    if n<0x80:return bytes([n])
    if n<0x4000:return bytes([(n>>8)|0x80,n&255])
    if n<0x200000:return bytes([(n>>16)|0xc0,(n>>8)&255,n&255])
    if n<0x10000000:return bytes([(n>>24)|0xe0,(n>>16)&255,(n>>8)&255,n&255])
    return b'\xf0'+struct.pack('!I',n)


def opus_clip(path):
    """Encode a bounded prepared PCM clip on demand; no per-actor codec process."""
    if path.stat().st_size>2_000_000:raise ValueError('Audio clip too large')
    with wave.open(str(path),'rb') as wav:
        if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())!=(1,2,48000):
            raise ValueError('Clip must be mono 16-bit PCM WAV at 48kHz')
        count=wav.getnframes()
        if not 960<=count<=48000*10:raise ValueError('Clip must be 20ms..10s')
        raw=wav.readframes(count)
    lib=ctypes.CDLL(ctypes.util.find_library('opus') or 'libopus.so.0')
    lib.opus_encoder_create.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.POINTER(ctypes.c_int)]
    lib.opus_encoder_create.restype=ctypes.c_void_p
    lib.opus_encode.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_int16),ctypes.c_int,ctypes.c_void_p,ctypes.c_int32]
    lib.opus_encoder_destroy.argtypes=[ctypes.c_void_p]
    error=ctypes.c_int();enc=lib.opus_encoder_create(48000,1,2048,ctypes.byref(error))
    if not enc or error.value:raise ValueError('Opus encoder unavailable')
    frames=[]
    try:
        for offset in range(0,len(raw),1920):
            pcm=(ctypes.c_int16*960).from_buffer_copy(raw[offset:offset+1920].ljust(1920,b'\0'))
            buf=ctypes.create_string_buffer(1275);size=lib.opus_encode(enc,pcm,960,buf,1275)
            if size<0:raise ValueError('Opus encoding failed')
            frames.append(buf.raw[:size])
    finally:lib.opus_encoder_destroy(enc)
    return frames


class Link:
    def __init__(self,daemon,entity,kind):
        self.daemon,self.entity,self.kind=daemon,entity,kind
        self.identity=daemon.config['identities'][entity['identity_slot']]
        self.info={'entity_id':entity['id'],'transport':kind,'connected':False,'reconnects':0,'last_error':None,'sent':0,'received':0}
        self.task=asyncio.create_task(self.run())
        self.writer=None;self.client=None;self.ptt_task=None
        self.write_lock=asyncio.Lock()
    async def receive(self,sender,body,channel,event_id=None):
        self.info['received']+=1
        # Each transport callback reflects only what this identity actually received.
        await asyncio.to_thread(self.daemon.perception.receive,event_id or self.kind+':'+uuid.uuid4().hex,
                                sender,[self.entity['uid']],body[:2000],self.kind+':'+channel)
    def cancel(self):
        self.task.cancel()
        if self.ptt_task:self.ptt_task.cancel()


class Xmpp(Link):
    def __init__(self,daemon,entity):super().__init__(daemon,entity,'xmpp')
    async def run(self):
        import slixmpp
        cfg=self.daemon.config['xmpp'];identity=self.identity
        delay=2
        while True:
            owner=self
            class Client(slixmpp.ClientXMPP):
                def __init__(self):
                    super().__init__(identity['username']+'@'+cfg['domain']+'/simkeeper',Path(identity['password_file']).read_text().strip())
                    self.register_plugin('xep_0045')
                    self.enable_direct_tls=True;self.enable_starttls=False;self.enable_plaintext=False
                    self.ssl_context=ssl.create_default_context()
                    if cfg.get('ca_file'):self.ssl_context.load_verify_locations(cfg['ca_file'])
                    self.ssl_context.load_cert_chain(identity['cert_file'],identity['key_file'])
                    self.add_event_handler('session_start',self.ready)
                    self.add_event_handler('message',self.message)
                    self.add_event_handler('failed_auth',self.failed)
                async def failed(self,_):
                    owner.info['last_error']='Authentication rejected';self.disconnect()
                async def ready(self,_):
                    self.send_presence()
                    owner.info.update(connected=True,last_error=None,rooms=[])
                    for room in identity.get('xmpp_rooms',[]):
                        try:
                            await self.plugin['xep_0045'].join_muc_wait(room,owner.entity['callsign'],maxstanzas=0,timeout=10)
                            owner.info['rooms'].append(room)
                        except Exception as exc:owner.info['last_error']='Room join: '+type(exc).__name__
                async def message(self,msg):
                    if msg['type'] not in ('chat','normal','groupchat') or not str(msg['body']):return
                    if msg.xml.find('{urn:xmpp:delay}delay') is not None:return
                    sender=str(msg['from']);bare=str(msg['from'].bare)
                    stanza=str(msg['id'])
                    event_id='xmpp:'+hashlib.sha256((sender+'\0'+stanza+'\0'+str(msg['body'])).encode()).hexdigest() if stanza else None
                    await owner.receive(sender,str(msg['body']),bare,event_id)
            client=None
            try:
                client=Client();self.client=client
                async with self.daemon.handshakes:
                    await asyncio.wait_for(client.connect(host=cfg.get('host','127.0.0.1'),port=cfg.get('port',5223)),15)
                await client.disconnected
            except asyncio.CancelledError:raise
            except Exception as exc:self.info['last_error']=type(exc).__name__
            finally:
                self.info['connected']=False;self.info['rooms']=[]
                if client:
                    client.disconnect(wait=0)
                    try:await asyncio.wait_for(asyncio.shield(client.disconnected),2)
                    except (Exception,asyncio.CancelledError):pass
                self.client=None
            self.info['reconnects']+=1
            await asyncio.sleep(delay+random.random());delay=min(60,delay*2)
    async def send_chat(self,target,message):
        if not self.client or not self.info['connected']:return False
        kind='groupchat' if target in self.identity.get('xmpp_rooms',[]) else 'chat'
        self.client.send_message(mto=target,mbody=message,mtype=kind)
        self.info['sent']+=1
        return True


class Mumble(Link):
    def __init__(self,daemon,entity):
        self.channels={};self.session=None;self.sequence=0
        super().__init__(daemon,entity,'mumble')
    async def send(self,kind,payload):
        async with self.write_lock:
            if not self.writer:return False
            self.writer.write(struct.pack('!HI',kind,len(payload))+payload)
            await asyncio.wait_for(self.writer.drain(),3)
            self.info['sent']+=1
            return True
    async def run(self):
        cfg=self.daemon.config['mumble'];delay=5
        context=ssl.create_default_context(cafile=cfg.get('ca_file'))
        context.load_cert_chain(self.identity['voice_cert_file'],self.identity['voice_key_file'])
        while True:
            reader=writer=None;ping=None
            try:
                # TAKS VX authentication requires the matching UID/callsign to be live on TAK.
                cot=self.daemon.sessions.get(self.entity['identity_slot'])
                if not cot or not cot.info['connected']:
                    await asyncio.sleep(2);continue
                await asyncio.sleep(3)
                async with self.daemon.handshakes:
                    reader,writer=await asyncio.wait_for(asyncio.open_connection(cfg.get('host','127.0.0.1'),cfg.get('port',64738),ssl=context,server_hostname=cfg['server_name'],limit=65536),15)
                self.writer=writer;self.channels={};self.session=None
                await self.send(0,proto(f1=0x010400,f2='TAKS SimKeeper',f3='Linux'))
                await self.send(2,proto(f1=self.entity['callsign']+'---'+self.entity['uid'],f5=1))
                async def keepalive():
                    while True:
                        await asyncio.sleep(10);await self.send(3,proto(f1=int(time.monotonic()*1000000)))
                ping=asyncio.create_task(keepalive())
                while True:
                    kind,size=struct.unpack('!HI',await asyncio.wait_for(reader.readexactly(6),30))
                    if size>262144:raise ValueError('Mumble frame too large')
                    payload=await reader.readexactly(size);self.info['received']+=1
                    if kind==1:
                        self.info['voice_packets_received']=self.info.get('voice_packets_received',0)+1;continue
                    fields=decode(payload)
                    def first(n,default=None):return fields.get(n,[default])[0]
                    if kind==4:raise ConnectionError('Mumble authentication rejected')
                    if kind==7 and first(1) is not None:
                        if first(3) is not None:self.channels[first(1)]=first(3).decode('utf8','replace')
                    elif kind==6:self.channels.pop(first(1),None)
                    elif kind==5:
                        self.session=first(1);self.info.update(connected=True,last_error=None,session=self.session)
                        await self.channel(self.entity.get('voice_channel') or self.identity['voice_channels'][0])
                    elif kind==9 and first(1)==self.session:
                        if first(5) is not None:self.info.update(channel_id=first(5),channel=self.channels.get(first(5)))
                    elif kind==8 and first(1)==self.session:raise ConnectionError('Mumble session removed')
                    elif kind==12:self.info['last_error']='Mumble permission denied'
                    elif kind==11:
                        await self.receive('mumble-session:'+str(first(1)),(first(5,b'')).decode('utf8','replace'),'text')
            except asyncio.CancelledError:raise
            except Exception as exc:self.info['last_error']=type(exc).__name__+(': '+str(exc) if isinstance(exc,ConnectionError) else '')
            finally:
                self.info['connected']=False;self.writer=None
                if ping:ping.cancel();await asyncio.gather(ping,return_exceptions=True)
                if writer:
                    writer.close()
                    try:await asyncio.wait_for(writer.wait_closed(),2)
                    except Exception:pass
            self.info['reconnects']+=1
            await asyncio.sleep(delay+random.random());delay=min(60,delay*2)
    async def channel(self,name):
        ids=[i for i,n in self.channels.items() if n==name]
        if len(ids)!=1 or not self.info['connected']:return False
        return await self.send(9,proto(f1=self.session,f5=ids[0]))
    async def ptt(self,frames):
        self.info['ptt']='transmitting'
        started=time.monotonic()
        try:
            for i,frame in enumerate(frames):
                if not self.info['connected']:raise ConnectionError('Voice disconnected')
                await asyncio.sleep(max(0,started+i*.02-time.monotonic()))
                # Opus type=4, normal target=0; sequence advances in 10ms units.
                await self.send(1,b'\x80'+mv(self.sequence)+mv(len(frame)|(0x2000 if i==len(frames)-1 else 0))+frame)
                self.sequence+=2
            self.info['ptt']='written_to_tls'
        except asyncio.CancelledError:
            self.info['ptt']='cancelled';raise
        except Exception:self.info['ptt']='failed_or_unknown'
