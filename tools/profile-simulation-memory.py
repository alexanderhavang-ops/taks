#!/usr/bin/env python3
"""Local footprint probe: one temporary relay process, one client process, no TAK changes."""
import argparse,asyncio,gc,json,os,ssl,subprocess,sys,tempfile,tracemalloc
from pathlib import Path


def memory(label, count=0):
    fields={}
    for line in Path('/proc/self/status').read_text().splitlines():
        key,_,v=line.partition(':')
        if key in ('VmRSS','RssAnon','RssFile','VmSwap'):fields[key+'_kib']=int(v.split()[0])
    current,peak=tracemalloc.get_traced_memory()
    print(json.dumps({'phase':label,'clients':count,'python_traced_kib':round(current/1024,1),
        'python_peak_kib':round(peak/1024,1),**fields}),flush=True)


async def relay(root):
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(root/'cert.pem',root/'key.pem')
    ctx.load_verify_locations(root/'cert.pem');ctx.verify_mode=ssl.CERT_REQUIRED
    async def peer(reader,writer):
        try:
            while await reader.read(16384):pass
        finally:writer.close()
    server=await asyncio.start_server(peer,'127.0.0.1',0,ssl=ctx)
    print(server.sockets[0].getsockname()[1],flush=True)
    async with server:await server.serve_forever()


async def clients(root,port,count):
    import asyncio.sslproto
    from takctl.simulation.orbat import build_hv_staging
    tracemalloc.start();memory('baseline')
    state=build_hv_staging({n:{'position':{'lat':55.,'lon':13.},'label':'synthetic'} for n in ('VQ','RQ','SQ','TQ')})
    memory('520_person_world',520)
    del state;gc.collect();memory('world_freed')
    contexts=[]
    for _ in range(count):
        ctx=ssl.create_default_context(cafile=str(root/'cert.pem'));ctx.load_cert_chain(root/'cert.pem',root/'key.pem');ctx.check_hostname=False;contexts.append(ctx)
    memory('distinct_ssl_contexts',count)
    sockets=[]
    for ctx in contexts:sockets.append(await asyncio.open_connection('127.0.0.1',port,ssl=ctx,server_hostname='localhost',limit=65536))
    memory('idle_mtls_connections',count)
    print(json.dumps({'python':sys.version.split()[0],'openssl':ssl.OPENSSL_VERSION,
        'asyncio_tls_receive_buffer_bytes':asyncio.sslproto.SSLProtocol.max_size,
        'fixture':'same disposable RSA certificate, distinct SSL contexts; relay memory excluded; idle, no fanout'}),flush=True)
    for _,writer in sockets:writer.close()
    await asyncio.gather(*(w.wait_closed() for _,w in sockets),return_exceptions=True)
    sockets.clear();contexts.clear();gc.collect();memory('connections_closed')


def main():
    p=argparse.ArgumentParser();p.add_argument('--relay');p.add_argument('--count',type=int,default=64);args=p.parse_args()
    if args.relay:return asyncio.run(relay(Path(args.relay)))
    if not 1<=args.count<=128:raise ValueError('count1..128')
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost',
            '-addext','subjectAltName=DNS:localhost','-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        child=subprocess.Popen([sys.executable,__file__,'--relay',str(root)],stdout=subprocess.PIPE,text=True)
        try:asyncio.run(clients(root,int(child.stdout.readline()),args.count))
        finally:child.terminate();child.wait(timeout=10)

if __name__=='__main__':main()
