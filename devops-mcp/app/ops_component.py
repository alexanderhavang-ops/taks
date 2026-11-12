"""Bounded host operations for the TAKS MCP gateway."""
import base64, hashlib, os, re, subprocess, tempfile
SERVICES={"taks-orch.service","taks-devops-mcp.service","taks-tunnel.service","nginx.service"}
TARGET="/etc/nginx/sites-available/orch-master.conf"
def run(args, timeout=15):
    try:
        p=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,timeout=timeout)
        return {"ok":p.returncode==0,"exit_code":p.returncode,
                "stdout":p.stdout[:12000].decode(errors="replace"),
                "stderr":p.stderr[:4000].decode(errors="replace")}
    except (OSError,subprocess.TimeoutExpired) as e:
        return {"ok":False,"error":type(e).__name__}
def register_ops_tools(mcp):
    @mcp.tool()
    def host_disk_diagnostics()->dict:
        """Disk space and inode utilization."""
        return {"space":run(["/usr/bin/df","-h","-P"]),
                "inodes":run(["/usr/bin/df","-i","-P"])}
    @mcp.tool()
    def host_memory_diagnostics()->dict:
        """RAM and swap usage."""
        return run(["/usr/bin/free","-h"])
    @mcp.tool()
    def host_process_diagnostics(sort_by:str="cpu",limit:int=15)->dict:
        """Top processes by CPU or RAM, omitting command arguments."""
        if sort_by not in ("cpu","memory") or not 1<=limit<=30:
            return {"ok":False,"error":"Invalid sort or limit"}
        key="-%cpu" if sort_by=="cpu" else "-%mem"
        r=run(["/usr/bin/ps","-eo","pid,user,stat,comm,%cpu,%mem,rss","--sort="+key,"--no-headers"])
        r["stdout"]="\n".join(r["stdout"].splitlines()[:limit])
        return r
    @mcp.tool()
    def aws_identity_diagnostics()->dict:
        """AWS account and caller role; never credentials."""
        return run(["/usr/bin/aws","sts","get-caller-identity","--output","json"],12)
    @mcp.tool()
    def aws_ec2_diagnostics(region:str="eu-north-1")->dict:
        """List EC2 instance identifiers, state, type and private IP."""
        if not re.fullmatch(r"[a-z]{2}-[a-z]+-\d",region):
            return {"ok":False,"error":"Invalid region"}
        return run(["/usr/bin/aws","ec2","describe-instances","--region",region,
            "--query","Reservations[].Instances[].{Id:InstanceId,State:State.Name,Type:InstanceType,PrivateIP:PrivateIpAddress}",
            "--output","json"],20)
    @mcp.tool()
    def daemon_status(service:str)->dict:
        """Status of allowlisted daemons."""
        if service not in SERVICES:return {"ok":False,"error":"Service not allowed"}
        return run(["/usr/bin/systemctl","show",service,
            "--property=Id,ActiveState,SubState,Result,MainPID,NRestarts","--no-pager"])
    @mcp.tool()
    def daemon_restart(service:str,confirm_restart:bool=False)->dict:
        """Restart allowlisted daemon with explicit confirmation."""
        if service not in SERVICES:return {"ok":False,"error":"Service not allowed"}
        if not confirm_restart:return {"ok":False,"confirmation_required":True}
        return run(["/usr/bin/sudo","-n","/usr/bin/systemctl","restart",service],25)
    @mcp.tool()
    def nginx_config_check()->dict:
        """Validate current Nginx config without reload."""
        return run(["/usr/bin/sudo","-n","/usr/sbin/nginx","-t"],12)
    @mcp.tool()
    def nginx_config_replace(base64_data:str,sha256:str,confirm_replace:bool=False)->dict:
        """Replace fixed orchestrator site config, test, reload, rollback on failure."""
        if not confirm_replace:return {"ok":False,"confirmation_required":True,"target":TARGET}
        if len(base64_data)>175000:return {"ok":False,"error":"Config too large"}
        try:data=base64.b64decode(base64_data,validate=True)
        except (ValueError,base64.binascii.Error):return {"ok":False,"error":"Invalid base64"}
        if not data or len(data)>131072 or b"\0" in data or hashlib.sha256(data).hexdigest()!=sha256.lower():
            return {"ok":False,"error":"Invalid config or checksum"}
        fd,temp=tempfile.mkstemp(prefix="taks-nginx-",suffix=".conf")
        try:
            with os.fdopen(fd,"wb") as f:f.write(data)
            backup=run(["/usr/bin/sudo","-n","/usr/bin/cp","-p",TARGET,TARGET+".mcp-backup"])
            if not backup["ok"]:return backup
            install=run(["/usr/bin/sudo","-n","/usr/bin/install","-m","0644",temp,TARGET])
            if not install["ok"]:return install
            check=run(["/usr/bin/sudo","-n","/usr/sbin/nginx","-t"])
            if check["ok"]:
                reload=run(["/usr/bin/sudo","-n","/usr/bin/systemctl","reload","nginx.service"])
                if reload["ok"]:return {"ok":True,"sha256":sha256,"test":check}
            rollback=run(["/usr/bin/sudo","-n","/usr/bin/cp",TARGET+".mcp-backup",TARGET])
            return {"ok":False,"error":"Validation or reload failed; rollback attempted",
                    "test":check,"rollback":rollback}
        finally:os.unlink(temp)

    @mcp.tool()
    def certbot_artifact_status()->dict:
        """Inspect the TAKS bundle certificate without exposing its private key."""
        cert="/opt/tak-orch/state/artifacts/letsencrypt/aws.tak-hv-sandbox.se/fullchain.pem"
        return run(["/usr/bin/openssl","x509","-in",cert,"-noout","-dates","-subject"],10)

    @mcp.tool()
    def certbot_sync_artifact(confirm_sync:bool=False)->dict:
        """Synchronize Certbot wildcard via the fixed installer-managed privileged helper."""
        if not confirm_sync:
            return {"ok":False,"confirmation_required":True}
        return run(["/usr/bin/sudo","-n","/usr/local/sbin/taks-sync-wildcard-cert"],30)
