#!/usr/bin/env python3
"""Disposable, local-only asynchronous mTLS fan-out load probe.

One process includes both the fake TAK relay and the simulator. The result's
memory peak includes both sides. Every client has a distinct ECDSA key/cert.
This is not a production TAK Server capacity claim.
"""
import argparse
import asyncio
import json
from pathlib import Path
import resource
import ssl
import subprocess
import tempfile
import time

from takctl.simulation.daemon import Daemon
from takctl.simulation.orbat import build_hv_staging


def openssl(*args):
    subprocess.run(["openssl",*args],check=True,stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)


async def probe(root, identities, duration):
    soft,hard=resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE,(min(max(soft,4096),hard),hard))
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(root/"ca.pem",root/"ca.key")
    ctx.load_verify_locations(cafile=str(root/"ca.pem"));ctx.verify_mode=ssl.CERT_REQUIRED
    peers,tasks,names=set(),set(),set()
    pending=asyncio.Queue(maxsize=4096)

    async def relay():
        while True:
            batch=[await pending.get()]
            for _ in range(7):
                try:batch.append(pending.get_nowait())
                except asyncio.QueueEmpty:break
            data=b"".join(batch)
            writers=list(peers)
            for writer in writers:writer.write(data)
            if writers:await asyncio.gather(*(w.drain() for w in writers),return_exceptions=True)

    async def peer(reader,writer):
        task=asyncio.current_task();tasks.add(task);peers.add(writer)
        cert=writer.get_extra_info("peercert")
        names.update(value for row in cert.get("subject",()) for key,value in row if key=="commonName")
        try:
            while data:=await reader.read(16384):await pending.put(data)
        finally:
            peers.discard(writer);tasks.discard(task);writer.close()

    server=await asyncio.start_server(peer,"127.0.0.1",0,ssl=ctx,backlog=1024)
    port=server.sockets[0].getsockname()[1]
    anchors={k:{"position":{"lat":55.71,"lon":13.21},"label":"synthetic load fixture"} for k in ("VQ","RQ","SQ","TQ")}
    state=build_hv_staging(anchors,active=True)
    statefile=root/"state.json";statefile.write_text(json.dumps(state))
    daemon=Daemon({"host":"127.0.0.1","port":port,"server_name":"localhost","ca_file":str(root/"ca.pem"),
                   "identities":identities,"state_file":str(statefile),"tick_seconds":10})
    daemon.reconcile();fanout=asyncio.create_task(relay());ticker=asyncio.create_task(daemon.tick())
    start=time.monotonic();connected_at=None
    try:
        while time.monotonic()-start < 90:
            connected=sum(s.info["connected"] for s in daemon.sessions.values())
            if connected==len(identities):
                if connected_at is None:connected_at=time.monotonic()
                if time.monotonic()-connected_at>=duration and len(daemon.observed)==605:break
            await asyncio.sleep(.2)
        sessions=[s.info for s in daemon.sessions.values()]
        result={"ok":len(names)==520 and all(s["connected"] for s in sessions) and len(daemon.observed)==605,
                "scope":"one process, fake relay plus daemon; distinct disposable ECDSA keys/certificates",
                "tls_clients":len(sessions),"connected":sum(s["connected"] for s in sessions),"unique_peer_cert_subjects":len(names),
                "observed_objects":len(daemon.observed),"reconnects":sum(s["reconnects"] for s in sessions),
                "receive_frames":daemon.frame_counts,"wall_s":round(time.monotonic()-start,2),
                "combined_peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        print(json.dumps(result),flush=True)
        if not result["ok"]:raise RuntimeError("TLS fan-out probe failed")
    finally:
        ticker.cancel();fanout.cancel()
        for s in daemon.sessions.values():s.task.cancel()
        await asyncio.gather(ticker,fanout,*(s.task for s in daemon.sessions.values()),return_exceptions=True)
        server.close();await server.wait_closed()
        for writer in list(peers):writer.close()
        for task in list(tasks):task.cancel()
        await asyncio.gather(*list(tasks),return_exceptions=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--seconds",type=int,default=20)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="taks-tls-probe-") as tmp:
        root=Path(tmp)
        openssl("req","-x509","-newkey","ec","-pkeyopt","ec_paramgen_curve:P-256","-nodes","-days","1",
                "-keyout",str(root/"ca.key"),"-out",str(root/"ca.pem"),"-subj","/CN=TAKS-disposable-load-CA",
                "-addext","subjectAltName=DNS:localhost")
        identities=[]
        for i in range(520):
            key,csr,cert=(root/f"client-{i}.{ext}" for ext in ("key","csr","pem"))
            openssl("req","-new","-newkey","ec","-pkeyopt","ec_paramgen_curve:P-256","-nodes",
                    "-keyout",str(key),"-out",str(csr),"-subj",f"/CN=SIM-LOAD-{i:04d}")
            openssl("x509","-req","-in",str(csr),"-CA",str(root/"ca.pem"),"-CAkey",str(root/"ca.key"),
                    "-set_serial",str(i+1),"-days","1","-out",str(cert))
            identities.append({"cert_file":str(cert),"key_file":str(key)})
            if (i+1)%128==0:print(json.dumps({"fixture_certificates":i+1}),flush=True)
        asyncio.run(probe(root,identities,args.seconds))


if __name__=="__main__":main()
