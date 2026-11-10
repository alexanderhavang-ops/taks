#!/usr/bin/env python3
"""Exercise the generated TAKS authenticator on a real isolated Murmur/Ice server.

Run with a Python that has the distribution's Ice bindings, plus openssl and
mumble-server. All credentials are synthetic, all sockets bind loopback, and
both child processes and fixture files are cleaned up on exit.
"""
from __future__ import annotations
import argparse
import ast
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--server',type=Path,required=True)
parser.add_argument('--slice',type=Path,default=Path('/usr/share/mumble-server/MumbleServer.ice'))
parser.add_argument('--ice-include',type=Path,default=Path('/usr/share/ice/slice'))
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'takctl'))
from takctl.onboarding import watch_voice as voice


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def integer(value):
    out=bytearray()
    while value>=128:out.append((value&127)|128);value>>=7
    out.append(value);return bytes(out)


def text(field,value):
    raw=value.encode();return integer(field*8+2)+integer(len(raw))+raw


def read(sock,count):
    out=bytearray()
    while len(out)<count:
        part=sock.recv(count-len(out))
        if not part:raise RuntimeError('Unexpected EOF')
        out.extend(part)
    return bytes(out)


def login(port,ca,name,password):
    context=ssl.create_default_context(cafile=str(ca))
    with socket.create_connection(('127.0.0.1',port),5) as tcp, context.wrap_socket(tcp,server_hostname='localhost') as tls:
        def send(kind,body):tls.sendall(struct.pack('!HI',kind,len(body))+body)
        send(0,integer(8)+integer(0x10300)+text(2,'TAKS watch regression'))
        send(2,text(1,name)+text(2,password)+integer(40)+integer(1))
        for _ in range(128):
            kind,length=struct.unpack('!HI',read(tls,6))
            if length>1024*1024:raise RuntimeError('Oversized Mumble packet')
            read(tls,length)
            if kind==4:return False
            if kind==5:return True
        raise RuntimeError('No authentication result')


with tempfile.TemporaryDirectory(prefix='taks-watch-interop-') as temporary:
    work=Path(temporary);port=free_port();ice_port=free_port();children=[]
    voice.DB_PATH=work/'watch/credentials.sqlite'
    ticket=voice.issue('synthetic-card','test-operator')
    profile=voice.redeem(ticket,lambda _: {'_username':'test-operator','_display':'Test operator'})
    source=ast.parse((root/'tak-installer/tak_installer/actions/mumble_server_core.py').read_text())
    script=next(ast.literal_eval(node.value) for node in source.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='AUTH_SCRIPT' for target in node.targets))
    for before,after in {
        '/etc/mumble/MumbleServer.ice':str(args.slice.resolve()),'/usr/share/ice/slice':str(args.ice_include.resolve()),
        '/etc/taks/mumble-ice-secret':str(work/'ice-secret'),
        '/opt/tak/tools/takctl/state/voice_pin_auth/users.json':str(work/'voice-state.json'),
        '/var/log/taks-mumble-voice-pin-auth.log':str(work/'auth.log'),
        '-p 6502':f'-p {ice_port}',
    }.items():script=script.replace(before,after)
    script=script.replace('class VoicePinAuthenticator',f'sys.path.insert(0, {str(root / "takctl")!r})\nfrom takctl.onboarding import watch_voice\nwatch_voice.DB_PATH = Path({str(voice.DB_PATH)!r})\n\nclass VoicePinAuthenticator',1)
    (work/'auth.py').write_text(script);(work/'ice-secret').write_text('synthetic-ice-secret')
    config=work/'mumble.ini'
    config.write_text(f'database={work / "mumble.sqlite"}\nhost=127.0.0.1\nport={port}\nbonjour=false\ncertrequired=false\nserverpassword=\n'
                      f'ice="tcp -h 127.0.0.1 -p {ice_port}"\nicesecretread=synthetic-ice-secret\nicesecretwrite=synthetic-ice-secret\n'
                      f'sslCert={work / "server.pem"}\nsslKey={work / "server.key"}\n')
    with (work/'setup.log').open('w') as log:
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost',
                        '-addext','subjectAltName=DNS:localhost','-keyout',str(work/'server.key'),'-out',str(work/'server.pem')],check=True,stdout=log,stderr=log)
        try:
            children.append(subprocess.Popen([str(args.server.resolve()),'-fg','-ini',str(config)],stdout=log,stderr=log))
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1',port),.2):break
                except OSError:time.sleep(.05)
            else:raise RuntimeError('Mumble did not start')
            children.append(subprocess.Popen([sys.executable,str(work/'auth.py')],stdout=log,stderr=log))
            for _ in range(100):
                if (work/'auth.log').exists() and 'READY' in (work/'auth.log').read_text():break
                if children[-1].poll() is not None:raise RuntimeError((work/'setup.log').read_text())
                time.sleep(.05)
            else:raise RuntimeError('Authenticator did not become ready')
            assert login(port,work/'server.pem',profile['username'],profile['password']), 'Valid watch credential rejected'
            assert not login(port,work/'server.pem',profile['username'],'wrong'), 'Wrong password accepted'
            assert not login(port,work/'server.pem','TW.not-valid',profile['password']), 'Malformed watch name accepted'
            voice.revoke('test-operator')
            assert not login(port,work/'server.pem',profile['username'],profile['password']), 'Revoked credential accepted'
            ticket=voice.issue('synthetic-card','expired-operator',now=100)
            expired=voice.redeem(ticket,lambda _: {'_username':'expired-operator'},now=101)
            assert not login(port,work/'server.pem',expired['username'],expired['password']), 'Expired credential accepted'
            print('PASS: real Murmur + generated TAKS Ice authenticator: valid watch login; wrong password, malformed identity, revoked and expired credentials rejected.')
        finally:
            for child in reversed(children):
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait()
