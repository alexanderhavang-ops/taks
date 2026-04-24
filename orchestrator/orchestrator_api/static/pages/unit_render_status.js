/* global CORE */

(function(){

  window.TAKS_UNIT = window.TAKS_UNIT || {};

  const S = window.TAKS_UNIT.shared;

  const A = window.TAKS_UNIT.api;

  function healthKind(status){
    const s = String(status || '').trim().toLowerCase();
    if(s === 'ok') return 'ok';
    if(s === 'warn') return 'warn';
    if(s === 'stale') return 'warn';
    if(s === 'fail' || s === 'error' || s === 'red') return 'err';
    if(s === 'skip' || s === 'skipped' || s === 'unknown') return 'muted';
    return 'muted';
  }

  function healthLabel(status){
    const s = String(status || '').trim().toLowerCase();
    if(s === 'ok') return 'OK';
    if(s === 'warn') return 'Varning';
    if(s === 'stale') return 'Senast känd';
    if(s === 'fail' || s === 'error' || s === 'red') return 'Fel';
    if(s === 'skip' || s === 'skipped') return 'Skip';
    if(s === 'unknown') return 'Okänd';
    return String(status || 'Okänd');
  }

  function severityKind(severity){
    const s = String(severity || '').trim().toLowerCase();
    if(s === 'critical') return 'err';
    if(s === 'warn' || s === 'warning') return 'warn';
    if(s === 'info') return 'muted';
    return 'muted';
  }


  function lightColors(kind){
    const k = String(kind || '').trim().toLowerCase();
    if(k === 'ok'){
      return {
        border: 'rgba(34,197,94,.34)',
        bg: 'rgba(34,197,94,.08)',
        dot: '#34d399',
        glow: 'rgba(34,197,94,.28)'
      };
    }
    if(k === 'warn'){
      return {
        border: 'rgba(245,158,11,.35)',
        bg: 'rgba(245,158,11,.10)',
        dot: '#f59e0b',
        glow: 'rgba(245,158,11,.45)'
      };
    }
    if(k === 'err'){
      return {
        border: 'rgba(239,68,68,.35)',
        bg: 'rgba(239,68,68,.10)',
        dot: '#ef4444',
        glow: 'rgba(239,68,68,.45)'
      };
    }
    return {
      border: 'rgba(148,163,184,.28)',
      bg: 'rgba(148,163,184,.08)',
      dot: '#94a3b8',
      glow: 'rgba(148,163,184,.35)'
    };
  }

  function lightPill(kind, text){
    const c = lightColors(kind);
    const wrap = S.el('span', {
      style: 'display:inline-flex;align-items:center;gap:8px;padding:6px 10px;border-radius:999px;border:1px solid ' + c.border + ';background:' + c.bg + ';white-space:nowrap'
    });
    wrap.appendChild(S.el('span', {
      style: 'display:inline-block;width:10px;height:10px;border-radius:999px;background:' + c.dot + ';box-shadow:0 0 10px ' + c.glow
    }));
    wrap.appendChild(S.el('span', { style: 'font-weight:700', text: text || '—' }));
    return wrap;
  }

  function nodeHeartbeatStatus(node){
    return String(S.heartbeatState(node) || 'never').trim().toLowerCase();
  }

  function checksObjectToArray(obj){
    if(!obj || typeof obj !== 'object' || Array.isArray(obj)) return [];
    return Object.keys(obj).sort().map(function(key){
      const item = obj[key];
      const out = (item && typeof item === 'object') ? Object.assign({}, item) : { summary: String(item || '') };
      if(!out.name) out.name = String(key);
      return out;
    });
  }

  function collectNodeHealth(node){
    const candidates = [
      (node && node.node_health) || null,
      (node && node.health) || null,
      (node && node.health_report) || null,
      (node && node.last_health) || null,
      (node && node.status_health) || null,
      (node && node.meta && node.meta.health) || null
    ];

    for(let i = 0; i < candidates.length; i++){
      const c = candidates[i];
      if(!c || typeof c !== 'object') continue;

      const rollup =
        c.rollup ||
        c.summary ||
        c.health_rollup ||
        c.overall ||
        null;

      const checksRaw =
        c.checks ||
        c.items ||
        c.services ||
        c.health_checks ||
        [];

      const checks = Array.isArray(checksRaw) ? checksRaw : checksObjectToArray(checksRaw);

      if(rollup || checks.length){
        return {
          rollup: rollup || {},
          checks: checks
        };
      }
    }

    const topLevelServices = (node && node.services && typeof node.services === 'object')
      ? node.services
      : null;

    const topLevelChecksRaw =
      (node && (node.health_checks || node.node_health_checks || node.checks)) || [];

    return {
      rollup: (node && (node.health_rollup || node.node_health_rollup)) || topLevelServices || {},
      checks: Array.isArray(topLevelChecksRaw) ? topLevelChecksRaw : checksObjectToArray(topLevelChecksRaw)
    };
  }

  function nodeStatusSnapshot(node){
    const awsState = String((node && node.aws_state) || '').trim().toLowerCase();
    const derivedStatus = String((node && node.derived_status) || '').trim().toLowerCase();
    const nodeId = String((node && (node.node_id || node.fqdn || node.instance_id)) || '').trim();
    const hb = S.heartbeatState(node);
    const hasNode = !!nodeId;
    const isStopped = hasNode && (awsState === 'stopped' || derivedStatus === 'stopped');
    const isBooting = hasNode && (awsState === 'pending' || derivedStatus === 'booting');
    const isRunning = hasNode && (
      awsState === 'running' ||
      derivedStatus === 'running' ||
      derivedStatus === 'stale'
    );

    if(!hasNode){
      return {
        tone: 'muted',
        text: '○ No node',
        detail: '',
        stale: false,
        hb: hb,
        awsState: awsState,
        derivedStatus: derivedStatus,
      };
    }

    if(isStopped){
      return {
        tone: 'warn',
        text: '💤 Sleeping',
        detail: 'Noden finns men är stoppad. Wake för att starta upp den igen. Quick links är avstängda medan den sover.',
        stale: false,
        hb: hb,
        awsState: awsState,
        derivedStatus: derivedStatus,
      };
    }

    if(hb === 'lost'){
      return {
        tone: 'err',
        text: '● Unreachable',
        detail: 'AWS-instansen kör men heartbeat är förlorad. Installation och nodhälsa nedan visas som senast kända värden.',
        stale: true,
        hb: hb,
        awsState: awsState,
        derivedStatus: derivedStatus,
      };
    }

    if(hb === 'stale'){
      return {
        tone: 'warn',
        text: '◔ Stale',
        detail: 'Heartbeat är gammal. Installation och nodhälsa nedan kan vara inaktuella.',
        stale: true,
        hb: hb,
        awsState: awsState,
        derivedStatus: derivedStatus,
      };
    }

    if(isBooting){
      return {
        tone: 'warn',
        text: '◔ Booting',
        detail: 'Instans startar. Väntar på första färska heartbeat.',
        stale: false,
        hb: hb,
        awsState: awsState,
        derivedStatus: derivedStatus,
      };
    }

    if(isRunning){
      return {
        tone: 'ok',
        text: '● Running',
        detail: '',
        stale: false,
        hb: hb,
        awsState: awsState,
        derivedStatus: derivedStatus,
      };
    }

    return {
      tone: 'muted',
      text: '◌ Unknown',
      detail: 'Det finns nodmetadata men ingen pålitlig aktuell nodstatus ännu.',
      stale: true,
      hb: hb,
      awsState: awsState,
      derivedStatus: derivedStatus,
    };
  }

  function renderNodeHealth(node){
    const data = collectNodeHealth(node);
    const rollup = (data && data.rollup && typeof data.rollup === 'object') ? data.rollup : {};
    const checks = Array.isArray(data && data.checks) ? data.checks.filter(function(x){
      return x && typeof x === 'object';
    }) : [];

    if(!Object.keys(rollup).length && !checks.length) return null;

    const snap = nodeStatusSnapshot(node);
    const stale = !!snap.stale || !!rollup.stale;

    function norm(v){
      return String(v || '').trim().toLowerCase();
    }

    const overallRaw = norm(rollup.overall);
    let overall = overallRaw;

    if(!overall){
      if(checks.some(function(x){ return ['fail','error','red'].includes(norm(x.status)); })){
        overall = 'fail';
      }else if(checks.some(function(x){ return ['warn','warning','stale'].includes(norm(x.status)); })){
        overall = 'warn';
      }else if(checks.some(function(x){ return norm(x.status) === 'ok'; })){
        overall = 'ok';
      }else{
        overall = 'unknown';
      }
    }

    if(stale) overall = 'stale';

    const wrap = S.el('section', {
      'data-node-health': '1',
      style: 'display:grid;gap:10px;margin-top:2px;padding:14px;border:1px solid rgba(255,255,255,0.08);border-radius:12px;background:rgba(255,255,255,0.02)'
    });

    const head = S.el('div', {
      style: 'display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap'
    });
    head.appendChild(S.el('div', { className: 'label', text: 'Nodhälsa' }));
    head.appendChild(lightPill(healthKind(overall), healthLabel(overall || 'unknown')));
    wrap.appendChild(head);

    const totalChecks =
      (typeof rollup.total_checks === 'number' && rollup.total_checks > 0)
        ? Number(rollup.total_checks)
        : checks.length;

    const warnCount =
      (typeof rollup.warn === 'number' ? Number(rollup.warn) : checks.filter(function(x){
        return ['warn','warning','stale'].includes(norm(x.status));
      }).length);

    const failCount =
      (typeof rollup.fail === 'number' ? Number(rollup.fail) : checks.filter(function(x){
        return ['fail','error','red'].includes(norm(x.status));
      }).length);

    const okCount =
      (typeof rollup.ok === 'number' ? Number(rollup.ok) : checks.filter(function(x){
        return norm(x.status) === 'ok';
      }).length);

    const bits = [];
    if(totalChecks > 0) bits.push(String(totalChecks) + ' checks');
    if(failCount > 0) bits.push(String(failCount) + ' fel');
    if(warnCount > 0) bits.push(String(warnCount) + ' varningar');
    if(okCount > 0) bits.push(String(okCount) + ' ok');
    if(stale) bits.push('senast känd');

    if(bits.length){
      wrap.appendChild(S.el('div', {
        className: 'muted',
        text: bits.join(' • ')
      }));
    }

    if(checks.length){
      const details = S.el('details', { style: 'margin-top:2px' });
      if(window.TAKS_UNIT && window.TAKS_UNIT.nodeAutoOpen === 'health') details.open = true;
      details.appendChild(S.el('summary', { text: 'Visa tjänster' }));

      const body = S.el('div', { style: 'display:grid;gap:8px;margin-top:10px' });

      checks
        .slice()
        .sort(function(a, b){
          return String(a.name || '').localeCompare(String(b.name || ''));
        })
        .forEach(function(item){
          const name = String(item.name || item.key || 'check');
          const sev = String(item.severity || '').trim().toLowerCase();
          const summary = String(item.summary || 'Ingen detalj rapporterad');

          const row = S.el('div', {
            style: 'padding:10px 12px;border-radius:10px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.03)'
          });

          const top = S.el('div', {
            style: 'display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap'
          });

          const left = S.el('div', { style: 'display:grid;gap:3px' });
          left.appendChild(S.el('div', {
            style: 'font-weight:600;word-break:break-word',
            text: name
          }));
          if(sev){
            left.appendChild(S.el('div', {
              className: 'muted',
              text: 'severity: ' + sev
            }));
          }

          top.appendChild(left);
          top.appendChild(lightPill(healthKind(item.status), healthLabel(item.status)));
          row.appendChild(top);

          row.appendChild(S.el('div', {
            className: 'muted',
            style: 'margin-top:8px;white-space:normal;line-height:1.4',
            text: summary
          }));

          body.appendChild(row);
        });

      details.appendChild(body);
      wrap.appendChild(details);
    }

    return wrap;
  }

  window.TAKS_UNIT.lightPill = lightPill;
  window.TAKS_UNIT.nodeStatusSnapshot = nodeStatusSnapshot;
  window.TAKS_UNIT.renderNodeHealth = renderNodeHealth;

})();
