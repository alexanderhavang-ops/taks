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

      const checks =
        c.checks ||
        c.items ||
        c.services ||
        c.health_checks ||
        [];

      if(rollup || (Array.isArray(checks) && checks.length)){
        return {
          rollup: rollup || {},
          checks: Array.isArray(checks) ? checks : []
        };
      }
    }

    const topLevelServices = (node && node.services && typeof node.services === 'object')
      ? node.services
      : null;

    return {
      rollup: (node && (node.health_rollup || node.node_health_rollup)) || topLevelServices || {},
      checks: Array.isArray(node && (node.health_checks || node.node_health_checks))
        ? (node.health_checks || node.node_health_checks)
        : []
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
    const rollup = data.rollup || {};
    const checks = Array.isArray(data.checks) ? data.checks : [];
    if(!rollup && !checks.length) return null;

    const snap = nodeStatusSnapshot(node);
    const stale = !!snap.stale || !!(rollup && rollup.stale);

    const wrap = S.el('section', {
      'data-node-health': '1',
      style: 'display:grid;gap:10px;margin-top:2px;padding:14px;border:1px solid rgba(255,255,255,0.08);border-radius:12px;background:rgba(255,255,255,0.02)'
    });

    const overallRaw = String((rollup && rollup.overall) || '').trim().toLowerCase();
    const overall = stale ? 'stale' : overallRaw;
    const head = S.el('div', {
      style: 'display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap'
    });
    head.appendChild(S.el('div', { className: 'label', text: 'Nodhälsa' }));
    head.appendChild(lightPill(healthKind(overall), healthLabel(overall || 'unknown')));
    wrap.appendChild(head);

    const bits = [];
    if(rollup && typeof rollup.total_checks === 'number') bits.push(String(rollup.total_checks) + ' checks');
    if(rollup && typeof rollup.fail === 'number' && rollup.fail > 0) bits.push(String(rollup.fail) + ' fel');
    if(rollup && typeof rollup.warn === 'number' && rollup.warn > 0) bits.push(String(rollup.warn) + ' varningar');
    if(rollup && typeof rollup.ok === 'number' && rollup.ok > 0) bits.push(String(rollup.ok) + ' ok');
    if(rollup && typeof rollup.skip === 'number' && rollup.skip > 0) bits.push(String(rollup.skip) + ' skip');
    if(stale) bits.push('senast känd');
    wrap.appendChild(S.el('div', { className: 'muted', text: bits.join(' • ') || 'Ingen health-rollup rapporterad' }));

    if(stale){
      wrap.appendChild(S.el('div', {
        className: 'muted',
        style: 'padding:8px 10px;border:1px solid rgba(245,158,11,0.35);border-radius:10px;background:rgba(245,158,11,0.08)',
        text: snap.hb === 'lost'
          ? 'Heartbeat är förlorad. Nodhälsa visas som senast kända värden tills ny heartbeat kommer in.'
          : 'Heartbeat är gammal. Nodhälsa visas som senast kända värden tills ny heartbeat kommer in.'
      }));
    }

    if(checks.length){
      const details = S.el('details', { style: 'margin-top:2px' });
      details.appendChild(S.el('summary', { text: 'Visa tjänster' }));

      const body = S.el('div', { style: 'display:grid;gap:10px;margin-top:10px' });

      const groups = [
        { key: 'critical', label: 'Kritisk', kind: 'err', items: [] },
        { key: 'warn', label: 'Varning', kind: 'warn', items: [] },
        { key: 'info', label: 'Info', kind: 'muted', items: [] },
        { key: 'other', label: 'Övrigt', kind: 'muted', items: [] },
      ];

      checks.forEach(function(item){
        const sev = String(item.severity || '').trim().toLowerCase();
        if(sev === 'critical'){
          groups[0].items.push(item);
        }else if(sev === 'warn' || sev === 'warning'){
          groups[1].items.push(item);
        }else if(sev === 'info'){
          groups[2].items.push(item);
        }else{
          groups[3].items.push(item);
        }
      });

      groups.forEach(function(group){
        if(!group.items.length) return;

        const gDetails = S.el('details', {
          style: 'border:1px solid rgba(255,255,255,0.06);border-radius:10px;background:rgba(255,255,255,0.02)'
        });
        if(group.key === 'critical') gDetails.open = true;

        const gSummary = S.el('summary', {
          style: 'display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 12px;cursor:pointer'
        });
        gSummary.appendChild(S.el('div', { style: 'font-weight:700', text: group.label + ' (' + group.items.length + ')' }));
        gSummary.appendChild(lightPill(group.kind, group.label));
        gDetails.appendChild(gSummary);

        const list = S.el('div', { style: 'display:grid;gap:8px;padding:10px 12px 12px 12px;border-top:1px solid rgba(255,255,255,0.06)' });

        group.items.forEach(function(item, idx){
          const row = S.el('details', {
            'data-accordion-group': 'node-health-checks-' + group.key,
            style: 'border:1px solid rgba(255,255,255,0.06);border-radius:10px;background:rgba(255,255,255,0.02)'
          });

          const summary = S.el('summary', {
            style: 'display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;padding:10px 12px;cursor:pointer;list-style:none'
          });

          const left = S.el('div', { style: 'min-width:0' });
          left.appendChild(S.el('div', {
            style: 'font-weight:700;word-break:break-word;white-space:normal',
            text: healthNameLabel(item.name)
          }));
          summary.appendChild(left);
          summary.appendChild(lightPill(healthKind(item.status), healthLabel(item.status)));
          row.appendChild(summary);

          const detail = S.el('div', {
            style: 'padding:0 12px 12px 12px;border-top:1px solid rgba(255,255,255,0.06);display:grid;gap:8px'
          });
          detail.appendChild(S.el('div', {
            className: 'muted',
            style: 'padding-top:10px;word-break:break-word;white-space:normal',
            text: item.summary || 'Ingen detalj rapporterad'
          }));
          detail.appendChild(S.el('div', {
            className: 'muted',
            text: 'Check-id: ' + (item.name || ('check_' + idx))
          }));
          row.appendChild(detail);

          bindAccordion(row, 'node-health-checks-' + group.key);
          list.appendChild(row);
        });

        gDetails.appendChild(list);
        body.appendChild(gDetails);
      });

      details.appendChild(body);
      wrap.appendChild(details);
    }

    return wrap;
  }

  window.TAKS_UNIT.lightPill = lightPill;

  window.TAKS_UNIT.lightColors = lightColors;
  window.TAKS_UNIT.nodeStatusSnapshot = nodeStatusSnapshot;

  window.TAKS_UNIT.renderNodeHealth = renderNodeHealth;

})();
