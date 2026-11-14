"""Durable, fail-closed idle evidence. Never stores message bodies or tool arguments."""
import json
from pathlib import Path
import sqlite3
import re
import threading
import time

IDLE_SECONDS=4*3600
FRESH_SECONDS=90
MONITOR_TOOLS={'runtime_status','api_surface','takctl_health','marti_diagnostics','product_health',
 'network_capture_start','onboarding_diagnostics','diagnostic_log','diagnostic_file_stat','network_capture_status',
 'taks_bundle_prepare_start','host_identity','host_resources','listening_ports','service_list','service_status','service_logs',
 'nginx_check','cert_status','file_stat','installer_tail','java_processes','takserver_logs',
 'takserver_readiness','netstat_listeners','lsof_tak_java','process_sample','memory_read','vmstat_sample'}


def monitoring(domain,name,args):
    if name in MONITOR_TOOLS:return True
    if name=='simulation_read':return args.get('view','status') in {'status','capabilities','provisioning'}
    if name=='service_read':return True
    return False


class ActivityStore:
    def __init__(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        self.db=sqlite3.connect(path,check_same_thread=False,timeout=10)
        path.chmod(0o600)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA busy_timeout=10000')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS nodes(node TEXT PRIMARY KEY,instance TEXT NOT NULL,tool_since REAL NOT NULL,
          cot_since REAL,last_tool REAL,last_cot REAL,last_ambiguous REAL,last_verified REAL,
          connected INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT 'Observer not connected',
          ignored_bot_frames INTEGER NOT NULL DEFAULT 0,observed_frames INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS channels(name TEXT PRIMARY KEY,epoch TEXT NOT NULL,since REAL NOT NULL,last REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY,at REAL,node TEXT,instance TEXT,kind TEXT,label TEXT);
        ''');self.db.commit()
        columns={r[1] for r in self.db.execute('PRAGMA table_info(nodes)')}
        for name,kind in (('last_direct','REAL'),('last_external','REAL'),('external_epoch','TEXT')):
            if name not in columns:self.db.execute('ALTER TABLE nodes ADD COLUMN '+name+' '+kind)
        self.db.commit()

        # Correct the initial collector's server-handshake misclassification.
        # Restart coverage for affected instances; never backdate idle proof.
        with self.lock,self.db:
            affected=self.db.execute("SELECT node,instance,COUNT(*) FROM audit WHERE kind='activity' AND label LIKE 't-x-takp-v:%' GROUP BY node,instance").fetchall()
            self.db.execute("DELETE FROM audit WHERE kind='activity' AND label LIKE 't-x-takp-v:%'")
            for node,instance,count in affected:
                self.db.execute("UPDATE nodes SET last_cot=(SELECT MAX(at) FROM audit WHERE node=? AND instance=? AND kind='activity'),observed_frames=MAX(0,observed_frames-?),cot_since=NULL,last_verified=NULL WHERE node=? AND instance=?",(node,instance,count,node,instance))

        # Bundle preparation is an orchestrator-only build, not node usage.
        with self.lock,self.db:
            affected=self.db.execute("SELECT DISTINCT node,instance FROM audit WHERE kind='tool' AND label='devops:taks_bundle_prepare_start:'").fetchall()
            self.db.execute("DELETE FROM audit WHERE kind='tool' AND label='devops:taks_bundle_prepare_start:'")
            for node,instance in affected:
                self.db.execute("UPDATE nodes SET last_tool=(SELECT MAX(at) FROM audit WHERE node=? AND instance=? AND kind='tool') WHERE node=? AND instance=?",(node,instance,node,instance))

    def close(self):self.db.close()
    def ensure(self,node,instance,now):
        row=self.db.execute('SELECT instance FROM nodes WHERE node=?',(node,)).fetchone()
        if not row or row[0]!=instance:
            self.db.execute('INSERT OR REPLACE INTO nodes(node,instance,tool_since) VALUES(?,?,?)',(node,instance,now))
    def note_tool(self,node,instance,domain,name,args,now=None):
        if monitoring(domain,name,args):return False
        now=time.time() if now is None else now
        operation=args.get('operation','')
        operation=operation if isinstance(operation,str) and re.fullmatch(r'[A-Za-z0-9_]{0,64}',operation) else 'invalid_operation'
        safe_name=name if isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_]{1,100}',name) else 'unrecognized_tool'
        label=(domain+':'+safe_name+':'+operation)[:160]
        with self.lock,self.db:
            self.ensure(node,instance,now)
            self.db.execute('UPDATE nodes SET last_tool=? WHERE node=?',(now,node))
            self.db.execute('INSERT INTO audit(at,node,instance,kind,label) VALUES(?,?,?,?,?)',(now,node,instance,'tool',label))
            self.db.execute('DELETE FROM audit WHERE seq < (SELECT COALESCE(MAX(seq),0)-5000 FROM audit)')
        return True
    def connection(self,node,instance,connected,error='',now=None):
        now=time.time() if now is None else now
        with self.lock,self.db:
            self.ensure(node,instance,now)
            self.db.execute('UPDATE nodes SET connected=?,cot_since=NULL,last_verified=NULL,error=? WHERE node=?',
                            (int(connected),error[:160] or ('Awaiting counter verification' if connected else 'Observer disconnected'),node))
    def observed(self,node,instance,kind,label='',now=None):
        now=time.time() if now is None else now
        if kind not in {'activity','ambiguous','bot'}:raise ValueError('Invalid observation')
        with self.lock,self.db:
            self.ensure(node,instance,now)
            column='last_cot' if kind=='activity' else 'last_ambiguous'
            self.db.execute('UPDATE nodes SET observed_frames=observed_frames+1 WHERE node=?',(node,))
            if kind=='bot':self.db.execute('UPDATE nodes SET ignored_bot_frames=ignored_bot_frames+1 WHERE node=?',(node,))
            else:
                self.db.execute('UPDATE nodes SET '+column+'=? WHERE node=?',(now,node))
                self.db.execute('INSERT INTO audit(at,node,instance,kind,label) VALUES(?,?,?,?,?)',(now,node,instance,kind,label[:160]))
                self.db.execute('DELETE FROM audit WHERE seq < (SELECT COALESCE(MAX(seq),0)-5000 FROM audit)')
    def verified(self,node,instance,matched,reason='',now=None):
        now=time.time() if now is None else now
        with self.lock,self.db:
            self.ensure(node,instance,now)
            row=self.db.execute('SELECT connected,cot_since,last_verified FROM nodes WHERE node=?',(node,)).fetchone()
            if not matched or not row[0]:
                self.db.execute('UPDATE nodes SET cot_since=NULL,last_verified=NULL,error=? WHERE node=?',((reason or 'Counter mismatch')[:160],node));return
            since=row[1]
            if since is None or row[2] is None or now-row[2]>FRESH_SECONDS or now<row[2]:since=now
            self.db.execute('UPDATE nodes SET cot_since=?,last_verified=?,error=? WHERE node=?',(since,now,'',node))
    def component(self,name,epoch,now=None):
        now=time.time() if now is None else now
        with self.lock,self.db:
            row=self.db.execute('SELECT epoch,since,last FROM channels WHERE name=?',(name,)).fetchone()
            since=row[1] if row and row[0]==epoch and 0<=now-row[2]<=FRESH_SECONDS else now
            self.db.execute('INSERT OR REPLACE INTO channels VALUES(?,?,?,?)',(name,epoch,since,now))
    def invalidate_component(self,name):
        with self.lock,self.db:self.db.execute('DELETE FROM channels WHERE name=?',(name,))
    def external(self,node,instance,evidence,now=None):
        import math
        now=time.time() if now is None else now
        value=float(evidence.get('last_human_event') or 0);epoch=evidence.get('epoch')
        if evidence.get('complete') is not True or not isinstance(epoch,str) or not 1<=len(epoch)<=128 or not math.isfinite(value) or value<0:raise ValueError('Incomplete direct-input evidence')
        with self.lock,self.db:
            self.ensure(node,instance,now)
            previous=self.db.execute('SELECT last_external,external_epoch FROM nodes WHERE node=?',(node,)).fetchone()
            if previous[1]!=epoch or value<(previous[0] or 0):
                self.db.execute('DELETE FROM channels WHERE name=?',('node_external:'+node,))
            self.component('node_external:'+node,epoch,now)
            last=(previous[0] or 0) if previous[1]==epoch else 0
            if previous[1]==epoch and value>last:
                self.db.execute('UPDATE nodes SET last_direct=? WHERE node=?',(now,node))
                self.db.execute('INSERT INTO audit(at,node,instance,kind,label) VALUES(?,?,?,?,?)',(now,node,instance,'direct','XMPP/voice/Martine input'))
            self.db.execute('UPDATE nodes SET last_external=?,external_epoch=? WHERE node=?',(value,epoch,node))
    def assess(self,node,instance,now=None):
        now=time.time() if now is None else now
        with self.lock:
            self.db.row_factory=sqlite3.Row
            row=self.db.execute('SELECT * FROM nodes WHERE node=?',(node,)).fetchone()
            self.db.row_factory=None
            recent=[dict(zip(('at','kind','label'),r)) for r in self.db.execute('SELECT at,kind,label FROM audit WHERE node=? AND instance=? ORDER BY seq DESC LIMIT 5',(node,instance))]
            channels={r[0]:r[1:] for r in self.db.execute('SELECT name,epoch,since,last FROM channels')}
        base={'node_id':node,'instance_id':instance,'assessed_at':now,'required_idle_seconds':IDLE_SECONDS,
              'eligible_for_idle_shutdown':False,'historical_backfill':False}
        if not row or row['instance']!=instance:return {**base,'reason':'No evidence for this exact instance','coverage_complete':False}
        data=dict(row);reasons=[]
        if not data['connected']:reasons.append('CoT observer disconnected')
        if data['cot_since'] is None:reasons.append(data['error'] or 'CoT feed not verified')
        if data['last_verified'] is None or not 0<=now-data['last_verified']<=FRESH_SECONDS:reasons.append('Counter verification missing or stale')
        channel_since=[]
        for name in ('bridge','devops','node_external:'+node):
            channel=channels.get(name)
            if not channel or not 0<=now-channel[2]<=FRESH_SECONDS:reasons.append(name+' tool audit coverage missing or stale')
            channel_since.append(channel[1] if channel else now)
        since=max(data['tool_since'],data['cot_since'] or now,*channel_since)
        activity=max(data['last_tool'] or 0,data['last_cot'] or 0,data['last_ambiguous'] or 0,data['last_direct'] or 0)
        quiet_since=max(since,activity)
        verified_end=min([data['last_verified'] or 0]+[channels.get(n,('',0,0))[2] for n in ('bridge','devops','node_external:'+node)])
        quiet=max(0,verified_end-quiet_since)
        if quiet<=IDLE_SECONDS:reasons.append('Four-hour verified quiet window not yet complete')
        return {**base,'coverage_complete':not any(x!='Four-hour verified quiet window not yet complete' for x in reasons),
            'coverage_since':since,'verified_through':verified_end,'quiet_since':quiet_since,
            'verified_quiet_seconds':int(quiet),'eligible_for_idle_shutdown':not reasons,
            'last_classified_events':recent,
            'observed_state':('unverified' if data['cot_since'] is None else 'idle' if activity==0 or now-activity>IDLE_SECONDS else 'recently_used'),
            'last_non_monitoring_tool_at':data['last_tool'],'last_non_bot_cot_at':data['last_cot'],
            'native_direct_input_watermark':data['last_external'],
            'last_direct_input_at':data['last_direct'],
            'last_ambiguous_bot_message_at':data['last_ambiguous'],'ignored_periodic_bot_frames':data['ignored_bot_frames'],
            'observed_frames':data['observed_frames'],'reason':'; '.join(reasons) if reasons else 'Verified quiet for more than four hours',
            'covered_activity':['orchestrator node tool calls','DevOps node tool calls','counter-verified CoT'],
            'martine_direct_xmpp_voice_coverage':'required through node_external audit; ambiguous observed bot messages count as use',
            'history_policy':'Gaps, observer restarts, counter mismatches and instance replacement restart coverage'}


_STORE=None
_LOCK=threading.Lock()
def store():
    global _STORE
    with _LOCK:
        if _STORE is None:
            from orchestrator_core.config import load_orch_config
            _STORE=ActivityStore(Path(load_orch_config().paths.state_dir)/'activity/evidence.sqlite')
        return _STORE


def instance_id(record):return str(record.get('aws_instance_id') or record.get('instance_id') or '')

def assessment(record):
    node=str(record.get('node_id') or '')
    try:return store().assess(node,instance_id(record))
    except Exception:return {'node_id':node,'instance_id':instance_id(record),'eligible_for_idle_shutdown':False,'coverage_complete':False,'reason':'Activity store unavailable'}
