"""Bounded ps/free/vmstat equivalents using kernel counters; no command lines."""
from datetime import datetime, timezone
import os
from pathlib import Path
import time

PROC = Path('/proc')
MEMORY_KEYS = ('MemTotal','MemFree','MemAvailable','Buffers','Cached','SwapCached','Active','Inactive','AnonPages','Mapped','Shmem','Slab','SReclaimable','SUnreclaim','KernelStack','PageTables','SwapTotal','SwapFree','Committed_AS','CommitLimit')


def memory_snapshot():
    values = {}
    for line in (PROC/'meminfo').read_text().splitlines():
        key, _, value = line.partition(':')
        if key in MEMORY_KEYS:
            values[key] = int(value.split()[0])
    values['used_excluding_reclaimable_kib'] = values['MemTotal']-values.get('MemAvailable',values.get('MemFree',0))
    values['swap_used_kib'] = values.get('SwapTotal',0)-values.get('SwapFree',0)
    return {'ok':True,'units':'KiB','memory':values}


def _counters():
    stat = {}
    for line in (PROC/'stat').read_text().splitlines():
        parts = line.split()
        if parts and parts[0] in ('cpu','ctxt','intr','procs_running','procs_blocked','processes'):
            stat[parts[0]] = [int(v) for v in parts[1:]]
    vm = {}
    for line in (PROC/'vmstat').read_text().splitlines():
        key, value = line.split()
        if key in ('pgfault','pgmajfault','pswpin','pswpout','pgpgin','pgpgout','oom_kill'):
            vm[key] = int(value)
    return stat, vm


def _processes():
    rows = {}
    for p in PROC.iterdir():
        if not p.name.isdigit(): continue
        try:
            raw = (p/'stat').read_text(); left, fields = raw.rsplit(') ',1)
            parts = fields.split(); pid = int(p.name)
            row = {'pid':pid,'name':left.split('(',1)[1][:80],'state':parts[0],
                   'cpu_ticks':int(parts[11])+int(parts[12]),'start_ticks':int(parts[19]),
                   'threads':int(parts[17]),'rss_kib':int(parts[21])*os.sysconf('SC_PAGE_SIZE')//1024,
                   'virtual_kib':int(parts[20])//1024}
            try:
                status = (p/'status').read_text()
                for line in status.splitlines():
                    key, _, val = line.partition(':')
                    if key in ('RssAnon','RssFile','RssShmem','VmSwap'):
                        row[key.lower()+'_kib'] = int(val.split()[0])
            except OSError: pass
            rows[pid] = row
        except (OSError,ValueError,IndexError): continue
    return rows


def _pressure():
    out = {}
    for name in ('cpu','memory','io'):
        try: out[name] = (PROC/'pressure'/name).read_text().strip().splitlines()
        except OSError: out[name] = None
    return out


def _validate(seconds, limit, sort_by):
    if type(seconds) not in (int,float) or not .2 <= seconds <= 5:
        raise ValueError('seconds must be .2..5')
    if type(limit) is not int or not 1 <= limit <= 50 or sort_by not in ('cpu','memory'):
        raise ValueError('limit must be 1..50 and sort_by cpu/memory')


def sample_snapshot(seconds=1, limit=20, sort_by='cpu'):
    _validate(seconds,limit,sort_by)
    first, vm1 = _counters(); proc1 = _processes(); started = time.monotonic()
    time.sleep(seconds)
    second, vm2 = _counters(); proc2 = _processes(); elapsed = time.monotonic()-started
    # Guest/guest_nice are already included in user/nice and must not count twice.
    deltas = [max(0,b-a) for a,b in zip(first['cpu'][:8],second['cpu'][:8])]
    total = sum(deltas) or 1
    cpu = {key:round(100*d/total,2) for key,d in zip(('user','nice','system','idle','iowait','irq','softirq','steal'),deltas)}
    cpu['busy_percent'] = round(100-cpu.get('idle',0)-cpu.get('iowait',0),2)
    hz = os.sysconf('SC_CLK_TCK'); entries = []
    for pid,row in proc2.items():
        previous = proc1.get(pid)
        row['cpu_percent_one_core'] = round(100*(row['cpu_ticks']-previous['cpu_ticks'])/(hz*elapsed),2) if previous and previous['start_ticks']==row['start_ticks'] else None
        row.pop('cpu_ticks');row.pop('start_ticks');entries.append(row)
    entries.sort(key=lambda r:r['rss_kib'] if sort_by=='memory' else (r['cpu_percent_one_core'] or 0),reverse=True)
    for row in entries[:limit]:
        try:
            for line in (PROC/str(row['pid'])/'smaps_rollup').read_text().splitlines():
                if line.startswith('Pss:'): row['pss_kib']=int(line.split()[1])
        except OSError: row['pss_kib']=None
        try:
            groups=(PROC/str(row['pid'])/'cgroup').read_text().splitlines()
            row['service']=next((line.rsplit('/',1)[-1][:120] for line in groups if '.service' in line),None)
        except OSError: row['service']=None
    vm = {key+'_per_second':round((vm2[key]-vm1.get(key,vm2[key]))/elapsed,2) for key in vm2}
    vm.update({'runnable':second.get('procs_running',[None])[0],'blocked':second.get('procs_blocked',[None])[0],
               'context_switches_per_second':round((second['ctxt'][0]-first['ctxt'][0])/elapsed,2),
               'interrupts_per_second':round((second['intr'][0]-first['intr'][0])/elapsed,2)})
    return {'ok':True,'sample_time':datetime.now(timezone.utc).isoformat(),'sample_seconds':round(elapsed,3),
            'logical_cpus':os.cpu_count(),'cpu_percent_all_cores':cpu,'loadavg':list(os.getloadavg()),
            'memory':memory_snapshot()['memory'],'memory_units':'KiB','vmstat':vm,'pressure':_pressure(),
            'processes':entries[:limit],'visible_processes':len(entries),'sort_by':sort_by,
            'process_cpu_units':'100 percent equals one logical CPU; host percentages cover all CPUs'}


def vmstat_samples(seconds=1,samples=3):
    _validate(seconds,1,'cpu')
    if type(samples) is not int or not 1 <= samples <= 5 or seconds*samples>15:
        raise ValueError('samples must be 1..5 and total sampling <=15 seconds')
    rows = []
    for _ in range(samples):
        row = sample_snapshot(seconds,1)
        row.pop('processes');rows.append(row)
    return {'ok':True,'samples':rows}
