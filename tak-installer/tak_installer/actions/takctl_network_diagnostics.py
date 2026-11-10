"""Install a socket-activated non-root packet broker, with NET_RAW only and no sudo."""
from pathlib import Path
import shutil
import subprocess

SOCKET='''[Unit]
Description=TAKS bounded packet diagnostics socket
[Socket]
ListenStream=/run/taks-network-capture.sock
SocketUser=root
SocketGroup=tak
SocketMode=0660
RemoveOnStop=yes
[Install]
WantedBy=sockets.target
'''
SERVICE='''[Unit]
Description=TAKS bounded packet metadata broker
Requires=taks-network-capture.socket
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/python3 -I /usr/local/libexec/taks-network-capture
DynamicUser=yes
User=taks-capture
AmbientCapabilities=CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_RAW
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictNamespaces=yes
RestrictAddressFamilies=AF_UNIX AF_PACKET AF_INET AF_INET6 AF_NETLINK
LockPersonality=yes
UMask=0077
LimitCORE=0
StandardOutput=null
StandardError=journal
'''
class _Action:
    ID='takctl-network-diagnostics'
    def inspect(self,ctx):return 0
    def apply(self,ctx):
        helper=Path('/usr/local/libexec/taks-network-capture');helper.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(Path(ctx.repo_root)/'takctl/bin/taks-network-capture',helper)
        helper.chmod(0o755);shutil.chown(helper,'root','root')
        for filename,text in [('taks-network-capture.socket',SOCKET),('taks-network-capture.service',SERVICE)]:
            target=Path('/etc/systemd/system')/filename;target.write_text(text);target.chmod(0o644);shutil.chown(target,'root','root')
        subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','enable','--now','taks-network-capture.socket'],check=True)
        return 0
ACTION=_Action()
